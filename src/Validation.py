"""NEMOS validation layer - public entry point.

This is the module the rest of NEMOS talks to. It composes the individual
checks into the four gates described in docs/guardrail_architecture.md:

    Gate A   preflight()          before SALOME runs (cheap, < 1 s)
    Gate B   check_mesh_stage()   after ideasUnvToFoam + checkMesh
    Gate B2  check_fields_stage() after the 0/ fields are generated
    Gate C   LogMonitor           streaming, while the solver runs
    Gate D   postflight()         after the solver exits

Every gate is an early-exit guard: it builds a ValidationReport, prints it,
and - under the default "strict" policy - raises NemosValidationError if the
report contains any ERROR. Pass validate="warn" to downgrade, or
validate="off" to skip validation entirely.

Host-side only: importing this module must never require SALOME, WSL,
OpenFOAM, matplotlib or pandas.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import validation_checks as _checks
import validation_parsers as _parsers
from validation_core import (  # noqa: F401  (re-exported for callers)
    ERROR,
    INFO,
    WARN,
    POLICY_OFF,
    POLICY_PREFLIGHT_ONLY,
    POLICY_STRICT,
    POLICY_WARN,
    VALID_POLICIES,
    EnvProbe,
    Extent,
    GeometryModel,
    Issue,
    MethodRecord,
    NemosValidationError,
    ObjectRecord,
    ValidationReport,
    class_to_object_type,
    error,
    format_number,
    info,
    plural,
    resolve_policy,
    warn,
)

LogMonitor = _parsers.LogMonitor
CheckMeshResult = _parsers.CheckMeshResult
Patch = _parsers.Patch

REPORT_FILE = "validation_report.json"
STATUS_FILE = ".nemos_status.json"

__all__ = [
    "Issue",
    "ValidationReport",
    "NemosValidationError",
    "GeometryModel",
    "ObjectRecord",
    "MethodRecord",
    "Extent",
    "EnvProbe",
    "LogMonitor",
    "resolve_policy",
    "doctor",
    "check_kwargs",
    "preflight",
    "check_mesh_stage",
    "check_fields_stage",
    "postflight",
    "compute_fingerprints",
    "check_stale",
    "write_status",
    "POLICY_STRICT",
    "POLICY_WARN",
    "POLICY_OFF",
    "POLICY_PREFLIGHT_ONLY",
]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _read_text(path) -> str | None:
    """Read a file, returning None instead of raising if it is unavailable."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _safe(fn, *args, code: str = "W-INTERNAL-01", label: str = "", **kwargs) -> list[Issue]:
    """Run a check, degrading to a warning instead of crashing the pipeline.

    A validation layer that raises an unexpected exception is worse than no
    validation layer: it blocks work it was supposed to protect.
    """
    try:
        result = fn(*args, **kwargs)
        return list(result or [])
    except Exception as exc:  # noqa: BLE001 - deliberately broad
        return [
            warn(
                code,
                f"Internal check failure in {label or getattr(fn, '__name__', 'check')}",
                f"The check raised {type(exc).__name__}: {exc}. This is a bug in the "
                "validation layer, not necessarily a problem with your case. The rest "
                "of the checks still ran.",
                "Report this message. To continue meanwhile, pass validate=\"warn\".",
            )
        ]


# --------------------------------------------------------------------------
# Gate A - preflight
# --------------------------------------------------------------------------


def doctor(
    salome_exe=None,
    case_path=None,
    parallel: bool = True,
    plot_residuals: bool = True,
    probe: EnvProbe | None = None,
    print_report: bool = True,
) -> ValidationReport:
    """One-shot environment diagnostic (docs section 2.1).

    Run this first when something does not work:

        python -c "import sys; sys.path.insert(0,'src'); import Validation; Validation.doctor()"

    Emits E-ENV-* / W-ENV-* / I-ENV-*. Never raises.
    """
    from Simulation import DEFAULT_SALOME_EXE

    report = ValidationReport("NEMOS doctor")
    issues = _safe(
        _checks.check_environment,
        probe or EnvProbe(),
        salome_exe or DEFAULT_SALOME_EXE,
        case_path,
        parallel,
        plot_residuals,
        label="check_environment",
    )
    if case_path is None:
        # doctor() diagnoses the machine, not a case. Complaining that
        # case_path is unset would be noise on the one command a stuck user is
        # most likely to run.
        issues = [i for i in issues if i.code != "E-ENV-05"]
    report.extend(issues)
    if print_report:
        report.print()
        if not report.has_errors:
            print("Environment looks usable.")
    return report


def check_kwargs(raw_kwargs: dict) -> list[Issue]:
    """Gate A0: unknown Simulation() keyword arguments (E-CFG-01).

    Split out from preflight() so it can run inside Simulation.__init__, while
    the raw keys are still visible and before any geometry is built. That way
    a typo is reported against the constructor call rather than three stages
    later, with the wrong defaults already baked in.
    """
    return _safe(_checks.check_simulation_kwargs, raw_kwargs, label="check_simulation_kwargs")


def preflight(
    simulation_config: dict,
    geometry: GeometryModel,
    case_path=None,
    salome_exe=None,
    raw_kwargs: dict | None = None,
    probe: EnvProbe | None = None,
    policy: str | None = None,
    write_json: bool = True,
    extra: list | None = None,
    mesh_imported: bool = False,
) -> ValidationReport:
    """Gate A: everything checkable before SALOME runs (docs section 2).

    Emits E-ENV-*, E-CFG-*, E-GEO-*, E-MSH-* and W-PHY-*. Under the "strict"
    policy this raises NemosValidationError, which is the point: a mistake
    costs one second here instead of forty minutes of meshing plus hours of
    solver time.
    """
    policy = resolve_policy(policy)
    report = ValidationReport("NEMOS preflight")
    if policy == POLICY_OFF:
        return report

    # Findings produced by the caller (currently the stale-case detector), so
    # the user sees one consolidated report instead of two.
    report.extend(extra or [])

    simulation_config = simulation_config or {}
    control_cfg = simulation_config.get("controlDict", {}) or {}
    fields_cfg = simulation_config.get("fields", {}) or {}
    decompose_cfg = simulation_config.get("decomposeParDict", {}) or {}
    monitoring_cfg = simulation_config.get("monitoring", {}) or {}

    parallel = str(decompose_cfg.get("parallel", "Y")).strip().upper().startswith("Y")
    plot_residuals = bool(monitoring_cfg.get("plot_residuals", True))

    # 2.1 environment
    report.extend(
        _safe(
            _checks.check_environment,
            probe or EnvProbe(),
            salome_exe,
            case_path,
            parallel,
            plot_residuals,
            label="check_environment",
        )
    )
    # 2.2 configuration
    if raw_kwargs:
        report.extend(
            _safe(_checks.check_simulation_kwargs, raw_kwargs, label="check_simulation_kwargs")
        )
    report.extend(_safe(_checks.check_control_config, control_cfg, label="check_control_config"))
    report.extend(
        _safe(_checks.check_field_config, fields_cfg, decompose_cfg, label="check_field_config")
    )
    # 2.3 / 2.4 / 2.5 need a recorded geometry. In the legacy reading mode
    # (Simulation(user_script_path=...)) nothing is recorded, so these checks
    # are skipped rather than reporting a phantom "no Room defined".
    if geometry is not None and geometry.objects:
        report.extend(_safe(_checks.check_inline_keys, geometry, label="check_inline_keys"))
        report.extend(
            _safe(_checks.check_geometry_structure, geometry, label="check_geometry_structure")
        )
        report.extend(
            _safe(_checks.check_geometry_placement, geometry, label="check_geometry_placement")
        )
        if mesh_imported:
            # A sweep with no swept mesh parameter has SIM_0 build Mesh_1.unv
            # and every other SIM import it, so those scripts genuinely have no
            # Mesh object. Running the mesh-parameter checks there would report
            # "No Mesh was created" and abort every SIM but the first.
            report.add(
                info(
                    "I-MSH-00",
                    "Mesh parameter checks skipped: this case imports an existing mesh",
                    "The mesh was built elsewhere (SIM_0 of a shared-mesh sweep, or an "
                    "explicit Import_mesh), so there are no mesh parameters here to "
                    "check. The mesh itself is still validated after conversion by "
                    "Gate B.",
                    "No action needed.",
                )
            )
        else:
            report.extend(
                _safe(_checks.check_mesh_params, geometry, label="check_mesh_params")
            )
        report.extend(
            _safe(_checks.check_physics, geometry, simulation_config, label="check_physics")
        )
    else:
        report.add(
            info(
                "I-GEO-00",
                "Geometry checks were skipped: no geometry was recorded",
                "Geometry validation needs the objects to be created through the "
                "recording proxies, which happens when you build the case with "
                "Simulation(case_path=...) and then nemos.Room(...), nemos.Person_seated(...) "
                "and so on. Resuming a case from disk, or the legacy "
                "Simulation(user_script_path=...) mode, has no recorded calls to check.",
                "No action needed if you are resuming a case that already validated.",
            )
        )

    if write_json and case_path:
        try:
            report.to_json(Path(case_path) / REPORT_FILE)
        except OSError:
            pass

    return report.enforce(policy)


# --------------------------------------------------------------------------
# Gate B - mesh, boundary and fields
# --------------------------------------------------------------------------


def check_mesh_stage(
    case_path,
    geometry: GeometryModel,
    object_types: dict | None = None,
    check_mesh_text: str | None = None,
    boundary_text: str | None = None,
    policy: str | None = None,
) -> ValidationReport:
    """Gate B: mesh validity, bounding-box continuity, patch inventory.

    Emits E-CHK-*, E-BOX-* and E-BND-*. Runs after ideasUnvToFoam + checkMesh
    and before the solver, so a broken mesh or an unmapped patch is caught
    before hours of compute are spent on it.
    """
    policy = resolve_policy(policy)
    report = ValidationReport("NEMOS mesh check")
    if policy == POLICY_OFF:
        return report

    case_path = Path(case_path)
    if check_mesh_text is None:
        check_mesh_text = _read_text(case_path / "log.checkMesh")
    if boundary_text is None:
        boundary_text = _read_text(case_path / "constant" / "polyMesh" / "boundary")

    room_dims = None
    try:
        room_dims = geometry.room_dims() if geometry else None
    except Exception:  # noqa: BLE001
        room_dims = None

    if check_mesh_text:
        result = _parsers.parse_check_mesh(check_mesh_text)
        report.extend(_safe(_parsers.check_mesh_quality, result, label="check_mesh_quality"))
        report.extend(
            _safe(_parsers.check_bounding_box, result, room_dims, label="check_bounding_box")
        )
    else:
        report.add(
            warn(
                "W-CHK-09",
                "checkMesh output was not available, so mesh quality was not verified",
                "Expected to find log.checkMesh in the case folder. Without it the "
                "mesh could not be checked for negative-volume cells, excessive "
                "non-orthogonality or a wrong unit scale.",
                "Re-run the mesh preparation stage, or inspect the output of "
                "comandos_1.sh by hand before trusting the results.",
                where=str(case_path / "log.checkMesh"),
            )
        )

    if boundary_text:
        patches, unparsed = _parsers.parse_boundary_file(boundary_text)
        report.extend(
            _safe(
                _parsers.check_patch_inventory,
                patches,
                geometry,
                object_types or {},
                label="check_patch_inventory",
            )
        )
        if unparsed:
            report.add(
                warn(
                    "W-BND-07",
                    f"{plural(len(unparsed), 'block')} in the boundary file could not be parsed",
                    "Blocks: "
                    + ", ".join(sorted(unparsed))
                    + ". The same regex is used by BoundaryManager to assign boundary "
                    "conditions, so any block it cannot read silently receives no "
                    "condition at all.",
                    "Check that every object name= is a plain identifier: letters, "
                    "digits and underscores only, starting with a letter.",
                )
            )
    else:
        report.add(
            error(
                "E-BND-09",
                "The mesh boundary file is missing",
                "constant/polyMesh/boundary does not exist, which means the mesh was "
                "never converted to OpenFOAM format. Nothing downstream can work.",
                "Check the output of comandos_1.sh: ideasUnvToFoam probably failed. "
                f"Confirm that {case_path / 'Mesh_1.unv'} exists and is non-empty.",
                where=str(case_path / "constant" / "polyMesh" / "boundary"),
            )
        )

    return report.enforce(policy)


def check_fields_stage(
    case_path,
    boundary_text: str | None = None,
    field_texts: dict | None = None,
    object_simulation: dict | None = None,
    policy: str | None = None,
) -> ValidationReport:
    """Gate B2: every field file covers every patch (docs section 3.4).

    Emits E-FLD-*. This is what catches a wall that silently fell through to
    zeroGradient on U - a free-slip, adiabatic surface that still produces
    plausible-looking results.
    """
    policy = resolve_policy(policy)
    report = ValidationReport("NEMOS field check")
    if policy == POLICY_OFF:
        return report

    case_path = Path(case_path)
    if boundary_text is None:
        boundary_text = _read_text(case_path / "constant" / "polyMesh" / "boundary")
    if field_texts is None:
        field_texts = {}
        zero_dir = case_path / "0"
        for name in _parsers.FIELD_NAMES if hasattr(_parsers, "FIELD_NAMES") else ():
            text = _read_text(zero_dir / name)
            if text is not None:
                field_texts[name] = text
        if not field_texts and zero_dir.is_dir():
            for entry in sorted(zero_dir.iterdir()):
                if entry.is_file():
                    text = _read_text(entry)
                    if text is not None:
                        field_texts[entry.name] = text

    patches, _ = _parsers.parse_boundary_file(boundary_text or "")
    report.extend(
        _safe(
            _parsers.check_field_coverage,
            field_texts,
            patches,
            object_simulation or {},
            label="check_field_coverage",
        )
    )
    return report.enforce(policy)


# --------------------------------------------------------------------------
# Gate D - post-run
# --------------------------------------------------------------------------


def postflight(
    case_path,
    monitor=None,
    returncode: int | None = None,
    parallel: bool = True,
    wall_clock_s: float | None = None,
    policy: str | None = None,
) -> ValidationReport:
    """Gate D: honest verdict plus artifact completeness (docs sections 5.1, 5.4).

    Emits E-RUN-*, W-RUN-*, W-POST-01 and W-ART-*, and writes
    .nemos_status.json. Note that the conservation balances (section 5.2) and
    the field-sanity/y+ checks (section 5.3) are NOT implemented yet: they
    depend on OpenFOAM function-object output whose format still needs
    calibrating against a real run (docs section 9).
    """
    policy = resolve_policy(policy)
    report = ValidationReport("NEMOS post-run check")
    if policy == POLICY_OFF:
        return report

    case_path = Path(case_path)

    if monitor is not None:
        report.extend(list(monitor.issues))
        verdict = monitor.verdict
        if verdict == "MAX_ITERATIONS":
            residuals = ", ".join(
                f"{name} {format_number(value)}"
                for name, value in sorted((monitor.final_residuals or {}).items())
            )
            report.add(
                warn(
                    "W-POST-01",
                    "The solver reached endTime without meeting residualControl "
                    f"({format_number(_parsers.RESIDUAL_CONTROL)})",
                    f"Final residuals: {residuals or 'unknown'} after "
                    f"{monitor.iterations} iterations.\n"
                    "This result is NOT converged and should not be reported as a "
                    "steady solution.",
                    "Increase endTime. Remember that endTime/delta is the iteration "
                    "count, not seconds: with delta=0.1, endTime=200 gives 2000 "
                    "iterations, which is a more realistic budget for a buoyant room.",
                )
            )

    report.extend(_safe(_parsers.check_artifacts, case_path, parallel, label="check_artifacts"))

    try:
        write_status(case_path, monitor, returncode, report, wall_clock_s)
    except OSError:
        pass

    # A post-run report never aborts: the run already happened, and the user
    # needs to see every finding rather than the first one.
    if report.issues:
        report.print()
    return report


def write_status(
    case_path,
    monitor=None,
    returncode: int | None = None,
    report: ValidationReport | None = None,
    wall_clock_s: float | None = None,
) -> Path:
    """Write .nemos_status.json - the honest replacement for .nemos_done.

    .nemos_done means only "the WSL process exited 0". This file records what
    actually happened, so an unconverged run cannot be mistaken for a finished
    one (docs section 5.1).
    """
    case_path = Path(case_path)
    if monitor is not None:
        payload = _parsers.summarize_status(monitor, case_path, wall_clock_s)
    else:
        payload = {"verdict": "INCOMPLETE", "iterations": 0, "final_residuals": {}}
    payload["returncode"] = returncode
    payload["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if report is not None:
        payload["checks"] = {
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "codes": report.codes(),
        }
    path = case_path / STATUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Stale-case fingerprinting (docs section 2.6)
# --------------------------------------------------------------------------


def _hash(value) -> str:
    blob = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def compute_fingerprints(
    machine_script: str | None,
    object_simulation: dict | None,
    object_types: dict | None,
    fields_cfg: dict | None,
    control_cfg: dict | None,
    decompose_cfg: dict | None = None,
) -> dict:
    """Three independent hashes describing what this case was built from.

    geometry_hash invalidates the mesh; bc_hash invalidates the 0/ fields;
    control_hash invalidates nothing (the solver just continues).
    """
    return {
        "geometry_hash": _hash(machine_script or ""),
        "bc_hash": _hash(
            {
                "object_simulation": object_simulation or {},
                "object_types": object_types or {},
                "fields": fields_cfg or {},
            }
        ),
        "control_hash": _hash(
            {"controlDict": control_cfg or {}, "decomposeParDict": decompose_cfg or {}}
        ),
    }


def _diff_mapping(previous: dict | None, current: dict | None, limit: int = 8) -> list[str]:
    """Human-readable per-key differences, for the stale-case message."""
    previous = previous or {}
    current = current or {}
    changes: list[str] = []
    for name in sorted(set(previous) | set(current)):
        before, after = previous.get(name), current.get(name)
        if before == after:
            continue
        if isinstance(before, dict) or isinstance(after, dict):
            before = before or {}
            after = after or {}
            for key in sorted(set(before) | set(after)):
                if before.get(key) != after.get(key):
                    changes.append(f"{name}.{key} ({before.get(key)!r} -> {after.get(key)!r})")
        else:
            changes.append(f"{name} ({before!r} -> {after!r})")
    if len(changes) > limit:
        changes = changes[:limit] + [f"... and {len(changes) - limit} more"]
    return changes


def check_stale(
    case_path,
    current: dict,
    stored: dict | None,
    previous_state: dict | None = None,
    current_state: dict | None = None,
) -> list[Issue]:
    """Detect a case folder that no longer matches the script (docs section 2.6).

    Emits E-STATE-01, E-STATE-02, I-STATE-03, W-STATE-04. Never deletes
    anything: it aborts and tells the user exactly which artifacts to remove.
    """
    case_path = Path(case_path)
    issues: list[Issue] = []
    if not stored:
        return issues  # first run in this folder, nothing to compare against

    mesh_file = case_path / "Mesh_1.unv"
    poly_mesh = case_path / "constant" / "polyMesh"
    zero_dir = case_path / "0"
    done = case_path / ".nemos_done"

    if stored.get("geometry_hash") and stored["geometry_hash"] != current.get("geometry_hash"):
        if mesh_file.exists():
            changes = _diff_mapping(
                (previous_state or {}).get("object_classes"),
                (current_state or {}).get("object_classes"),
            )
            detail = (
                "The existing Mesh_1.unv was built from the previous geometry, and the "
                "pipeline reuses a mesh whenever the file is present. Continuing would "
                "run today's boundary conditions on yesterday's geometry."
            )
            if changes:
                detail = "Changed: " + ", ".join(changes) + "\n" + detail
            targets = [mesh_file, poly_mesh, zero_dir]
            targets += sorted(case_path.glob("processor*"))
            targets.append(done)
            issues.append(
                error(
                    "E-STATE-01",
                    "The geometry in this script does not match the mesh in the case folder",
                    detail,
                    "To rebuild, delete:\n"
                    + "\n".join(f"  {p}" for p in targets)
                    + "\nOr point case_path at a new folder to keep both results.",
                    where=str(case_path),
                )
            )
    elif stored.get("bc_hash") and stored["bc_hash"] != current.get("bc_hash"):
        if (zero_dir / "T").exists():
            changes = _diff_mapping(
                (previous_state or {}).get("object_simulation"),
                (current_state or {}).get("object_simulation"),
            )
            detail = (
                "The 0/ folder already exists, and the pipeline skips field generation "
                "whenever it does. Continuing would run the solver with the previous "
                "boundary conditions and silently ignore your edit."
            )
            if changes:
                detail = "Changed: " + ", ".join(changes) + "\n" + detail
            targets = [zero_dir] + sorted(case_path.glob("processor*")) + [done]
            issues.append(
                error(
                    "E-STATE-02",
                    "The boundary conditions in this script do not match the case folder",
                    detail,
                    "To apply the new boundary conditions, delete:\n"
                    + "\n".join(f"  {p}" for p in targets)
                    + "\nThe mesh (Mesh_1.unv) can be kept - it is unaffected.",
                    where=str(case_path),
                )
            )

    if stored.get("control_hash") and stored["control_hash"] != current.get("control_hash"):
        issues.append(
            info(
                "I-STATE-03",
                "Solver control settings changed since the last run in this folder",
                "Only controlDict/decomposeParDict changed. Nothing needs to be "
                "deleted: the solver continues from the latest written time.",
                "No action needed.",
            )
        )

    if done.exists():
        issues.append(
            warn(
                "W-STATE-04",
                "This case is already marked as finished",
                f"{done} exists, so the pipeline considers this case complete and "
                "will not re-run the solver.",
                "Delete .nemos_done to force a re-run, or use a different case_path.",
                where=str(done),
            )
        )

    return issues

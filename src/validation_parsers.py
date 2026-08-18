"""Text parsers and runtime monitors for the NEMOS validation layer.

Gate B / C / D of docs/guardrail_architecture.md. Everything here is pure
text in, `Issue` objects out: no SALOME, no OpenFOAM, no subprocess, no
numpy/pandas/matplotlib. Standard library only, so every parser is testable
from a synthetic string.

Contents
--------
`parse_check_mesh` / `check_mesh_quality` / `check_bounding_box`
    Gate B, section 3.1 and 3.2. Codes E-CHK-01..I-CHK-08, E-BOX-01..03.
`parse_boundary_file` / `check_patch_inventory`
    Gate B, section 3.3. Codes E-BND-01..W-BND-08.
`parse_field_file` / `check_field_coverage`
    Gate B2, section 3.4. Codes E-FLD-01..W-FLD-06.
`LogMonitor`
    Gate C, sections 4.2/4.3/4.4. Codes E-RUN-01..W-RUN-15. Streaming: fed
    one line at a time from the loop in
    `OpenFOAMRunner._rodar_simulacao_com_plot`, beside `plotter.feed_line`.
`check_artifacts` / `summarize_status`
    Gate D, sections 5.4 and 5.1. Codes W-ART-01..W-ART-04.

Degradation contract
--------------------
No function here raises. When a parser cannot make sense of its input it
returns a partially filled result and the matching check emits a WARN with
the family's `-00` code (`W-CHK-00`, `W-BOX-00`, `W-BND-00`, `W-FLD-00`,
`W-RUN-00`, `W-ART-00`) saying plainly that the check could not be
performed. An unrecognised log must never produce a false pass, so
`LogMonitor.verdict` falls back to `INCOMPLETE`, never to `CONVERGED`.

Steady-state caveat
-------------------
The generated `fvSchemes` uses `ddtSchemes { default steadyState; }` with
`buoyantSimpleFoam` (section 4.3). A steady SIMPLE run prints no Courant
number, and the `Time =` value is a SIMPLE iteration counter scaled by
`deltaT`, not a physical time. Nothing in this module presents a `Time`
value as seconds. The Courant checks (E-RUN-14, W-RUN-15) are implemented
but expected to stay dormant until a transient solver is added.
"""

# ---------------------------------------------------------------------------
# PATTERNS THAT STILL NEED CALIBRATION AGAINST A REAL CAPTURED LOG
# ---------------------------------------------------------------------------
# docs/guardrail_architecture.md section 9 item 3 records that the exact
# OpenFOAM v2312 strings below are inferred, not verified. Every one of them
# is written as a tolerant regex and every one of them degrades to "cannot
# verify" rather than to a pass. Confirm each against a real
# `log.simulation` / `log.checkMesh` and then delete its entry from this list.
#
#   _BOUNDING_RE          W-RUN-07  "bounding k, min: ... max: ... average: ..."
#                                   -- the leading token, the comma and the
#                                   field name all need confirming.
#   _LIMIT_TEMP_RE        W-RUN-08  "limitTemperature <name> Lower limited N
#                                   (X%) of cells" -- word order and whether
#                                   the count precedes or follows "limited".
#   _CONVERGED_RE         I-RUN-13  "SIMPLE solution converged in N iterations"
#                                   -- v2312 may print "solution converged in
#                                   N iterations" without the solver prefix.
#   _MINMAX_RE            W-RUN-09  fieldMinMax output: "min(T) = ..." vs
#                         E-RUN-03  "min(T) = ... in cell N at location (...)"
#                                   vs "max(mag(U)) = ...". Only fires once
#                                   the functions{} block of section 4.1 is
#                                   actually written to controlDict.
#   _MAXITER_RE           W-RUN-10  "No Iterations 1000" -- the linear-solver
#                                   ceiling is assumed to be maxIter 1000.
#   _COURANT_RE           E-RUN-14  "Courant Number mean: X max: Y" -- dormant
#                         W-RUN-15  on steadyState, so unverifiable here.
#   _MPI_PATTERNS         E-RUN-05  "not enough slots", "mpirun noticed that
#                                   process rank ... exited".
#   _END_RE               E-RUN-06  the trailing "End" marker. Universal in
#                                   OpenFOAM, but confirm it survives the
#                                   `wsl bash` wrapper and the tee.
#   _SEVERE_* (checkMesh) E-CHK-02  "***Zero or negative cell volume
#                         E-CHK-03  detected", "***Open edges found",
#                                   "***Number of not closed cells". The
#                                   wording of the "***" lines drifts between
#                                   OpenFOAM releases.
# ---------------------------------------------------------------------------

from __future__ import annotations

import csv
import functools
import math
import re
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from validation_core import (
    Issue, error, warn, info, ERROR, WARN, INFO,
    GeometryModel, as_float, format_number, plural,
    FIELD_NAMES, RESIDUAL_CONTROL, MESH_FILE_NAME, DECOMPOSE_SUBDOMAINS,
    LIMIT_TEMPERATURE_MIN, LIMIT_TEMPERATURE_MAX, VELOCITY_DAMPING_UMAX,
)

__all__ = [
    "CheckMeshResult", "parse_check_mesh", "check_mesh_quality", "check_bounding_box",
    "Patch", "parse_boundary_file", "check_patch_inventory",
    "FieldFile", "parse_field_file", "check_field_coverage",
    "LogMonitor", "MONITOR_CSV_COLUMNS",
    "check_artifacts", "summarize_status",
]


# ---------------------------------------------------------------------------
# Thresholds (single source of truth for the messages)
# ---------------------------------------------------------------------------

NON_ORTHO_MAX = 70.0          # W-CHK-04, degrees
SKEWNESS_MAX = 4.0            # W-CHK-05
ASPECT_RATIO_MAX = 100.0      # W-CHK-06
CELL_COUNT_FACTOR = 3.0       # W-CHK-07
BBOX_TOLERANCE_PCT = 1.0      # E-BOX-01
MM_SCALE_LOW = 500.0          # E-BOX-02 window around 1000x
MM_SCALE_HIGH = 2000.0
COURANT_ERROR = 1.0           # E-RUN-14
COURANT_WARN = 0.5            # W-RUN-15
BOUNDING_EVENT_LIMIT = 50     # W-RUN-07
LIMIT_TEMP_EVENT_LIMIT = 1    # W-RUN-08, one report of limited cells is enough
LINEAR_SOLVER_MAX_ITER = 1000  # W-RUN-10
UMAX_CEILING_TOL = 0.01       # W-RUN-09, relative closeness to UMax
STAGNATION_REL_CHANGE = 0.05  # W-RUN-11, "flat" means < 5 % change
SMALL_PATCH_FACES = 4         # W-BND-08


# ---------------------------------------------------------------------------
# Guards: nothing in this module raises
# ---------------------------------------------------------------------------


def _guard_issues(code: str, what: str):
    """Wrap a check so an unexpected exception degrades to one WARN."""

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - never propagate
                return [warn(
                    code,
                    f"{what} could not be performed ({type(exc).__name__}: {exc}).",
                    "The validation layer failed while inspecting this input, so this "
                    "family of checks did not run. Nothing was verified here; treat the "
                    "result as unchecked rather than as passing.",
                    "Report this together with the file that was being parsed. "
                    "Meanwhile, inspect the file by hand before trusting the run.",
                )]
        return wrapper
    return decorate


def _guard_value(fallback):
    """Wrap a parser so an unexpected exception yields `fallback(*args)`."""

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001 - never propagate
                return fallback(*args, **kwargs)
        return wrapper
    return decorate


def _as_text(value) -> str:
    """Coerce any input to text without raising."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""
    return str(value)


# ---------------------------------------------------------------------------
# Shared OpenFOAM dictionary text helpers
# ---------------------------------------------------------------------------
# The dictionaries this library generates are written with leading
# indentation on every line (see OpenFOAMCase.gerar_arquivos_base and
# BoundaryManager._generate_field_file) and the `boundary` file comes
# straight from ideasUnvToFoam. Every helper below therefore tolerates
# arbitrary leading whitespace, `//` comments and the banner comment.

#: A token: anything that is not whitespace, a brace, a paren or a semicolon.
_TOKEN_RE = re.compile(r"[^\s{}();]+")


def _strip_foam_comments(text: str) -> str:
    """Remove the `/*---*\\ ... \\*---*/` banner, block comments and `//` tails."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _iter_blocks(text: str) -> list[tuple[str, str]]:
    """Every `name { ... }` block at the top level of `text`, in order.

    Brace depth is tracked so nested blocks stay inside their parent's body
    instead of being returned separately. An unterminated block yields the
    remainder of the text, which is what lets a truncated file still parse.
    """
    out: list[tuple[str, str]] = []
    pending: str | None = None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "{":
            depth = 1
            j = i + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            body = text[i + 1: j - 1] if depth == 0 else text[i + 1: n]
            if pending:
                out.append((pending, body))
            pending = None
            i = j
            continue
        if ch in "};":
            pending = None
            i += 1
            continue
        match = _TOKEN_RE.match(text, i)
        if match:
            pending = match.group(0)
            i = match.end()
        else:
            i += 1
    return out


def _find_block(text: str, name: str) -> str | None:
    """Body of the first top-level block called `name`, or None."""
    for block_name, body in _iter_blocks(text):
        if block_name == name:
            return body
    return None


def _entry(body: str, key: str) -> str | None:
    """Value of a `key   value;` entry.

    A negative lookbehind for word characters is what keeps `type` from
    matching inside `physicalType`, without requiring the entry to start a
    line: `{ type wall; nFaces 42; }` on a single line is valid OpenFOAM, and
    anchoring to line starts silently failed to find every entry after the
    first one.
    """
    match = re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(key) + r"\s+([^;{}]+);",
        body,
    )
    if not match:
        return None
    return " ".join(match.group(1).split())


def _parse_uniform_scalar(text: str | None):
    """`uniform 293` -> 293.0. None when there is no numeric value."""
    if text is None:
        return None
    match = re.search(r"uniform\s+([-+]?[0-9][0-9.eE+\-]*)", text)
    if match:
        return as_float(match.group(1), None)
    if re.fullmatch(r"\s*[-+]?[0-9][0-9.eE+\-]*\s*", text or ""):
        return as_float(text, None)
    return None


def _parse_uniform_vector(text: str | None):
    """`uniform (0 -1.2 0)` -> (0.0, -1.2, 0.0). None when not parseable."""
    if text is None:
        return None
    match = re.search(r"\(\s*([^)]*?)\s*\)", text)
    if not match:
        return None
    parts = match.group(1).split()
    if len(parts) != 3:
        return None
    values = [as_float(p, None) for p in parts]
    if any(v is None for v in values):
        return None
    return tuple(values)


def _close(a, b, rel: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    """Numeric agreement, tolerant of the round trip through text."""
    if a is None or b is None:
        return False
    try:
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return False


def _number_list(text: str) -> list[float]:
    """Every number in `text`, in order."""
    out = []
    for token in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", text):
        value = as_float(token, None)
        if value is not None:
            out.append(value)
    return out


# ===========================================================================
# 3.1  checkMesh
# ===========================================================================

_CM_POINTS_RE = re.compile(r"^\s*points:\s*(\d+)", re.M)
_CM_FACES_RE = re.compile(r"^\s*faces:\s*(\d+)", re.M)
_CM_CELLS_RE = re.compile(r"^\s*cells:\s*(\d+)", re.M)
_CM_BBOX_RE = re.compile(
    r"bounding box[^(]*\(([^)]*)\)\s*\(([^)]*)\)", re.I
)
_CM_ASPECT_RE = re.compile(r"Max aspect ratio\s*=\s*([0-9.eE+\-]+)", re.I)
_CM_NONORTHO_RE = re.compile(r"non-orthogonality\s+Max:\s*([0-9.eE+\-]+)", re.I)
_CM_SKEW_RE = re.compile(r"Max skewness\s*=\s*([0-9.eE+\-]+)", re.I)
_CM_FAILED_RE = re.compile(r"Failed\s+(\d+)\s+mesh\s+check", re.I)
_CM_OK_RE = re.compile(r"^\s*Mesh OK\.?\s*$", re.M | re.I)
_CM_SEVERE_RE = re.compile(r"^\s*\*\*\*\s*(.+?)\s*$", re.M)


@dataclass
class CheckMeshResult:
    """Everything worth knowing from a `checkMesh` run."""

    ok: bool = False
    failed_checks: int = 0
    cells: int | None = None
    faces: int | None = None
    points: int | None = None
    bbox_min: tuple | None = None
    bbox_max: tuple | None = None
    max_non_ortho: float | None = None
    max_skewness: float | None = None
    max_aspect_ratio: float | None = None
    severe_problems: list = dc_field(default_factory=list)
    raw: str = ""

    @property
    def parsed(self) -> bool:
        """True when the text looked like checkMesh output at all."""
        return self.cells is not None or self.ok or self.failed_checks > 0


@_guard_value(lambda text, *a, **k: CheckMeshResult(raw=_as_text(text)))
def parse_check_mesh(text: str) -> CheckMeshResult:
    """Parse `checkMesh` output. Never raises; unknown fields stay None."""
    raw = _as_text(text)
    result = CheckMeshResult(raw=raw)

    failed = _CM_FAILED_RE.search(raw)
    result.failed_checks = int(failed.group(1)) if failed else 0
    result.ok = bool(_CM_OK_RE.search(raw)) and result.failed_checks == 0

    for attr, pattern, cast in (
        ("points", _CM_POINTS_RE, int),
        ("faces", _CM_FACES_RE, int),
        ("cells", _CM_CELLS_RE, int),
    ):
        match = pattern.search(raw)
        if match:
            setattr(result, attr, cast(match.group(1)))

    bbox = _CM_BBOX_RE.search(raw)
    if bbox:
        low = _number_list(bbox.group(1))
        high = _number_list(bbox.group(2))
        if len(low) == 3 and len(high) == 3:
            result.bbox_min = tuple(low)
            result.bbox_max = tuple(high)

    for attr, pattern in (
        ("max_aspect_ratio", _CM_ASPECT_RE),
        ("max_non_ortho", _CM_NONORTHO_RE),
        ("max_skewness", _CM_SKEW_RE),
    ):
        match = pattern.search(raw)
        if match:
            setattr(result, attr, as_float(match.group(1), None))

    result.severe_problems = [
        line.strip() for line in _CM_SEVERE_RE.findall(raw) if line.strip()
    ]
    return result


@_guard_issues("W-CHK-00", "The checkMesh quality check")
def check_mesh_quality(result: CheckMeshResult, expected_cells: int = None) -> list[Issue]:
    """Emits E-CHK-01..03, W-CHK-04..07, I-CHK-08."""
    issues: list[Issue] = []

    if not result.parsed:
        return [warn(
            "W-CHK-00",
            "checkMesh output could not be interpreted",
            "The text did not contain the usual 'Mesh stats' / 'Mesh OK' markers, so "
            "mesh validity was NOT verified. Treat the mesh as unchecked.",
            "Open log.checkMesh and read it by hand before trusting the results.",
        )]

    # -- E-CHK-02/03 severe problems first (most specific message wins) ----
    negative_volume = [p for p in result.severe_problems
                       if re.search(r"negative|zero.*volume|volume.*zero", p, re.I)]
    if negative_volume:
        issues.append(error(
            "E-CHK-02",
            "The mesh has cells with zero or negative volume",
            "checkMesh reported: " + "; ".join(negative_volume[:3]) + ".\n"
            "An inverted or degenerate cell makes the finite-volume discretisation "
            "invalid. The solver will either abort immediately or produce nonsense.",
            "Coarsen the mesh (increase m3DMinSize / m3DMaxSize) or simplify the "
            "geometry near the affected region. Very thin gaps between bodies and the "
            "viscous layers are the usual cause.",
            value=negative_volume,
        ))

    open_edges = [p for p in result.severe_problems
                  if re.search(r"open edge|not closed|non.?closed", p, re.I)]
    if open_edges:
        issues.append(error(
            "E-CHK-03",
            "The mesh has open edges or cells that are not closed",
            "checkMesh reported: " + "; ".join(open_edges[:3]) + ".\n"
            "A closed cell volume is a hard requirement: OpenFOAM cannot conserve "
            "mass across a cell whose faces do not form a closed surface.",
            "This normally means the SALOME geometry had a defect before meshing. "
            "Check that no two bodies overlap and that every opening is fully inside "
            "the ceiling.",
            value=open_edges,
        ))

    # -- E-CHK-01 overall verdict ------------------------------------------
    if result.failed_checks:
        others = [p for p in result.severe_problems
                  if p not in negative_volume and p not in open_edges]
        issues.append(error(
            "E-CHK-01",
            f"checkMesh failed {plural(result.failed_checks, 'check')}",
            ("Also reported: " + "; ".join(others[:4]) + ".\n" if others else "")
            + "Running the solver on a mesh that failed checkMesh wastes hours and "
            "produces a result that cannot be defended.",
            "Fix the mesh before solving. Read log.checkMesh for the specific "
            "failures, then adjust the mesh sizes or the geometry.",
            value=result.failed_checks,
        ))
    elif not result.ok:
        issues.append(warn(
            "W-CHK-00",
            "checkMesh did not report 'Mesh OK'",
            "No explicit failure count was found either, so the run may have been "
            "interrupted before finishing its checks.",
            "Re-run the mesh preparation stage and read log.checkMesh.",
        ))

    # -- W-CHK-04/05/06 quality metrics ------------------------------------
    if result.max_non_ortho is not None and result.max_non_ortho > NON_ORTHO_MAX:
        issues.append(warn(
            "W-CHK-04",
            f"Maximum mesh non-orthogonality is {format_number(result.max_non_ortho)} "
            f"degrees (above {format_number(NON_ORTHO_MAX)})",
            "Non-orthogonality is the angle between the face normal and the line "
            "joining the two cell centres. High values make the Laplacian terms "
            "inaccurate; fvSchemes here uses 'orthogonal' corrections with "
            "nNonOrthogonalCorrectors 0, which assumes a fairly orthogonal mesh.",
            "Improve the mesh in the offending region, or add "
            "nNonOrthogonalCorrectors 1-2 to the SIMPLE block in system/fvSolution.",
            value=result.max_non_ortho,
        ))
    if result.max_skewness is not None and result.max_skewness > SKEWNESS_MAX:
        issues.append(warn(
            "W-CHK-05",
            f"Maximum face skewness is {format_number(result.max_skewness)} "
            f"(above {format_number(SKEWNESS_MAX)})",
            "Skewness measures how far the face centre is from the line between cell "
            "centres. Highly skewed cells add numerical diffusion exactly where the "
            "mesh is worst, which is usually next to a body surface.",
            "Increase m3DMinSize slightly, or relax the local refinement near the "
            "affected surfaces.",
            value=result.max_skewness,
        ))
    if result.max_aspect_ratio is not None and result.max_aspect_ratio > ASPECT_RATIO_MAX:
        issues.append(warn(
            "W-CHK-06",
            f"Maximum cell aspect ratio is {format_number(result.max_aspect_ratio)} "
            f"(above {format_number(ASPECT_RATIO_MAX)})",
            "Very stretched cells slow the linear solvers down and can stall "
            "convergence of p_rgh. The viscous layers deliberately create stretched "
            "cells, so a moderate value is expected, but this is beyond that.",
            "Reduce the viscous-layer stretch, or increase m3DMinSize.",
            value=result.max_aspect_ratio,
        ))

    # -- W-CHK-07 cell count vs the Gate A estimate ------------------------
    if result.cells and expected_cells:
        ratio = result.cells / float(expected_cells)
        if ratio > CELL_COUNT_FACTOR or ratio < 1.0 / CELL_COUNT_FACTOR:
            issues.append(warn(
                "W-CHK-07",
                f"The mesh has {result.cells:,} cells, but about {expected_cells:,} "
                "were expected from the mesh parameters",
                f"That is a factor of {ratio:.1f} difference. Either the local "
                "refinement is doing much more (or much less) than intended, or the "
                "geometry is not the size you think it is.",
                "Check m3DMaxSize and the room dimensions. A far larger count than "
                "expected also means a far longer solve.",
                value=result.cells,
            ))

    # -- I-CHK-08 record --------------------------------------------------
    if result.cells is not None:
        bbox = ""
        if result.bbox_min and result.bbox_max:
            size = tuple(
                result.bbox_max[i] - result.bbox_min[i] for i in range(3)
            )
            bbox = (" Bounding box "
                    + " x ".join(format_number(s) for s in size) + " m.")
        issues.append(info(
            "I-CHK-08",
            f"Mesh: {result.cells:,} cells, "
            f"{(result.faces or 0):,} faces, {(result.points or 0):,} points",
            f"Quality: max non-orthogonality "
            f"{format_number(result.max_non_ortho)}, max skewness "
            f"{format_number(result.max_skewness)}, max aspect ratio "
            f"{format_number(result.max_aspect_ratio)}.{bbox}",
            "No action needed; recorded for reproducibility.",
            value=result.cells,
        ))
    return issues


@_guard_issues("W-BOX-00", "The bounding-box continuity check")
def check_bounding_box(result: CheckMeshResult, room_dims=None) -> list[Issue]:
    """Emits E-BOX-01, E-BOX-02, E-BOX-03."""
    if result.bbox_min is None or result.bbox_max is None:
        return [warn(
            "W-BOX-00",
            "The mesh bounding box could not be read from checkMesh output",
            "Without it, a mesh exported in the wrong units (millimetres instead of "
            "metres) cannot be detected. That failure mode otherwise produces a "
            "silently absurd simulation.",
            "Check log.checkMesh for the 'Overall domain bounding box' line.",
        )]
    if not room_dims:
        return []

    issues: list[Issue] = []
    size = tuple(result.bbox_max[i] - result.bbox_min[i] for i in range(3))
    declared = tuple(float(v) for v in room_dims)

    # -- E-BOX-02 unit scale (checked before the generic mismatch) --------
    ratios = [
        size[i] / declared[i] for i in range(3) if declared[i] > 0
    ]
    if ratios and all(MM_SCALE_LOW <= r <= MM_SCALE_HIGH for r in ratios):
        return [error(
            "E-BOX-02",
            "The mesh appears to be in millimetres rather than metres",
            f"The room was declared as "
            + " x ".join(format_number(d) for d in declared)
            + " m, but the mesh bounding box is "
            + " x ".join(format_number(s) for s in size)
            + f" - about {ratios[0]:.0f} times larger.\n"
            "OpenFOAM has no notion of units: it would solve a room the size of a "
            "city block, and every velocity, temperature gradient and Rayleigh number "
            "would be meaningless.",
            "Re-export the mesh in metres from SALOME, or scale the converted mesh:\n"
            "    wsl bash -c 'source /usr/lib/openfoam/openfoam2312/etc/bashrc; "
            "transformPoints -scale \"(0.001 0.001 0.001)\"'",
            value=size,
        )]

    # -- E-BOX-01 size agreement ------------------------------------------
    labels = ("dx", "dy", "dz")
    bad = []
    for i in range(3):
        if declared[i] <= 0:
            continue
        deviation = abs(size[i] - declared[i]) / declared[i] * 100.0
        if deviation > BBOX_TOLERANCE_PCT:
            bad.append(
                f"{labels[i]}: declared {format_number(declared[i])} m, "
                f"mesh {format_number(size[i])} m ({deviation:.1f}% off)"
            )
    if bad:
        issues.append(error(
            "E-BOX-01",
            "The mesh does not match the room dimensions in the script",
            "\n".join(bad)
            + "\nThe mesh on disk was built from a different geometry than the one "
            "this script describes, so the boundary conditions are being applied to "
            "the wrong surfaces.",
            "This usually means a stale Mesh_1.unv. Delete Mesh_1.unv and "
            "constant/polyMesh/ and let the mesh rebuild, or point case_path at a "
            "fresh folder.",
            value=size,
        ))

    # -- E-BOX-03 origin ---------------------------------------------------
    if any(abs(v) > 1e-6 for v in result.bbox_min):
        issues.append(error(
            "E-BOX-03",
            "The mesh does not start at the origin",
            f"Minimum corner is ("
            + ", ".join(format_number(v) for v in result.bbox_min)
            + ") but GeoMesh builds every room from (0, 0, 0) into the first octant.\n"
            "Ceiling and floor detection compares face centres against y = 0 and "
            "y = room height, so an offset mesh gets its outlet patches wrong.",
            "Rebuild the mesh from the geometry script rather than reusing an "
            "imported or transformed mesh.",
            value=result.bbox_min,
        ))
    return issues


# ===========================================================================
# 3.3  boundary file and patch inventory
# ===========================================================================


@dataclass
class Patch:
    """One entry of constant/polyMesh/boundary."""

    name: str
    patch_type: str = ""
    n_faces: int | None = None
    start_face: int | None = None


@_guard_value(lambda text, *a, **k: ([], []))
def parse_boundary_file(text: str) -> tuple:
    """(patches, unparsable_block_names) from a polyMesh/boundary file."""
    body = _strip_foam_comments(_as_text(text))
    patches: list[Patch] = []
    unparsed: list[str] = []

    for name, block in _iter_blocks(body):
        if name in ("FoamFile", "boundaryField"):
            continue
        # A patch block always has a `type`. Anything else at this level is
        # the list count or a stray token.
        patch_type = _entry(block, "type")
        if patch_type is None:
            if "{" in block or "nFaces" in block:
                unparsed.append(name)
            continue
        n_faces = _entry(block, "nFaces")
        start_face = _entry(block, "startFace")
        patches.append(Patch(
            name=name,
            patch_type=patch_type.split()[0] if patch_type else "",
            n_faces=int(as_float(n_faces, -1)) if n_faces is not None else None,
            start_face=int(as_float(start_face, -1)) if start_face is not None else None,
        ))

    if not patches:
        for name, _block in _iter_blocks(body):
            if name not in ("FoamFile",):
                unparsed.append(name)
    return patches, unparsed


def _semantic_type(patch_name: str, object_types: dict) -> str | None:
    """Mirror of BoundaryManager._infer_semantic_type."""
    if patch_name == "wall":
        return "wall"
    if patch_name == "outlet":
        return "outlet"
    if patch_name.startswith("inlet_"):
        return "inlet"
    if patch_name in (object_types or {}):
        return (object_types or {})[patch_name]
    for prefix, kind in (
        ("wall", "wall"), ("inlet", "inlet"), ("outlet", "outlet"),
        ("person", "person"), ("dip", "dip"), ("table", "table"),
    ):
        if patch_name.startswith(prefix):
            return kind
    return None


def _boundary_type(patch_name: str, object_types: dict) -> str | None:
    """Mirror of BoundaryManager._infer_boundary_type."""
    semantic = _semantic_type(patch_name, object_types)
    if semantic in ("person", "dip", "table", "wall"):
        return "wall"
    if semantic in ("inlet", "outlet"):
        return semantic
    return None


@_guard_issues("W-BND-00", "The patch inventory check")
def check_patch_inventory(patches, geometry: GeometryModel = None,
                          object_types: dict = None) -> list[Issue]:
    """Emits E-BND-01..06, W-BND-08."""
    issues: list[Issue] = []
    object_types = object_types or {}
    patches = list(patches or [])

    if not patches:
        return [error(
            "E-BND-01",
            "No patches were found in the mesh boundary file",
            "constant/polyMesh/boundary contained no readable patch blocks, so the "
            "mesh has no named surfaces to attach boundary conditions to.",
            "Check log.ideasUnvToFoam: the conversion probably failed, or the SALOME "
            "mesh was exported without face groups.",
        )]

    by_name = {p.name: p for p in patches}

    # -- E-BND-01 unresolved patches (the highest-impact check here) -------
    unresolved = [p.name for p in patches
                  if _boundary_type(p.name, object_types) is None]
    if unresolved:
        issues.append(error(
            "E-BND-01",
            f"{plural(len(unresolved), 'mesh patch', 'es')} could not be matched to a "
            "boundary type: " + ", ".join(sorted(unresolved)),
            "A patch that matches no known type keeps 'type patch;' in the boundary "
            "file, and then every field falls through to the zeroGradient default. "
            "That silently turns a solid wall into a frictionless, adiabatic, "
            "free-slip surface: the solver runs, converges, and gives a physically "
            "wrong answer that looks entirely plausible.",
            "Patch names come from each object's name=. Check that the name= you gave "
            "every object matches the patch names above, and that no object was "
            "renamed after the mesh was built.",
            value=sorted(unresolved),
        ))

    # -- E-BND-06 defaultFaces --------------------------------------------
    for name, patch in by_name.items():
        if name.lower().startswith("defaultfaces") and (patch.n_faces or 0) > 0:
            issues.append(error(
                "E-BND-06",
                f"The mesh has a '{name}' patch with {patch.n_faces} faces",
                "ideasUnvToFoam puts every face that belonged to no SALOME group into "
                "this catch-all patch. Those faces are real surfaces of the domain "
                "that will receive no meaningful boundary condition.",
                "Some geometry did not end up in a face group. Check that a.add([...]) "
                "lists every object and that create_faces_groups ran (it is called by "
                "add), then rebuild the mesh.",
                value=patch.n_faces,
            ))

    # -- E-BND-04 an outlet must exist ------------------------------------
    outlets = [p for p in patches if _boundary_type(p.name, object_types) == "outlet"]
    if not outlets:
        issues.append(error(
            "E-BND-04",
            "The mesh has no outlet patch",
            "Without an outlet the domain is sealed. The dips keep pushing mass in "
            "and there is nowhere for it to leave, so no steady solution exists and "
            "the pressure equation cannot converge.",
            "Add at least one ceiling or floor opening in the geometry script:\n"
            "    a.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)\n"
            "then rebuild the mesh.",
        ))
    elif outlets and all(p.n_faces == 0 for p in outlets):
        # `is 0`, not `or 0`: an unparsed nFaces is None, and treating that as
        # zero would report a perfectly good outlet as empty.
        issues.append(error(
            "E-BND-04",
            "Every outlet patch is empty (nFaces = 0)",
            "The outlet patches exist by name but contain no faces, so the domain is "
            "effectively sealed.",
            "The ceiling openings were probably not detected. Check that each opening "
            "lies fully inside the ceiling and that the openings were inserted BEFORE "
            "a.add([...]).",
        ))

    # -- E-BND-05 empty patches -------------------------------------------
    empty = [p.name for p in patches if p.n_faces == 0]
    if empty:
        inlet_empty = [n for n in empty if n.startswith("inlet_")]
        detail = ("Empty patches: " + ", ".join(sorted(empty)) + ".\n")
        if inlet_empty:
            detail += (
                "An empty inlet is the worst case: the patch exists, the boundary "
                "condition is written, and no air whatsoever enters the room. The "
                "solver reports no error and converges to a room with no ventilation."
            )
        else:
            detail += (
                "A patch with no faces carries a boundary condition that applies to "
                "nothing, which usually means the surface it was meant to represent "
                "was never detected."
            )
        issues.append(error(
            "E-BND-05",
            f"The mesh has {plural(len(empty), 'patch', 'es')} with no faces",
            detail,
            "For an inlet, check that the dip axis (x, z) is inside the ceiling and "
            "that no two dips share the same axis. Then rebuild the mesh.",
            value=sorted(empty),
        ))

    # -- E-BND-02 / E-BND-03 expected patches ------------------------------
    if geometry is not None and geometry.objects:
        for obj in geometry.bodies():
            if obj.name not in by_name:
                issues.append(error(
                    "E-BND-02",
                    f"{obj.name} has no patch in the mesh",
                    f"The script defines {obj.name} ({obj.class_name}) and gives it "
                    "boundary conditions, but the converted mesh has no patch with "
                    "that name. Its surface is part of some other patch, so its "
                    "temperature or flow condition is not being applied at all.",
                    "The face group was not created. Confirm that a.add([...]) "
                    f"includes {obj.name}, then delete Mesh_1.unv and "
                    "constant/polyMesh/ and rebuild.",
                    where=obj.name,
                ))
        for dip in geometry.of_type("dip"):
            expected = f"inlet_{dip.name}"
            if expected not in by_name:
                issues.append(error(
                    "E-BND-03",
                    f"{dip.name} has no '{expected}' inlet patch",
                    "GeoMesh finds the supply face by looking for the ceiling face "
                    "whose centre matches the dip axis. When that search fails no "
                    "inlet group is created, so this diffuser supplies no air.",
                    f"Check that {dip.name} sits under the ceiling with a unique "
                    "(x, z), then rebuild the mesh.",
                    where=dip.name,
                ))

    # -- W-BND-08 suspiciously small patches -------------------------------
    small = [p for p in patches
             if p.n_faces is not None and 0 < p.n_faces <= SMALL_PATCH_FACES]
    if small:
        issues.append(warn(
            "W-BND-08",
            f"{plural(len(small), 'patch', 'es')} have very few faces: "
            + ", ".join(f"{p.name} ({p.n_faces})" for p in small),
            "A patch resolved by a handful of faces cannot represent a flow or a heat "
            "flux with any accuracy. For an inlet it also means the supply jet enters "
            "through almost a single cell.",
            "Refine the mesh near these surfaces (reduce m3DMaxSize, or lower the "
            "local size for that group).",
            value=[p.name for p in small],
        ))
    return issues


# ===========================================================================
# 3.4  0/ field files
# ===========================================================================

#: class + dimensions each generated field must declare.
_FIELD_SPEC = {
    "U": ("volVectorField", "[0 1 -1 0 0 0 0]"),
    "T": ("volScalarField", "[0 0 0 1 0 0 0]"),
    "p": ("volScalarField", "[1 -1 -2 0 0 0 0]"),
    "p_rgh": ("volScalarField", "[1 -1 -2 0 0 0 0]"),
    "k": ("volScalarField", "[0 2 -2 0 0 0 0]"),
    "epsilon": ("volScalarField", "[0 2 -3 0 0 0 0]"),
    "nut": ("volScalarField", "[0 2 -1 0 0 0 0]"),
    "alphat": ("volScalarField", "[1 -1 -1 0 0 0 0]"),
}


@dataclass
class FieldFile:
    """A parsed 0/<field> file."""

    name: str = ""
    class_name: str | None = None
    dimensions: str | None = None
    internal_field: str | None = None
    boundary: dict = dc_field(default_factory=dict)


@_guard_value(lambda text, name="", *a, **k: FieldFile(name=name))
def parse_field_file(text: str, name: str = "") -> FieldFile:
    """Parse an OpenFOAM field file into its header and per-patch entries."""
    body = _strip_foam_comments(_as_text(text))
    parsed = FieldFile(name=name)

    header = _find_block(body, "FoamFile")
    if header:
        parsed.class_name = _entry(header, "class")
        if not name:
            parsed.name = _entry(header, "object") or ""

    parsed.dimensions = _entry(body, "dimensions")
    parsed.internal_field = _entry(body, "internalField")

    boundary_body = _find_block(body, "boundaryField")
    if boundary_body:
        for patch_name, patch_body in _iter_blocks(boundary_body):
            parsed.boundary[patch_name] = patch_body
    return parsed


def _normalise_dimensions(text) -> str:
    if text is None:
        return ""
    return "[" + " ".join(_as_text(text).strip().strip("[]").split()) + "]"


@_guard_issues("W-FLD-00", "The field coverage check")
def check_field_coverage(field_texts: dict, patches, object_simulation: dict = None
                         ) -> list[Issue]:
    """Emits E-FLD-01..05, W-FLD-06."""
    issues: list[Issue] = []
    field_texts = field_texts or {}
    object_simulation = object_simulation or {}
    patch_names = [p.name for p in (patches or [])]

    # -- E-FLD-01 every field present -------------------------------------
    missing = [name for name in FIELD_NAMES if name not in field_texts]
    if missing:
        issues.append(error(
            "E-FLD-01",
            f"{plural(len(missing), 'field file')} missing from 0/: "
            + ", ".join(missing),
            "buoyantSimpleFoam reads all of "
            + ", ".join(FIELD_NAMES)
            + ". A missing one aborts the solver at startup with a FOAM FATAL IO "
            "ERROR. A half-written 0/ folder is also enough to make the pipeline skip "
            "field generation on the next run, so the gap persists.",
            "Delete the 0/ folder and re-run so the fields are regenerated from "
            "scratch.",
            value=missing,
        ))

    if not patch_names:
        issues.append(warn(
            "W-FLD-00",
            "No mesh patches were available, so per-patch coverage was not checked",
            "Without the patch list from constant/polyMesh/boundary this check cannot "
            "tell whether every patch has a boundary condition in every field.",
            "Make sure the mesh was converted before the fields were generated.",
        ))

    parsed_fields: dict[str, FieldFile] = {}
    for name, text in sorted(field_texts.items()):
        parsed_fields[name] = parse_field_file(text, name)

    for name, parsed in parsed_fields.items():
        spec = _FIELD_SPEC.get(name)

        # -- E-FLD-05 header ----------------------------------------------
        if spec:
            expected_class, expected_dims = spec
            if parsed.class_name and parsed.class_name != expected_class:
                issues.append(error(
                    "E-FLD-05",
                    f"0/{name} declares class {parsed.class_name!r}, expected "
                    f"{expected_class!r}",
                    "OpenFOAM uses the class to decide whether the field is a scalar "
                    "or a vector. A mismatch aborts the run at startup.",
                    f"Regenerate the 0/ folder. If you edited 0/{name} by hand, "
                    f"restore 'class {expected_class};' in its FoamFile header.",
                    where=f"0/{name}",
                ))
            if parsed.dimensions and _normalise_dimensions(
                parsed.dimensions
            ) != _normalise_dimensions(expected_dims):
                issues.append(error(
                    "E-FLD-05",
                    f"0/{name} has dimensions {parsed.dimensions}, expected "
                    f"{expected_dims}",
                    "OpenFOAM checks dimensional consistency at run time and aborts "
                    "when an equation mixes incompatible units.",
                    f"Regenerate the 0/ folder, or restore "
                    f"'dimensions {expected_dims};' in 0/{name}.",
                    where=f"0/{name}",
                ))

        if not patch_names:
            continue

        # -- E-FLD-02 coverage --------------------------------------------
        absent = [p for p in patch_names if p not in parsed.boundary]
        extra = [p for p in parsed.boundary if p not in patch_names]
        if absent:
            issues.append(error(
                "E-FLD-02",
                f"0/{name} has no entry for {plural(len(absent), 'patch', 'es')}: "
                + ", ".join(sorted(absent)),
                "Every patch in the mesh needs a boundary condition in every field. "
                "OpenFOAM aborts at startup with a FOAM FATAL IO ERROR naming the "
                "first patch it cannot find.",
                "Delete the 0/ folder and re-run so the fields are regenerated for "
                "the current mesh. This mismatch usually means the mesh was rebuilt "
                "while the old 0/ folder was kept.",
                where=f"0/{name}",
                value=sorted(absent),
            ))
        if extra:
            issues.append(error(
                "E-FLD-02",
                f"0/{name} defines {plural(len(extra), 'patch', 'es')} that the mesh "
                "does not have: " + ", ".join(sorted(extra)),
                "These entries refer to patches that no longer exist, which means the "
                "field files and the mesh come from different geometries.",
                "Delete the 0/ folder and re-run to regenerate the fields.",
                where=f"0/{name}",
                value=sorted(extra),
            ))

    # -- E-FLD-03 U fell through to zeroGradient --------------------------
    u_field = parsed_fields.get("U")
    if u_field and patch_names:
        slipped = []
        for patch_name, block in u_field.boundary.items():
            entry_type = (_entry(block, "type") or "").strip()
            if entry_type == "zeroGradient":
                slipped.append(patch_name)
        if slipped:
            issues.append(error(
                "E-FLD-03",
                f"0/U uses zeroGradient on {plural(len(slipped), 'patch', 'es')}: "
                + ", ".join(sorted(slipped)),
                "zeroGradient on velocity is the fallback BoundaryManager applies when "
                "it cannot classify a patch. Physically it is a free-slip surface: no "
                "friction, no boundary layer, no wall shear. A room whose walls do not "
                "grip the air produces completely different circulation, and nothing "
                "in the solver output hints at it.",
                "These patches were not recognised as wall/inlet/outlet. Fix the "
                "object names so they match the patch names, delete the 0/ folder and "
                "re-run.",
                value=sorted(slipped),
            ))

    # -- E-FLD-04 inlets carry the values from the script ------------------
    t_field = parsed_fields.get("T")
    for patch_name in patch_names:
        if not patch_name.startswith("inlet_"):
            continue
        dip_name = patch_name[len("inlet_"):]
        wanted = object_simulation.get(dip_name, {}) or {}

        if u_field is not None:
            block = u_field.boundary.get(patch_name)
            vector = _parse_uniform_vector(_entry(block, "value")) if block else None
            if block is None or vector is None:
                issues.append(error(
                    "E-FLD-04",
                    f"0/U has no numeric fixedValue for {patch_name}",
                    "A supply inlet needs an explicit velocity vector. Without it the "
                    "solver either aborts or, worse, treats the inlet as a wall.",
                    "Delete the 0/ folder and re-run so the inlet conditions are "
                    f"regenerated from V_Flow on {dip_name}.",
                    where=f"0/U:{patch_name}",
                ))
            else:
                expected = as_float(wanted.get("V_Flow"), None)
                if expected is not None and not _close(vector[1], expected):
                    issues.append(error(
                        "E-FLD-04",
                        f"0/U on {patch_name} is "
                        f"{format_number(vector[1])} m/s but the script says "
                        f"V_Flow={format_number(expected)}",
                        "The generated field does not match the script, so the case on "
                        "disk is not the case you described. This happens when the 0/ "
                        "folder was kept from an earlier run with different values.",
                        "Delete the 0/ folder and re-run to regenerate the fields.",
                        where=f"0/U:{patch_name}",
                    ))

        if t_field is not None:
            block = t_field.boundary.get(patch_name)
            value = _parse_uniform_scalar(_entry(block, "value")) if block else None
            if block is None or value is None:
                issues.append(error(
                    "E-FLD-04",
                    f"0/T has no numeric fixedValue for {patch_name}",
                    "The supply air temperature is what drives the whole thermal "
                    "comfort result; an inlet without it is meaningless.",
                    "Delete the 0/ folder and re-run so the inlet temperature is "
                    f"regenerated from T_Flow on {dip_name}.",
                    where=f"0/T:{patch_name}",
                ))
            else:
                expected = as_float(wanted.get("T_Flow"), None)
                if expected is not None and not _close(value, expected):
                    issues.append(error(
                        "E-FLD-04",
                        f"0/T on {patch_name} is {format_number(value)} K but the "
                        f"script says T_Flow={format_number(expected)}",
                        "The generated field does not match the script, so the case on "
                        "disk is not the case you described.",
                        "Delete the 0/ folder and re-run to regenerate the fields.",
                        where=f"0/T:{patch_name}",
                    ))

    # -- W-FLD-06 wall temperatures fell back ------------------------------
    if t_field is not None:
        for patch_name in patch_names:
            if patch_name.startswith("inlet_") or patch_name in ("wall", "outlet"):
                continue
            wanted = object_simulation.get(patch_name, {}) or {}
            if "T_Face" in wanted or "T_face" in wanted:
                continue
            if patch_name in t_field.boundary:
                issues.append(warn(
                    "W-FLD-06",
                    f"{patch_name} has no T_Face, so it inherited the room temperature",
                    "BoundaryManager falls back to the room's T_Face (or the T "
                    "internalField) for any wall without its own value. A person or a "
                    "piece of furniture at exactly room temperature exchanges no heat, "
                    "so it contributes nothing to the thermal result.",
                    f"Give it a temperature, for example T_Face=305 on {patch_name} "
                    "for a clothed person (about 32 C).",
                    where=patch_name,
                ))
    return issues


# ===========================================================================
# 4.2 / 4.3 / 4.4  LogMonitor
# ===========================================================================

_TIME_RE = re.compile(r"^\s*Time\s*=\s*([0-9.eE+\-]+)\s*$")
_RESIDUAL_RE = re.compile(
    r"Solving for (?P<field>[\w()|]+),\s*Initial residual = (?P<initial>[0-9.eE+\-]+)"
)
_FATAL_RE = re.compile(r"FOAM FATAL (ERROR|IO ERROR)", re.I)
_FPE_RE = re.compile(r"Floating point exception|signal\s*(8|11)\b", re.I)
_NAN_RE = re.compile(r"\b(nan|-?inf)\b", re.I)
_MPI_RE = re.compile(
    r"not enough slots|mpirun noticed that process rank|"
    r"MPI_ABORT|primary job\s+.*has aborted",
    re.I,
)
_CONVERGED_RE = re.compile(
    r"solution converged in\s+(\d+)\s+iterations", re.I
)
_BOUNDING_RE = re.compile(r"^\s*bounding\s+([\w.]+)", re.M | re.I)
_LIMIT_TEMP_RE = re.compile(r"limitTemperature.*?limited", re.I)
_MAXITER_RE = re.compile(r"No Iterations\s+(\d+)")
_COURANT_RE = re.compile(
    r"Courant Number mean:\s*([0-9.eE+\-]+)\s*max:\s*([0-9.eE+\-]+)", re.I
)
_MINMAX_RE = re.compile(
    r"(?:min|max)\((mag\()?(\w+)\)?\)\s*=\s*([0-9.eE+\-]+)", re.I
)
_END_RE = re.compile(r"^\s*End\s*$", re.M)

MONITOR_CSV_COLUMNS = (
    "iteration", "time", "Ux", "Uy", "Uz", "h", "p_rgh", "k", "epsilon",
    "Tmin", "Tmax", "Umax", "flags",
)

VERDICT_CONVERGED = "CONVERGED"
VERDICT_MAX_ITERATIONS = "MAX_ITERATIONS"
VERDICT_DIVERGED = "DIVERGED"
VERDICT_CRASHED = "CRASHED"
VERDICT_INCOMPLETE = "INCOMPLETE"


class LogMonitor:
    """Streaming monitor for the solver log (Gate C).

    Fed one line at a time, exactly like ResidualPlotter.feed_line. Emits
    E-RUN-01..06, W-RUN-07..12, I-RUN-13 and the dormant E-RUN-14/W-RUN-15
    Courant checks. `fatal` tells the caller the run is not worth continuing.

    Nothing here presents a `Time =` value as seconds: with
    ddtSchemes steadyState it is a SIMPLE iteration counter.
    """

    def __init__(self, residual_control: float = RESIDUAL_CONTROL,
                 divergence_threshold: float = 1e3, rise_window: int = 20,
                 stagnation_window: int = 200, stall_seconds: float = 600.0,
                 clock=time.monotonic):
        self.residual_control = residual_control
        self.divergence_threshold = divergence_threshold
        self.rise_window = max(2, int(rise_window))
        self.stagnation_window = max(10, int(stagnation_window))
        self.stall_seconds = float(stall_seconds)
        self._clock = clock

        self._issues: list[Issue] = []
        self._seen_codes: set = set()
        self._history: dict = {}
        self._pending: dict = {}
        self._rows: list = []
        self._current_time = None
        self._iterations = 0
        self._fatal = False
        self._diverged = False
        self._converged = False
        self._converged_iterations = None
        self._saw_end = False
        self._returncode = None
        self._finished = False
        self._bounding_counts: dict = {}
        self._minmax: dict = {}
        self._fatal_context: list = []
        self._capture_context = 0
        self._last_line_at = self._clock()
        self._stall_reported = False

    # -- public state ------------------------------------------------------
    @property
    def issues(self) -> list:
        return list(self._issues)

    @property
    def fatal(self) -> bool:
        return self._fatal

    @property
    def diverged(self) -> bool:
        return self._diverged

    @property
    def should_abort(self) -> bool:
        """True only when killing the solver actually saves time.

        Divergence is worth interrupting: the solver would keep iterating for
        hours on a solution that is already ruined. A FOAM FATAL ERROR, a
        floating-point exception or an MPI failure is not - the process is
        already dying, and killing it early would cut off the lines that name
        the missing file or dictionary key.
        """
        return self._diverged

    @property
    def iterations(self) -> int:
        return self._iterations

    @property
    def converged(self) -> bool:
        return self._converged

    @property
    def final_residuals(self) -> dict:
        return {name: values[-1][1] for name, values in self._history.items() if values}

    @property
    def verdict(self) -> str:
        if self._diverged:
            return VERDICT_DIVERGED
        if self._fatal:
            return VERDICT_CRASHED
        if self._converged:
            return VERDICT_CONVERGED
        if self._returncode not in (None, 0):
            return VERDICT_CRASHED
        if self._saw_end and self._iterations > 0:
            return VERDICT_MAX_ITERATIONS
        return VERDICT_INCOMPLETE

    # -- ingestion ---------------------------------------------------------
    def _emit(self, issue: Issue, once: bool = True):
        """Record an issue, optionally only the first time for its code."""
        if once:
            if issue.code in self._seen_codes:
                return []
            self._seen_codes.add(issue.code)
        self._issues.append(issue)
        return [issue]

    def feed_line(self, line: str) -> list:
        """Consume one log line; return the issues it raised (usually none)."""
        try:
            return self._feed(line)
        except Exception:  # noqa: BLE001 - a monitor must never kill the run
            return []

    def _feed(self, line: str) -> list:
        raw = _as_text(line).rstrip("\n")
        self._last_line_at = self._clock()
        out: list = []

        # Capture the lines that follow a FOAM FATAL ERROR: that is where
        # OpenFOAM names the missing file or dictionary key.
        if self._capture_context > 0 and raw.strip():
            self._fatal_context.append(raw.strip())
            self._capture_context -= 1
            if self._capture_context == 0 and self._fatal_context:
                out += self._emit(error(
                    "E-RUN-01",
                    "The solver stopped with a FOAM FATAL ERROR",
                    "OpenFOAM reported:\n  " + "\n  ".join(self._fatal_context[:8]),
                    "Read the lines above: OpenFOAM names the file or dictionary key "
                    "it could not resolve. A missing entry in 0/ or system/ is the "
                    "usual cause, and regenerating the case (delete 0/ and re-run) "
                    "fixes most of them.",
                ))
            return out

        if _FATAL_RE.search(raw):
            self._fatal = True
            self._capture_context = 8
            self._fatal_context = [raw.strip()]
            return out

        if _FPE_RE.search(raw):
            self._fatal = True
            out += self._emit(error(
                "E-RUN-02",
                "The solver crashed with a floating-point exception",
                f"Reported: {raw.strip()}\n"
                "This is almost always divergence that grew until a value overflowed: "
                "the pressure or temperature field ran away before the run ended.",
                "Reduce the relaxation factors in system/fvSolution (try U 0.2, "
                "h 0.2), check that V_Flow has the right sign, and confirm the mesh "
                "passed checkMesh.",
            ))
            return out

        if _MPI_RE.search(raw):
            self._fatal = True
            out += self._emit(error(
                "E-RUN-05",
                "The parallel run failed to start or was aborted by MPI",
                f"Reported: {raw.strip()}\n"
                f"The solver is launched with 'mpirun -np {DECOMPOSE_SUBDOMAINS}' and "
                f"decomposeParDict always splits the case into {DECOMPOSE_SUBDOMAINS} "
                "subdomains.",
                f"Give WSL at least {DECOMPOSE_SUBDOMAINS} CPU cores, or switch to "
                'serial with parallel="N".',
            ))
            return out

        time_match = _TIME_RE.match(raw)
        if time_match:
            out += self._commit()
            self._current_time = as_float(time_match.group(1), None)
            self._pending = {}
            self._iterations += 1
            return out

        # A residual of "nan"/"inf" does not match _RESIDUAL_RE's numeric class,
        # so the line would otherwise slip through unnoticed.
        if "Initial residual" in raw and _NAN_RE.search(raw):
            self._fatal = True
            self._diverged = True
            return out + self._emit(error(
                "E-RUN-03",
                "A residual is 'nan' or 'inf' - the solution has blown up",
                f"Reported: {raw.strip()}\n"
                "Once a residual is not a number the fields are already destroyed. "
                "Every further iteration is meaningless and the written time "
                "directories from here on are unusable.",
                "Lower the relaxation factors in system/fvSolution (try U 0.2 and "
                "h 0.2), confirm V_Flow is negative on the ceiling diffusers, check "
                "that the room has an outlet opening, and re-read log.checkMesh for "
                "bad cells.",
            ))

        residual_match = _RESIDUAL_RE.search(raw)
        if residual_match:
            value = as_float(residual_match.group("initial"), None)
            field_name = residual_match.group("field")
            if value is None or value != value or value in (float("inf"), float("-inf")):
                self._fatal = True
                self._diverged = True
                out += self._emit(error(
                    "E-RUN-03",
                    f"The residual for {field_name} is not a number",
                    f"Reported: {raw.strip()}\n"
                    "A NaN or infinity in the residuals means the solution has already "
                    "blown up. Every iteration from here on is meaningless.",
                    "Lower the relaxation factors in system/fvSolution, verify the "
                    "boundary-condition values, and re-check the mesh quality.",
                ))
                return out
            self._pending[field_name] = value

            if value > self.divergence_threshold:
                self._fatal = True
                self._diverged = True
                out += self._emit(error(
                    "E-RUN-04",
                    f"The residual for {field_name} reached "
                    f"{format_number(value)} - the run is diverging",
                    f"Initial residuals should fall towards "
                    f"{format_number(self.residual_control)}, not grow past "
                    f"{format_number(self.divergence_threshold)}. Continuing only "
                    "burns machine time.",
                    "Common causes here: V_Flow with the wrong sign (positive blows "
                    "air out through the ceiling), no outlet opening, or relaxation "
                    "factors that are too aggressive. Try U 0.2 and h 0.2 in "
                    "system/fvSolution.",
                ))
            return out

        bounding = _BOUNDING_RE.match(raw)
        if bounding:
            name = bounding.group(1).rstrip(",")
            self._bounding_counts[name] = self._bounding_counts.get(name, 0) + 1
            if self._bounding_counts[name] == BOUNDING_EVENT_LIMIT:
                out += self._emit(warn(
                    "W-RUN-07",
                    f"'bounding {name}' has been reported "
                    f"{BOUNDING_EVENT_LIMIT} times",
                    "OpenFOAM clips a turbulence quantity back into a physical range "
                    "every time it prints this. A few at start-up are normal; this "
                    "many means the turbulence field is being held together by the "
                    "limiter rather than solved.",
                    "The hardcoded inlet values (k = 0.00375, mixingLength = 0.0168) "
                    "may not suit your diffuser. Check the inlet entries in 0/k and "
                    "0/epsilon, and look for poor cells near the diffusers in "
                    "log.checkMesh.",
                ))
            return out

        if _LIMIT_TEMP_RE.search(raw):
            out += self._emit(warn(
                "W-RUN-08",
                "The temperature limiter in fvOptions is actively clamping cells",
                f"Reported: {raw.strip()}\n"
                f"system/fvOptions constrains temperature to "
                f"[{format_number(LIMIT_TEMPERATURE_MIN)}, "
                f"{format_number(LIMIT_TEMPERATURE_MAX)}] K over all cells. While it "
                "is limiting, the energy equation is not being solved as written and "
                "the result is shaped by the limiter.",
                "Either widen min/max on limitTAir in system/fvOptions, or bring the "
                "boundary temperatures inside that window.",
            ))
            return out

        max_iter = _MAXITER_RE.search(raw)
        if max_iter and int(max_iter.group(1)) >= LINEAR_SOLVER_MAX_ITER:
            out += self._emit(warn(
                "W-RUN-10",
                f"A linear solver is hitting its iteration ceiling "
                f"({max_iter.group(1)} iterations)",
                "The pressure or momentum equation is not converging within the "
                "allowed iterations each outer step, which makes the whole SIMPLE loop "
                "crawl and can stall convergence entirely.",
                "This usually points at mesh quality (check non-orthogonality in "
                "log.checkMesh) or too tight a tolerance on p_rgh in "
                "system/fvSolution.",
            ))
            return out

        courant = _COURANT_RE.search(raw)
        if courant:
            max_courant = as_float(courant.group(2), None)
            if max_courant is not None:
                if max_courant > COURANT_ERROR:
                    out += self._emit(error(
                        "E-RUN-14",
                        f"Courant number reached {format_number(max_courant)}",
                        "Above 1 an explicit time integration is unstable. Note that "
                        "the case NEMOS generates is steady-state and prints no "
                        "Courant number, so seeing this means the solver or fvSchemes "
                        "was changed to a transient setup.",
                        "Reduce deltaT so the maximum Courant number stays below 1.",
                    ))
                elif max_courant > COURANT_WARN:
                    out += self._emit(warn(
                        "W-RUN-15",
                        f"Courant number reached {format_number(max_courant)}",
                        "Above about 0.5 the time integration accuracy starts to "
                        "suffer in a transient run.",
                        "Consider reducing deltaT.",
                    ))
            return out

        for _mag, name, value_text in _MINMAX_RE.findall(raw):
            value = as_float(value_text, None)
            if value is None:
                continue
            self._minmax[name] = value
            if name == "T" and (
                _close(value, LIMIT_TEMPERATURE_MIN, rel=1e-4)
                or _close(value, LIMIT_TEMPERATURE_MAX, rel=1e-4)
            ):
                out += self._emit(warn(
                    "W-RUN-08",
                    f"Temperature is sitting exactly on the fvOptions limit "
                    f"({format_number(value)} K)",
                    "A field pinned to the limiter value means the limiter, not the "
                    "physics, is setting the answer there.",
                    "Widen min/max on limitTAir in system/fvOptions, or adjust the "
                    "boundary temperatures.",
                ))
            if name == "U" and value >= VELOCITY_DAMPING_UMAX * (1 - UMAX_CEILING_TOL):
                out += self._emit(warn(
                    "W-RUN-09",
                    f"Velocity has reached the damping ceiling "
                    f"({format_number(value)} m/s)",
                    f"system/fvOptions damps velocities above "
                    f"{format_number(VELOCITY_DAMPING_UMAX)} m/s over all cells. At "
                    "the ceiling the momentum equation is being overridden.",
                    "Raise UMax in system/fvOptions if these speeds are real, or find "
                    "out why the flow is accelerating this much (often a tiny outlet).",
                ))

        if _END_RE.match(raw):
            self._saw_end = True
        return out

    def _commit(self) -> list:
        """Close the current iteration: push residuals into the history."""
        out: list = []
        if self._current_time is None or not self._pending:
            return out
        row = {"iteration": self._iterations, "time": self._current_time}
        for name, value in self._pending.items():
            self._history.setdefault(name, []).append((self._current_time, value))
            row[name] = value
        for key, value in self._minmax.items():
            row[f"minmax_{key}"] = value
        self._rows.append(row)
        out += self._check_stagnation()
        return out

    def _check_stagnation(self) -> list:
        """W-RUN-11 - residuals flat but still above residualControl."""
        if self._converged:
            return []
        window = self.stagnation_window
        for name, values in self._history.items():
            if len(values) < window:
                continue
            recent = [v for _t, v in values[-window:]]
            if min(recent) <= self.residual_control:
                continue
            first, last = recent[0], recent[-1]
            if first <= 0:
                continue
            change = abs(first - last) / first
            if change < STAGNATION_REL_CHANGE:
                return self._emit(warn(
                    "W-RUN-11",
                    f"The residual for {name} has been flat for {window} iterations "
                    f"at about {format_number(last)}",
                    f"It has moved less than {STAGNATION_REL_CHANGE * 100:.0f}% over "
                    f"that window while still far above the residualControl target of "
                    f"{format_number(self.residual_control)}. The run has settled into "
                    "a limit cycle: more iterations will not converge it.",
                    "Lower the relaxation factors in system/fvSolution (U and h are "
                    "at 0.3, p_rgh at 0.7), or improve the mesh where "
                    "log.checkMesh flagged poor cells. Adding more iterations alone "
                    "will not help.",
                ))
        return []

    def check_stall(self) -> list:
        """W-RUN-12 - no output for a long time.

        Detected retroactively: the streaming loop blocks waiting for the next
        line, so a total freeze is noticed only once something is written again
        (or when the caller polls this method from elsewhere).
        """
        if self._stall_reported or self._finished:
            return []
        idle = self._clock() - self._last_line_at
        if idle < self.stall_seconds:
            return []
        self._stall_reported = True
        return self._emit(warn(
            "W-RUN-12",
            f"The solver produced no output for {idle / 60:.0f} minutes",
            "Either an iteration is genuinely taking that long (a very large mesh on "
            "few cores), or the process is stuck. A stuck decomposePar or an MPI rank "
            "waiting on another looks exactly like this.",
            "Check CPU usage. If it is idle, stop the run and re-check the "
            f"decomposition ({DECOMPOSE_SUBDOMAINS} subdomains) and the mesh size.",
        ))

    def finish(self, returncode: int = None, end_time: float = None) -> None:
        """Close the final iteration and settle the verdict."""
        try:
            self._commit()
            self._returncode = returncode
            self._finished = True

            # Flush a fatal error whose trailing context never arrived, either
            # because the process died mid-message or because the caller stopped
            # reading. Without this the single most useful message in the whole
            # layer - the lines naming the missing file - would be lost.
            if self._fatal_context and "E-RUN-01" not in self._seen_codes:
                self._emit(error(
                    "E-RUN-01",
                    "The solver stopped with a FOAM FATAL ERROR",
                    "OpenFOAM reported:\n  " + "\n  ".join(self._fatal_context[:8]),
                    "Read the lines above: OpenFOAM names the file or dictionary key "
                    "it could not resolve. A missing or malformed entry in 0/ or "
                    "system/ is the usual cause; deleting the 0/ folder and re-running "
                    "regenerates it.",
                ))
                self._capture_context = 0

            if not self._converged and self._history and not self._fatal:
                worst = max(
                    (values[-1][1] for values in self._history.values() if values),
                    default=None,
                )
                if worst is not None and worst <= self.residual_control:
                    self._converged = True

            if self._converged:
                self._emit(info(
                    "I-RUN-13",
                    "The solver reported a converged solution after "
                    f"{self._converged_iterations or self._iterations} iterations",
                    "Every monitored residual fell below the residualControl target of "
                    f"{format_number(self.residual_control)}.",
                    "No action needed.",
                ))
            elif returncode not in (None, 0) and not self._fatal:
                self._emit(error(
                    "E-RUN-06",
                    f"The solver exited with code {returncode}",
                    "It stopped without reporting convergence and without a FOAM FATAL "
                    "ERROR, so the failure came from the shell or from MPI.",
                    "Read log.simulation from the end backwards; the last lines before "
                    "the exit usually name the cause.",
                ))
            elif not self._saw_end and self._iterations > 0 and not self._fatal:
                # When a fatal error was already reported, a second "it did not
                # reach the end" message adds nothing but noise.
                self._emit(error(
                    "E-RUN-06",
                    f"The solver stopped after {self._iterations} iterations without "
                    "reaching the end of the run",
                    "OpenFOAM never printed its final 'End' marker, so the process was "
                    "interrupted rather than finishing.",
                    "Re-run to continue: controlDict uses 'startFrom latestTime', so "
                    "the solver picks up from the last written time directory.",
                ))
        except Exception:  # noqa: BLE001
            pass

    # -- outputs -----------------------------------------------------------
    def rows(self) -> list:
        return list(self._rows)

    def write_csv(self, path):
        """Write monitor.csv (section 4.4). Returns the path, or None."""
        try:
            if not self._rows:
                return None
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            keys: list = []
            for row in self._rows:
                for key in row:
                    if key not in keys:
                        keys.append(key)
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                for row in self._rows:
                    writer.writerow(row)
            return path
        except (OSError, ValueError):
            return None


# ===========================================================================
# 5.1 / 5.4  status summary and artifacts
# ===========================================================================


def summarize_status(monitor: LogMonitor, case_path=None, wall_clock_s: float = None
                     ) -> dict:
    """Payload for .nemos_status.json (section 5.1)."""
    try:
        residuals = {
            name: value for name, value in (monitor.final_residuals or {}).items()
        }
        return {
            "verdict": monitor.verdict,
            "iterations": monitor.iterations,
            "final_residuals": residuals,
            "residual_control": monitor.residual_control,
            "residual_control_met": bool(monitor.converged),
            "wall_clock_s": round(wall_clock_s, 1) if wall_clock_s else None,
            "case_path": str(case_path) if case_path else None,
        }
    except Exception:  # noqa: BLE001
        return {"verdict": VERDICT_INCOMPLETE, "iterations": 0, "final_residuals": {}}


@_guard_issues("W-ART-00", "The artifact completeness check")
def check_artifacts(case_path, parallel: bool = True) -> list[Issue]:
    """Emits W-ART-01..04."""
    issues: list[Issue] = []
    case = Path(case_path)

    # -- W-ART-01 results were written ------------------------------------
    time_dirs = []
    processor_dirs = sorted(case.glob("processor*"))
    try:
        for entry in case.iterdir():
            if entry.is_dir() and re.fullmatch(r"\d+(\.\d+)?", entry.name):
                if entry.name not in ("0",):
                    time_dirs.append(entry.name)
    except OSError:
        pass

    reconstructed = bool(time_dirs)
    decomposed_results = False
    for processor in processor_dirs:
        try:
            for entry in processor.iterdir():
                if (entry.is_dir() and re.fullmatch(r"\d+(\.\d+)?", entry.name)
                        and entry.name != "0"):
                    decomposed_results = True
                    break
        except OSError:
            continue
        if decomposed_results:
            break

    if not reconstructed and not decomposed_results:
        issues.append(warn(
            "W-ART-01",
            "No result time directory was written",
            "Only the initial 0/ folder exists, so the solver never reached a write "
            "step. There is nothing to post-process.",
            "Check that writeInterval is smaller than the number of iterations: with "
            "writeControl timeStep, writeInterval counts iterations.",
        ))

    # -- W-ART-03 reconstructPar ------------------------------------------
    if parallel and decomposed_results and not reconstructed:
        issues.append(warn(
            "W-ART-03",
            "Results are still split across the processor directories",
            f"{plural(len(processor_dirs), 'processor directory', 'ies')} hold time "
            "data but the case root has no reconstructed time directory. ParaView "
            "opening caso.foam will show nothing.",
            "Reconstruct the fields before post-processing:\n"
            "    wsl bash -c 'source /usr/lib/openfoam/openfoam2312/etc/bashrc; "
            f"cd \"{str(case).replace(chr(92), '/').replace('C:', '/mnt/c')}\"; "
            "reconstructPar'",
        ))

    # -- W-ART-02 expected files ------------------------------------------
    expected = {
        "log.simulation": "the full solver output",
        "monitor.csv": "the per-iteration residual history",
        "residuals.png": "the convergence plot",
    }
    absent = [name for name in expected if not (case / name).exists()]
    if absent:
        issues.append(warn(
            "W-ART-02",
            f"{plural(len(absent), 'expected output file')} missing: "
            + ", ".join(sorted(absent)),
            "Missing: "
            + "; ".join(f"{name} ({expected[name]})" for name in sorted(absent))
            + ". residuals.png needs matplotlib and plot_residuals=True.",
            "Not fatal, but without log.simulation and monitor.csv there is no record "
            "of how the run converged.",
            value=sorted(absent),
        ))

    # -- W-ART-04 mesh quality summaries ----------------------------------
    summaries = sorted(case.glob("*_summary.txt"))
    for summary in summaries:
        try:
            text = summary.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r"Elements flagged:\s*(\d+)\s*/\s*(\d+)", text)
        if match and int(match.group(1)) > 0:
            flagged, total = int(match.group(1)), int(match.group(2))
            share = 100.0 * flagged / total if total else 0.0
            issues.append(warn(
                "W-ART-04",
                f"{summary.stem.replace('_summary', '')}: {flagged:,} of {total:,} "
                f"elements ({share:.1f}%) were flagged by check_quality",
                f"See {summary.name} for the breakdown per region. Poor elements "
                "concentrated on one surface are worth looking at before trusting "
                "gradients there.",
                "If the share is large, refine the mesh near the flagged region.",
                value=flagged,
            ))
    return issues

"""Shared harness for the NEMOS stress scripts.

These are not user templates to copy: they are automated end-to-end runs that
drive the real Python -> SALOME -> OpenFOAM chain and then inspect what came
out. Each stress script imports this module for path setup and for the
post-run report.

The report deliberately reuses the validation layer's own parsers
(validation_parsers), so a stress run also exercises Gate B/C/D against real
OpenFOAM output instead of the synthetic strings they were developed against.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

#: Everything is written under here. Must be on C: with no spaces - the WSL
#: path translation in Simulation.py only rewrites a literal "C:" (E-ENV-05).
DEFAULT_ROOT = r"C:\Users\pedro\Desktop\TCC1\STRESS"


def bootstrap():
    """Put src/ on sys.path and return (repo_root, src_dir).

    Self-locating, so a stress script runs from any working directory.
    """
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return repo, src


def stress_root() -> Path:
    """Root output folder, overridable with NEMOS_STRESS_ROOT."""
    return Path(os.environ.get("NEMOS_STRESS_ROOT", DEFAULT_ROOT))


def case_dir(name: str, fresh: bool = False) -> Path:
    """Case folder for one stress run.

    `fresh` only removes the completion markers, never the mesh: rebuilding a
    mesh costs tens of minutes and the stale-case guard (E-STATE-01) will speak
    up anyway if the geometry actually changed.
    """
    path = stress_root() / name
    path.mkdir(parents=True, exist_ok=True)
    if fresh:
        for marker in (".nemos_done", ".nemos_status.json"):
            target = path / marker
            if target.exists():
                target.unlink()
    return path


def preflight_only() -> bool:
    """True when NEMOS_VALIDATE=preflight-only is forcing a dry run.

    In that mode every script validates its configuration and stops before
    SALOME, so there are no artifacts to report on. Running the whole suite
    this way validates every case in seconds:

        NEMOS_VALIDATE=preflight-only python Templates/run_all_stress.py
    """
    return os.environ.get("NEMOS_VALIDATE", "").strip().lower() == "preflight-only"


def banner(title: str, detail: str = "") -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}")
    if detail:
        print(detail.strip() + "\n")


class Timer:
    def __init__(self, label: str):
        self.label = label
        self.seconds = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *exc):
        self.seconds = time.time() - self._start
        print(f"[timing] {self.label}: {self.seconds / 60:.1f} min "
              f"({self.seconds:.0f} s)")
        return False


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def inspect_case(case: Path) -> dict:
    """Everything worth knowing about a finished case, as plain data."""
    import validation_parsers as parsers

    facts: dict = {"case": str(case)}

    status = _read_json(case / ".nemos_status.json") or {}
    facts["verdict"] = status.get("verdict")
    facts["iterations"] = status.get("iterations")
    facts["converged"] = status.get("residual_control_met")
    facts["done_marker"] = (case / ".nemos_done").exists()

    check_mesh = _read_text(case / "log.checkMesh")
    if check_mesh:
        result = parsers.parse_check_mesh(check_mesh)
        facts["cells"] = result.cells
        facts["mesh_ok"] = result.ok
        facts["max_non_ortho"] = result.max_non_ortho
        facts["max_skewness"] = result.max_skewness
        if result.bbox_min and result.bbox_max:
            facts["bbox"] = tuple(
                round(result.bbox_max[i] - result.bbox_min[i], 3) for i in range(3)
            )

    boundary = _read_text(case / "constant" / "polyMesh" / "boundary")
    if boundary:
        patches, _unparsed = parsers.parse_boundary_file(boundary)
        facts["patches"] = {p.name: p.n_faces for p in patches}
        facts["empty_patches"] = sorted(p.name for p in patches if p.n_faces == 0)

    zero = case / "0"
    facts["fields"] = sorted(f.name for f in zero.iterdir()) if zero.is_dir() else []
    facts["time_dirs"] = sorted(
        d.name for d in case.iterdir()
        if d.is_dir() and d.name.replace(".", "", 1).isdigit() and d.name != "0"
    ) if case.is_dir() else []
    facts["processor_dirs"] = len(list(case.glob("processor*")))
    return facts


def report(case: Path, expect_patches=None, expect_inlets=None) -> int:
    """Print a compact result table. Returns a process exit code.

    A stress run "passes" when the chain produced a usable case: a mesh, a full
    set of fields and at least one solver iteration. Convergence is NOT part of
    the pass criterion - most of these runs are deliberately too short for it.
    """
    if preflight_only():
        print("\nSTRESS RESULT: configuration valid (preflight-only dry run, "
              "nothing was executed)")
        return 0

    facts = inspect_case(case)
    problems: list[str] = []

    print("\n--- result " + "-" * 66)
    print(f"  case         : {facts['case']}")
    print(f"  verdict      : {facts.get('verdict')}   "
          f"iterations={facts.get('iterations')}   "
          f"done={facts.get('done_marker')}")

    if "cells" in facts:
        print(f"  mesh         : {facts['cells']:,} cells   ok={facts.get('mesh_ok')}   "
              f"bbox={facts.get('bbox')}")
        print(f"  quality      : max non-ortho={facts.get('max_non_ortho')}   "
              f"max skewness={facts.get('max_skewness')}")
    else:
        problems.append("no log.checkMesh - the mesh was never converted")

    patches = facts.get("patches") or {}
    if patches:
        print(f"  patches ({len(patches)})  : "
              + ", ".join(f"{n}={c}" for n, c in sorted(patches.items())))
        if facts.get("empty_patches"):
            problems.append(f"empty patches: {', '.join(facts['empty_patches'])}")
        if expect_patches is not None and len(patches) != expect_patches:
            problems.append(
                f"expected {expect_patches} patches, found {len(patches)}")
        if expect_inlets is not None:
            inlets = [n for n in patches if n.startswith("inlet_")]
            if len(inlets) != expect_inlets:
                problems.append(
                    f"expected {expect_inlets} inlet patches, found {len(inlets)}: "
                    + ", ".join(sorted(inlets)))
    else:
        problems.append("no boundary file - conversion did not produce patches")

    missing_fields = sorted({"U", "T", "p", "p_rgh", "k", "epsilon", "nut", "alphat"}
                            - set(facts.get("fields") or []))
    print(f"  fields       : {len(facts.get('fields') or [])} written"
          + (f"   MISSING: {', '.join(missing_fields)}" if missing_fields else ""))
    if missing_fields:
        problems.append(f"missing fields: {', '.join(missing_fields)}")

    print(f"  time dirs    : {facts.get('time_dirs')}   "
          f"processor dirs={facts.get('processor_dirs')}")

    if not facts.get("iterations"):
        problems.append("the solver never completed an iteration")

    print("-" * 78)
    if problems:
        print("STRESS RESULT: PROBLEMS FOUND")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("STRESS RESULT: OK (chain produced a usable case)")
    return 0

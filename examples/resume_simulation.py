"""
Resume a single interrupted simulation
======================================

Point this at the folder of a case that was already started and it picks up
where it stopped. Every completed stage (mesh, conversion, fields,
decomposition) is detected from its artifact and skipped, and the solver
continues from the last written timestep.

Requires `Mesh_1.unv` to already exist -- the common case, since interruptions
usually happen during the solver. For an interruption BEFORE meshing, re-run
the original geometry script instead (those are idempotent too).

To force a clean redo, delete the `.nemos_done` marker -- and, if you want the
earlier stages rebuilt as well, `Mesh_1.unv`, the `0/` folder and the
`processor*` folders.

Usage
-----
    python examples/resume_simulation.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Simulation as nemos

# EDIT THIS: the folder of the case you want to resume.
CASE_PATH = Path(__file__).resolve().parents[1] / "cases" / "01_single_run"

nemos.resume(str(CASE_PATH))

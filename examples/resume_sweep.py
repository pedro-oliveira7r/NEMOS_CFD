"""
Resume an interrupted parameter sweep
=====================================

Point this at the ROOT folder of a sweep -- the one containing SIM_0, SIM_1,
... and the `scripts/` folder -- and it continues the batch.

Every SIM_i carrying a `.nemos_done` marker is skipped; the rest are re-run
from the scripts already generated in `scripts/`. Because each per-SIM script
calls the idempotent `Simulation.run`, an interrupted SIM continues from where
it stopped rather than restarting.

To force one finished SIM_i to run again, delete the `.nemos_done` marker
inside that SIM_i folder.

Usage
-----
    python examples/resume_sweep.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Manager as nemos

# EDIT THIS: the root folder of the sweep you want to resume.
CASE_ROOT = Path(__file__).resolve().parents[1] / "cases" / "03_sweep_conditions"

nemos.resume(str(CASE_ROOT))

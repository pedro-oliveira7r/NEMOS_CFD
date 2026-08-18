"""Stress 06 - resume: idempotency and continuation.

Purpose: prove that re-running an existing case CONTINUES it rather than
silently restarting or silently reusing a stale result. This is the behaviour
the whole resume feature rests on, and it is easy to break.

Two phases in one process, against one case folder:

  Phase 1   endTime=10   ->  100 iterations from scratch
  Phase 2   endTime=30   ->  should add ~200 more, starting from 10

What it stresses
  * `startFrom latestTime` in controlDict, which is what makes the solver pick
    up from the newest time directory.
  * The stage detectors in OpenFOAMCase. Phase 2 must skip SALOME, skip the
    mesh conversion and skip field generation, and go straight to the solver.
  * The guarded decomposePar: processor0/ already exists in phase 2, so the
    decomposition must not be redone.
  * The stale-case fingerprints. Only endTime changed, so control_hash differs
    while geometry_hash and bc_hash match: the run must report I-STATE-03 and
    proceed, NOT abort with E-STATE-01/02. A false abort here would make the
    resume feature unusable.

The pass criterion is the interesting part: phase 2 must report FEWER new
iterations than a cold 300-iteration run, which is only true if it resumed.

Expected cost: one meshing stage plus two short solves.

Run:  python Templates/stress_06_resume.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import (  # noqa: E402
    Timer, banner, bootstrap, case_dir, inspect_case, preflight_only,
)

bootstrap()
import Simulation as nemos  # noqa: E402

CASE = case_dir("06_resume", fresh=True)


def build(end_time: float):
    """Identical geometry every time; only endTime differs between phases."""
    sim = nemos.Simulation(
        case_path=str(CASE),
        startTime=0,
        endTime=end_time,
        delta=0.1,
        writeInterval=25,
        parallel="Y",
        T_internalField="uniform 300",
        p_internalField="uniform 101325",
        k_internalField="uniform 0.001",
        epsilon_internalField="uniform 1e-5",
        validate="warn",
    )
    a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=298, name="Room")
    b = nemos.Person_seated(x=1.5, z=1.6, theta=0, thickness=0.15,
                            T_Face=305, name="Person_1")
    c = nemos.Dip_type_01(x=1.5, y=1.0, z=0.8, V_Flow=-1.2, T_Flow=292,
                          name="Dip_1")
    a.insert_ceiling_opening(x=0.6, z=2.4, d=0.12)
    a.insert_ceiling_opening(x=2.4, z=2.4, d=0.12)
    a.add([b, c])
    mesh = nemos.Mesh(a, m2DMaxSize=0.25, m2DMinSize=0.05, m3DMaxSize=0.12,
                      m3DMinSize=0.005, fineness=2)
    mesh.create_mesh(export=True)
    return sim


if preflight_only():
    # A dry run cannot demonstrate resuming: nothing is ever executed. Validate
    # the configuration once and stop, so the suite stays checkable in seconds.
    banner("STRESS 06 - resume", "preflight-only: validating the configuration only")
    nemos.run(build(10))
    print("\nSTRESS RESULT: configuration valid (preflight-only dry run, "
          "nothing was executed)")
    raise SystemExit(0)

banner("STRESS 06 - resume, phase 1", f"endTime=10 (100 iterations)\nCase: {CASE}")
with Timer("phase 1"):
    nemos.run(build(10))
phase1 = inspect_case(CASE)
print(f"  phase 1: verdict={phase1.get('verdict')} "
      f"iterations={phase1.get('iterations')} time_dirs={phase1.get('time_dirs')}")

banner("STRESS 06 - resume, phase 2",
       "endTime=30 (300 total). Only controlDict changed, so this must CONTINUE:\n"
       "expect I-STATE-03 and the SALOME / conversion / field stages to be skipped.")
with Timer("phase 2"):
    nemos.run(build(30))
phase2 = inspect_case(CASE)
print(f"  phase 2: verdict={phase2.get('verdict')} "
      f"iterations={phase2.get('iterations')} time_dirs={phase2.get('time_dirs')}")

print("\n--- resume assertions " + "-" * 55)
problems = []

p1_iters = phase1.get("iterations") or 0
p2_iters = phase2.get("iterations") or 0

if not p1_iters:
    problems.append("phase 1 completed no iterations at all")
if not p2_iters:
    problems.append("phase 2 completed no iterations at all")

# The decisive check: a resumed phase 2 runs only the REMAINING iterations.
# A silent restart would run the full 300.
if p2_iters >= 290:
    problems.append(
        f"phase 2 ran {p2_iters} iterations, which looks like a full restart "
        "from zero rather than a continuation from time 10")
else:
    print(f"  ok: phase 2 ran {p2_iters} iterations, not a full 300 -> it resumed")

dirs1 = set(phase1.get("time_dirs") or [])
dirs2 = set(phase2.get("time_dirs") or [])
if not dirs1 <= dirs2:
    problems.append(
        f"phase 2 lost time directories that phase 1 had written: "
        f"{sorted(dirs1 - dirs2)}")
else:
    print(f"  ok: phase 1 output preserved, phase 2 added "
          f"{sorted(dirs2 - dirs1)}")

if phase2.get("processor_dirs") not in (0, 4):
    problems.append(
        f"unexpected processor directory count: {phase2.get('processor_dirs')}")

print("-" * 78)
if problems:
    print("STRESS RESULT: PROBLEMS FOUND")
    for item in problems:
        print(f"  - {item}")
    raise SystemExit(1)
print("STRESS RESULT: OK (the case resumed instead of restarting)")

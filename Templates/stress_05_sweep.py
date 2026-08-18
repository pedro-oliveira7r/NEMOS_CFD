"""Stress 05 - sweep: the Manager queue and the shared-mesh optimisation.

Purpose: exercise Manager end to end with a sweep long enough that the
shared-mesh path actually matters.

What it stresses
  * The sweep preflight (E-SWP-05): all 6 configurations are validated in child
    processes BEFORE SIM_0 starts meshing. Break one value on purpose and the
    whole batch should abort in seconds instead of hours.
  * The shared-mesh optimisation. No mesh parameter is swept here, so SIM_0
    builds Mesh_1.unv and SIM_1..5 import it through
    nemos.Simulation.Import_mesh. That copy path is the least-travelled code in
    Manager, and a failure in SIM_0 blocks the whole queue (W-SWP-06).
  * Six sequential OpenFOAM runs in one batch, each writing its own
    .nemos_status.json, with the queue stopping on the first failure.
  * check_quality being skipped for SIM_1..5, because those import a mesh and
    have no SALOME mesh object to inspect.

Note that this script must be run as a file, not pasted into a REPL: Manager
finds the sweep lists by parsing its own source (script_path=__file__), so a
list defined anywhere other than the top level is not recognised (E-SWP-02).

Expected cost: one meshing stage plus six short solves.

Run:  python Templates/stress_05_sweep.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import (  # noqa: E402
    Timer, banner, bootstrap, case_dir, inspect_case, preflight_only,
)

bootstrap()
import Manager as nemos  # noqa: E402

CASE = case_dir("05_sweep")

banner(
    "STRESS 05 - sweep",
    f"""6 simulations, boundary conditions only -> SIM_0 meshes, SIM_1..5 import.
Case root: {CASE}""",
)

sim = nemos.Simulation(
    script_path=__file__,
    case_path=str(CASE),
    startTime=0,
    endTime=15,
    delta=0.1,
    writeInterval=100,
    parallel="Y",
    T_internalField="uniform 299",
    p_internalField="uniform 101325",
    k_internalField="uniform 0.001",
    epsilon_internalField="uniform 1e-5",
    validate="warn",
)

# Top-level lists only: this is how Manager discovers the sweep parameters.
# All of them must have the same length (E-SWP-01).
T_Supply = [289, 291, 293, 295, 297, 299]
V_Supply = [-0.8, -1.0, -1.2, -1.4, -1.6, -1.8]
T_Occupant = [304, 305, 306, 307, 308, 309]
T_Walls = [296, 297, 298, 299, 300, 301]

a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=T_Walls, name="Room")
b = nemos.Person_seated(x=1.9, z=1.5, theta=0, thickness=0.15,
                        T_Face=T_Occupant, name="Person_1")
c = nemos.Person_seated(x=1.0, z=1.5, theta=180, thickness=0.15,
                        T_Face=305, name="Person_2")
d = nemos.Dip_type_01(x=1.5, y=1.0, z=0.7, V_Flow=V_Supply, T_Flow=T_Supply,
                      name="Dip_1")
e = nemos.Table_circular(x=1.5, y=0.6, z=2.3, raio=0.30, T_Face=299, name="Table")

a.insert_ceiling_opening(x=0.6, z=2.4, d=0.12)
a.insert_ceiling_opening(x=2.4, z=2.4, d=0.12)
a.add([b, c, d, e])

mesh = nemos.Mesh(a, m2DMaxSize=0.25, m2DMinSize=0.05, m3DMaxSize=0.12,
                  m3DMinSize=0.005, fineness=2)
mesh.create_mesh(export=True)
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=8)

scripts = sim.build_machine_script()

with Timer("stress 05 total"):
    exit_code = nemos.main(scripts)

if preflight_only():
    # Manager already ran every generated script in preflight-only mode and
    # would have aborted the batch on the first invalid configuration.
    print(f"\nSTRESS RESULT: {len(scripts)} sweep configurations valid "
          "(preflight-only dry run, nothing was executed)")
    raise SystemExit(0 if exit_code == 0 else 1)

print("\n--- sweep summary " + "-" * 59)
failures = 0
for index in range(len(T_Supply)):
    sim_dir = CASE / f"SIM_{index}"
    facts = inspect_case(sim_dir)
    ok = bool(facts.get("iterations")) and not facts.get("empty_patches")
    failures += 0 if ok else 1
    print(f"  SIM_{index}: verdict={str(facts.get('verdict')):<15} "
          f"iters={str(facts.get('iterations')):<6} "
          f"cells={facts.get('cells')}  "
          f"patches={len(facts.get('patches') or {})}  "
          f"{'ok' if ok else 'PROBLEM'}")
print("-" * 78)

if exit_code != 0 or failures:
    print(f"STRESS RESULT: PROBLEMS FOUND "
          f"(queue exit={exit_code}, {failures} SIM with problems)")
    raise SystemExit(1)
print("STRESS RESULT: OK (all 6 simulations produced usable cases)")

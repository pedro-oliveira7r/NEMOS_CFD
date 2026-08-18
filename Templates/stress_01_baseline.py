"""Stress 01 - baseline: the smallest run that touches every stage.

Purpose: prove the whole Python -> SALOME -> OpenFOAM chain still works before
spending hours on the heavy runs. If this one fails, nothing below it matters.

Exercises: recording proxies, machine script generation, SALOME batch meshing,
ideasUnvToFoam + checkMesh, boundary rewriting, field generation, decomposePar,
mpirun, residual parsing, Gate A/B/C/D.

Expected cost: a few minutes of meshing, a few minutes of solving.

Run:  python Templates/stress_01_baseline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _stress_lib
from _stress_lib import Timer, banner, bootstrap, case_dir, report  # noqa: E402

bootstrap()  # puts src/ on sys.path
import Simulation as nemos  # noqa: E402

CASE = case_dir("01_baseline", fresh=True)

banner(
    "STRESS 01 - baseline",
    f"""One person, one ceiling diffuser, two openings, deliberately coarse mesh.
Case folder: {CASE}
Iterations : endTime/delta = 30/0.1 = 300""",
)

sim = nemos.Simulation(
    case_path=str(CASE),
    startTime=0,
    endTime=30,
    delta=0.1,
    writeInterval=100,
    parallel="Y",
    T_internalField="uniform 300",
    p_internalField="uniform 101325",
    k_internalField="uniform 0.001",
    epsilon_internalField="uniform 1e-5",
    # "warn" so advisory findings (a short run is deliberate here) do not stop
    # the chain: this script is stressing the workflow, not the guardrails.
    validate="warn",
)

a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=299, name="Room")
b = nemos.Person_seated(x=1.5, z=1.5, theta=0, thickness=0.15, T_Face=305, name="Person_1")
c = nemos.Dip_type_01(x=1.5, y=1.0, z=0.8, V_Flow=-1.2, T_Flow=292, name="Dip_1")
a.insert_ceiling_opening(x=0.6, z=2.4, d=0.12)
a.insert_ceiling_opening(x=2.4, z=2.4, d=0.12)
a.add([b, c])

mesh = nemos.Mesh(
    a,
    m2DMaxSize=0.25,
    m2DMinSize=0.05,
    m3DMaxSize=0.12,
    m3DMinSize=0.005,
    fineness=2,          # coarse on purpose: this run is about coverage, not accuracy
)
mesh.create_mesh(export=True)
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=8)

with Timer("stress 01 total"):
    nemos.run(sim)

# Person_1, Dip_1, inlet_Dip_1, outlet, wall
raise SystemExit(report(CASE, expect_patches=5, expect_inlets=1))

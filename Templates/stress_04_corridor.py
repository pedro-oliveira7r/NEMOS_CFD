"""Stress 04 - corridor: an extreme room aspect ratio.

Purpose: every other case in this repo is roughly cubic. This one is 10 m long
and 2 m wide, which breaks several assumptions that are invisible in a cube.

What it stresses
  * The decomposition. decomposeParDict is hardcoded to `n (1 4 1)`, i.e. four
    slices along Y - the VERTICAL axis. In a 2.4 m tall corridor that means
    four 0.6 m thick horizontal slabs stacked across a 10 m long domain: a poor
    split with a large interface area, and the buoyant plume crosses every
    processor boundary. Watch the solver time against stress 01.
  * The face-classification heuristic. GeoMesh calls a face an outlet when it
    lies on the ceiling or floor AND its area is below
    Room.area = 0.8 * (the two smallest room dimensions) = 0.8 * 2.0 * 2.4
    = 3.84 m2 here. The end walls are 2.0 x 2.4 = 4.8 m2, only 25 % above that
    threshold - the tightest margin any realistic room gives.
  * Long thin cells and the resulting non-orthogonality, reported by Gate B.
  * Two diffusers 3 m apart, so the room is genuinely under-ventilated at the
    ends - a physically hard case for the pressure equation.

Expected cost: moderate meshing, slow solve relative to the cell count.

Run:  python Templates/stress_04_corridor.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import Timer, banner, bootstrap, case_dir, report  # noqa: E402

bootstrap()
import Simulation as nemos  # noqa: E402

CASE = case_dir("04_corridor", fresh=True)

DX, DY, DZ = 10.0, 2.4, 2.0
threshold = 0.8 * sorted((DX, DY, DZ))[0] * sorted((DX, DY, DZ))[1]

banner(
    "STRESS 04 - corridor",
    f"""Room       : {DX} x {DY} x {DZ} m  (aspect ratio {DX / DZ:.1f}:1)
Outlet area threshold (Room.area) : {threshold:.2f} m2
End wall area                     : {DZ * DY:.2f} m2  <- must stay above it
Decomposition: 4 slabs along Y, each {DY / 4:.2f} m thick, across a {DX} m domain
Case folder: {CASE}""",
)

sim = nemos.Simulation(
    case_path=str(CASE),
    startTime=0,
    endTime=30,
    delta=0.1,
    writeInterval=100,
    parallel="Y",
    T_internalField="uniform 297",
    p_internalField="uniform 101325",
    k_internalField="uniform 0.001",
    epsilon_internalField="uniform 1e-5",
    validate="warn",
)

a = nemos.Room(dx=DX, dy=DY, dz=DZ, T_Face=296, name="Room")

# Occupants strung along the corridor, all on the centre line.
p1 = nemos.Person_seated(x=2.0, z=1.0, theta=90, thickness=0.15, T_Face=305, name="Person_1")
p2 = nemos.Person_seated(x=5.0, z=1.0, theta=90, thickness=0.15, T_Face=306, name="Person_2")
p3 = nemos.Person_standing(x=8.0, z=1.0, theta=270, T_Face=307, name="Person_3")

# Short tubes: the ceiling is only 2.4 m up, so a 1.2 m diffuser would reach
# head height. These end at 2.4 - 0.07 - 0.5 = 1.83 m.
d1 = nemos.Dip_type_01(x=3.5, y=0.50, z=1.0, V_Flow=-1.1, T_Flow=291, name="Dip_1")
d2 = nemos.Dip_type_01(x=6.5, y=0.50, z=1.0, V_Flow=-1.1, T_Flow=291, name="Dip_2")

# Extract at the two far ends, as far from the supplies as the room allows.
a.insert_ceiling_opening(x=1.0, z=1.0, d=0.12)
a.insert_ceiling_opening(x=9.0, z=1.0, d=0.12)

a.add([p1, p2, p3, d1, d2])

mesh = nemos.Mesh(
    a,
    m2DMaxSize=0.25,
    m2DMinSize=0.04,
    m3DMaxSize=0.12,
    m3DMinSize=0.003,
    fineness=3,
)
mesh.create_mesh(export=True)
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=10)

with Timer("stress 04 total"):
    nemos.run(sim)

# Person_1..3, Dip_1, Dip_2, inlet_Dip_1, inlet_Dip_2, outlet, wall
raise SystemExit(report(CASE, expect_patches=9, expect_inlets=2))

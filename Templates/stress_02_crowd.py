"""Stress 02 - crowd: every geometry class at once, many patches.

Purpose: push the parts of the pipeline whose cost grows with the number of
objects, and exercise every geometry class in a single case.

What it stresses
  * Room.create_faces_groups compares every face of every object against every
    face of the room. With 12 bodies that inner loop is the slowest part of
    meshing, and it is where face-group misdetection shows up.
  * All four diffuser types in one case. Dip_type_02 is the odd one out: it
    hangs 0.30 m below the ceiling instead of 0.07 m, so it is placed with a
    shorter tube to keep clear of the seated occupants.
  * Both person classes and both table classes.
  * 18 patches through BoundaryManager and 8 field files, i.e. 144 per-patch
    boundary entries written and then checked by Gate B2.

Expected cost: long meshing stage (the face matching dominates), short solve.

Run:  python Templates/stress_02_crowd.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import Timer, banner, bootstrap, case_dir, report  # noqa: E402

bootstrap()
import Simulation as nemos  # noqa: E402

CASE = case_dir("02_crowd", fresh=True)

banner(
    "STRESS 02 - crowd",
    f"""6 occupants + 4 diffusers (types 00/01/02/03) + 2 tables + 4 openings
in a 6.0 x 3.0 x 6.0 m room. 12 bodies -> 18 mesh patches.
Case folder: {CASE}""",
)

sim = nemos.Simulation(
    case_path=str(CASE),
    startTime=0,
    endTime=20,
    delta=0.1,
    writeInterval=100,
    parallel="Y",
    T_internalField="uniform 299",
    p_internalField="uniform 101325",
    k_internalField="uniform 0.001",
    epsilon_internalField="uniform 1e-5",
    validate="warn",
)

a = nemos.Room(dx=6.0, dy=3.0, dz=6.0, T_Face=298, name="Room")

# Occupants on a 3 x 2 grid, 1.8 m apart in x and 3.6 m in z. A seated body
# needs roughly 0.55 m of clearance, so this leaves plenty of margin.
p1 = nemos.Person_seated(x=1.2, z=1.2, theta=0, thickness=0.16, T_Face=305, name="Person_1")
p2 = nemos.Person_seated(x=3.0, z=1.2, theta=45, thickness=0.16, T_Face=304, name="Person_2")
p3 = nemos.Person_seated(x=4.8, z=1.2, theta=90, thickness=0.16, T_Face=306, name="Person_3")
p4 = nemos.Person_seated(x=1.2, z=4.8, theta=180, thickness=0.16, T_Face=305, name="Person_4")
p5 = nemos.Person_standing(x=3.0, z=4.8, theta=270, T_Face=307, name="Person_5")
p6 = nemos.Person_standing(x=4.8, z=4.8, theta=135, T_Face=306, name="Person_6")

# One of each diffuser type. Type 02 sits 0.30 m below the ceiling, so its tube
# is shortened to 0.9 m to keep its outlet above head height.
d1 = nemos.Dip_type_00(x=1.5, y=1.10, z=3.0, V_Flow=-1.0, T_Flow=292, name="Dip_00")
d2 = nemos.Dip_type_01(x=3.0, y=1.10, z=2.0, V_Flow=-1.2, T_Flow=291, name="Dip_01")
d3 = nemos.Dip_type_02(x=3.0, y=0.90, z=4.0, V_Flow=-1.1, T_Flow=293, name="Dip_02")
d4 = nemos.Dip_type_03(x=4.5, y=1.10, z=3.0, V_Flow=-1.3, T_Flow=292, name="Dip_03")

t1 = nemos.Table_circular(x=2.1, y=0.60, z=3.0, raio=0.35, T_Face=299, name="Table_round")
t2 = nemos.Table_retangular(x=3.9, y=0.60, z=3.0, dx=0.7, dz=0.7, T_Face=299,
                            name="Table_rect")

for x, z in ((1.0, 1.0), (5.0, 1.0), (1.0, 5.0), (5.0, 5.0)):
    a.insert_ceiling_opening(x=x, z=z, d=0.15)

a.add([p1, p2, p3, p4, p5, p6, d1, d2, d3, d4, t1, t2])

mesh = nemos.Mesh(
    a,
    m2DMaxSize=0.30,
    m2DMinSize=0.05,
    m3DMaxSize=0.15,
    m3DMinSize=0.005,
    fineness=2,
)
mesh.create_mesh(export=True)
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=10)

with Timer("stress 02 total"):
    nemos.run(sim)

# 12 bodies + 4 inlet_* + outlet + wall
raise SystemExit(report(CASE, expect_patches=18, expect_inlets=4))

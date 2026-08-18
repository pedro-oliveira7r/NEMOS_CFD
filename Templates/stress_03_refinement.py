"""Stress 03 - refinement: drive the mesh toward the memory and time ceiling.

Purpose: find where NETGEN, ideasUnvToFoam and decomposePar start to hurt.
The solver stage is kept deliberately short: this run is about producing and
handling a large mesh, not about converging it.

What it stresses
  * NETGEN with viscous layers at a cell size where the layer stack (0.030 m on
    walls, 0.010 m on people, 0.0025 m on diffusers) is comparable to the bulk
    cell size. This is where layer collapse and sliver cells appear.
  * ideasUnvToFoam on a large .unv file, and the conversion's peak memory.
  * decomposePar with the hardcoded 4 subdomains on a big cell count.
  * Gate B's checkMesh parsing against a mesh that genuinely has quality
    warnings to report.

Levels (set NEMOS_STRESS_LEVEL):
    coarse  m3DMaxSize=0.10   a few hundred thousand cells
    medium  m3DMaxSize=0.06   roughly 1 million          (default)
    fine    m3DMaxSize=0.04   several million - expect a long meshing stage
                              and several GB of RAM

Run:  python Templates/stress_03_refinement.py
      NEMOS_STRESS_LEVEL=fine python Templates/stress_03_refinement.py
"""

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import Timer, banner, bootstrap, case_dir, report  # noqa: E402

bootstrap()
import Simulation as nemos  # noqa: E402

LEVELS = {
    "coarse": dict(m2DMaxSize=0.20, m2DMinSize=0.03, m3DMaxSize=0.10,
                   m3DMinSize=0.002, fineness=3),
    "medium": dict(m2DMaxSize=0.12, m2DMinSize=0.02, m3DMaxSize=0.06,
                   m3DMinSize=0.001, fineness=3),
    "fine":   dict(m2DMaxSize=0.08, m2DMinSize=0.01, m3DMaxSize=0.04,
                   m3DMinSize=0.001, fineness=4),
}

LEVEL = os.environ.get("NEMOS_STRESS_LEVEL", "medium").strip().lower()
if LEVEL not in LEVELS:
    raise SystemExit(
        f"NEMOS_STRESS_LEVEL={LEVEL!r} is not valid. "
        f"Choose one of: {', '.join(LEVELS)}."
    )
PARAMS = LEVELS[LEVEL]

CASE = case_dir(f"03_refinement_{LEVEL}", fresh=True)

# Same crude estimate the W-MSH-04 check uses, so the two can be compared.
ROOM = (3.0, 3.0, 3.0)
estimate = 6 * math.sqrt(2) * (ROOM[0] * ROOM[1] * ROOM[2]) / PARAMS["m3DMaxSize"] ** 3

banner(
    "STRESS 03 - refinement",
    f"""Level      : {LEVEL}  (m3DMaxSize={PARAMS['m3DMaxSize']}, fineness={PARAMS['fineness']})
Estimate   : ~{estimate / 1e6:.1f} million cells before local refinement
Case folder: {CASE}
Solver     : 50 iterations only - this run is about the mesh.""",
)

sim = nemos.Simulation(
    case_path=str(CASE),
    startTime=0,
    endTime=5,
    delta=0.1,
    writeInterval=50,
    parallel="Y",
    T_internalField="uniform 300",
    p_internalField="uniform 101325",
    k_internalField="uniform 0.001",
    epsilon_internalField="uniform 1e-5",
    validate="warn",
)

a = nemos.Room(dx=ROOM[0], dy=ROOM[1], dz=ROOM[2], T_Face=298, name="Room")
b = nemos.Person_seated(x=1.5, z=1.8, theta=0, thickness=0.15, T_Face=306, name="Person_1")
c = nemos.Dip_type_01(x=1.5, y=1.0, z=0.9, V_Flow=-1.4, T_Flow=291, name="Dip_1")
a.insert_ceiling_opening(x=0.7, z=2.3, d=0.12)
a.insert_ceiling_opening(x=2.3, z=2.3, d=0.12)
a.add([b, c])

mesh = nemos.Mesh(a, **PARAMS)
mesh.create_mesh(export=True)
# Two metrics: aspect ratio catches the viscous-layer slivers, and the volume
# check catches cells that collapsed where the layers met.
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=20)
mesh.check_quality("Volume3D", element_type="VOLUME", comparison="<", threshold=1e-9)

with Timer(f"stress 03 ({LEVEL}) total"):
    nemos.run(sim)

raise SystemExit(report(CASE, expect_patches=5, expect_inlets=1))

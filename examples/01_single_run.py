"""
01 - Single simulation run
==========================

The smallest complete NEMOS pipeline: define a 3x3x3 m room with two seated
people, two air diffusers and a circular table, mesh it in SALOME, build the
OpenFOAM case and run the solver.

Demonstrates : Simulation (recording mode), Room, Person_seated, Dip_type_01,
               Table_circular, ceiling openings, Mesh, mesh quality check
Runtime      : ~15-40 min (meshing dominates; endTime=20 iterations)
Produces     : cases/01_single_run/ with Mesh_1.unv, 0/, constant/, system/,
               residuals.png, log.simulation and a .nemos_done marker

Re-running this script is safe: every stage is skipped if its artifact already
exists, and the solver continues from the last written timestep.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Simulation as nemos

# Where the OpenFOAM case is written. Change this to any absolute path you
# like -- it must be on a Windows drive reachable from WSL (C:, D:, ...).
CASE_PATH = Path(__file__).resolve().parents[1] / "cases" / "01_single_run"

sim = nemos.Simulation(
	case_path=str(CASE_PATH),
	startTime=0,
	endTime=20,
	delta=0.1,
	writeInterval=3,
	parallel="Y",
	T_internalField="uniform 300",
	p_internalField="uniform 101322",
	k_internalField="uniform 0.001",
	epsilon_internalField="uniform 1e-5"
)
a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=300, name = "Room")
b = nemos.Person_seated(x=2.025, z=1.5, theta=0, thickness=0.15, T_Face=304, name = "Person_1")
c = nemos.Person_seated(x=0.975, z=1.5, theta=180, thickness=0.15, T_Face=305, name = "Person_2")
d = nemos.Dip_type_01(x=2.025, y=1.0, z=1.5, V_Flow=-1.2, T_Flow=291, T_Face=293, name = "Dip_1")
e = nemos.Dip_type_01(x=0.975, y=1.2, z=1.5, V_Flow=-1.2, T_Flow=293, name = "Dip_2")
f = nemos.Table_circular(x=1.5, y=0.6, z=1.5, T_Face=300, name = "Table")
a.insert_ceiling_opening(x=0.5, z=2.5, d=0.1)
a.insert_ceiling_opening(x=2.5, z=0.5, d=0.1)
a.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)
a.insert_ceiling_opening(x=2.5, z=2.5, d=0.1)
a.add([b, c, d, e, f])
#a.add_box_volume(person=c, H_Tubo=1.2)
#a.add_box_volume(person=d)
#a.add_cilinder(salome_env=a, dip=e)
#a.add_cilinder(salome_env=a, dip=f)
mesh = nemos.Mesh(a, m2DMaxSize=0.2, m2DMinSize=0.02, m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
mesh.create_mesh(export=True)
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=5)

case = nemos.run(sim)

"""
05 - Reusing an existing mesh
=============================

Same geometry as example 01, but instead of meshing in SALOME it imports a
`Mesh_1.unv` produced by an earlier run. Meshing is by far the slowest stage,
so this is how you iterate on boundary conditions or solver settings without
paying for it every time.

The geometry objects are still declared: their `name=` values are what the
patch names in the imported mesh are matched against, and their inline values
(T_Face, T_Flow, V_Flow) still drive the boundary conditions. The geometry
must therefore match the mesh you are importing.

Demonstrates : Simulation.Import_mesh
Runtime      : solver only -- minutes to hours, no meshing
Produces     : cases/05_import_mesh/

Prerequisite : run example 01 first, or edit MESH_PATH below.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Simulation as nemos

CASE_PATH = Path(__file__).resolve().parents[1] / "cases" / "05_import_mesh"

# EDIT THIS if your mesh lives elsewhere. It must be a SALOME .unv file whose
# patch names match the object names declared below.
MESH_PATH = Path(__file__).resolve().parents[1] / "cases" / "01_single_run" / "Mesh_1.unv"

sim = nemos.Simulation(
	case_path=str(CASE_PATH),
	startTime=0,
	endTime=3,
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
d = nemos.Dip_type_01(x=2.025, y=1.0, z=1.5, V_Flow=-1.2, T_Flow=291, name = "Dip_1")
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

# Replaces the Mesh(...) + create_mesh(...) pair used in example 01: the .unv
# is copied into the case folder instead of being built by SALOME.
mesh = nemos.Simulation.Import_mesh(str(MESH_PATH))

case = nemos.run(sim)

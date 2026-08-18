"""
02 - Classroom
==============

A larger, more populated room: 4.5 x 3.0 x 4.0 m with four seated people, four
Dip_type_00 diffusers and four rectangular tables. Unlike example 01 it also
uses floor openings alongside the ceiling ones.

Demonstrates : Dip_type_00, Table_retangular, insert_floor_opening,
               a room with many objects
Runtime      : longer than 01 -- more geometry means a heavier mesh
Produces     : cases/02_classroom/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Simulation as nemos

CASE_PATH = Path(__file__).resolve().parents[1] / "cases" / "02_classroom"

sim = nemos.Simulation(
	case_path=str(CASE_PATH),
	startTime=0,
	endTime=3,
	delta=0.1,
	writeInterval=3,
	parallel="Y",
	T_internalField="uniform 301",
	p_internalField="uniform 101323",
	k_internalField="uniform 0.001",
	epsilon_internalField="uniform 1e-5"
)
a = nemos.Room(dx=4.5, dy=3.0, dz=4.0, T_Face=299, name = "Room")
b = nemos.Person_seated(x=1.0, z=1.0, thickness=0.15, T_Face=304, name = "Person_1")
c = nemos.Person_seated(x=1.0, z=3.0, thickness=0.15, T_Face=303, name = "Person_2")
d = nemos.Person_seated(x=3.0, z=1.0, thickness=0.15, T_Face=305, name = "Person_3")
e = nemos.Person_seated(x=3.0, z=3.0, thickness=0.15, T_Face=303, name = "Person_4")
f = nemos.Dip_type_00(x=1.0, z=1.0, y=0.65, V_Flow=-1.1, T_Flow=294, name = "Dip_1")
g = nemos.Dip_type_00(x=1.0, z=3.0, y=0.65, V_Flow=-1.1, T_Flow=294, name = "Dip_2")
h = nemos.Dip_type_00(x=3.0, z=1.0, y=0.65, V_Flow=-1.1, T_Flow=294, name = "Dip_3")
i = nemos.Dip_type_00(x=3.0, z=3.0, y=0.65, V_Flow=-1.1, T_Flow=294, name = "Dip_4")
j = nemos.Table_retangular(x=0.5, z=1.0, dz=1.0, T_Face=300, name = "Table_1")
k = nemos.Table_retangular(x=0.5, z=3.0, dz=1.0, T_Face=301, name = "Table_2")
l = nemos.Table_retangular(x=2.5, z=1.0, dz=1.0, T_Face=302, name = "Table_3")
m = nemos.Table_retangular(x=2.5, z=3.0, dz=1.0, T_Face=300, name = "Table_4")
a.insert_ceiling_opening(x=0.5, z=3.5, d=0.1)
a.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)
a.insert_ceiling_opening(x=3.0, z=0.5, d=0.1)
a.insert_ceiling_opening(x=3.0, z=3.5, d=0.1)
a.insert_floor_opening(x=0.5, z=3.5, d=0.1)
a.insert_floor_opening(x=0.5, z=0.5, d=0.1)
a.insert_floor_opening(x=3.0, z=0.5, d=0.1)
a.insert_floor_opening(x=3.0, z=3.5, d=0.1)
a.add([b, c, d, e, f, g, h, i, j, k, l, m])
mesh = nemos.Mesh(a, m2DMaxSize=0.2, m2DMinSize=0.02, m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
mesh.create_mesh(export=True)

case = nemos.run(sim)

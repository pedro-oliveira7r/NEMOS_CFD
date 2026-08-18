"""
03 - Parameter sweep: boundary conditions
=========================================

Runs FIVE simulations in sequence, varying only the boundary conditions. The
geometry and the mesh parameters are identical across all of them, so Manager
meshes once in SIM_0 and every later SIM imports that mesh -- a large saving.

Any top-level list in this script is treated as a sweep parameter: simulation
i uses element i of every list. All sweep lists must therefore have the SAME
length (5 here) and must not be empty.

Demonstrates : Manager, sweep lists, the shared-mesh optimisation
Runtime      : 5 simulations back to back -- expect hours
Produces     : cases/03_sweep_conditions/SIM_0 .. SIM_4, plus scripts/ and logs/

NOTE the different import: sweeps use Manager, not Simulation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import Manager as nemos

CASE_PATH = Path(__file__).resolve().parents[1] / "cases" / "03_sweep_conditions"

sim = nemos.Simulation(
	script_path=__file__,
	case_path=str(CASE_PATH),
	startTime=0,
	endTime=5,
	delta=0.1,
	writeInterval=3,
	parallel="Y",
	T_internalField="uniform 300",
	p_internalField="uniform 101322",
	k_internalField="uniform 0.001",
	epsilon_internalField="uniform 1e-5"
)

# --- Sweep parameters: one value per simulation, all lists the same length ---
T_Room_Face = [299, 300, 301, 302, 303]
T_Flow = [291, 293, 294, 295, 296]
V_Flow = [-1.0, -1.1, -1.3, -1.4, -1.5]
T_Person_Face = [304, 305, 306, 307, 308]
T_Table_Face = [300, 301, 302, 303, 304]

# A sweep list may be used anywhere a scalar would be; mixing the two is fine
# (Person_2 and Dip_2 below keep constant values while their siblings vary).
a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=T_Room_Face, name = "Room")
b = nemos.Person_seated(x=2.025, z=1.5, theta=0, thickness=0.15, T_Face=T_Person_Face, name = "Person_1")
c = nemos.Person_seated(x=0.975, z=1.5, theta=180, thickness=0.15, T_Face=305, name = "Person_2")
d = nemos.Dip_type_01(x=2.025, y=1.0, z=1.5, V_Flow=V_Flow, T_Flow=T_Flow, name = "Dip_1")
e = nemos.Dip_type_01(x=0.975, y=1.2, z=1.5, V_Flow=-1.2, T_Flow=T_Flow, name = "Dip_2")
f = nemos.Table_circular(x=1.5, y=0.6, z=1.5, T_Face=T_Table_Face, name = "Table")
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

scripts = sim.build_machine_script()
nemos.main(scripts)

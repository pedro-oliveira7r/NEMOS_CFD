import Auto_8 as nemos

sim = nemos.Simulation(
	case_path=r"C:\Users\pedro\Desktop\TCC1\TESTS\script_H_new",
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

mesh = nemos.Simulation.Import_mesh(r"C:\Users\pedro\Desktop\TCC1\TESTS\script_H\Mesh_1.unv")

case, mesher, boundary_manager, runner = nemos.setup_workflow(sim) 

case = nemos.run(sim)
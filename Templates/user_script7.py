import Simulation.Auto_8 as nemos

sim = nemos.Simulation(
	case_path=r"C:\Users\pedro\Desktop\TCC1\Sim_000",
	startTime=0,
	endTime=2000,
	delta=0.1,
	writeInterval=200,
	parallel="Y",
	T_internalField="uniform 300",
	p_internalField="uniform 101325",
	k_internalField="uniform 0.001",
	epsilon_internalField="uniform 1e-5",
	U_internalField="uniform (0 -1 0)",
)
a = nemos.Salome_Env()
b = nemos.Room(salome_env=a,dx=3.0, dy=3.0, dz=3.0, T_Face=300, name = "Room")
c = nemos.Person_seated(salome_env=a,x=2.025, z=1.5, theta=0, thickness=0.15, T_Face=304, name = "Person_1")
d = nemos.Person_seated(salome_env=a,x=0.975, z=1.5, theta=180, thickness=0.15, T_Face=303, name = "Person_2")
e = nemos.Dip_type_00(salome_env=a,x=2.025, y=1.0, z=1.5, V_Flow=-1.0, T_Flow=293, name = "Dip_1")
f = nemos.Dip_type_00(salome_env=a,x=0.975, y=1.2, z=1.5, V_Flow=-1.0, T_Flow=293, name = "Dip_2")
g = nemos.Table_circular(salome_env=a,x=1.5, y=0.6, z=1.5, T_Face=300, name = "Table")
b.insert_ceiling_opening(x=0.5, z=2.5, d=0.1)
b.insert_ceiling_opening(x=2.5, z=0.5, d=0.1)
b.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)
b.insert_ceiling_opening(x=2.5, z=2.5, d=0.1)
b.add([c, d, e, f, g])
b.create_faces_groups()
#b.add_box_volume(person=c, H_Tubo=1.2)
#b.add_box_volume(person=d)
#b.add_cilinder(salome_env=a, dip=e)
#b.add_cilinder(salome_env=a, dip=f)
nemos.salome_update()
mesh = nemos.Mesh(b, m2DMaxSize=0.2, m2DMinSize=0.02, m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
mesh.create_mesh(export=True, caminho=r"C:\Users\pedro\Desktop\TCC1\Sim_000\Mesh_1.unv")
sim.build_machine_script()

case, mesher, boundary_manager, runner = nemos.setup_workflow(sim)

mesher.executar_batch()
runner.preparar_malha()
boundary_manager.editar_boundary()
boundary_manager.generate_all_fields()
runner.rodar_simulacao()
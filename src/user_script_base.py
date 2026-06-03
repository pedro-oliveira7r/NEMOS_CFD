import Auto_8 as nemos

sim = nemos.Simulation(
	case_path=r"C:\Users\pedro\Desktop\TCC1\TESTS\script_base",
	startTime=0,
	endTime=3,
	delta=0.1,
	writeInterval=3,
	parallel="Y",
	T_internalField="uniform 299",
	p_internalField="uniform 101321",
	k_internalField="uniform 0.001",
	epsilon_internalField="uniform 1e-5"
)
a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=301, name = "Room")
b = nemos.Person_seated(x=1.5, z=1.5, theta=0, thickness=0.15, T_Face=304, name = "Person_1")
c = nemos.Dip_type_01(x=1.5, y=1.0, z=1.5, V_Flow=-1.1, T_Flow=293, name = "Dip_1")
d = nemos.Table_retangular(x=1.0, y=0.6, z=1.5, T_Face=300, name = "Table")
a.insert_ceiling_opening(x=0.5, z=2.5, d=0.1)
a.insert_ceiling_opening(x=2.5, z=0.5, d=0.1)
a.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)
a.insert_ceiling_opening(x=2.5, z=2.5, d=0.1)
a.add([b, c, d])
#a.add_box_volume(person=c, H_Tubo=1.2)
#a.add_box_volume(person=d)
#a.add_cilinder(salome_env=a, dip=e)
#a.add_cilinder(salome_env=a, dip=f)
mesh = nemos.Mesh(a, m2DMaxSize=0.2, m2DMinSize=0.02, m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
mesh.create_mesh(export=True, caminho=r"C:\Users\pedro\Desktop\TCC1\TESTS\script_base\Mesh_1.unv")

sim.build_machine_script()

case, mesher, boundary_manager, runner = nemos.setup_workflow(sim)

mesher.executar_batch()
runner.preparar_malha()
boundary_manager.editar_boundary()
boundary_manager.generate_all_fields()
runner.rodar_simulacao()
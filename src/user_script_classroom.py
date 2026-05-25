import Auto_7 as nemos

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
	epsilon_internalField="uniform 1e-5"
)
a = nemos.Room(dx=4.5, dy=3.0, dz=4.0, T_Face=300, name = "Room")
b = nemos.Person_seated(x=1.0, z=1.0, thickness=0.15, T_Face=304, name = "Person_1")
c = nemos.Person_seated(x=1.0, z=3.0, thickness=0.15, T_Face=303, name = "Person_2")
d = nemos.Person_seated(x=3.0, z=1.0, thickness=0.15, T_Face=303, name = "Person_3")
e = nemos.Person_seated(x=3.0, z=3.0, thickness=0.15, T_Face=303, name = "Person_4")
f = nemos.Dip_type_00(x=1.0, z=1.0, y=0.65, V_Flow=-1.0, T_Flow=293, name = "Dip_1")
g = nemos.Dip_type_00(x=1.0, z=3.0, y=0.65, V_Flow=-1.0, T_Flow=293, name = "Dip_2")
h = nemos.Dip_type_00(x=3.0, z=1.0, y=0.65, V_Flow=-1.0, T_Flow=293, name = "Dip_3")
i = nemos.Dip_type_00(x=3.0, z=3.0, y=0.65, V_Flow=-1.0, T_Flow=293, name = "Dip_4")
j = nemos.Table_retangular(x=0.5, z=1.0, dz=1.0, T_Face=300, name = "Table_1")
k = nemos.Table_retangular(x=0.5, z=3.0, dz=1.0, T_Face=300, name = "Table_2")
l = nemos.Table_retangular(x=2.5, z=1.0, dz=1.0, T_Face=300, name = "Table_3")
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
mesh.create_mesh(export=True, caminho=r"C:\Users\pedro\Desktop\TCC1\Sim_000\Mesh_1.unv")

sim.build_machine_script()

case, mesher, boundary_manager, runner = nemos.setup_workflow(sim)

mesher.executar_batch()
runner.preparar_malha()
boundary_manager.editar_boundary()
boundary_manager.generate_all_fields()
runner.rodar_simulacao()
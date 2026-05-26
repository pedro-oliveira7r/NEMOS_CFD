from simulation_analisys import Simulation, SimulationAnalysis, Regularization

# caminho para a pasta do caso OpenFOAM (onde esta o caso.foam)
case_dir = r"C:\Users\pedro\Desktop\TCC1\SIM_C2"

output_dir = rf"{case_dir}\analysis_output"

sim = Simulation(case_dir)  # usa o ultimo time step automaticamente

# listar e acessar fronteiras
boundaries = sim.list_boundaries()
if boundaries:
	first_boundary = sim.get_boundary(boundaries[0])

# leitura direta de probes (T e U)
# probe_path pode ser relativo a postProcessing, por exemplo: "probes/0"
#probe_path = "probes"
#try:
#	t_u, u_values = sim.read_probe(probe_path, field="U")
#	t_t, t_values = sim.read_probe(probe_path, field="T")
#except FileNotFoundError:
#	t_u, u_values, t_t, t_values = None, None, None, None

# leitura conjunta de U e T
#try:
#	t_u2, u2, t_t2, t2 = sim.read_U_T(probe_path)
#except FileNotFoundError:
#	t_u2, u2, t_t2, t2 = None, None, None, None

analysis = SimulationAnalysis(sim)

# plot de campos no plano (T e U)
analysis.plot(parameter="T", out_dir=output_dir, plane="xy")
analysis.plot(parameter="U", out_dir=output_dir, plane="xy")

# probes RMS e instantaneos (usam T e U juntos)
#try:
#	t_u_rms, u_rms, t_t_rms, t_rms = analysis.read_U_T_rms_probe(probe_path)
#	analysis.plot_UT_rms(probe_path)
#	analysis.plot_UT_instant(probe_path)
#except FileNotFoundError:
#	t_u_rms, u_rms, t_t_rms, t_rms = None, None, None, None

reg = Regularization(sim)

# regularizacao 2D e visualizacao/salvamento (T e U)
df2d, plane2d = reg.reg2D(out_dir=output_dir, n1=500, n2=500, plane="xy")
reg.plot_2D(plane2d, scalar="T")
reg.plot_2D(plane2d, scalar="U")
reg.save_plot_2D_reg(plane2d, scalar="T", filename="reg2D_T.png", out_dir=output_dir)
reg.save_plot_2D_reg(plane2d, scalar="U", filename="reg2D_U.png", out_dir=output_dir)

# regularizacao 3D e visualizacao/salvamento (T e U)
df3d, grid3d = reg.reg3D(nx=50, ny=50, nz=50, out_dir=output_dir)
reg.plot_reg_3D(grid3d, scalar="T")
reg.plot_reg_3D(grid3d, scalar="U")
reg.save_plot_3D_reg(grid3d, scalar="T", filename="reg3D_T.png", out_dir=output_dir)
reg.save_plot_3D_reg(grid3d, scalar="U", filename="reg3D_U.png", out_dir=output_dir)
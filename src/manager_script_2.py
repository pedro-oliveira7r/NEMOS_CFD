import Manager as nemos
from sim_analysis_v3 import Simulation, SimulationAnalysis, Regularization
import os
import time
from pathlib import Path

sim = nemos.Simulation(
	script_path=__file__,
	case_path=r"C:\Users\pedro\Desktop\TCC1\TESTS",
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

T_Room_Face = [299, 300, 301, 302, 303]
T_Flow = [291, 293, 294, 295, 296]
V_Flow = [-1.0, -1.1, -1.3, -1.4, -1.5]
T_Person_Face = [304, 305, 306, 307, 308]
T_Table_Face = [300, 301, 302, 303, 304]

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
mesh.create_mesh(export=True, caminho=r"C:\Users\pedro\Desktop\TCC1\TESTS\Mesh_1.unv")

scripts = sim.build_machine_script()
nemos.main(scripts)

case_path = r"C:\Users\pedro\Desktop\TCC1\TESTS"
output_dir = rf"{case_path}\analysis_output"

os.makedirs(output_dir, exist_ok=True)

try:
	timestep_interval = float(input("Enter the timestep interval for analysis (e.g. 20, 40, 60): "))
	if timestep_interval <= 0:
		raise ValueError("timestep interval must be positive")
except ValueError as e:
	print(f"Invalid interval: {e}")
	print("Using default interval of 20.0")
	timestep_interval = 20.0

processed_timesteps = set()
check_interval = 5

print("\nStarting post-processing loop...")
print(f"Case path: {case_path}")
print(f"Output dir: {output_dir}")
print(f"TimeStep interval: {timestep_interval}")

try:
	while True:
		available_timesteps = []
		case_folder = Path(case_path)

		if case_folder.exists():
			for item in case_folder.iterdir():
				if item.is_dir():
					try:
						available_timesteps.append(float(item.name))
					except ValueError:
						pass

		available_timesteps.sort()

		if not available_timesteps:
			print(f"[{time.strftime('%H:%M:%S')}] Waiting for timeSteps...", end="\r")
			time.sleep(check_interval)
			continue

		for timestep in available_timesteps:
			is_interval_match = abs(timestep - round(timestep / timestep_interval) * timestep_interval) < 1e-6

			if not is_interval_match or timestep in processed_timesteps:
				continue

			print(f"\n[{time.strftime('%H:%M:%S')}] Processing timeStep {timestep}")

			try:
				sim = Simulation(case_path, time_step=timestep)
				analysis = SimulationAnalysis(sim)
				analysis.plot(parameter="T", out_dir=output_dir, plane="xy")
				analysis.plot(parameter="U", out_dir=output_dir, plane="xy")

				reg = Regularization(sim)
				_, plane2d = reg.reg2D(out_dir=output_dir, n1=500, n2=500, plane="xy")
				reg.plot_2D(plane2d, scalar="T")
				reg.plot_2D(plane2d, scalar="U")

				ts_suffix = str(timestep).replace(".", "_")
				reg.save_plot_2D_reg(plane2d, scalar="T", filename=f"reg2D_T_ts{ts_suffix}.png", out_dir=output_dir)
				reg.save_plot_2D_reg(plane2d, scalar="U", filename=f"reg2D_U_ts{ts_suffix}.png", out_dir=output_dir)

				processed_timesteps.add(timestep)
				print(f"[{time.strftime('%H:%M:%S')}] Finished timeStep {timestep}")
			except Exception as e:
				print(f"[{time.strftime('%H:%M:%S')}] Analysis failed for timeStep {timestep}: {e}")

		time.sleep(check_interval)

except KeyboardInterrupt:
	print("\nPost-processing loop stopped by user")
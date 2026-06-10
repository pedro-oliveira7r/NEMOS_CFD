import Manager as nemos
from sim_analysis_v3 import Simulation, SimulationAnalysis, Regularization
import time
import os
from pathlib import Path


def get_available_timesteps(case_path):
    """
    Get all available timeStep directories in the case folder.
    OpenFOAM case directories are named with their time values (0, 20, 40, etc).
    """
    case_path = Path(case_path)
    timesteps = []
    
    if not case_path.exists():
        return timesteps
    
    for item in case_path.iterdir():
        if item.is_dir():
            try:
                # Try to convert directory name to float (timeStep value)
                timestep = float(item.name)
                timesteps.append(timestep)
            except (ValueError, AttributeError):
                # Skip directories that are not timeSteps (e.g., constant, system, 0)
                continue
    
    return sorted(timesteps)


def run_analysis(case_path, output_dir, timestep):
    """
    Run post-processing analysis for a given timeStep.
    Returns True if successful, False otherwise.
    """
    try:
        # Load simulation data (uses the latest timeStep by default)
        sim = Simulation(case_path)
        
        # List boundaries
        boundaries = sim.list_boundaries()
        if boundaries:
            first_boundary = sim.get_boundary(boundaries[0])
        
        # Analysis and plotting
        analysis = SimulationAnalysis(sim)
        analysis.plot(parameter="T", out_dir=output_dir, plane="xy")
        analysis.plot(parameter="U", out_dir=output_dir, plane="xy")
        
        # Regularization and saving
        reg = Regularization(sim)
        df2d, plane2d = reg.reg2D(out_dir=output_dir, n1=500, n2=500, plane="xy")
        reg.plot_2D(plane2d, scalar="T")
        reg.plot_2D(plane2d, scalar="U")
        
        # Save with timeStep identifier
        ts_suffix = f"_ts{timestep:.1f}" if timestep != int(timestep) else f"_ts{int(timestep)}"
        reg.save_plot_2D_reg(plane2d, scalar="T", filename=f"reg2D_T{ts_suffix}.png", out_dir=output_dir)
        reg.save_plot_2D_reg(plane2d, scalar="U", filename=f"reg2D_U{ts_suffix}.png", out_dir=output_dir)
        
        return True
    except Exception as e:
        print(f"Error analyzing timeStep {timestep}: {e}")
        return False

# Caso Tipo 1: Apenas as condições de contorno variam

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

# ==================== POST-PROCESSING AND MONITORING ====================
# caminho para a pasta do caso OpenFOAM (onde esta o caso.foam)
case_path = r"C:\Users\pedro\Desktop\TCC1\TESTS"
output_dir = rf"{case_path}\analysis_output"

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# User input for timeStep interval
print("\n" + "="*70)
print("POST-PROCESSING MONITORING LOOP")
print("="*70)
try:
    timestep_interval = float(input("\nEnter the timeStep interval for analysis (e.g., 20, 40, 60): "))
    if timestep_interval <= 0:
        raise ValueError("TimeStep interval must be positive")
except ValueError as e:
    print(f"Invalid input: {e}")
    print("Using default interval of 20.0")
    timestep_interval = 20.0

# Monitoring variables
processed_timesteps = set()
last_analyzed_timestep = None
check_interval = 5  # Check for new timeSteps every 5 seconds

print(f"\nConfiguration:")
print(f"  Case path: {case_path}")
print(f"  Output directory: {output_dir}")
print(f"  TimeStep interval: {timestep_interval}")
print(f"  Check interval: {check_interval}s")
print(f"\nStarting monitoring loop (Ctrl+C to stop)...\n")

try:
    while True:
        # Get available timeSteps
        available_timesteps = get_available_timesteps(case_path)
        
        if not available_timesteps:
            print(f"[{time.strftime('%H:%M:%S')}] No timeSteps found yet in {case_path}")
            time.sleep(check_interval)
            continue
        
        # Check for new timeSteps that match the interval
        new_timestep_found = False
        for timestep in available_timesteps:
            # Check if this timeStep matches the interval (with tolerance for floating point)
            closest_interval_multiple = round(timestep / timestep_interval) * timestep_interval
            is_interval_match = abs(timestep - closest_interval_multiple) < 0.5
            
            if is_interval_match and timestep not in processed_timesteps:
                new_timestep_found = True
                print(f"\n[{time.strftime('%H:%M:%S')}] New timeStep detected: {timestep}")
                print(f"[{time.strftime('%H:%M:%S')}] Starting analysis...")
                
                # Run analysis
                if run_analysis(case_path, output_dir, timestep):
                    print(f"[{time.strftime('%H:%M:%S')}] ✓ Analysis completed for timeStep {timestep}")
                    processed_timesteps.add(timestep)
                    last_analyzed_timestep = timestep
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ✗ Analysis failed for timeStep {timestep}")
        
        if not new_timestep_found:
            latest_ts = available_timesteps[-1] if available_timesteps else "N/A"
            print(f"[{time.strftime('%H:%M:%S')}] Waiting for next timeStep (current: {latest_ts})...", end='\r')
        
        time.sleep(check_interval)

except KeyboardInterrupt:
    print(f"\n\n[{time.strftime('%H:%M:%S')}] Monitoring loop stopped by user")
    print(f"[{time.strftime('%H:%M:%S')}] TimeSteps analyzed: {sorted(processed_timesteps)}")
    print(f"[{time.strftime('%H:%M:%S')}] Last analyzed timeStep: {last_analyzed_timestep}")
    print("[INFO] Simulation may still be running in the background")

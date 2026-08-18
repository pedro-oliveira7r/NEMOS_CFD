"""
06 - Post-processing a finished case
====================================

Reads a completed OpenFOAM case and produces slice images, point samples and
regularised (structured-grid) exports.

Demonstrates : NEMOS_SimulationAnalysis.LoadSimulation, SimulationAnalysis,
               Regularization
Runtime      : minutes
Produces     : <case>/analysis/images/*.png and <case>/analysis/data/*.xlsx

Prerequisites
-------------
1. The case must have finished (a `.nemos_done` marker exists in its folder).
2. If it ran in PARALLEL, reconstruct the time directories first -- otherwise
   only `processor*/` folders exist and the reader sees no timestep past 0:
       wsl bash -c "source /usr/lib/openfoam/openfoam2312/etc/bashrc && \
                    cd /mnt/c/.../your_case && reconstructPar"
3. `caso.foam` must exist at the case root. NEMOS writes it automatically at
   setup; example 07 recreates it if missing.
4. Packages: pyvista, numpy, pandas, matplotlib, openpyxl (for .xlsx).

Usage
-----
    python examples/06_analysis.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import NEMOS_SimulationAnalysis as nemos

# =========================================================
# 0. CONFIGURATION
# =========================================================

# EDIT THIS: point at a case that has already finished running.
CASE_PATH = str(Path(__file__).resolve().parents[1] / "cases" / "01_single_run")

OUT_DIR = os.path.join(CASE_PATH, "analysis")
IMG_DIR = os.path.join(OUT_DIR, "images")
DATA_DIR = os.path.join(OUT_DIR, "data")

# Name of the probe folder inside <case>/postProcessing/
PROBE_NAME = "probes"

# Interactive plots (pv.Plotter.show / plt.show) block execution until the
# window is closed. Leave False for a fully unattended run.
SHOW_INTERACTIVE = False

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# =========================================================
# 1. LoadSimulation - reading the case
# =========================================================

# time_step=None -> loads the last written time.
# For a specific time: nemos.LoadSimulation(CASE_PATH, time_step=20.0)
sim = nemos.LoadSimulation(CASE_PATH)

print("\n===== CASE LOADED =====")
print(sim)                                    # __repr__
print("Available times    :", sim.available_times)
print("Active time        :", sim.time_step)
print("Boundaries         :", sim._list_boundaries())
print("Available fields   :", sim.internal_mesh.array_names)
print("Cells / points     :", sim.internal_mesh.n_cells,
      "/", sim.internal_mesh.n_points)
print("Bounds             :", sim.internal_mesh.bounds)

# Direct access to a specific patch (dict name -> pv.PolyData)
for patch_name, patch in list(sim.boundaries.items())[:3]:
    print(f"  patch '{patch_name}': {patch.n_cells} cells")

# ---------------------------------------------------------
# 1.1 Switching time step
# ---------------------------------------------------------
# CAUTION: SimulationAnalysis and Regularization capture the mesh at
# construction time. Do every time switch BEFORE instantiating them -- or
# re-instantiate the objects after each set_time().

if len(sim.available_times) > 1:

    sim.set_time(sim.available_times[-2])
    print(f"\nset_time -> {sim.time_step} "
          f"(mean T = {sim.internal_mesh['T'].mean():.3f} K)")

    sim.set_time(sim.available_times[-1])
    print(f"set_time -> {sim.time_step} "
          f"(mean T = {sim.internal_mesh['T'].mean():.3f} K)")


# Useful references, derived from the mesh itself
x_min, x_max, y_min, y_max, z_min, z_max = sim.internal_mesh.bounds

center = [
    (x_min + x_max) / 2,
    (y_min + y_max) / 2,
    (z_min + z_max) / 2,
]

T_field = sim.internal_mesh["T"]
CLIM_T = (float(T_field.min()), float(T_field.max()))


# =========================================================
# 2. SimulationAnalysis - slices, probes and point values
# =========================================================

analysis = nemos.SimulationAnalysis(sim)

# ---------------------------------------------------------
# 2.1 plot() - plane slice + PNG (2400x1800, jet colormap)
# ---------------------------------------------------------
# The file is named "<parameter>_<plane>_<time>.png".
# Vector fields become magnitudes (U -> U_mag), symmetric tensors become
# RMS (R -> R_rms) and TPrime2Mean becomes T_rms automatically.

print("\n===== SLICES (SimulationAnalysis.plot) =====")

# Scalar, automatic central plane (value=None)
analysis.plot("T", out_dir=IMG_DIR, plane="xy")

# Scalar with explicit plane and colour scale
analysis.plot("T", out_dir=IMG_DIR, plane="xz",
              value=center[1], clim=CLIM_T)

# Vector -> plotted as |U|
analysis.plot("U", out_dir=IMG_DIR, plane="yz", value=center[0])

# The remaining fields written by buoyantSimpleFoam
for parameter in ["p", "p_rgh", "k", "epsilon", "nut", "alphat"]:
    if parameter in sim.internal_mesh.array_names:
        analysis.plot(parameter, out_dir=IMG_DIR, plane="xy")

print(f"Images saved to: {IMG_DIR}")


# ---------------------------------------------------------
# 2.2 get_point_value() - sampling a point / region
# ---------------------------------------------------------
# Prints {mean, min, max, std, n_points, n_invalid, field}.
# Note: the function PRINTS the dictionary and returns None.

print("\n===== POINT VALUES (get_point_value) =====")

# Exact point (single-point interpolation)
print("Room centre, T:")
analysis.get_point_value(center, field="T")

# Sphere: mean T within a 15 cm radius around the point
print("Sphere r=0.15 m, T:")
analysis.get_point_value(center, geometric_type="sphere",
                         interpolation_radius=0.15, field="T")

# Plane: 0.5 m square centred on the point
print("Plane 0.5 m, T:")
analysis.get_point_value(center, geometric_type="plane",
                         interpolation_radius=0.5, field="T")

# Box: cube of side 2*r centred on the point
print("Box r=0.25 m, p:")
analysis.get_point_value(center, geometric_type="box",
                         interpolation_radius=0.25, field="p")

# Vector fields work too - the statistics are computed over all components
# lumped together (Ux, Uy and Uz in the same bag).
print("Sphere r=0.20 m, U (aggregated components):")
analysis.get_point_value(center, geometric_type="sphere",
                         interpolation_radius=0.20, field="U")

# =========================================================
# 3. Regularization - structured grid + export
# =========================================================
# Resamples OpenFOAM's unstructured mesh onto a regular grid, exports the
# table (X, Y, Z, T, Ux, Uy, Uz, U) and plots the result. Points outside the
# domain (inside the manikins, for instance) become NaN and are dropped from
# the DataFrame.

reg = nemos.Regularization(sim)

# ---------------------------------------------------------
# 3.1 reg2D - 2D grid on a plane
# ---------------------------------------------------------

print("\n===== 2D REGULARIZATION =====")

# Central XY plane -> saves Sim_points_2D_xy_t<time>.xlsx
df_xy, plane_xy = reg.reg2D(out_dir=DATA_DIR, n1=120, n2=120, plane="xy")
print(df_xy[["T", "U"]].describe())

# XZ plane at a specific height (e.g. head height)
df_xz, plane_xz = reg.reg2D(out_dir=DATA_DIR, n1=120, n2=120,
                            plane="xz", value=center[1])

# YZ plane
df_yz, plane_yz = reg.reg2D(out_dir=DATA_DIR, n1=100, n2=100,
                            plane="yz", value=center[0])

# PNG of the regularised plane (scalar or vector - U becomes U_mag on its own)
reg.save_plot_2D_reg(plane_xy, scalar="T", filename="reg2D_T_xy.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

reg.save_plot_2D_reg(plane_xy, scalar="U", filename="reg2D_U_xy.png",
                     out_dir=IMG_DIR)

reg.save_plot_2D_reg(plane_xz, scalar="T", filename="reg2D_T_xz.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

# Interactive version (pyvista window)
if SHOW_INTERACTIVE:
    reg.plot_2D(plane_xy, scalar="T", clim=CLIM_T)
    reg.plot_2D(plane_yz, scalar="U")


# ---------------------------------------------------------
# 3.2 reg3D - 3D grid over the whole volume
# ---------------------------------------------------------
# Mind nx*ny*nz: 60^3 = 216 thousand points is already heavy.

print("\n===== 3D REGULARIZATION =====")

df_3d, grid_3d = reg.reg3D(nx=50, ny=50, nz=50, out_dir=DATA_DIR)
print("Valid points in the volume:", len(df_3d))
print(df_3d[["T", "U"]].describe())

reg.save_plot_3D_reg(grid_3d, scalar="T", filename="reg3D_T.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

reg.save_plot_3D_reg(grid_3d, scalar="U", filename="reg3D_U.png",
                     out_dir=IMG_DIR)

if SHOW_INTERACTIVE:
    reg.plot_reg_3D(grid_3d, scalar="T", clim=CLIM_T)


# =========================================================
# 4. Comparing time steps (optional)
# =========================================================
# Because the analysis objects freeze the mesh, each time needs a fresh
# instance. Useful for tracking convergence of the temperature field.

print("\n===== TIME EVOLUTION =====")

for t in sim.available_times[-3:]:

    sim_t = nemos.LoadSimulation(CASE_PATH, time_step=t)
    analysis_t = nemos.SimulationAnalysis(sim_t)

    analysis_t.plot("T", out_dir=IMG_DIR, plane="xy", clim=CLIM_T)

    print(f"t = {t:>8} | mean T = {sim_t.internal_mesh['T'].mean():.3f} K")


print(f"\nAnalysis complete. Results in: {OUT_DIR}")

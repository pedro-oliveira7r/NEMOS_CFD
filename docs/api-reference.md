# API reference

Everything you can call from a user script. Signatures are as implemented in
[`src/GeoMesh.py`](../src/GeoMesh.py) (geometry) and
[`src/Simulation.py`](../src/Simulation.py) (driver).

> **Coordinate system: Y is up.** `dy` is the room height; `x` and `z` place
> things on the floor plane. Ceiling openings sit at `y = dy`, floor openings at
> `y = 0`. All lengths are metres, all temperatures kelvin.

> **Unrecognised keyword arguments are silently discarded.** `endtime=20` and
> `Thickness=0.15` raise nothing and do nothing. Check spelling here.

---

## `Simulation` — the driver

```python
import Simulation as nemos

sim = nemos.Simulation(case_path=r"C:\path\to\case", **config)
```

`case_path` must be an absolute Windows path on a drive WSL can reach via
`/mnt/`. The folder is created if missing.

### Configuration keyword arguments

Friendly aliases for the nested config. Anything omitted keeps its default.

| Keyword | Default | Effect |
|---|---|---|
| `startTime` | `0` | `controlDict.startTime` |
| `endTime` | `3500` | `controlDict.endTime` — iteration count for this steady solver |
| `deltaT` / `delta` | `0.1` | `controlDict.deltaT` |
| `writeInterval` | `200` | how often a time directory is written |
| `parallel` | `"N"` | `"Y"` runs `mpirun -np 4`; `"N"` runs serially |
| `plot_residuals` | `True` | live residual plot; **makes the solver run synchronously** |
| `T_internalField` / `T_Field` | `"uniform 300"` | initial temperature |
| `p_internalField` / `p_Field` | `"uniform 101325"` | initial pressure |
| `k_internalField` / `k_Field` | `"uniform 0.001"` | initial turbulent kinetic energy |
| `epsilon_internalField` / `epsilon_Field` | `"uniform 1e-5"` | initial dissipation |
| `U_internalField` / `U_Field` | `"uniform (0 -1 0)"` | initial velocity |

The four nested sections can also be passed wholesale as dicts:
`controlDict=`, `decomposeParDict=`, `fields=`, `monitoring=`.

### `Simulation.Import_mesh(mesh_path)`

Static method. Reuses an existing mesh instead of running SALOME. Replaces the
`Mesh(...)` + `create_mesh(...)` pair.

```python
mesh = nemos.Simulation.Import_mesh(r"C:\...\previous_case\Mesh_1.unv")
```

The file **must** be named `Mesh_1.unv`; passing a directory looks for
`Mesh_1.unv` inside it. Still declare the geometry objects — their names and
inline values are what the boundary conditions are built from.

---

## Module functions

| Function | Does |
|---|---|
| `nemos.run(sim, salome_exe=None, script_path=None)` | The whole pipeline. Idempotent — see [workflow.md](workflow.md) |
| `nemos.setup_workflow(sim, ...)` | Stage 1 only: build the case folder and dictionaries, without meshing or solving |
| `nemos.resume(case_path, salome_exe=None)` | Rebuild a `Simulation` from `.nemos_state.json` and re-enter `run()`. Requires `Mesh_1.unv` to exist |

`salome_exe` overrides the compiled-in SALOME path for that call.

---

## Geometry

All geometry classes take `name=` — **required**, and enforced. It becomes the
OpenFOAM patch name and the key the boundary conditions are looked up by.

### `Room`

```python
Room(dx=3.0, dy=3.0, dz=3.0, name="Room", T_Face=300)
```

| Argument | Default | Meaning |
|---|---|---|
| `dx`, `dz` | `3.0` | floor dimensions |
| `dy` | `3.0` | **height** |

#### `room.add(obj_list)`

Cuts every object in the list out of the room volume and registers its faces as
named patches. Call it once, after creating the objects and after any openings.

```python
room.add([person_1, person_2, dip_1, table])
```

#### `room.insert_ceiling_opening(x, z, d=0.025)` / `insert_floor_opening(x, z, d=0.025)`

Places a circular opening at `(x, dy, z)` or `(x, 0, z)`. `d` is passed to SALOME
as the circle's **radius**, so `d=0.1` gives a 0.2 m-wide opening. These become
the outlet patches, so a room with no openings has nowhere for air to leave.

Call these **before** `add()`.

#### `room.add_box_volume(...)` / `room.add_cilinder(...)`

```python
add_box_volume(x=1.5, z=1.5, theta=0, R_Tubo=0.1, R_Vol=0.33,
               H_Tubo=0.92, H_Vol=0.9, Filete=0.35, name='Box', person=None)

add_cilinder(salome_env=None, x=1.5, z=1.5, R_Tubo=0.05, R_Ponta=0.075,
             H_Tubo=1.2, H_Ponta=0.085, name='Box', dip=None)
```

Local mesh-refinement volumes placed around a person or a diffuser. Pass
`person=` or `dip=` to position them automatically. Commented out in the examples
— enable them when you need a finer mesh in the plume region.

### People

```python
Person_seated(x=1.5, z=1.5, theta=0, h=1.700, thickness=0.200,
              width=0.225, fillet_radius=0.030, name=..., T_Face=...)

Person_standing(x=1.0, z=1.5, theta=0, name=..., T_Face=...)
```

`theta` is the rotation in degrees about the vertical axis. `T_Face` sets the
skin-surface temperature in kelvin (a seated person is typically ~304 K).

### Diffusers (`Dip_type_00` … `Dip_type_03`)

```python
Dip_type_01(x=1.0, y=1.2, z=1.5, d=0.05, name=..., V_Flow=-1.2, T_Flow=291)
```

Identical signatures; they differ in the nozzle geometry generated inside SALOME.
All four hang from the ceiling, their outlet placed at `room.H - 0.07 - y` — so
**`y` is the drop below the ceiling**, not an absolute height.

| Argument | Meaning |
|---|---|
| `x`, `z` | position on the floor plane |
| `y` | how far the outlet sits below the ceiling |
| `d` | nozzle diameter parameter |
| `V_Flow` | inlet velocity, m/s. **Negative blows downward into the room** |
| `T_Flow` | supply air temperature, K |

Diffuser patches are classified as `inlet`.

### Tables

```python
Table_retangular(x=1.5, y=0.6, z=1.5, dx=0.6, dy=0.02, dz=0.6, name=..., T_Face=300)
Table_circular(x=1.5, y=0.6, z=1.5, raio=0.35, espessura=0.02, name=..., T_Face=300)
```

`y` is the tabletop height; `dy` / `espessura` is its thickness.

### Inline boundary-condition keywords

These are stripped from the geometry call and used to write the `0/` fields:

| Keyword | Applies to | Effect today |
|---|---|---|
| `T_Face` (or `T_face`) | room, people, tables | fixed wall temperature, K |
| `T_Flow` | diffusers | inlet air temperature, K |
| `V_Flow` | diffusers | inlet velocity, m/s |
| `metabolic_heat_W` | — | **accepted and ignored** |
| `emissivity` | — | **accepted and ignored** |
| `species_source` | — | **accepted and ignored** |
| `supply_T_C` | — | **accepted and ignored** |
| `supply_velocity_m_s` | — | **accepted and ignored** |
| `flow_profile` | — | **accepted and ignored** |
| `material` | — | **accepted and ignored** |

The bottom seven parse without complaint and then do nothing. Only the top three
reach OpenFOAM.

---

## Meshing

### `Mesh(room, ...)`

```python
Mesh(room, m2DMaxSize=0.2, m2DMinSize=0.02,
     m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
```

| Argument | Default | Meaning |
|---|---|---|
| `m2DMaxSize` / `m2DMinSize` | `0.2` / `0.02` | surface element size bounds, m |
| `m3DMaxSize` / `m3DMinSize` | `0.075` / `0.001` | volume element size bounds, m |
| `fineness` | `3` | NETGEN fineness: 3 = Fine, 4 = Very Fine |

### `mesh.create_mesh(K_mesh=1, export=False, caminho='')`

Computes the mesh. **`export=True` is required** — it is what makes NEMOS inject
the export path and write `<case>/Mesh_1.unv`. Without it SALOME meshes and then
throws the result away.

### `mesh.check_quality(name_metric, element_type, comparison, threshold, create_group=False)`

```python
mesh.check_quality("AspectRatio", element_type="FACE", comparison=">", threshold=5)
```

| Argument | Accepts |
|---|---|
| `name_metric` | any SMESH filter name, e.g. `"AspectRatio"`, `"Warping"`, `"Skew"` |
| `element_type` | `"FACE"` or `"VOLUME"` |
| `comparison` | `">"`, `"<"`, `"="` / `"=="` |
| `threshold` | numeric cutoff |
| `create_group` | `True` also creates a SALOME group of the flagged elements |

NEMOS translates the friendly strings into SMESH constants and writes
`<case>/<name_metric>_summary.txt`: how many elements were flagged, the value
range, and a per-region breakdown. It is a report, not a gate — nothing stops
because the mesh is poor.

---

## `Manager` — parameter sweeps

```python
import Manager as nemos

sim = nemos.Simulation(script_path=__file__, case_path=..., **config)
```

Note the extra `script_path=__file__`: Manager parses its own script text to find
the sweep lists. The geometry classes have the same names and signatures as
above.

**Every top-level list in the script is a sweep parameter.** They must all have
the same, non-zero length; that length is the number of simulations.

| Call | Does |
|---|---|
| `sim.build_machine_script()` | Creates `SIM_0/` … `SIM_N/` and one `scripts/script_i.py` each; returns the list of script paths |
| `nemos.main(scripts)` | Runs them sequentially, logging to `logs/script_i.log`, stopping at the first failure |
| `nemos.resume(case_root)` | Re-runs only the `SIM_i` without a `.nemos_done` marker |

If no sweep list feeds the `Mesh(...)` call, only `SIM_0` meshes and the rest
import its mesh.

---

## Post-processing

```python
import NEMOS_SimulationAnalysis as nemos
```

Requires the case to have finished, `caso.foam` at its root, and — for parallel
runs — a `reconstructPar` first.

### `LoadSimulation(sim_path, time_step=None)`

`time_step=None` loads the last written time.

| Member | Is |
|---|---|
| `.available_times` | list of times on disk |
| `.time_step` | the active time |
| `.internal_mesh` | the volume as a PyVista mesh |
| `.boundaries` | dict of patch name → `pv.PolyData` |
| `.set_time(t)` | switch time — **do this before constructing the analysis objects, which freeze the mesh** |

### `SimulationAnalysis(load_simulation)`

| Method | Does |
|---|---|
| `.plot(field, out_dir, plane, value=None, clim=None)` | Slice through `"xy"`/`"xz"`/`"yz"` and save a PNG. Vectors become magnitudes (`U` → `U_mag`) |
| `.get_point_value(point, field, geometric_type=None, interpolation_radius=None)` | Sample a point, `"sphere"`, `"plane"` or `"box"`. **Prints** the statistics and returns `None` |
| `.get_probe_data(probe_name, field, magnitude=False, return_dataframe=False)` | Time history from a `probes` functionObject |
| `.probe_to_excel(probe_name, field, output_excel=...)` | Probe history to `.xlsx` |
| `.plot_probe(probe_name, field, magnitude=False)` | matplotlib plot; blocks until closed |

Probes need a `probes` block in `system/controlDict`, which NEMOS does not write.
[`07_analysis_full.py`](../examples/07_analysis_full.py) shows the block to paste.

### `Regularization(load_simulation)`

Resamples the unstructured mesh onto a regular grid. Points outside the domain
(inside a manikin, say) become `NaN` and are dropped.

| Method | Returns |
|---|---|
| `.reg2D(out_dir, n1, n2, plane, value=None)` | `(DataFrame, plane)`, and writes an `.xlsx` |
| `.reg3D(nx, ny, nz, out_dir)` | `(DataFrame, grid)` — mind the cube: 60³ ≈ 216k points |
| `.save_plot_2D_reg(plane, scalar, filename, out_dir, clim=None)` | writes a PNG |
| `.save_plot_3D_reg(grid, scalar, filename, out_dir, clim=None)` | writes a PNG |
| `.plot_2D(...)` / `.plot_reg_3D(...)` | interactive PyVista windows; block until closed |

`NEMOS_MeshAnalysis` offers a parallel `LoadSimulation` focused on mesh metrics.

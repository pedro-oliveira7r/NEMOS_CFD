# NEMOS_CFD — Architecture & Context

> Reusable context for future chats. Describes how the `Simulation` and `Manager`
> modules automate real-scale OpenFOAM CFD simulations. Reflects the code as of the
> resume/idempotency update (July 2026). Paths and class names below are current.

---

## 1. TL;DR (read this first)

NEMOS automates the full CFD pipeline for indoor-thermal-comfort rooms:
**Python geometry definition → SALOME meshing → OpenFOAM case setup → solver run.**

There are **two layers**, and this is the single most important thing to understand:

| Layer | Files | Runs where | Job |
|---|---|---|---|
| **Host / driver** | `src/Simulation.py`, `src/Manager.py` | normal CPython (Windows) | *Records* the user's geometry calls into a text "machine script", generates the OpenFOAM case files, and orchestrates SALOME + WSL subprocesses. |
| **SALOME engine** | `src/GeoMesh.py` (installed into SALOME's `site-packages`) | SALOME's embedded Python | *Actually builds* the geometry and mesh using SALOME's `GEOM`/`SMESH` APIs. |

The host-side classes `Room`, `Person_seated`, `Dip_type_01`, `Mesh`, etc. in
`Simulation.py`/`Manager.py` are **thin recording proxies** — they don't build any
geometry. They just capture the call (class, args, kwargs) and emit a line of Python
that will later be executed *inside SALOME*, where the same-named classes in `GeoMesh.py`
do the real work.

Two entry scripts styles:
- **`user_script_*.py`** → one simulation. Uses `Simulation.py`.
- **`manager_script_*.py`** → a parameter *sweep* (N simulations). Uses `Manager.py`.

The pipeline is now **idempotent/resumable**: re-running skips already-completed stages
(detected by on-disk artifacts) and the solver continues from its last written timestep.

---

## 2. The end-to-end workflow (`Simulation.run`)

`run(simulation)` in `Simulation.py` executes these stages in order. Each stage is
**gated on an artifact** so a re-run resumes instead of overwriting:

1. **`setup_workflow`** — builds an `OpenFOAMCase`, reads config, writes `machine_script.py`
   into the case folder, generates the OpenFOAM base dictionaries (`constant/`, `system/`),
   and saves `.nemos_state.json` (for resume-by-folder).
2. **Mesh geometry** — skip if `Mesh_1.unv` exists; else run SALOME in batch
   (`SalomeMesher.executar_batch`) on the machine script, **or** copy an imported mesh
   (`_ensure_imported_mesh`) if `Import_mesh` was used.
3. **Mesh conversion** — skip if `constant/polyMesh/boundary` exists; else
   `OpenFOAMRunner.preparar_malha` runs WSL: `ideasUnvToFoam Mesh_1.unv` + `checkMesh`.
4. **Boundary + fields** — skip if `0/T` and `0/U` exist; else `BoundaryManager.editar_boundary`
   (rewrites patch `type`s in the `boundary` file) then `generate_all_fields` (writes all
   `0/` field files with per-patch BCs). These two must stay paired — `editar_boundary` sets
   `fields_config`/`field_conditions` that `generate_all_fields` consumes.
5. **Solver** — `OpenFOAMRunner.rodar_simulacao` runs WSL: `decomposePar` (guarded — skipped
   if `processor0/` already exists) then `mpirun -np 4 buoyantSimpleFoam -parallel` (or serial).
   `controlDict` uses `startFrom latestTime`, so the solver natively continues from the last
   written time directory. Live residuals are parsed/plotted.
6. On a **converged** solver run, a `.nemos_done` marker is written in the case folder.
   Every run also writes `.nemos_status.json` with the verdict — see §8.

Validation gates are interleaved between these stages (§8): Gate A before stage 1,
Gate B after stage 3, Gate B2 after stage 4, Gate C during stage 5, Gate D after it.

---

## 3. `Simulation.py` — the host driver

### 3.1 Two ways a `Simulation` gets its data
- **Recording mode** (`user_script_path is None`) — the common path used by `user_script_*.py`
  and by Manager's generated per-SIM scripts. You construct `nemos.Simulation(case_path=..., **cfg)`
  and then instantiate geometry objects; each records itself live (see §3.4).
- **Reading mode** (`user_script_path` given) — legacy. `read_user_script()` parses the script
  *text*: it extracts a `simulation_config` dict literal (if present) and sanitizes each
  `x = nemos.Class(...)` line via regex/AST to rebuild object metadata + the machine script.

### 3.2 Configuration model
`simulation_config` is a nested dict with four sections, seeded from
`DEFAULT_SIMULATION_CONFIG` and overridden by kwargs (`_apply_simulation_kwargs`) or the
user script's `simulation_config` literal:
- `controlDict`: `startTime`, `endTime`, `deltaT`/`delta`, `writeInterval`
- `decomposeParDict`: `parallel` ("Y"/"N")
- `fields`: `U/T/p/k/epsilon` → `internalField` (and `U.value`)
- `monitoring`: `plot_residuals` (bool)

**Friendly kwarg aliases** accepted by the `Simulation(...)` constructor:
`startTime, endTime, delta/deltaT, writeInterval, parallel, plot_residuals`, and
`T_internalField/T_Field` (→ `fields.T.internalField`), same for `p_/k_/epsilon_/U_`.

### 3.3 Per-object metadata (drives boundary conditions)
When a geometry object is recorded, **inline simulation keys** are stripped from the geometry
call and stored separately, so they can be applied as OpenFOAM BCs later. Three dicts, all keyed
by the object's `name=`:
- `object_classes`: name → class name (e.g. `"Person_1" → "Person_seated"`)
- `object_types`: name → semantic type (`room`/`person`/`dip`/`table`)
- `object_simulation`: name → inline BC values (`T_Face`, `T_Flow`, `V_Flow`, …)

`SIMULATION_INLINE_KEYS` lists which kwargs are treated as BC data (T_face/T_Face, T_Flow,
V_Flow, metabolic_heat_W, emissivity, …). Everything else stays a geometry arg.
**Every geometry object must be given `name=`** (enforced in `_register_object`).

### 3.4 The recording mechanism (how the machine script is built)
- Module global `_ACTIVE_SIMULATION` points at the most recently constructed `Simulation`.
- Geometry classes (`Room`, `Person_seated`, `Person_standing`, `Dip_type_00..03`,
  `Table_retangular`, `Table_circular`, `Mesh`, `Salome_Env`) subclass `_RecordedObject`.
- `_RecordedObject.__init__` calls `_register_object`, which reserves a variable name, stores
  the metadata above, and appends a line like `a = nemos.Room(dx=3.0, ...)` to `_machine_lines`.
- `_RecordedObject.__getattr__` returns a recorder, so method calls like `a.add([b,c])`,
  `a.insert_ceiling_opening(...)`, `mesh.create_mesh(export=True)` also become recorded lines.
- The recorded script's **first line is `import GeoMesh as nemos`** — i.e. the machine script
  is meant to run against the SALOME-side engine, not this host module.
- `mesh.create_mesh(export=True)` auto-injects the export path `<case>/Mesh_1.unv`.

### 3.5 Execution engine classes
- **`OpenFOAMCase`** — directory structure (`constant/`, `constant/polyMesh/`, `0/`, `system/`)
  and `gerar_arquivos_base` which writes all base dicts (`g`, `thermophysicalProperties`,
  `turbulenceProperties`, `controlDict`, `decomposeParDict`, `fvOptions`, `fvSchemes`,
  `fvSolution`). `controlDict` is parametrized from `controlDict` cfg; `decomposeParDict` is
  dropped for serial runs. Also holds the **resume detectors**: `mesh_geometry_ready()`,
  `mesh_converted()`, `fields_ready()`, `decomposed()`, `done_marker()`/`is_complete()`.
- **`SalomeMesher`** — runs `"<salome_exe>" -t "<machine_script>"` via `shell=True` (batch mode)
  to produce `Mesh_1.unv`. Default exe: `c:\SALOME-9.15.0\run_salome.bat`.
- **`BoundaryManager`** — after conversion: `editar_boundary` infers each patch's OpenFOAM type
  (`wall`/`inlet`/`outlet`) from its name using `object_types` (patches are named after the
  object's `name=`; `inlet_<dipVar>`, `outlet`, `wall` special-cased). `generate_all_fields`
  writes `0/{U,alphat,epsilon,k,nut,p,p_rgh,T}` with per-patch BCs, pulling per-object values
  from `object_simulation` (T_Face for person/table walls, T_Flow/V_Flow for dips/inlets).
- **`OpenFOAMRunner`** — writes `comandos_1.sh` (mesh prep) and `comandos_2.sh` (solver) and runs
  them through `wsl bash`. Reads `parallel` and `plot_residuals` from config. `decomposePar` is
  now bash-guarded (`[ -d processor0 ] || decomposePar`). Has `wait_*`, `is_*_running`, `kill_*`
  helpers for the background processes.
- **`ResidualPlotter`** — parses solver stdout (`Time = …`, `Solving for X, Initial residual = …`),
  live-plots residuals (log Y) via matplotlib, and saves `residuals.png` + `log.simulation`.
  Because it drains stdout line-by-line, enabling `plot_residuals` makes the solver run
  **synchronous**.

### 3.6 Resume support (added in the idempotency update)
- **`run(simulation)`** is idempotent (see §2); writes `.nemos_done` on success.
- **`Simulation.save_state()`** dumps `simulation_config`, `object_simulation`, `object_types`,
  `object_classes` to `<case>/.nemos_state.json` (all JSON-safe).
- **`Simulation.load_state(case_path)`** (classmethod) rebuilds a `Simulation` from that file
  in recording mode with `_loaded=True`.
- **`resume(case_path)`** (module function): `load_state` → `run`. Early-returns if `.nemos_done`
  exists. **Limitation:** it cannot rebuild the SALOME geometry (that needs the original object
  calls), so resume-by-folder requires `Mesh_1.unv` to already exist — i.e. the common
  mid-solver interruption. Earlier interruptions: re-run the original geometry script (also
  idempotent now).

---

## 4. `Manager.py` — parameter sweeps

Manager turns one templated script into **N simulations**, one per index of the sweep lists.

- It has its **own** lightweight `Simulation` class (distinct from `Simulation.py`'s) plus its
  own recording proxies (`Room`, `Person_*`, …). These only capture the sweep *structure*.
- `_load_list_names` parses the manager script text to find top-level list assignments (the
  sweep parameters, e.g. `T_Flow = [291, 293, ...]`).
- `build_machine_script()`:
  - collects the actual list values from the caller's globals (`inspect` on the calling frame),
  - validates **all sweep lists have equal, non-zero length**,
  - for each index `i`, creates `SIM_i/` and writes `scripts/script_i.py` — a self-contained
    script that `import Simulation as nemos`, rebuilds the case with the **i-th value** of each
    sweep list substituted (`_format_value` indexes into the lists), and calls `nemos.run(sim)`.
  - **Shared mesh optimization:** if mesh parameters are *not* swept (`_mesh_uses_sweep` is
    False), only `SIM_0` builds the mesh; `SIM_i>0` imports it via `nemos.Simulation.Import_mesh`.
    If mesh params *are* swept, every SIM builds its own.
- `main(scripts)` runs each `script_i.py` sequentially via `run_script` (a `subprocess.run`),
  logging stdout/stderr to `<case>/logs/script_i.log`, stopping on the first failure.
- **`resume(case_root)`** (added): scans `scripts/script_*.py` in numeric order, skips any
  `SIM_i` that has a `.nemos_done` marker, and re-runs the rest with `run_script`. Because each
  per-SIM script calls the now-idempotent `run`, an interrupted SIM continues from where it left off.

---

## 5. Entry-point scripts & the resume scripts

- `src/user_script_H.py` — example single run (recording mode): define `Simulation(...)`, build
  Room/People/Dips/Table/Mesh, `mesh.create_mesh(export=True)`, then `nemos.run(sim)`.
- `src/manager_script_original.py` — example sweep varying **boundary conditions only**.
- `src/manager_script_mesh.py` — example sweep varying **mesh refinement**.
- **`src/simulation_resume.py`** (new) — `nemos.resume(r"...case folder")` for one simulation.
- **`src/manager_resume.py`** (new) — `nemos.resume(r"...case root")` for a sweep.

To force a clean redo, delete the relevant artifacts (`.nemos_done`, and optionally
`Mesh_1.unv` / `0/` / `processor*`).

---

## 6. Generated files inside a case folder

```
<case>/
  constant/            thermophysicalProperties, turbulenceProperties, g, polyMesh/boundary
  system/              controlDict, fvSchemes, fvSolution, fvOptions, (decomposeParDict)
  0/                   U T p p_rgh k epsilon nut alphat   (generated field files)
  Mesh_1.unv           SALOME mesh (imported by ideasUnvToFoam)
  processor0..3/       decomposition (parallel runs)
  machine_script.py    the recorded SALOME geometry/mesh script
  comandos_1.sh        WSL mesh-prep script
  comandos_2.sh        WSL solver script
  log.simulation       solver stdout
  residuals.png        residual convergence plot
  .nemos_state.json    saved config/metadata (enables resume-by-folder)
  .nemos_done          marker: this case finished successfully
```
For a sweep, the root also holds `SIM_0..N/` (each like above), `scripts/script_i.py`, and `logs/`.

---

## 7. Key invariants, defaults & gotchas

- **Two layers**: host proxies record; `GeoMesh.py` inside SALOME builds. Don't
  expect the host `Room`/`Mesh` classes to compute geometry.
- Every geometry object **requires `name=`**; patch names in OpenFOAM derive from it.
- Sweep lists must be **equal length and non-empty**.
- The mesh file must be named **`Mesh_1.unv`**.
- **Solver**: `buoyantSimpleFoam` (steady, buoyant), kEpsilon RAS, Boussinesq. Parallel uses a
  hardcoded **4 subdomains** (`numberOfSubdomains 4`, `n (1 4 1)`, `mpirun -np 4`).
- **Hardcoded environment paths**: SALOME at `c:\SALOME-9.15.0\run_salome.bat`; OpenFOAM under
  WSL at `/usr/lib/openfoam/openfoam2312`; case paths are absolute Windows paths converted to
  `/mnt/c/...` for WSL.
- `plot_residuals=True` (default) makes the solver run **synchronously** (needed to drain stdout).
- `startFrom latestTime` in `controlDict` is what lets the solver resume natively — the resume
  feature relies on it plus the guarded `decomposePar`.
- Some `.pyc` files are tracked in this repo's `src/__pycache__/`.

---

## 8. Validation & guardrail layer

Design doc: [docs/guardrail_architecture.md](docs/guardrail_architecture.md). Four host-side
modules, none of which may import SALOME, WSL, matplotlib or pandas — so every check is
runnable and testable on a bare machine:

| File | Role |
|---|---|
| `src/validation_core.py` | `Issue`, `ValidationReport`, policy resolution, `EnvProbe`, `GeometryModel`, `Extent`, and the constants mirroring the generated OpenFOAM dicts |
| `src/validation_checks.py` | Gate A checks: environment, config, geometry, mesh params, physics advisories |
| `src/validation_parsers.py` | Gate B/C/D: `checkMesh` / `boundary` / field-file parsers, and `LogMonitor` |
| `src/Validation.py` | Public facade — the gate functions the pipeline calls |

### 8.1 Gates

| Gate | Where | Checks |
|---|---|---|
| **A0** | `Simulation.__init__` → `_guard_kwargs` | `E-CFG-01` unknown kwargs, raised at the constructor call |
| **A** | `setup_workflow` → `guard_preflight` | environment, config, geometry, mesh params, physics, stale case |
| **B** | `run()` after mesh conversion | `checkMesh` parse, bounding-box continuity, patch inventory |
| **B2** | `run()` after `generate_all_fields` | every patch covered in every field file |
| **C** | `_rodar_simulacao_com_plot` | `LogMonitor` fed beside `ResidualPlotter`; writes `monitor.csv` |
| **D** | `run()` after the solver | verdict, `.nemos_status.json`, artifact completeness |

### 8.2 Policy

`validate="strict"` (default) aborts on any `ERROR`; `"warn"` only reports; `"off"` skips;
`"preflight-only"` runs Gate A and stops. Resolution order is kwarg → `NEMOS_VALIDATE` env
var → `"strict"`. `Manager.main()` uses `preflight-only` in a child process to validate all
N sweep configurations *before* running any of them.

### 8.3 Behaviour changes this introduced

- **`.nemos_done` now means "converged"**, not "exit code 0". Every run also writes
  `.nemos_status.json` with a verdict of `CONVERGED` / `MAX_ITERATIONS` / `DIVERGED` /
  `CRASHED` / `INCOMPLETE`. Pass `accept_unconverged=True` to mark a `MAX_ITERATIONS` run as
  done. This matters because `Manager.resume()` skips any SIM that has the marker.
- **`fields_ready()` now requires all eight fields**, not just `0/T` and `0/U`.
- **`comandos_1.sh` / `comandos_2.sh` check every command's exit code** (`set -o pipefail`
  plus explicit `$?` tests) and tee `log.ideasUnvToFoam` / `log.checkMesh` to disk for Gate B.
- **The solver log is redirected to `log.simulation` inside bash when `plot_residuals=False`.**
  Previously that path used a `PIPE` nobody drained, so the solver deadlocked at ~64 KB of
  output. `run()` also now calls `rodar_simulacao(wait=True)`.
- **Re-running an edited script into an existing case folder aborts** (`E-STATE-01` /
  `E-STATE-02`) instead of silently reusing the stale mesh or stale `0/` fields. Nothing is
  deleted automatically; the message lists the artifacts to remove.
- Geometry calls are recorded into `Simulation._events` and exposed as
  `Simulation.geometry_model()`; `save_state()` also stores fingerprint hashes.

### 8.4 Not yet implemented

Sections 5.2 and 5.3 of the design doc — global mass/energy conservation balances, field
boundedness and y+ — plus the `functions {}` block in `controlDict` they depend on. Adding an
unverified function-object entry to `controlDict` makes OpenFOAM fail at startup, so that
block needs one confirmed run before it becomes the default. Section 9 of the design doc lists
the log patterns still to be calibrated against real output.

`nemos.doctor()` runs the environment checks alone:

```
python -c "import sys; sys.path.insert(0,'src'); import Validation; Validation.doctor()"
```

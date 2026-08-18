# The workflow

What happens between `nemos.run(sim)` and a solved case, and why re-running is
safe.

## The shape of a user script

Every single-simulation script has the same four parts:

```python
sim  = nemos.Simulation(case_path=..., **config)   # 1. configure
a    = nemos.Room(...); a.add([...])               # 2. describe the geometry
mesh = nemos.Mesh(a, ...); mesh.create_mesh(export=True)   # 3. describe the mesh
case = nemos.run(sim)                              # 4. execute everything
```

Nothing happens until step 4. Steps 2 and 3 only *record* — each constructor and
method call appends a line of Python to an in-memory buffer. `run()` writes that
buffer out as `machine_script.py` and hands it to SALOME.

This is why the order matters and why every object needs a `name=`: the recorded
script is replayed verbatim inside SALOME, and the names become the OpenFOAM
patch names.

## The six stages of `run()`

Each stage checks for an artifact on disk first and skips itself if the artifact
is already there. That is the entire resume mechanism.

| # | Stage | Skipped when | Produces |
|---|---|---|---|
| 1 | **Setup** — build the case directory, write `machine_script.py` and every base dictionary | never (cheap, idempotent) | `constant/`, `system/`, `machine_script.py`, `caso.foam`, `.nemos_state.json` |
| 2 | **Geometry + mesh** — run SALOME in batch on the machine script | `Mesh_1.unv` exists | `Mesh_1.unv` |
| 3 | **Mesh conversion** — `ideasUnvToFoam` + `checkMesh` under WSL | `constant/polyMesh/boundary` exists | `constant/polyMesh/` |
| 4 | **Boundaries + fields** — rewrite patch types, then write all eight `0/` fields | `0/T` and `0/U` exist | `0/U T p p_rgh k epsilon nut alphat` |
| 5 | **Solve** — `decomposePar` (guarded), then `buoyantSimpleFoam` | `processor0/` exists (decomposition only) | `processor*/`, time directories, `log.simulation`, `residuals.png` |
| 6 | **Mark done** | — | `.nemos_done` |

Stage 2 has an alternative path: if the script called
`Simulation.Import_mesh(...)` instead of `Mesh(...).create_mesh()`, the `.unv` is
copied into the case folder and SALOME is never launched.

Stages 4's two halves must stay together — rewriting the patch types is what
populates the configuration that the field writer then consumes.

## How boundary conditions are derived

You never write a `0/` file by hand. Values ride along on the geometry:

```python
nemos.Person_seated(..., T_Face=304, name="Person_1")
nemos.Dip_type_01(..., V_Flow=-1.2, T_Flow=291, name="Dip_1")
```

When an object is recorded, NEMOS splits its keyword arguments in two: the
geometric ones go into the machine script, and the *inline simulation keys*
(`T_Face`, `T_Flow`, `V_Flow`, …) are stored separately, keyed by `name=`.

After conversion, each patch in `constant/polyMesh/boundary` is classified:

| Patch name | Becomes |
|---|---|
| `wall` | `wall` |
| `outlet` | `outlet` |
| `inlet_<something>` | `inlet` |
| a name you gave an object | `wall` for people, tables and dips |
| anything else | left as `patch` — **see the warning below** |

Then all eight `0/` fields are written, with each patch getting the condition
implied by its type and the object's stored values.

> **Unclassified patches get `zeroGradient` on every field.** A patch NEMOS
> cannot classify silently becomes a frictionless, adiabatic surface. If results
> look physically wrong, check the patch names in
> `constant/polyMesh/boundary` against your object names first.

## Parameter sweeps

`Manager.py` turns one templated script into N simulations.

1. Every **top-level list** in the script is a sweep parameter. They must all have
   the same, non-zero length — that length is N.
2. `build_machine_script()` writes `SIM_0/` … `SIM_{N-1}/` and a self-contained
   `scripts/script_i.py` for each, substituting element `i` of every list.
3. `main(scripts)` runs them sequentially, logging to `logs/script_i.log`, and
   stops at the first failure.

**Shared mesh:** if no sweep list feeds the `Mesh(...)` call, only `SIM_0` builds
the mesh and every later SIM imports it. If a mesh parameter *is* swept — as in
[`04_sweep_mesh.py`](../examples/04_sweep_mesh.py) — each SIM meshes its own.
This is usually the difference between a sweep taking hours and taking a day.

## Resuming

Because every stage is artifact-gated, **re-running the original script is
already a resume.** The solver additionally uses `startFrom latestTime`, so it
continues from the last written time directory rather than from zero, and
`decomposePar` is guarded so it will not re-decompose.

Two convenience entry points exist for when you do not want to re-run the script:

- [`resume_simulation.py`](../examples/resume_simulation.py) — rebuilds the
  `Simulation` from `.nemos_state.json` and re-enters `run()`. It **cannot**
  rebuild the SALOME geometry, so `Mesh_1.unv` must already exist. For an
  interruption before meshing, re-run the original script.
- [`resume_sweep.py`](../examples/resume_sweep.py) — skips every `SIM_i` with a
  `.nemos_done` marker and re-runs the rest from the already-generated scripts.

### Forcing a redo

| Delete | To re-run |
|---|---|
| `.nemos_done` | the solver (from the last timestep) |
| `.nemos_done` + `processor*/` | the solver from scratch |
| `.nemos_done` + `0/` | boundaries and fields |
| `.nemos_done` + `Mesh_1.unv` + `constant/polyMesh/` + `0/` | everything, including SALOME |

> **Editing a script does not invalidate anything.** The gates ask only whether
> an artifact exists, never whether it still matches your script. After changing
> geometry, delete `Mesh_1.unv` — otherwise you will solve the old room.

## What "finished" means

`.nemos_done` is written when the solver process exits with status 0. That is
**not** a convergence check: a run that reaches `endTime` with residuals stuck at
1e-1 exits cleanly and is marked done. Always look at `residuals.png`.

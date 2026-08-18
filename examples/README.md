# Examples

Every runnable script lives here. They are numbered in suggested reading order —
each one introduces roughly one new idea on top of the previous.

Run any of them from anywhere; each inserts `src/` on `sys.path` itself:

```bash
python examples/01_single_run.py
```

By default they write their cases into `cases/<example name>/` at the repository
root, which is git-ignored. Change the `CASE_PATH` constant at the top of a
script to put the case somewhere else — it must be on a Windows drive reachable
from WSL.

## The examples

| # | Script | Drives | What it adds | Rough runtime |
|---|---|---|---|---|
| 01 | [01_single_run.py](01_single_run.py) | `Simulation` | The whole pipeline end to end: room, people, diffusers, table, mesh, solver. **Start here.** | ~15–40 min |
| 02 | [02_classroom.py](02_classroom.py) | `Simulation` | A bigger, busier room; `Dip_type_00`, rectangular tables, floor openings | longer than 01 |
| 03 | [03_sweep_conditions.py](03_sweep_conditions.py) | `Manager` | 5 runs varying boundary conditions; meshes once and shares it | hours |
| 04 | [04_sweep_mesh.py](04_sweep_mesh.py) | `Manager` | 5 runs varying mesh refinement — a mesh-independence study; meshes 5 times | many hours |
| 05 | [05_import_mesh.py](05_import_mesh.py) | `Simulation` | Reuses example 01's mesh instead of remeshing | solver only |
| 06 | [06_analysis.py](06_analysis.py) | `NEMOS_SimulationAnalysis` | Post-processing: slices, point sampling, 2D/3D regularisation | minutes |
| 07 | [07_analysis_full.py](07_analysis_full.py) | `NEMOS_SimulationAnalysis` | Everything in 06 plus the probe/time-history API | minutes |
| — | [resume_simulation.py](resume_simulation.py) | `Simulation` | Continues one interrupted case | varies |
| — | [resume_sweep.py](resume_sweep.py) | `Manager` | Continues an interrupted sweep | varies |

## Notes before you run one

- **01 is the only cheap one.** 03 and 04 each run five full simulations back to
  back. Do not start them to "see if it works" — run 01 for that.
- **Everything is resumable.** Re-running a script skips stages whose artifacts
  already exist and the solver continues from its last written timestep. To force
  a clean redo, delete `.nemos_done` in the case folder (and `Mesh_1.unv`, `0/`,
  `processor*/` if you want the earlier stages rebuilt too).
- **06 and 07 need a case that has already finished**, and — if it ran in
  parallel — one `reconstructPar` first. Both scripts say so in their header.
- Every geometry object **must** have a `name=`. Patch names in OpenFOAM are
  derived from it, and the boundary conditions are matched by it.

See [../docs/api-reference.md](../docs/api-reference.md) for what each class and
keyword argument actually does.

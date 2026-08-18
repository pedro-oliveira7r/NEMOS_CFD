# NEMOS_CFD — Validation & Guardrail Architecture

> ## ⚠️ Roadmap document — none of this is implemented
>
> This is a **design proposal**, drafted 2026-07-25. Nothing described below exists
> in the code today: there is no validation module, no gates, no error codes, and
> no honest-verdict classification. Do not read any of it as behaviour you can
> rely on, and do not file bugs against it.
>
> For how the pipeline actually works today, see
> [ARCHITECTURE.md](../../ARCHITECTURE.md) and [../workflow.md](../workflow.md).
> The failure inventory in section 0 *is* accurate — it documents real, current
> weaknesses, and the short version of it appears under "Known limitations" in the
> [README](../../README.md).

---

## Why this is needed

NEMOS_CFD works, but it is **silent when it is wrong**. The library is driven by tiny user
scripts, and almost every failure mode currently surfaces either as a confusing exception
deep inside SALOME/WSL, or — far worse — as a simulation that completes, writes
`.nemos_done`, produces a `residuals.png`, and is physically meaningless. For an OpenFOAM
beginner that is the worst possible failure mode: the tool signals success.

Concretely, today:

- A typo in a `Simulation(...)` kwarg (`endtime=20`) is **silently discarded** —
  [Simulation.py:1665-1678](../../src/Simulation.py#L1665-L1678) skips any key it does not
  recognise, so the case runs with `endTime=3500` instead of 20.
- A typo in a geometry kwarg (`Thickness=0.15`) is **silently swallowed** by `**kwargs` in
  [GeoMesh.py:730-741](../../src/GeoMesh.py#L730-L741), which pops only `name`.
- A patch whose name maps to no known type keeps `type patch;`
  ([Simulation.py:800-806](../../src/Simulation.py#L800-L806)) and then receives `zeroGradient`
  on **every** field via the fallback at [Simulation.py:1034](../../src/Simulation.py#L1034) —
  a wall silently becomes a frictionless, adiabatic, free-slip surface.
- `metabolic_heat_W`, `emissivity`, `species_source`, `supply_T_C`, `supply_velocity_m_s`,
  `flow_profile` and `material` are all accepted as inline keys
  ([Simulation.py:1534-1546](../../src/Simulation.py#L1534-L1546)) but **never read** by
  `BoundaryManager`. Only `T_Face`, `T_Flow` and `V_Flow` do anything.
- `.nemos_done` is written on **solver exit code 0**
  ([Simulation.py:2423-2424](../../src/Simulation.py#L2423-L2424)), not on convergence. A run
  that hits `endTime` with residuals at 1e-1 is marked "finished successfully".
- Re-running an edited script into the same `case_path` reuses the **stale mesh and stale
  `0/` fields** — the resume detectors at
  [Simulation.py:76-97](../../src/Simulation.py#L76-L97) only ask "does the artifact exist",
  never "does it match the current script".

The goal is a **guardrail layer** that turns each of these into a clear, actionable message
delivered *before* the expensive stage runs, and that classifies the outcome of a finished
run honestly.

### Design decisions

| Decision | Choice |
|---|---|
| Enforcement | Two tiers — `ERROR` aborts, `WARN` advises — with a `validate="strict"\|"warn"\|"off"` override |
| Runtime monitoring | Live log parsing **and** a `functions {}` block in the generated `controlDict` |
| Language | English, for both the messages and this document |
| Stale case | Fingerprint and **abort with instructions**; never auto-delete a user's artifacts |

### Scope

Covers `src/GeoMesh.py`, `src/Simulation.py` and `src/Manager.py`. Explicitly
**out of scope**: `examples/`, `experimental/`, `src/NEMOS_MeshAnalysis.py` and
`src/NEMOS_SimulationAnalysis.py` — the two analysis modules are a separate effort.

---

## 0. Failure inventory

This is the evidence base. Every row was verified against the current source; each check in
Sections 2–6 traces back to an `F`-number here.

### 0.1 Silent-wrong-answer failures (highest priority)

| # | Failure | Evidence | Today's symptom |
|---|---|---|---|
| F1 | Unknown `Simulation(...)` kwarg dropped | [Simulation.py:1665](../../src/Simulation.py#L1665) | Defaults used; `endTime=3500` |
| F2 | Unknown geometry kwarg dropped | [GeoMesh.py:730](../../src/GeoMesh.py#L730) | Parameter has no effect |
| F3 | Unmapped patch → `zeroGradient` on all fields | [Simulation.py:800](../../src/Simulation.py#L800), [1034](../../src/Simulation.py#L1034) | Slip/adiabatic wall |
| F4 | Inline BC keys accepted but unimplemented | [Simulation.py:1534](../../src/Simulation.py#L1534) | User believes a heat source exists |
| F5 | `.nemos_done` means "exit 0", not "converged" | [Simulation.py:2423](../../src/Simulation.py#L2423) | Unconverged case looks finished |
| F6 | Stale mesh / stale `0/` reused after a script edit | [Simulation.py:76-97](../../src/Simulation.py#L76-L97) | Yesterday's physics, today's parameters |
| F7 | `fvOptions` clamps `T` to [280, 310] and \|U\| to 10 | [Simulation.py:328-347](../../src/Simulation.py#L328-L347) | BCs outside the clamp are silently limited |
| F8 | `p` from config (e.g. 101322) vs `p_rgh` hardcoded 101325 | [Simulation.py:857](../../src/Simulation.py#L857) vs [862](../../src/Simulation.py#L862) | Spurious initial transient |
| F9 | Inlet `k`/`epsilon` hardcoded regardless of `V_Flow` | [Simulation.py:893](../../src/Simulation.py#L893), [902](../../src/Simulation.py#L902) | Turbulence inconsistent with the jet |
| F10 | `fields_ready()` checks only `0/T` and `0/U` | [Simulation.py:84-86](../../src/Simulation.py#L84-L86) | Half-written `0/` accepted; solver fails on `p_rgh` |

### 0.2 Confusing-crash failures

| # | Failure | Evidence | Today's symptom |
|---|---|---|---|
| F11 | `case_path` not on `C:` — the WSL translation replaces only the literal `C:` | [Simulation.py:1213-1218](../../src/Simulation.py#L1213-L1218) | Bash `cd` fails, script continues (no `set -e`), garbage downstream |
| F12 | Lowercase `c:\...` in `case_path` is not converted either | same | Same as F11 |
| F13 | Spaces in `case_path` — `wsl bash {path}` is unquoted | [Simulation.py:1257](../../src/Simulation.py#L1257) | Cryptic bash error |
| F14 | Missing SALOME exe only prints and `return`s — no raise | [Simulation.py:569-572](../../src/Simulation.py#L569-L572) | Failure surfaces two stages later |
| F15 | `Dip` created before `Room` → `salome_env.room` is `None` | [GeoMesh.py:1030](../../src/GeoMesh.py#L1030), [1140](../../src/GeoMesh.py#L1140) | `AttributeError` inside the SALOME batch |
| F16 | Dip axis matches no room face → `dip_face_max` stays `None` | [GeoMesh.py:367-370](../../src/GeoMesh.py#L367-L370) | `GetSubShapeID(None)` error inside SALOME |
| F17 | `insert_*_opening` called **after** `add()` re-partitions the room | [GeoMesh.py:454-457](../../src/GeoMesh.py#L454-L457) vs [287](../../src/GeoMesh.py#L287) | Face groups reference a dead shape; patches wrong or missing |
| F18 | WSL `nproc` < 4 while `mpirun -np 4` is hardcoded | [Simulation.py:1313](../../src/Simulation.py#L1313), [300](../../src/Simulation.py#L300) | "not enough slots available" |
| F19 | `plot_residuals=False` → `Popen(PIPE)` with `wait=False`; nobody drains the pipe | [Simulation.py:1329-1350](../../src/Simulation.py#L1329-L1350), called from [2417](../../src/Simulation.py#L2417) | Solver **deadlocks** at ~64 KB of output; no `.nemos_done` ever |
| F20 | `comandos_*.sh` have no `set -e`; the return code is the last command's | [Simulation.py:1219](../../src/Simulation.py#L1219) | A failed `ideasUnvToFoam` can be masked by a passing `checkMesh` on an old mesh |

### 0.3 Geometry / meshing failures

| # | Failure | Evidence |
|---|---|---|
| F21 | Object partly or wholly outside the room; objects overlapping each other | no check anywhere |
| F22 | Two dips sharing the same `(x, z)` — inlet detection uses a `1e-6` match on both coordinates | [GeoMesh.py:333-339](../../src/GeoMesh.py#L333-L339) |
| F23 | Total ceiling-opening area > 20 % of the ceiling → the **whole ceiling** becomes one `outlet` patch, because the remaining ceiling face drops below `Room.area = 0.8·(two smallest dims)` | [GeoMesh.py:73](../../src/GeoMesh.py#L73), [404-425](../../src/GeoMesh.py#L404-L425) |
| F24 | `insert_ceiling_opening(d=...)` passes `d` to `MakeCircle` as a **radius**, not a diameter | [GeoMesh.py:450](../../src/GeoMesh.py#L450) |
| F25 | Duplicate object names, names `_parse_boundary_file` cannot handle (spaces, dashes), or reserved names (`wall`, `outlet`, `inlet_*`, `defaultFaces`) | [Simulation.py:942](../../src/Simulation.py#L942) |
| F26 | `m2DMinSize > m2DMaxSize`, `fineness` out of range, cell-count explosion | [GeoMesh.py:482-497](../../src/GeoMesh.py#L482-L497) |
| F27 | Viscous-layer stack (0.030 m on walls) thicker than the gap between two bodies | [GeoMesh.py:578](../../src/GeoMesh.py#L578) |
| F28 | Mesh exported in millimetres → bounding box 3000 × 3000 × 3000 | detectable only from `checkMesh` |

### 0.4 Sweep (Manager) failures

| # | Failure | Evidence |
|---|---|---|
| F29 | A list built by comprehension or defined inside a function is **not** recognised as a sweep list — only a top-level `ast.Assign` of a `List`/`Tuple` is scanned — so the literal list is embedded in every SIM | [Manager.py:37-45](../../src/Manager.py#L37-L45) |
| F30 | A bad parameter in `SIM_4` is discovered only after `SIM_0..3` have run for hours | [Manager.py:348-356](../../src/Manager.py#L348-L356) |
| F31 | Reusing a `case_path` for a shorter sweep leaves stale `SIM_i` that `resume()` re-runs | [Manager.py:387](../../src/Manager.py#L387) |
| F32 | Sign inconsistency across a sweep — the repo's own example has `V_Flow=1.2` on `Dip_1` and `-1.2` on `Dip_2` | [manager_script_mesh.py:22-23](../../examples/04_sweep_mesh.py#L22-L23) |

### 0.5 Solver-setup failures a beginner cannot see

| # | Failure | Evidence |
|---|---|---|
| F33 | `ddtSchemes default steadyState` → "time" is the **iteration count**. `endTime=20, delta=0.1` is **200 iterations**, which will not meet `residualControl 1e-6` | [Simulation.py:370](../../src/Simulation.py#L370), [460-466](../../src/Simulation.py#L460-L466), [user_script_H.py:6-7](../../examples/01_single_run.py#L6-L7) |
| F34 | `startFrom latestTime` makes the written `startTime` inert | [Simulation.py:253-255](../../src/Simulation.py#L253-L255) |
| F35 | `writeInterval=3` over 200 iterations = 66 full 3D field dumps | [user_script_H.py:8](../../examples/01_single_run.py#L8) |
| F36 | Boussinesq `T0 300`, `rho0 1`, `mu 1e-5` — `rho0` is ~15 % below air at 300 K, so reported pressures and any balance in kg/s or W inherit that scaling; a `T` far from `T0` invalidates the linearisation | [Simulation.py:174-196](../../src/Simulation.py#L174-L196) |
| F37 | The inlet Reynolds number can fall in the laminar range while `kEpsilon` + wall functions are used | — |
| F38 | No outlet opening at all while dips inject mass → no steady solution exists | [GeoMesh.py:404-425](../../src/GeoMesh.py#L404-L425) |

---

## 1. Architecture of the guardrail layer

### 1.1 One new module

**`src/Validation.py`** — host-side only. Hard constraint: **it must import with zero heavy
dependencies** (no `GEOM`, no `SMESH`, no `salome`, no `matplotlib`, no `pandas`), so every
check is unit-testable on a machine with neither SALOME nor WSL installed. Its inputs are
plain Python data and **text**; its outputs are `Issue` objects.

```
Issue(code, severity, title, detail, hint, where=None, value=None)
    severity ∈ {ERROR, WARN, INFO}
    code     e.g. "E-CFG-01"   (stable; documented in the catalogue)
    hint     always imperative and concrete: "Rename it to endTime."

ValidationReport
    .add(issue) / .extend(issues)
    .errors / .warnings / .infos
    .render()            → the boxed console report
    .to_json(path)       → <case>/validation_report.json
    .enforce(policy)     → raises NemosValidationError if policy == "strict" and errors exist
```

One console format for all gates, so it becomes recognisable:

```
================ NEMOS preflight — 2 errors, 3 warnings ================
[E-CFG-01] Unknown Simulation() argument: 'endtime'
    Closest valid name: endTime
    -> Rename it. Unknown arguments are ignored, so the run would have
       used endTime=3500 (the default) instead of your value.

[W-PHY-04] Inlet Reynolds number is 350 (Dip_2, d=0.05, V_Flow=-0.05)
    The case uses the kEpsilon model with wall functions, which assumes
    turbulent flow (Re > ~2300).
    -> Raise |V_Flow|, or accept that the turbulence model is out of range.
=======================================================================
Aborting: fix the 2 errors above, or pass validate="warn" to continue anyway.
```

### 1.2 Four gates, mapped onto the existing stages of `run()`

`run()` at [Simulation.py:2373](../../src/Simulation.py#L2373) already has clean stage
boundaries. The gates slot between them; **no stage is restructured**.

```
Simulation(...)          → Gate A0  config check, immediately (fail on typos at line 3)
geometry objects         → recorded into a GeometryModel
setup_workflow()         → Gate A   full preflight  ── cheap, no subprocess, < 1 s
  ├─ SALOME batch                                      (skipped if Mesh_1.unv exists)
  ├─ ideasUnvToFoam + checkMesh
  └─ ─────────────────── → Gate B   mesh + boundary validation
      editar_boundary / generate_all_fields
      ─────────────────── → Gate B2 field/patch coverage check
  └─ solver             → Gate C   live log monitor (streaming)
                        → Gate D   post-run sanity + honest verdict
```

Gate A is the highest-value gate by a wide margin: it is where a beginner's mistake costs
one second instead of forty minutes of NETGEN plus two hours of solver.

### 1.3 Hook points (exact, minimal edits)

| Gate | File / function | Edit |
|---|---|---|
| A0 | `Simulation.__init__` [Simulation.py:1548](../../src/Simulation.py#L1548) | Accept `validate=`; call `check_simulation_kwargs(kwargs)` **before** `_apply_simulation_kwargs`, while the raw keys are still visible |
| A | `Simulation._register_object` [Simulation.py:1874](../../src/Simulation.py#L1874) | Append `(class_name, geometry_kwargs, inline_sim, order_index)` to a new `self._events` list. Both halves are already separated here by the inline-key pop |
| A | `Simulation._record_method` [Simulation.py:1923](../../src/Simulation.py#L1923) | Append method events — this is what makes the **call-order** check (F17) possible |
| A | `setup_workflow` [Simulation.py:2352](../../src/Simulation.py#L2352) | Run `preflight()` after `read_user_script()`, before `gerar_arquivos_base` |
| A | `OpenFOAMCase` [Simulation.py:64](../../src/Simulation.py#L64) | Add `fingerprint()` + `check_stale()`; extend `fields_ready()` to all eight fields (F10) |
| B | `OpenFOAMRunner.preparar_malha` [Simulation.py:1211](../../src/Simulation.py#L1211) | `set -o pipefail`, per-command exit-code checks, and `tee` into `log.ideasUnvToFoam` / `log.checkMesh` so the logs survive a crash and a resume |
| B | new `Validation.parse_check_mesh(text)` | Pure text → issues |
| B2 | `BoundaryManager.editar_boundary` [Simulation.py:767](../../src/Simulation.py#L767) | Return the `{patch: type}` map instead of `None`; collect unmapped patches |
| C | `OpenFOAMRunner._rodar_simulacao_com_plot` [Simulation.py:1355](../../src/Simulation.py#L1355) | Feed each line to `LogMonitor` next to the existing `plotter.feed_line` — the streaming loop already exists |
| C | `OpenFOAMRunner.rodar_simulacao` [Simulation.py:1282](../../src/Simulation.py#L1282) | Redirect solver output **inside the bash script** (`> log.simulation 2>&1`) instead of through a `PIPE`; this removes the F19 deadlock and makes both code paths monitorable |
| D | `run()` [Simulation.py:2417-2424](../../src/Simulation.py#L2417-L2424) | `postflight()`; write `.nemos_status.json`; write `.nemos_done` **only** on a genuinely complete run |
| Sweep | `Manager.Simulation.build_machine_script` [Manager.py:256](../../src/Manager.py#L256) | Sweep-structure checks + the preflight-all-SIMs pass (§6) |

### 1.4 Policy resolution

`validate` resolves in this order: explicit kwarg → `NEMOS_VALIDATE` env var → default
`"strict"`. Beginners are protected by default; the sweep preflight (§6) uses the env var to
run child scripts in preflight-only mode.

---

## 2. Gate A — pre-execution checks

Runs in-process, before SALOME. Target: **under one second**, no subprocess except the cheap
environment probes in §2.1, which are cached per process.

### 2.1 Environment (`*-ENV-*`)

| Code | Check | Sev |
|---|---|---|
| E-ENV-01 | SALOME executable exists at `salome_exe`; is a file; is `.bat`/`.exe`. **Raise**, unlike today's silent `return` (F14) | ERROR |
| E-ENV-02 | `wsl.exe` is on PATH and `wsl -l -q` lists at least one distro | ERROR |
| E-ENV-03 | `/usr/lib/openfoam/openfoam2312/etc/bashrc` exists in WSL (`wsl test -f ...`) | ERROR |
| E-ENV-04 | After sourcing it, `ideasUnvToFoam`, `checkMesh`, `decomposePar`, `buoyantSimpleFoam` and `postProcess` all resolve (`command -v`) | ERROR |
| E-ENV-05 | `case_path` is on a drive the WSL translation actually handles — reject any non-`C:` drive and any UNC path (F11) | ERROR |
| E-ENV-06 | The drive letter is normalised case-insensitively before translation; a lowercase `c:` must not fall through (F12) | ERROR |
| E-ENV-07 | `case_path` contains no spaces and no non-ASCII characters (F13) | ERROR |
| W-ENV-08 | WSL `nproc` ≥ 4 when `parallel="Y"` (F18) | WARN |
| W-ENV-09 | Free disk space on the case drive ≥ the estimated need (cells × fields × time dirs) | WARN |
| W-ENV-10 | `matplotlib` importable when `plot_residuals=True` | WARN |
| I-ENV-11 | Record SALOME version, OpenFOAM version, distro and `nproc` into `validation_report.json` for reproducibility | INFO |

**`nemos.doctor()`** — a public one-shot function that runs only §2.1 and prints a pass/fail
table. This should be the first thing a new user is told to run, and it is the fastest way to
triage an "it does not work" report.

### 2.2 Configuration (`*-CFG-*`)

| Code | Check | Sev |
|---|---|---|
| E-CFG-01 | Every `Simulation(...)` kwarg is recognised; unknown → error with a `difflib.get_close_matches` suggestion (F1). This single check removes the worst silent failure in the library | ERROR |
| E-CFG-02 | `endTime > startTime`; `deltaT > 0`; `writeInterval ≥ 1`; all numeric and finite | ERROR |
| E-CFG-03 | `delta` and `deltaT` both given with conflicting values | ERROR |
| E-CFG-04 | `parallel` is `Y`/`N` (case-insensitive) | ERROR |
| E-CFG-05 | `internalField` strings parse as `uniform <scalar>` / `uniform (x y z)` | ERROR |
| W-CFG-06 | **Iteration budget**: `(endTime − startTime)/deltaT` is the SIMPLE iteration count, not seconds. Warn below ~500 iterations for a buoyant room case (F33). The message must state the arithmetic explicitly: `endTime=20, delta=0.1 → 200 iterations` | WARN |
| W-CFG-07 | Time directories `= iterations/writeInterval` > 50 → disk/IO warning with the estimated total size (F35) | WARN |
| I-CFG-08 | `startTime` is inert because of `startFrom latestTime` (F34) | INFO |
| W-CFG-09 | An accepted inline key is not implemented by `BoundaryManager` — `metabolic_heat_W`, `emissivity`, `species_source`, `supply_T_C`, `supply_velocity_m_s`, `flow_profile`, `material` (F4). Must name the key and say plainly that it has no effect | WARN |

### 2.3 Geometry (`*-GEO-*`)

This is the only part that needs new domain logic: a **static shape-spec table** giving a
conservative bounding volume per class as a function of its kwargs, derived from the
constructors in `GeoMesh.py`. Roughly 80 lines, no SALOME needed.

| Class | Conservative extent | Source |
|---|---|---|
| `Room` | `[0,dx] × [0,dy] × [0,dz]` | [GeoMesh.py:93-102](../../src/GeoMesh.py#L93-L102) |
| `Person_seated` | vertical `[0, h]`; horizontal disc of radius `√((0.25h + thickness/2)² + width²)` centred on `(x,z)` — rotation-invariant, so `theta` needs no special case. Depth is `2·width`, because the profile is extruded both ways | [GeoMesh.py:762-882](../../src/GeoMesh.py#L762-L882) |
| `Person_standing` | fixed dimensions; read them off `standing()` | [GeoMesh.py:898](../../src/GeoMesh.py#L898) |
| `Dip_type_00..03` | cylinder of radius `≈ d` at `(x,z)`, spanning `y ∈ [H − 0.07 − y_param, H − 0.07]` — i.e. it **hangs from the ceiling** | [GeoMesh.py:1139-1141](../../src/GeoMesh.py#L1139-L1141) |
| `Table_retangular` | `dx × dy × dz` box centred on `(x,z)` at height `y` | [GeoMesh.py:1432-1445](../../src/GeoMesh.py#L1432-L1445) |
| `Table_circular` | disc of radius `raio`, thickness `espessura`, at height `y` | [GeoMesh.py:1463-1469](../../src/GeoMesh.py#L1463-L1469) |

| Code | Check | Sev |
|---|---|---|
| E-GEO-01 | Exactly one `Room`, created **first**. A `Dip` before a `Room` is the F15 crash | ERROR |
| E-GEO-02 | Every geometry kwarg is in the class's whitelist (signatures above) — kills F2, with a suggestion | ERROR |
| E-GEO-03 | `name=` present, unique, matching `^[A-Za-z][A-Za-z0-9_]*$`, and not reserved (`wall`, `outlet`, `inlet_*`, `defaultFaces`, `internalField`) (F25) | ERROR |
| E-GEO-04 | Every object's extent lies inside the room, with a minimum clearance from each wall (F21) | ERROR |
| E-GEO-05 | No two objects' extents overlap (F21) | ERROR |
| E-GEO-06 | Every object created is passed to `Room.add([...])` exactly once; nothing added twice | ERROR |
| E-GEO-07 | **Call order**: `Room` → objects → `insert_*_opening` → `add` → `Mesh` → `create_mesh` → `check_quality`. An opening inserted after `add()` invalidates the face groups (F17). The recorder already stores the ordered event list, so this is a pure sequence check | ERROR |
| E-GEO-08 | Each dip reaches the ceiling (`y_param ≤ H − 0.07`) and does not reach the floor (F16) | ERROR |
| E-GEO-09 | No two dips share `(x, z)` within `1e-6`; each dip's `(x, z)` is strictly inside the ceiling (F22) | ERROR |
| E-GEO-10 | Each opening is fully inside the ceiling/floor rectangle; openings do not overlap each other or a dip axis | ERROR |
| E-GEO-11 | **Total opening area < 20 % of the ceiling area**, i.e. `Σ π·d² < 0.2·dx·dz`, mirroring the `Room.area = 0.8·(two smallest dims)` filter. Beyond that threshold the entire ceiling collapses into one `outlet` patch (F23) | ERROR |
| E-GEO-12 | At least one opening exists when any dip exists — otherwise the domain has inflow and no outflow, and no steady solution (F38) | ERROR |
| W-GEO-13 | `d` in `insert_*_opening` is used as a **radius** by `MakeCircle`; echo the resulting diameter and area so the user sees what they actually asked for (F24) | WARN |
| W-GEO-14 | The gap between any two bodies, and between a body and a wall, exceeds the summed viscous-layer thickness plus ~3 cells (F27) | WARN |

### 2.4 Mesh parameters (`*-MSH-*`)

| Code | Check | Sev |
|---|---|---|
| E-MSH-01 | `m2DMinSize ≤ m2DMaxSize`, `m3DMinSize ≤ m3DMaxSize`, all > 0 | ERROR |
| E-MSH-02 | `fineness ∈ {0,1,2,3,4}` | ERROR |
| E-MSH-03 | `Mesh(room, ...)` receives the `Room`, and `create_mesh` is called exactly once | ERROR |
| W-MSH-04 | Estimated cell count `≈ 6√2·V/h³` with `h = m3DMaxSize`; warn above ~3 M cells, with the RAM and wall-clock estimate | WARN |
| W-MSH-05 | `m3DMaxSize` resolves the smallest feature — at least 3 cells across a dip diameter — unless a local size already covers it (dips get 0.005, persons 0.02, walls 0.05) | WARN |
| W-MSH-06 | The `check_quality` metric is a real `SMESH.FT_*` functor, and `element_type`/`comparison` are in `_ELEMENT_TYPE_MAP` / `_COMPARISON_MAP`, since an unmapped value silently degrades to `SMESH.FACE` / `FT_MoreThan` ([Simulation.py:1973-1974](../../src/Simulation.py#L1973-L1974)) | WARN |

### 2.5 Physics consistency (`*-PHY-*`) — advisory, never blocking

This is the section that teaches. Each item prints the number it computed.

| Code | Check |
|---|---|
| W-PHY-01 | Every `T_Face` / `T_Flow` / `T internalField` lies inside the `fvOptions limitTemperature` window [280, 310]. Outside it the solution is **silently clamped** (F7). Offer the fix: widen the limits, or change the BC |
| W-PHY-02 | Every `\|V_Flow\|` is below the `velocityDampingConstraint` `UMax = 10` (F7) |
| W-PHY-03 | **Sign convention**: ceiling dips supply air downward, so `V_Flow` must be negative. Flag any positive value, and flag any case or sweep that mixes signs across dips (F32, the repo's own `manager_script_mesh.py`) |
| W-PHY-04 | Inlet Reynolds number `\|V\|·2d/ν` with `ν = mu/rho0 = 1e-5`; warn below ~2300 that `kEpsilon` with wall functions is out of range (F37) |
| W-PHY-05 | Air changes per hour `= Σ(\|V_Flow\|·π d²)·3600 / (dx·dy·dz)`; warn outside ~0.5–20 ACH. For an indoor-comfort study this is the single most interpretable number the preflight can print |
| W-PHY-06 | Estimated outlet velocity `= Q_in / Σ opening area`; warn above ~5 m/s (openings too small for the supply) |
| W-PHY-07 | Boussinesq validity: all BC temperatures within ~±15 K of `T0 = 300`; report the Rayleigh number from `ΔT` and `dy` |
| W-PHY-08 | `p internalField` vs the hardcoded `p_rgh` 101325 (F8) |
| W-PHY-09 | Inlet `k = 0.00375` and `mixingLength = 0.0168` are hardcoded; compare against `k = 1.5(I·V)²` at `I = 5 %` for the actual `V_Flow`, and report the discrepancy (F9) |
| I-PHY-10 | **Assumption register**: print the fluid properties actually in use — `rho0 = 1`, `mu = 1e-5`, `Pr = 0.7`, `Cp = 1040`, `beta = 3e-3`, `T0 = 300` — and note that `rho0 = 1` is ~15 % below air at 300 K, so any balance reported in kg/s or W carries that scaling (F36) |

`W-PHY-05` and `W-PHY-06` rely on the estimate `A_inlet ≈ π·d²`. Gate B re-checks both
against the **real** patch areas from the mesh, so a wrong estimate cannot mislead for long.

### 2.6 Stale-case detection (`*-STATE-*`)

Agreed behaviour: fingerprint, abort, instruct — never delete.

`OpenFOAMCase.fingerprint()` writes three independent hashes into `.nemos_state.json`:

| Hash | Covers | Invalidates |
|---|---|---|
| `geometry_hash` | the recorded `machine_script.py` text | `Mesh_1.unv`, `constant/polyMesh/`, `0/`, `processor*/` |
| `bc_hash` | `object_simulation` + `object_types` + the `fields` config | `0/`, `processor*/` |
| `control_hash` | the `controlDict` / `decomposeParDict` config | nothing — a safe change; note it and proceed |

| Code | Check | Sev |
|---|---|---|
| E-STATE-01 | `geometry_hash` changed but `Mesh_1.unv` exists → abort, naming the artifacts to delete (F6) | ERROR |
| E-STATE-02 | `bc_hash` changed but `0/T` exists → abort, naming `0/` and `processor*/` | ERROR |
| I-STATE-03 | `control_hash` changed → report it; the solver simply continues from `latestTime` | INFO |
| W-STATE-04 | `.nemos_done` exists → say so and stop, rather than half-resuming | WARN |

The abort message must be copy-pasteable:

```
[E-STATE-01] The geometry in this script does not match the mesh in the case folder.
    Changed: Person_1.x (2.025 -> 2.4), Room.dy (3.0 -> 2.7)
    The existing Mesh_1.unv was built from the previous geometry.
    -> To rebuild, delete:
         C:\...\script_H_resume\Mesh_1.unv
         C:\...\script_H_resume\constant\polyMesh\
         C:\...\script_H_resume\0\
         C:\...\script_H_resume\processor0..3\
         C:\...\script_H_resume\.nemos_done
       Or point case_path at a new folder to keep both results.
```

---

## 3. Gate B — mesh and boundary validation

Runs after `ideasUnvToFoam` + `checkMesh`, before the solver. Prerequisite edit: the mesh-prep
script must persist its logs (`log.ideasUnvToFoam`, `log.checkMesh`) and check each command's
exit status individually (F20).

### 3.1 `parse_check_mesh(text)` (`*-CHK-*`)

`checkMesh` already runs and its output is already captured — it is simply never read.

| Code | Check | Sev |
|---|---|---|
| E-CHK-01 | `Failed N mesh checks` present, or `Mesh OK` absent | ERROR |
| E-CHK-02 | Negative-volume cells, or zero/negative face areas | ERROR |
| E-CHK-03 | Non-closed cells / open edges | ERROR |
| W-CHK-04 | Max non-orthogonality > 70° | WARN |
| W-CHK-05 | Max skewness > 4 | WARN |
| W-CHK-06 | Max aspect ratio > 100 | WARN |
| W-CHK-07 | Cell count far from the Gate A estimate (factor > 3 either way) | WARN |
| I-CHK-08 | Record cells, faces, points and the bounding box | INFO |

### 3.2 Bounding-box continuity (`*-BOX-*`)

| Code | Check | Sev |
|---|---|---|
| E-BOX-01 | The bounding box matches the declared `Room(dx, dy, dz)` within 1 % | ERROR |
| E-BOX-02 | **Unit-scale detection**: if the box is ~1000× the declared size, say "the mesh appears to be in millimetres" rather than reporting a generic mismatch (F28) | ERROR |
| E-BOX-03 | The minimum corner is `≈ (0, 0, 0)` — the whole geometry is built in the first octant | ERROR |

### 3.3 Patch inventory (`*-BND-*`)

Parsed from `constant/polyMesh/boundary` and cross-checked against `object_types`.

| Code | Check | Sev |
|---|---|---|
| E-BND-01 | Every patch resolves to `wall`/`inlet`/`outlet`; list every unmapped patch. This is F3 — the highest-impact single check in Gate B | ERROR |
| E-BND-02 | Every object in `object_types` has its patch present in the mesh | ERROR |
| E-BND-03 | Every dip has a matching `inlet_<name>` patch (F16 leaves it missing) | ERROR |
| E-BND-04 | An `outlet` patch exists with `nFaces > 0` | ERROR |
| E-BND-05 | No patch has `nFaces == 0` — an empty inlet means zero supply air with no error message | ERROR |
| E-BND-06 | No `defaultFaces` patch with `nFaces > 0` (faces that reached no SALOME group) | ERROR |
| W-BND-07 | `_parse_boundary_file`'s `(\w+)\s*\{\s*type\s+(\w+);` regex matched every block — a name or key order it cannot parse must not fail silently ([Simulation.py:942](../../src/Simulation.py#L942)) | WARN |
| W-BND-08 | Real inlet/outlet areas from the mesh vs the Gate A estimates; re-run `W-PHY-05`/`W-PHY-06` with exact numbers | WARN |

### 3.4 Field coverage (`*-FLD-*`), after `generate_all_fields`

| Code | Check | Sev |
|---|---|---|
| E-FLD-01 | All eight files exist: `U T p p_rgh k epsilon nut alphat` — replaces the two-file `fields_ready()` (F10) | ERROR |
| E-FLD-02 | Every field's `boundaryField` names **every** patch in `boundary`, with no extras | ERROR |
| E-FLD-03 | No patch fell through to the `zeroGradient` fallback for `U` — that is a silent free-slip surface (F3) | ERROR |
| E-FLD-04 | Every `inlet_*` patch has a numeric `fixedValue` in both `T` and `U`, and the values match `object_simulation` | ERROR |
| E-FLD-05 | `dimensions` and `class` are correct for each field | ERROR |
| W-FLD-06 | Person/table walls carry the intended `T_Face`; report any that silently fell back to the room temperature. A person with no `T_Face` is not a heat source | WARN |

---

## 4. Gate C — runtime monitoring

### 4.1 Two prerequisites

1. **Persist the solver log unconditionally.** Move the redirection into the bash script
   (`... buoyantSimpleFoam -parallel > log.simulation 2>&1`) and have Python `tail` the file.
   This removes the F19 pipe deadlock, makes `plot_residuals=False` monitorable, and leaves a
   complete log after a crash.
2. **Add a `functions {}` block to the generated `controlDict`**, written by
   `gerar_arquivos_base` ([Simulation.py:235](../../src/Simulation.py#L235)) alongside the
   existing keys:

| Function object | Purpose | Consumed by |
|---|---|---|
| `residuals` (`U`, `h`, `p_rgh`, `k`, `epsilon`) | machine-readable residual history in `postProcessing/` | Gate C, D |
| `fieldMinMax` (`T`, `U`, `p_rgh`, `k`, `epsilon`) | per-iteration bounds; NaN and clamping detection | Gate C, D |
| `patchFlowRate` per `inlet_*` and per `outlet` | mass balance | Gate D |
| `surfaceFieldValue` (area-integrate on each inlet/outlet) | exact patch areas and enthalpy flux | Gate B, D |
| `wallHeatFlux` | energy balance | Gate D |
| `yPlus` (write on final only) | wall-function validity | Gate D |

The `residuals` function object is not redundant with `ResidualPlotter`: the plotter's history
is in memory and is lost on a crash, whereas `postProcessing/residuals/**/residuals.dat`
survives — and that file is what Gate D reads on a resumed or interrupted run.

### 4.2 `LogMonitor` (`*-RUN-*`) — streaming, one line at a time

Sits beside `plotter.feed_line` in the existing loop
([Simulation.py:1386-1389](../../src/Simulation.py#L1386-L1389)).

**Fatal patterns → abort immediately when `validate="strict"`** (kill the process; a diverged
run only wastes hours):

| Code | Pattern / condition |
|---|---|
| E-RUN-01 | `FOAM FATAL ERROR`, `FOAM FATAL IO ERROR` — capture the following lines, which name the missing file or dictionary key |
| E-RUN-02 | `Floating point exception`, `signal 8`, `signal 11` |
| E-RUN-03 | `nan` or `inf` in any residual or in `fieldMinMax` output |
| E-RUN-04 | A residual rising monotonically over N consecutive iterations (N ≈ 20), or exceeding ~1e3 → divergence |
| E-RUN-05 | MPI failure: `not enough slots`, `mpirun noticed that process rank ... exited` |
| E-RUN-06 | Solver exits non-zero, or exits before reaching `endTime` |

**Advisory patterns:**

| Code | Pattern / condition |
|---|---|
| W-RUN-07 | Repeated `bounding k` / `bounding epsilon` / `bounding omega` — a few at startup is normal; hundreds means bad inlet turbulence or a bad mesh |
| W-RUN-08 | `limitTemperature` reporting limited cells → `fvOptions` is masking the physics (F7) |
| W-RUN-09 | `max(U)` sitting at the `UMax = 10` damping ceiling |
| W-RUN-10 | Linear solver hitting its iteration ceiling every outer iteration |
| W-RUN-11 | **Stagnation**: residuals flat (< 5 % change) over ~200 iterations while still above `residualControl` — the classic under-relaxed limit cycle |
| W-RUN-12 | **Stall**: no new line for > 10 min of wall clock → warn; configurable hard timeout |
| I-RUN-13 | `SIMPLE solution converged in N iterations` → record `CONVERGED` |

### 4.3 The Courant number, honestly

The generated `fvSchemes` sets `ddtSchemes { default steadyState; }`
([Simulation.py:370](../../src/Simulation.py#L370)) and the solver is `buoyantSimpleFoam`. **A
steady SIMPLE run has no time step and prints no Courant number**, so a literal
Courant-number check can never fire on the cases NEMOS generates today. Rather than ship a
dead check, this design specifies three things:

1. **A Courant parser that is present but dormant** — `Courant Number mean: X max: Y` — with
   `E-RUN-14` (`max > 1` on a transient run) and `W-RUN-15` (`max > 0.5`). It costs nothing
   and starts working the day a transient solver is added.
2. **The steady-state equivalents**, which are the checks that actually matter here:
   `W-RUN-11` (stagnation), `W-RUN-07` (bounding), and the relaxation-factor sanity note.
3. **A post-hoc cell-Courant/Péclet diagnostic** in Gate D — `postProcess -func CourantNo` on
   the converged field — reported as a mesh-adequacy indicator (where the flow sweeps through
   cells fastest relative to their size), not as a stability criterion.

### 4.4 Structured runtime output

Written continuously to `<case>/monitor.csv`: `iteration, Ux, Uy, Uz, h, p_rgh, k, epsilon,
Tmin, Tmax, Umax, flags`. This is the file a future `NEMOS_SimulationAnalysis` should read,
and it is trivially plottable in a report.

---

## 5. Gate D — post-processing and sanity checks

### 5.1 An honest verdict, and what `.nemos_done` means

`.nemos_done` currently means "the WSL process exited 0" (F5). Replace it with
`<case>/.nemos_status.json`:

```json
{
  "verdict": "CONVERGED | MAX_ITERATIONS | DIVERGED | CRASHED | INCOMPLETE",
  "iterations": 200,
  "final_residuals": {"Ux": 3.1e-3, "h": 8.0e-4, "p_rgh": 2.2e-3},
  "residual_control_met": false,
  "mass_imbalance_pct": 0.42,
  "energy_imbalance_pct": 3.1,
  "checks": {"errors": 0, "warnings": 4},
  "wall_clock_s": 4831
}
```

`.nemos_done` is written **only** for `CONVERGED`, and additionally for `MAX_ITERATIONS` when
the user explicitly opts in. This matters for sweeps: `Manager.resume()` skips any `SIM_i`
that has a `.nemos_done` marker ([Manager.py:400-403](../../src/Manager.py#L400-L403)), so today
an unconverged SIM is skipped permanently. `MAX_ITERATIONS` must print:

```
[W-POST-01] The solver reached endTime without meeting residualControl (1e-6).
    Final: p_rgh 2.2e-03, U 3.1e-03, h 8.0e-04  after 200 iterations.
    This result is NOT converged and should not be reported as a steady solution.
    -> Increase endTime (endTime/delta = iterations; 200 is very few for a
       buoyant room). Try endTime=200 with delta=0.1 for 2000 iterations.
```

### 5.2 Global conservation balances (`*-BAL-*`)

The most valuable post-check, because a converged-looking run with a 5 % mass imbalance is
not converged. Inputs are the `patchFlowRate` / `surfaceFieldValue` / `wallHeatFlux` outputs
from §4.1.

| Code | Check | Sev |
|---|---|---|
| E-BAL-01 | **Mass**: `\|Σ ṁ\| / Σ\|ṁ_in\| < 1e-3` over all inlets and outlets | ERROR |
| W-BAL-02 | The same ratio in 1e-4…1e-3 → borderline, probably under-converged | WARN |
| E-BAL-03 | **Energy**: `\|Σ(ṁ·h)_boundary + Σ Q_wall\| < 1 %` of the total wall heat input | ERROR |
| W-BAL-04 | Net flow through a single `outlet` is *into* the domain while all supplies are inlets — usually a sign inversion (F32) | WARN |
| I-BAL-05 | Report the balance table in W and kg/s, with the `rho0 = 1` caveat from `I-PHY-10` attached | INFO |

### 5.3 Field sanity (`*-FSAN-*`)

| Code | Check | Sev |
|---|---|---|
| E-FSAN-01 | No `nan`/`inf` in any final field | ERROR |
| E-FSAN-02 | **Boundedness**: with no volumetric heat source, `min/max(T)` in the domain must lie within `[min, max]` of the temperature BCs, plus a small tolerance. A violation means numerical trouble, not physics | ERROR |
| E-FSAN-03 | `min(k) ≥ 0`, `min(epsilon) > 0`, `min(nut) ≥ 0` | ERROR |
| W-FSAN-04 | `max(T)` or `min(T)` sitting exactly on the `fvOptions` limit (310/280) → the limiter shaped the answer (F7) | WARN |
| W-FSAN-05 | `max\|U\|` at the damping ceiling of 10, or > 3× the inlet velocity away from the jet | WARN |
| W-FSAN-06 | **y+**: per-patch min/mean/max from the `yPlus` function object. `kqRWallFunction` / `nutkWallFunction` / `epsilonWallFunction` / `alphatJayatillekeWallFunction` want roughly 30–300; report the fraction of each patch outside that band. With a 0.030 m viscous stack on walls and 0.0025 m on dips, this is exactly where the mesh design should be questioned | WARN |
| W-FSAN-07 | Cell-Courant/Péclet from `postProcess -func CourantNo` on the converged field (§4.3) | WARN |
| I-FSAN-08 | Report volume-averaged `T`, mean age of air if computed, and per-patch heat flux — the physically meaningful summary for a thermal-comfort case | INFO |

### 5.4 Artifact completeness (`W-ART-*`)

| Code | Check |
|---|---|
| W-ART-01 | At least one time directory beyond `0/` was written |
| W-ART-02 | `residuals.png`, `log.simulation`, `monitor.csv` and `validation_report.json` are all present |
| W-ART-03 | `reconstructPar` has been run — or the user is told that results still live in `processor*/` and that ParaView will not see them through `caso.foam` |
| W-ART-04 | Any `*_summary.txt` / `*_df.csv` from `check_quality` is present, with the flagged-element count echoed |

---

## 6. Sweep-level guardrails (`Manager.py`)

| Code | Check | Sev |
|---|---|---|
| E-SWP-01 | Sweep lists equal length and non-empty — **already implemented** at [Manager.py:59-72](../../src/Manager.py#L59-L72); reuse it, do not duplicate | ERROR |
| E-SWP-02 | A list-valued kwarg reached a recording proxy but was **not** recognised as a sweep list (built by comprehension, or defined inside a function). Today it is embedded literally into all N scripts and every SIM is identical (F29) | ERROR |
| E-SWP-03 | `script_path=__file__` was passed; without it `_load_list_names` returns an empty set | ERROR |
| E-SWP-04 | `SIM_i` directories exist beyond the current sweep length → a stale sweep in this folder (F31) | ERROR |
| E-SWP-05 | **Preflight all N before running any.** Render the scripts, then execute each with `NEMOS_VALIDATE=preflight-only` so `run()` stops after Gate A, and aggregate into one table. This is the single biggest win for sweeps: a bad `T_Flow` in `SIM_4` is reported in seconds instead of after `SIM_0..3` have run for hours (F30) | ERROR |
| W-SWP-06 | Shared-mesh mode (`_mesh_uses_sweep()` false) → state plainly that `SIM_0` builds the mesh and `SIM_1..N` import it, so a `SIM_0` mesh failure blocks everything | WARN |
| W-SWP-07 | The sign or magnitude of a swept `V_Flow` / `T_Flow` is inconsistent across indices (F32) | WARN |
| I-SWP-08 | Print the full sweep matrix (index × parameter) before starting, plus the estimated total wall-clock time | INFO |

The preflight-all pass gives the sweep a natural summary:

```
Sweep preflight — C:\...\Manager_Condition_Test  (5 SIMs)
  SIM_0  OK       2 warnings
  SIM_1  OK       2 warnings
  SIM_2  OK       2 warnings
  SIM_3  ERROR    [E-CFG-02] endTime=5, delta=0.1 -> 50 iterations
  SIM_4  ERROR    [W-PHY-01] T_Person_Face=312 exceeds the fvOptions
                             limitTemperature max of 310 -> would be clamped
                  [E-GEO-11] openings total 2.04 m2 > 20% of the 9 m2 ceiling
Aborting before SIM_0 starts: 2 of 5 configurations are invalid.
```

---

## 7. Implementation phases

Ordered by value per unit of effort. Each phase is independently shippable and leaves the
library working.

| Phase | Content | Files |
|---|---|---|
| **1** | `Validation.py` skeleton — `Issue`, `ValidationReport`, policy resolution, console renderer, `NemosValidationError`. Plus the §2.1 environment checks and `nemos.doctor()` | new `src/Validation.py`; small hook in `Simulation.py` |
| **2** | Config checks §2.2 — **starting with `E-CFG-01`** (unknown kwargs). Highest value-to-effort ratio in the whole plan: ~30 lines, removes the worst silent failure | `Validation.py`, `Simulation.__init__` |
| **3** | Geometry model + §2.3/§2.4 — the shape-spec table, the event list on the recorder, the call-order check | `Validation.py`, `_register_object`, `_record_method` |
| **4** | Stale-case fingerprinting §2.6 | `OpenFOAMCase`, `save_state`/`load_state`, `run` |
| **5** | Mesh-prep hardening + Gate B §3 — `set -o pipefail`, persisted logs, `checkMesh` parsing, patch/field coverage | `preparar_malha`, `editar_boundary`, `generate_all_fields` |
| **6** | Gate C §4 — log redirection to file (fixes F19), `LogMonitor`, `monitor.csv`, `functions {}` in `controlDict` | `rodar_simulacao`, `_rodar_simulacao_com_plot`, `gerar_arquivos_base` |
| **7** | Gate D §5 — verdict, `.nemos_status.json`, conservation balances, field sanity, y+ | `run`, `Validation.py` |
| **8** | Sweep guardrails §6, including the preflight-all pass | `Manager.py` |
| **9** | Physics advisories §2.5 and a troubleshooting table in `docs/` keyed by check code | `Validation.py`, `docs/` |

Phases 1–4 need neither SALOME nor OpenFOAM to develop or test.

---

## 8. Verification

The guardrail layer must be verifiable without a two-hour solver run. Every parser takes text,
so:

1. **Fixture-based unit tests** — `tests/fixtures/` holding a real `log.checkMesh`, a real
   `log.simulation` from a converged run, one from a diverged run, one truncated
   mid-iteration, and a real `boundary` file. Assert the exact issue codes each produces.
   These fixtures must be captured from a real run first: the parsers in §3.1 and §4.2 are the
   only part of this design whose string patterns need calibration against actual output
   before they can be trusted.
2. **Negative-path scripts** — small variants of [user_script_H.py](../../examples/01_single_run.py),
   each rigged to trip exactly one check, asserting the code fires and that nothing expensive
   ran: `endtime=20` (E-CFG-01), `Thickness=0.15` (E-GEO-02), a person at `x=5.0` in a 3 m
   room (E-GEO-04), openings after `add()` (E-GEO-07), `T_Face=320` (W-PHY-01),
   `case_path="D:\..."` (E-ENV-05), openings with `d=0.5` (E-GEO-11).
3. **Golden-path regression** — [user_script_H.py](../../examples/01_single_run.py) unchanged must
   pass Gate A with zero errors and exactly the expected warnings (`W-CFG-06` on 200
   iterations, `W-PHY-09` on hardcoded inlet turbulence). This is the test that the guardrails
   do not block real work.
4. **`nemos.doctor()`** on the development machine — expect all green.
5. **End-to-end**, once, on a deliberately coarse mesh with ~300 iterations: confirm Gate B
   parses the real `checkMesh` output, Gate C writes `monitor.csv`, Gate D reports a
   `MAX_ITERATIONS` verdict with a real mass balance, and `.nemos_done` is **not** written.
6. **Sweep**, once: [manager_script_original.py](../../examples/03_sweep_conditions.py) with one
   deliberately bad index, confirming it aborts before `SIM_0` starts.
7. **Stale case**: run a case, edit `Room(dy=...)`, re-run, and confirm `E-STATE-01` fires with
   the correct artifact list and that nothing was deleted.

---

## 9. Assumptions to confirm during implementation

Recorded explicitly so that nobody implements them as though they were verified facts:

1. **SALOME `ViscousLayers(0.030, 5, 1.2, ...)`** — `W-GEO-14` assumes the first argument is
   the *total* stack thickness. Confirm against the SALOME 9.15 API; if it is the first-layer
   thickness, the wall stack is ~0.22 m and the gap check changes materially.
2. **Dip inlet area `≈ π·d²`** — inferred from the `F3` revolution profile at
   [GeoMesh.py:1089-1118](../../src/GeoMesh.py#L1089-L1118). This only affects the Gate A
   *estimates* (`W-PHY-05`, `W-PHY-06`); Gate B measures the real area.
3. **Exact log strings** for `bounding`, `limitTemperature` and `SIMPLE solution converged in`
   in OpenFOAM v2312 — must be calibrated against a captured log (Verification item 1).
   Patterns should be tolerant regexes, and an unrecognised log must degrade to "cannot
   verify", never to a false pass.
4. **`patchFlowRate` sign convention**, and whether it reports mass or volume flow for
   `buoyantSimpleFoam` — this determines the `E-BAL-01` formula.
5. **The 20 % opening-area threshold** in `E-GEO-11` follows from `Room.area = 0.8·(two
   smallest dims)` at [GeoMesh.py:73](../../src/GeoMesh.py#L73). Confirm with one deliberate
   over-opening test that the ceiling really does collapse into a single `outlet` patch.
6. **`rho0 = 1`** is flagged as a consistency note (`I-PHY-10`), not corrected. If it is a
   deliberate normalisation, this document should say so; if it is an oversight, fixing it is a
   physics change, separate from the guardrail work.

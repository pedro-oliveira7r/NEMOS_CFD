# NEMOS_CFD

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![OpenFOAM v2312](https://img.shields.io/badge/OpenFOAM-v2312-green)](https://openfoam.com)
[![SALOME 9.15](https://img.shields.io/badge/SALOME-9.15.0-orange)](https://www.salome-platform.org/)

**NEMOS_CFD automates the entire OpenFOAM workflow for indoor thermal-comfort
simulations** — from a handful of lines of Python describing a room to a solved,
post-processed CFD case.

You describe the geometry (a room, seated people, air diffusers, tables) in a
short Python script. NEMOS builds it in SALOME, meshes it, converts the mesh to
OpenFOAM, writes every dictionary and boundary condition, runs the solver under
WSL, and plots the residuals live. Parameter sweeps run the same script N times
with N sets of values.

```python
sim = nemos.Simulation(case_path=..., endTime=20, parallel="Y")

room = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=300, name="Room")
p1   = nemos.Person_seated(x=2.025, z=1.5, T_Face=304, name="Person_1")
dip1 = nemos.Dip_type_01(x=2.025, y=1.0, z=1.5, V_Flow=-1.2, T_Flow=291, name="Dip_1")
room.add([p1, dip1])

mesh = nemos.Mesh(room, m3DMaxSize=0.075, fineness=3)
mesh.create_mesh(export=True)

nemos.run(sim)          # SALOME -> OpenFOAM -> solver, all of it
```

> **Research software.** NEMOS was written for an undergraduate thesis (TCC) on
> indoor thermal comfort. It is actively developed, targets one specific
> toolchain, and has the rough edges listed under

## Features

- **One script, whole pipeline** — geometry, meshing, case setup, solving, and
  post-processing from a single Python file.
- **Parametric sweeps** — turn any value into a list and NEMOS runs one
  simulation per entry, reusing the mesh when the geometry does not change.
- **Resumable** — every stage is gated on an artifact on disk. Re-running skips
  what is already done, and the solver continues from its last written timestep.
- **Boundary conditions from the geometry** — set `T_Face` on a person or
  `T_Flow`/`V_Flow` on a diffuser and the matching OpenFOAM patch conditions are
  written for you across all eight fields.
- **Live residual plots** — parsed from solver stdout and saved as
  `residuals.png`.
- **Post-processing included** — slice images, point sampling, and
  structured-grid exports to Excel/CSV via PyVista.

## Requirements

NEMOS is a Windows host driving two external tools — SALOME natively, and
OpenFOAM inside WSL. All four pieces are needed.

| Component | Version | Runs where | Used for |
|---|---|---|---|
| Windows | 10 or 11 | host | case paths are translated `C:\…` to `/mnt/c/…` for WSL |
| Python | 3.9+ | host | the driver itself |
| SALOME | 9.15.0 | host (native Windows) | geometry construction and meshing |
| WSL2 + Ubuntu | 22.04 / 24.04 | WSL | hosts OpenFOAM |
| OpenFOAM | v2312 | WSL | `ideasUnvToFoam`, `buoyantSimpleFoam`, `decomposePar` |

The solver runs in parallel over a **fixed 4 subdomains**, so 4 usable cores are
assumed. Set `parallel="N"` to run serially instead.

## Installation

### 1. Clone

```bash
git clone https://github.com/pedro-oliveira7r/NEMOS_CFD.git
cd NEMOS_CFD
```

### 2. Install the Python dependencies

```bash
pip install -r requirements.txt
```

These are for the host driver and the post-processing modules. The core of
`Simulation.py` and `Manager.py` is pure standard library.

### 3. Install `GeoMesh.py` into SALOME — easy to miss

This is the step nothing else will remind you about. `src/GeoMesh.py` is the half
of NEMOS that runs *inside* SALOME, and SALOME's embedded Python cannot see your
repository. Copy it into SALOME's `site-packages`:

```powershell
Copy-Item src\GeoMesh.py "C:\SALOME-9.15.0\W64\Python\lib\site-packages\GeoMesh.py"
```

Adjust the path if SALOME is installed elsewhere, and re-copy whenever
`GeoMesh.py` changes. SALOME 9.15.0 already ships the `pandas` and `numpy` that
`GeoMesh.py` imports, so nothing else needs installing there.

### 4. Verify OpenFOAM in WSL

```bash
wsl bash -c "source /usr/lib/openfoam/openfoam2312/etc/bashrc && which buoyantSimpleFoam ideasUnvToFoam"
```

Both commands should print a path. If they do not, see
[docs/installation.md](docs/installation.md).

### 5. Point NEMOS at your environment

There is no config file yet — two paths are compiled into the source. Check them
against your machine:

| What | Where | Default |
|---|---|---|
| SALOME launcher | `DEFAULT_SALOME_EXE`, [src/Simulation.py:13](src/Simulation.py#L13) | `c:\SALOME-9.15.0\run_salome.bat` |
| OpenFOAM environment | [src/Simulation.py:1227](src/Simulation.py#L1227) and [:1298](src/Simulation.py#L1298) | `/usr/lib/openfoam/openfoam2312/etc/bashrc` |

The SALOME path can also be overridden per call without editing anything:

```python
nemos.run(sim, salome_exe=r"D:\SALOME-9.15.0\run_salome.bat")
```

## Quick start

Run the smallest complete example:

```bash
python examples/01_single_run.py
```

It builds a 3 × 3 × 3 m room with two seated people, two air diffusers and a
circular table, meshes it, and solves it — roughly 15–40 minutes, most of that
meshing. Results land in `cases/01_single_run/`.

The script itself is about twenty lines:

```python
import Simulation as nemos

sim = nemos.Simulation(
    case_path=str(CASE_PATH),
    startTime=0, endTime=20, delta=0.1, writeInterval=3,
    parallel="Y",
    T_internalField="uniform 300",
    p_internalField="uniform 101322",
)

a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, T_Face=300, name="Room")
b = nemos.Person_seated(x=2.025, z=1.5, theta=0, thickness=0.15, T_Face=304, name="Person_1")
c = nemos.Person_seated(x=0.975, z=1.5, theta=180, thickness=0.15, T_Face=305, name="Person_2")
d = nemos.Dip_type_01(x=2.025, y=1.0, z=1.5, V_Flow=-1.2, T_Flow=291, name="Dip_1")
f = nemos.Table_circular(x=1.5, y=0.6, z=1.5, T_Face=300, name="Table")

a.insert_ceiling_opening(x=0.5, z=2.5, d=0.1)
a.add([b, c, d, f])

mesh = nemos.Mesh(a, m2DMaxSize=0.2, m2DMinSize=0.02,
                  m3DMaxSize=0.075, m3DMinSize=0.001, fineness=3)
mesh.create_mesh(export=True)

case = nemos.run(sim)
```

Then post-process it:

```bash
python examples/06_analysis.py
```

Every geometry object **must** be given a `name=` — the OpenFOAM patch names and
their boundary conditions are derived from it.

See [examples/README.md](examples/README.md) for the other eight examples.

## How it works

NEMOS has two layers, and this is the one thing worth understanding before
reading the source:

1. **The host driver** (`src/Simulation.py`, `src/Manager.py`) runs in ordinary
   CPython. The `Room`, `Person_seated` and `Mesh` classes it exposes are **thin
   recording proxies** — they build no geometry. They capture each call and emit
   a line of Python into a generated `machine_script.py`.
2. **The SALOME engine** (`src/GeoMesh.py`) runs inside SALOME's embedded Python
   and holds the same class names for real. SALOME is launched in batch mode on
   the generated script, and *that* is where the geometry and mesh are built.

The host then converts the mesh, writes the OpenFOAM dictionaries and fields, and
drives the solver through WSL.

Full detail in [ARCHITECTURE.md](ARCHITECTURE.md); the stage-by-stage pipeline is
in [docs/workflow.md](docs/workflow.md).

## Project structure

```text
NEMOS_CFD/
├── src/                            the library
│   ├── Simulation.py               host driver: recording, case setup, solver
│   ├── Manager.py                  parameter sweeps
│   ├── GeoMesh.py                  SALOME-side geometry/mesh engine
│   ├── NEMOS_SimulationAnalysis.py post-processing (slices, probes, export)
│   └── NEMOS_MeshAnalysis.py       mesh-focused analysis
├── examples/                       nine runnable scripts, numbered
├── docs/                           installation, workflow, API reference
│   └── roadmap/                    designs not yet implemented
├── experimental/                   unfinished, unsupported
├── ARCHITECTURE.md                 internal design reference
└── requirements.txt
```

## What a finished case contains

| Path | Contents |
|---|---|
| `0/` | `U T p p_rgh k epsilon nut alphat` — generated initial and boundary fields |
| `constant/` | `thermophysicalProperties`, `turbulenceProperties`, `g`, `polyMesh/` |
| `system/` | `controlDict`, `fvSchemes`, `fvSolution`, `fvOptions`, `decomposeParDict` |
| `Mesh_1.unv` | the SALOME mesh, before conversion |
| `processor0..3/` | decomposed domains (parallel runs only) |
| `machine_script.py` | the recorded SALOME script that built the geometry |
| `comandos_1.sh`, `comandos_2.sh` | the WSL scripts for mesh prep and solving |
| `log.simulation` | full solver stdout |
| `residuals.png` | residual convergence plot |
| `caso.foam` | empty marker file for ParaView / PyVista |
| `.nemos_state.json` | saved config, so the case can be resumed by folder |
| `.nemos_done` | written when the solver exits successfully |

A sweep root additionally holds `SIM_0…SIM_N/`, `scripts/script_i.py` and `logs/`.

## Documentation

| Document | What it covers |
|---|---|
| [docs/installation.md](docs/installation.md) | Full environment setup and a troubleshooting table |
| [docs/workflow.md](docs/workflow.md) | The pipeline stage by stage, and how resume works |
| [docs/api-reference.md](docs/api-reference.md) | Every class, method and keyword argument |
| [examples/README.md](examples/README.md) | What each example demonstrates |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Internal design, for contributors |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up a dev environment and report bugs |

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Because the toolchain is specific, bug reports are far more useful with your
SALOME, OpenFOAM, WSL and Python versions attached; the issue template asks for
them.

## Citation

If NEMOS_CFD contributes to published work, a link back to this repository is
appreciated.

## License

Distributed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).

## Acknowledgements

Built on [OpenFOAM](https://openfoam.com),
[SALOME](https://www.salome-platform.org/) and
[PyVista](https://pyvista.org/).

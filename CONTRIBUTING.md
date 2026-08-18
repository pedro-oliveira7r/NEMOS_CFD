# Contributing to NEMOS_CFD

Thanks for looking. NEMOS is research software with a demanding toolchain, so a
few things are worth knowing before you start.

## Setting up

Follow [docs/installation.md](docs/installation.md) in full — SALOME, WSL2 and
OpenFOAM v2312 all have to work before any change can be tested. Then confirm the
baseline runs on your machine:

```bash
python examples/01_single_run.py
```

If that fails before you have changed anything, fix the environment first. Nothing
else is diagnosable until it passes.

### The one setup trap

`src/GeoMesh.py` runs inside SALOME's own Python, from SALOME's `site-packages`.
Editing the file in your clone changes nothing until you copy it across:

```powershell
Copy-Item src\GeoMesh.py "C:\SALOME-9.15.0\W64\Python\lib\site-packages\GeoMesh.py"
```

Do this after **every** edit to `GeoMesh.py`. A stale installed copy fails
silently — you get the old geometry with no warning at all.

## How the code is organised

| Path | Contains |
|---|---|
| `src/` | the library — five modules, nothing else |
| `examples/` | every runnable script |
| `docs/` | user documentation |
| `docs/roadmap/` | designs not implemented |
| `experimental/` | unfinished, unsupported |

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing anything in `src/`. The
host/SALOME split is not obvious from the code, and getting it wrong is the most
common way to waste an afternoon: the `Room` and `Mesh` classes in
`Simulation.py` are *recorders* that emit text; the ones that build geometry are
the same-named classes in `GeoMesh.py`.

## Testing

**There is no automated test suite.** Changes are verified by running the
examples. Please state in your pull request which ones you ran and what the
outcome was.

| If you changed | Run at least |
|---|---|
| `Simulation.py` | `examples/01_single_run.py` end to end |
| `GeoMesh.py` | `examples/01_single_run.py` **and** `examples/02_classroom.py` (different object mix) |
| `Manager.py` | `examples/03_sweep_conditions.py` — check that SIM_1+ import SIM_0's mesh |
| `NEMOS_*Analysis.py` | `examples/07_analysis_full.py` against a finished case |
| docs or examples only | say so; no simulation needed |

A cheap syntax check before you commit:

```bash
python -c "import sys; sys.path.insert(0,'src'); import Simulation, Manager; print('ok')"
python -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read()) for f in sys.argv[1:]]" examples/*.py
```

`GeoMesh.py` cannot be imported outside SALOME — that failure is expected.

Contributions that add real tests are very welcome. The obstacle is that the
pipeline needs SALOME and OpenFOAM, so the useful first step is probably unit
tests for the parts that do not: config merging, the recording mechanism, patch
name classification, `Manager`'s sweep-list validation.

## Style

Match what is already there rather than reformatting.

- Existing comments are largely in Portuguese; new user-facing text (docs,
  READMEs, example headers, error messages) should be English.
- No formatter or linter is enforced. Keep diffs small and focused.
- Do not commit generated artifacts — `cases/`, `__pycache__/`, `*.unv`, logs and
  `.nemos_*` markers are all git-ignored for a reason.

## Reporting a bug

Because four separate pieces of software are involved, a report without version
information usually cannot be acted on. The
[issue template](.github/ISSUE_TEMPLATE/bug_report.yml) asks for:

- OS, Python version, SALOME version, OpenFOAM version, WSL distro
- Which example or script triggered it
- The **full** traceback, plus the SALOME or WSL output above it
- Whether `examples/01_single_run.py` works on the same machine

That last one separates "NEMOS has a bug" from "the environment is not set up",
which is by far the more common cause.

## Pull requests

1. Branch from `main`.
2. Keep the change focused — one concern per PR.
3. Say which examples you ran.
4. Update the docs when behaviour changes, especially
   [docs/api-reference.md](docs/api-reference.md) if you touch a signature or a
   keyword argument.

## Licence

Contributions are accepted under the [GPL-3.0](LICENSE) that covers the project.

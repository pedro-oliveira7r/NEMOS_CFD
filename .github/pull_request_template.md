## What this changes

<!-- One or two sentences. If it fixes an issue, add "Fixes #123". -->

## Why

<!-- The problem being solved. Skip if it is obvious from the above. -->

## How it was verified

There is no automated test suite, so please say what you actually ran.

- [ ] `examples/01_single_run.py` — completed, produced `.nemos_done`
- [ ] `examples/02_classroom.py`
- [ ] `examples/03_sweep_conditions.py`
- [ ] `examples/07_analysis_full.py` against a finished case
- [ ] Syntax/import check only (`import Simulation, Manager`)
- [ ] Documentation or examples only — no simulation needed

<!-- Paste the relevant output, or attach residuals.png if the physics changed. -->

## Checklist

- [ ] I read [ARCHITECTURE.md](../blob/main/ARCHITECTURE.md) if I touched `src/`
- [ ] If I changed `GeoMesh.py`, I re-copied it into SALOME's `site-packages` before testing
- [ ] [docs/api-reference.md](../blob/main/docs/api-reference.md) updated if a signature or keyword argument changed
- [ ] No generated artifacts committed (`cases/`, `__pycache__/`, `*.unv`, logs, `.nemos_*`)
- [ ] The change is focused on one concern

## Notes for the reviewer

<!-- Anything you are unsure about, or that needs testing on a different setup. -->

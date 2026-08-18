# NEMOS stress suite

Automated end-to-end runs that drive the real **Python → SALOME → OpenFOAM** chain and then
inspect what came out. They are deliberately harder than the example scripts: each one targets
a place where the library is expected to strain.

These are *harnesses*, not templates to copy. For a starting point for your own case, use
`user_script_base.py` in this folder.

---

## Quick start

```bash
# Validate every case in seconds - no SALOME, no OpenFOAM, nothing executed
NEMOS_VALIDATE=preflight-only python Templates/run_all_stress.py

# Check the machine is actually usable
python -c "import sys; sys.path.insert(0,'src'); import Validation; Validation.doctor()"

# The two short runs (~25 min total)
python Templates/run_all_stress.py --quick

# Everything, cheapest first
python Templates/run_all_stress.py

# One script on its own
python Templates/stress_04_corridor.py
```

Always do the preflight dry run first. It executes the real scripts through the real recording
proxies and Gate A, so it catches a bad geometry or a typo in seconds instead of forty minutes
into a meshing stage.

---

## The suite

| # | Script | Targets | Rough cost |
|---|---|---|---|
| 01 | `stress_01_baseline.py` | Every stage once, coarse mesh. Run this first — if it fails, nothing else matters. | ~10 min |
| 06 | `stress_06_resume.py` | Idempotency: two phases against one case folder, asserting the second **continues** rather than restarting. | ~15 min |
| 04 | `stress_04_corridor.py` | A 10 × 2.4 × 2.0 m room. Extreme aspect ratio, and the hardcoded `n (1 4 1)` decomposition slicing the *short* axis. | ~30 min |
| 02 | `stress_02_crowd.py` | 12 bodies, every geometry class, 18 patches. Hammers `create_faces_groups`, whose inner loop is O(object faces × room faces). | ~60 min |
| 05 | `stress_05_sweep.py` | Manager: 6 simulations, shared-mesh path (`Import_mesh`), sweep preflight, sequential queue. | ~60 min |
| 03 | `stress_03_refinement.py` | Cell count toward the memory ceiling. Three levels via `NEMOS_STRESS_LEVEL`. | hours |

Costs are order-of-magnitude on 4 cores and depend heavily on your machine.

---

## Configuration

| Variable | Meaning |
|---|---|
| `NEMOS_STRESS_ROOT` | Output root. Default `C:\Users\pedro\Desktop\TCC1\STRESS`. **Must be on `C:` with no spaces** — the WSL path translation only rewrites a literal `C:` (`E-ENV-05`). |
| `NEMOS_STRESS_LEVEL` | `coarse` / `medium` / `fine`, for stress 03 only. |
| `NEMOS_VALIDATE` | `preflight-only` forces every script to validate and stop. This one value overrides the `validate=` in the scripts, precisely so a dry run cannot accidentally launch real work. |

Runner flags: `--quick`, `--list`, `--stop-first`, `--timeout <seconds>`, or bare keys
(`python Templates/run_all_stress.py 01 04`). Every run is streamed to the console and saved to
`<root>/logs/<script>.log`.

---

## What "passing" means

A stress run passes when the chain produced a **usable case**: a converted mesh, all eight
`0/` fields, every patch non-empty, and at least one solver iteration. Convergence is *not*
part of the criterion — most of these runs are deliberately far too short for it, and will end
with a `MAX_ITERATIONS` verdict and no `.nemos_done`. That is expected.

Each script prints a result table and exits non-zero on a problem, so the runner can aggregate.
`_stress_lib.report()` builds that table with the validation layer's own parsers, which means a
stress run also exercises Gate B/C/D against *real* OpenFOAM output rather than the synthetic
strings they were written against.

## Warnings you should expect, and ignore

These fire on almost every script and are not failures:

- `W-CFG-06` — few iterations. Deliberate; these runs are about the workflow, not convergence.
- `W-GEO-13` — `d` in `insert_ceiling_opening` is a **radius**, not a diameter.
- `W-GEO-14` — tight clearance between a diffuser and someone's head. Real, and inherent to
  putting a ceiling diffuser directly above an occupant.
- `W-PHY-09` — inlet `k` is hardcoded regardless of the supply velocity.
- `I-PHY-10` — `rho0 = 1 kg/m³`, about 15 % below air. Any result quoted in kg/s or W inherits
  that scaling.

## Things worth watching for

The suite exists to find these, so read past the pass/fail line:

- **Stress 04** — compare solver time per iteration against stress 01. Four 0.6 m slabs across a
  10 m corridor is a poor decomposition, and this is where that should show.
- **Stress 02** — how long the meshing stage takes relative to stress 01. The face-group matching
  grows with the number of bodies; check every one of the 18 patches came out non-empty.
- **Stress 03 at `fine`** — where NETGEN, `ideasUnvToFoam` or `decomposePar` gives up first, and
  whether the viscous layers collapse (the `Volume3D` quality check catches that).
- **Stress 06** — phase 2 must run roughly 200 iterations, not 300. Three hundred means it
  silently restarted.

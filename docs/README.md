# NEMOS_CFD documentation

| Document | Read it when |
|---|---|
| [installation.md](installation.md) | Setting the environment up, or something in the toolchain is failing |
| [workflow.md](workflow.md) | You want to know what happens between `nemos.run(sim)` and a solved case |
| [api-reference.md](api-reference.md) | You need the exact classes, methods and keyword arguments |
| [../examples/README.md](../examples/README.md) | You want a script to start from |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | You are changing the library itself |
| [roadmap/](roadmap/) | You want to know where this is going — **designs, not shipped behaviour** |

## Suggested path for a new user

1. [installation.md](installation.md) — get SALOME, WSL and OpenFOAM in place.
   Do not skip installing `GeoMesh.py` into SALOME.
2. Run [`examples/01_single_run.py`](../examples/01_single_run.py).
3. [api-reference.md](api-reference.md) — change the geometry to your own room.
4. [`examples/06_analysis.py`](../examples/06_analysis.py) — look at the results.
5. [`examples/03_sweep_conditions.py`](../examples/03_sweep_conditions.py) — turn
   it into a parametric study.

## The one concept to grasp first

NEMOS is split across two Python interpreters. The classes you call in your
script (`Room`, `Person_seated`, `Mesh`) are **recorders** — they write a script
that SALOME executes later, in its own embedded Python, against identically named
classes in `GeoMesh.py`. If you go looking for the geometry code in
`Simulation.py`, you will not find it; it is in `GeoMesh.py`.

[workflow.md](workflow.md) walks through what that means in practice.

# Experimental

Unfinished work kept for reference. **Nothing here is supported, tested, or
imported by the library.** It is not part of the pipeline described in
[../ARCHITECTURE.md](../ARCHITECTURE.md).

## `GeoMesh_Test.py`

An in-progress extension of the SALOME-side geometry engine
([../src/GeoMesh.py](../src/GeoMesh.py)) adding building-envelope objects:

- `Window` — a rectangular opening placed on a wall face
- `ACUnit` — a wall-mounted air-conditioning unit
- `Room` — a subclass of `GeoMesh.Room` that knows how to host them

It is imported by no script in the repository. Treat it as a sketch of where the
geometry library might go, not as something you can call today. Like `GeoMesh.py`
it can only run inside SALOME's embedded Python.

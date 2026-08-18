# Installation

NEMOS coordinates three environments. Getting each one right matters more than
anything else in this repository, so this page is deliberately literal.

| Environment | What lives there |
|---|---|
| **Windows host** | your Python, the NEMOS driver (`Simulation.py`, `Manager.py`), the analysis modules |
| **SALOME's embedded Python** | `GeoMesh.py` — a *separate* Python 3.9 with its own `site-packages` |
| **WSL2 / Ubuntu** | OpenFOAM v2312 |

They do not share packages. Installing something with `pip` on the host does
**not** make it available inside SALOME.

---

## 1. Windows and Python

Windows 10 or 11, and Python 3.9 or newer on `PATH`.

```powershell
python --version
```

NEMOS assumes Windows because it translates case paths (`C:\Users\...`) into WSL
paths (`/mnt/c/Users/...`) when it invokes OpenFOAM.

## 2. WSL2 with Ubuntu

```powershell
wsl --install -d Ubuntu-24.04
wsl --status                 # confirm "Default Version: 2"
```

Ubuntu 22.04 works as well.

## 3. OpenFOAM v2312 inside WSL

Install the ESI (`openfoam.com`) release — **not** the Foundation `openfoamN`
packages, whose paths and solver set differ.

```bash
wsl
sudo sh -c "wget -O - https://dl.openfoam.com/add-debian-repo.sh | bash"
sudo apt-get update
sudo apt-get install openfoam2312-default
```

Verify from the Windows side, exactly as NEMOS will call it:

```bash
wsl bash -c "source /usr/lib/openfoam/openfoam2312/etc/bashrc && which buoyantSimpleFoam ideasUnvToFoam decomposePar"
```

Three paths should print. If the `source` line fails, find the real location with
`ls /usr/lib/openfoam/` and update it in
[../src/Simulation.py:1227](../src/Simulation.py#L1227) and
[:1298](../src/Simulation.py#L1298).

## 4. SALOME 9.15.0

Download the Windows binary from
[salome-platform.org](https://www.salome-platform.org/) and install it. The
default location is `C:\SALOME-9.15.0`. Confirm the launcher exists:

```powershell
Test-Path "C:\SALOME-9.15.0\run_salome.bat"
```

NEMOS runs SALOME in batch mode (`run_salome.bat -t script.py`); you never need
to open the GUI, though it is useful for inspecting a mesh.

If you installed elsewhere, either edit `DEFAULT_SALOME_EXE` at
[../src/Simulation.py:13](../src/Simulation.py#L13) or pass the path per run:

```python
nemos.run(sim, salome_exe=r"D:\SALOME-9.15.0\run_salome.bat")
```

## 5. Clone and install the Python dependencies

```bash
git clone https://github.com/pedro-oliveira7r/NEMOS_CFD.git
cd NEMOS_CFD
pip install -r requirements.txt
```

## 6. Install `GeoMesh.py` into SALOME

**The step most likely to be skipped.** `src/GeoMesh.py` runs inside SALOME, and
SALOME cannot see your clone. The generated `machine_script.py` opens with
`import GeoMesh as nemos`, so the module has to be on SALOME's own path:

```powershell
Copy-Item src\GeoMesh.py "C:\SALOME-9.15.0\W64\Python\lib\site-packages\GeoMesh.py"
```

Verify:

```powershell
Test-Path "C:\SALOME-9.15.0\W64\Python\lib\site-packages\GeoMesh.py"
```

Two things to remember:

- **Re-copy after every change to `GeoMesh.py`.** There is no link between the
  repository copy and the installed one — a stale copy silently produces the old
  geometry.
- SALOME 9.15.0 already ships `pandas` 1.5.3 and `numpy` 1.21.6, which is all
  `GeoMesh.py` imports. Nothing else needs installing there.

## 7. Run the smoke test

```bash
python examples/01_single_run.py
```

Expect roughly 15–40 minutes. It succeeded if `cases/01_single_run/` contains
`Mesh_1.unv`, a populated `0/` folder, `residuals.png` and `.nemos_done`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'GeoMesh'` in the SALOME output | Step 6 was skipped, or SALOME is installed somewhere else | Copy `GeoMesh.py` into SALOME's `site-packages` |
| `ERRO: Executável do SALOME não encontrado em: ...` | Wrong `DEFAULT_SALOME_EXE` | Fix [Simulation.py:13](../src/Simulation.py#L13) or pass `salome_exe=` |
| `ideasUnvToFoam: command not found` | The OpenFOAM `bashrc` did not source | Check the path in [Simulation.py:1227](../src/Simulation.py#L1227) / [:1298](../src/Simulation.py#L1298) against `ls /usr/lib/openfoam/` |
| `wsl: command not found` / WSL errors | WSL2 not installed, or no default distro | `wsl --install -d Ubuntu-24.04`, then `wsl --set-default Ubuntu-24.04` |
| Geometry changes have no effect | Stale `Mesh_1.unv` is being reused | Delete `Mesh_1.unv` and `.nemos_done` in the case folder |
| SALOME finishes but no `Mesh_1.unv` appears | `create_mesh(export=True)` was omitted | `export=True` is what injects the export path |
| `Todas as listas devem ter o mesmo tamanho` | Sweep lists of differing length | All top-level lists in a manager script must be the same non-zero length |
| Solver hangs immediately | `mpirun` cannot get 4 slots | Use `parallel="N"`, or free up cores — the 4 subdomains are hardcoded |
| The run seems to block on a plot | `plot_residuals=True` drains stdout synchronously | Expected. Pass `plot_residuals=False` for an async run |
| `FileNotFoundError: .../caso.foam` during analysis | Analysing a case built by an older version | Create an empty `caso.foam` at the case root; example 07 does this automatically |
| Analysis sees only time 0 | Parallel run was never reconstructed | `wsl bash -c "source .../etc/bashrc && cd /mnt/c/... && reconstructPar"` |

## A note on paths

Case paths must live on a Windows drive that WSL can reach through `/mnt/`.
Network shares, mapped drives and paths inside the WSL filesystem itself
(`\\wsl$\...`) are not translated and will fail.

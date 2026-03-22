# Example: Simple_Meeting_Room

This example demonstrates how to use the library to generate a 3D geometry and mesh for a meeting room that seats 2 people and a custom air conditioning unit.

## 🎯 Objective
To show the automated workflow from Python geometry definition to a ready-to-run OpenFOAM case.

## 🛠 Prerequisites
- OpenFOAM (v2012 or newer recommended)
- nemos1_02.py (or newer) ready to go

## 🏃 How to Run

Follow these steps to execute the case:

1. **Generate the Mesh and Setup:**
   Run the Python script to build the `polyMesh` and dictionary files:
   ```bash
   python run_simulation.py

# NEMOS_CFD

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![OpenFOAM](https://img.shields.io/badge/OpenFOAM-v2012%20%7C%20v9-green)](https://openfoam.com)

**NEMOS_CFD** is a Python library designed to automate the preprocessing workflow for OpenFOAM simulations. It streamlines the generation of mesh dictionaries and case setup, allowing users to configure complex CFD cases programmatically.

Stop copy-pasting dictionaries. Create parametric OpenFOAM cases using simple Python scripts.

## 🚀 Key Features

* **Automated Mesh Setup:** Generates meshes programmatically based on user parameters.
* **Case Configuration:** Automates the setup of `boundaryConditions`, `transportProperties`, and turbulence models.
* **Python Interface:** Full control over simulation parameters using Python classes and methods.
* **Reproducibility:** Ensures consistent case setup for parametric studies or optimization loops.

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

* **Python 3.8** or higher
* **OpenFOAM** (Tested on version [v2012 / v9 / v2306 - liste as versões que você testou])
* **Salome** (For visualization)

## 📦 Installation

1.  Clone the repository:
    ```bash
    git clone [https://github.com/seu-usuario/nome-da-sua-biblioteca.git](https://github.com/seu-usuario/nome-da-sua-biblioteca.git)
    cd nome-da-sua-biblioteca
    ```

2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

    ## ⚡ Quick Start / Test Case

To verify the installation and see the library in action, run the included test case. This example simulates [descreva o caso, ex: laminar flow in a pipe / flow over a cavity].

1.  **Navigate to the example directory:**
    ```bash
    cd examples/quick_start_case
    ```

2.  **Generate the case files:**
    Run the Python script to create the mesh dictionaries and initial conditions.
    ```bash
    # O nome do script que roda sua automação
    python generate_case.py
    ```

3.  **Run the Simulation:**
    Execute the standard OpenFOAM commands (or use the provided run script if available):
    ```bash
    blockMesh
    simpleFoam  # Ou o solver adequado para o seu caso
    ```

4.  **Visualize:**
    Open the case in Paraview:
    ```bash
    paraFoam
    ```

## 📂 Project Structure

```text
nome-da-sua-biblioteca/
├── src/               # Source code of the library
├── examples/          # Ready-to-run examples and test cases
│   └── quick_start/   # The basic test case
├── tests/             # Unit tests
├── docs/              # Documentation
└── README.md

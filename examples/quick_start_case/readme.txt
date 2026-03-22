# Example: Simple_Meeting_Room

This example demonstrates how to use the library to generate a 3D geometry and mesh for a meeting room that seats 2 people and a custom air conditioning unit.

## 🎯 Objective
To show the automated workflow from Python geometry definition to a ready-to-run OpenFOAM case.

## 🛠 Prerequisites
- OpenFOAM (v2012 or newer recommended)
- nemos1_02.py (or newer) ready to go

## 🏃 How to Run

Follow these steps to execute the case:

1. **Setup the NEMOS library in SALOME**
   Download the library "nemos_102.py" or newer from src;
   Navigate to the "site-packages" paste from your SALOME - "C:\SALOME-9.15.0\W64\Python\lib\site-packages"
   and paste the NEMOS library.

2. **Create a case folder with the base files**
   Download the "quick_start_case" folder to your computer;
   Run "Base_files.py", it will automatically create the OPENFOAM base files for your simulation.

3. **Generate the 3D geometry and Mesh**
   The "script.py" defines the room layout. Here, a 3x3x3m Simple_Meeting_Room is defined with 2 people, 
   a custom air conditioning unit, a table and 4 air outlets.
   The "add_box" and "add_cilinder" commands can be commented out, they create custom 3D volumes for further mesh refining 
   around the seated people. 
   The scrip can be modified indefinitely as long as the shown structure and geometrical boundaries are respected.
   **To generate the mesh**, all you have to do is to copy the text from the script, open SALOME, and paste the script
   in the SALOME terminal.
   The geometry and mesh generation process will start.
   **Note:** you dont have to copy the script all at once. You can go to SALOME's geometry tab and input it gradually
   in order to verify the geometry.
   This example's mesh took 923.34 seconds to generate in a Ryzen 5600H with 16gb ram system. It has 4106135 elements and 549MB size.
   Without the extra refinement the mesh took 528.35 seconds, has 2828534 elements and 397MB size.
   Export the mesh to your case's folder.

4. **Convert the mesh and edit the boundary file**
   After step 3 you will have a full 3D CFD-ready mesh with all the geometrical elements named and appropriately
   refined for a high accuracy simulation. In OPENFOAM, navigate to your case folder and convert the mesh with a 
   "ideasUnvToFoam Mesh_1.unv" command. After this you can use the "checkMesh" command to verify mesh quality.
   This will generate a "polyMesh" folder inside the "constant" base file. Open the **boundary** file inside "polyMesh" and edit it:
   person- to -wall
   dip- to -wall
   inlet- to -inlet
   table- to -wall
   outlet- to -outlet
   wall- to -wall
   After editing, save the file.

5. **Generate the 0 folder**
   Copy the new boundary filepath, open the 0.py file, input the filepath and run the code. 0.py will generate the 0 OPENFOAM folder with all boundary
   conditions already defined for all elements. After this step, you will have a full CDF sim ready to go.

5. **Run the case**
   Now you can run the case as you like. You can chose to modify the "controlDict" or run in parallel.
   This case is setup to use the "buoyantSimpleFoam" solver.

   


   

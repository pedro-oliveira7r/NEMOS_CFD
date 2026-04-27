simulation_config = {
    "case": {
        "name": "quick_start_parametrizado",
        "description": "Sala simples com ocupantes e fontes térmicas",
    },
    "solver": {
        "application": "buoyantSimpleFoam",
        "parallel_cores": 4,
        "turbulence_model": "kEpsilon",
    },
    "time": {
        "startTime": 0,
        "endTime": 3600,
        "deltaT": 0.2,
        "writeInterval": 200,
    },
    "numerics": {
        "residual_target": 1e-6,
        "max_outer_iterations": 250,
    },
    "thermal": {
        "T_initial_K": 300,
        "T_inlet_K": 293,
        "gravity": [0, -9.81, 0],
    },
}

# O bloco simulation_config é opcional.
# Se não existir no script, a Supervisor aplica valores padrão.

import nemos1_06 as nemos
a = nemos.Salome_Env()
b = nemos.Room(salome_env=a, dx=3.000, dy=3.000, dz=3.000, name='Room')
c = nemos.Person_seated(salome_env=a, x=2.025, thickness=0.15, T_face: 36, metabolic_heat_W: 95, species_source: "CO2")
d = nemos.Person_seated(salome_env=a, x=0.975, thickness=0.15, theta=180, T_face: 35, metabolic_heat_W: 85, species_source: "CO2")
e = nemos.Dip_type_00(salome_env=a, x=2.025, y=1, supply_T_C: 20, supply_velocity_m_s: 0.85, flow_profile: "uniform")
f = nemos.Dip_type_00(salome_env=a, x=0.975, y=1.2, supply_T_C: 20, supply_velocity_m_s: 0.85, flow_profile: "uniform")
g = nemos.Table_circular(salome_env=a, x=1.5, T_face: 27, material: "wood", emissivity: 0.9)
b.insert_ceiling_opening(x=0.5, z=2.5, d=0.1)
b.insert_ceiling_opening(x=2.5, z=0.5, d=0.1)
b.insert_ceiling_opening(x=0.5, z=0.5, d=0.1)
b.insert_ceiling_opening(x=2.5, z=2.5, d=0.1)
b.add([c, d, e, f, g])
b.create_faces_groups()
b.add_box_volume(person=c, H_Tubo=1.2)
b.add_box_volume(person=d)
b.add_cilinder(salome_env=a, dip=e)
b.add_cilinder(salome_env=a, dip=f)
nemos.salome_update()
mesh = nemos.Mesh(b)
mesh.create_mesh(export=True, caminho=r"C:\Users\pedro\Desktop\TCC1\Mesh_3.unv")

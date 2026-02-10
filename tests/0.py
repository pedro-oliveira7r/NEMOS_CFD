import os
import re
from collections import defaultdict

# Configurações dos campos (class, dimensions, internalField)
fields_config = {
    'U': {
        'class': 'volVectorField',
        'dimensions': '[0 1 -1 0 0 0 0]',
        'internalField': 'uniform (0 0 0)',
    },
    'alphat': {
        'class': 'volScalarField',
        'dimensions': '[1 -1 -1 0 0 0 0]',
        'internalField': 'uniform 0',
    },
    'epsilon': {
        'class': 'volScalarField',
        'dimensions': '[0 2 -3 0 0 0 0]',
        'internalField': 'uniform 1e-5',
    },
    'k': {
        'class': 'volScalarField',
        'dimensions': '[0 2 -2 0 0 0 0]',
        'internalField': 'uniform 0.001',
    },
    'nut': {
        'class': 'volScalarField',
        'dimensions': '[0 2 -1 0 0 0 0]',
        'internalField': 'uniform 0',
    },
    'p': {
        'class': 'volScalarField',
        'dimensions': '[1 -1 -2 0 0 0 0]',
        'internalField': 'uniform 101325',
    },
    'p_rgh': {
        'class': 'volScalarField',
        'dimensions': '[1 -1 -2 0 0 0 0]',
        'internalField': 'uniform 101325',
    },
    'T': {
        'class': 'volScalarField',
        'dimensions': '[0 0 0 1 0 0 0]',
        'internalField': 'uniform 300',
    },
}

# Condições específicas por variável e tipo de patch
field_conditions = {
    'U': {
        'wall': """        type            noSlip;""",
        'inlet': """        type            fixedValue;
        value           uniform (0 -1 0);""",
        'outlet': """        type            pressureInletOutletVelocity;
        value           $internalField;""",
    },
    'alphat': {
        'wall': """        type            compressible::alphatJayatillekeWallFunction;
        Prt             0.85;
        value           $internalField;""",
        'inlet': """        type            calculated;
        value           $internalField;""",
        'outlet': """        type            calculated;
        value           $internalField;""",
    },
    'epsilon': {
        'wall': """        type            epsilonWallFunction;
        value           $internalField;""",
        'inlet': """        type            turbulentMixingLengthDissipationRateInlet;
        mixingLength    0.0168;
        value           $internalField;""",
        'outlet': """        type            inletOutlet;
        inletValue      $internalField;""",
    },
    'k': {
        'wall': """        type            kqRWallFunction;
        value           $internalField;""",
        'inlet': """        type            fixedValue;
        value           uniform 0.00375;""",
        'outlet': """        type            inletOutlet;
        inletValue      $internalField;""",
    },
    'nut': {
        'wall': """        type            nutkWallFunction;
        value           $internalField;""",
        'inlet': """        type            calculated;
        value           $internalField;""",
        'outlet': """        type            calculated;
        value           $internalField;""",
    },
    'p': {
        'wall': """        type            calculated;
        value           $internalField;""",
        'inlet': """        type            calculated;
        value           $internalField;""",
        'outlet': """        type            fixedValue;
        value           uniform 101325;""",
    },
    'p_rgh': {
        'wall': """        type            fixedFluxPressure;
        value           $internalField;""",
        'inlet': """        type            fixedFluxPressure;
        value           $internalField;""",
        'outlet': """        type            prghPressure;
        p               $internalField;
        value           $internalField;""",
    },
    'T': {
        # Condições padrão para T, a lógica para walls será tratada separadamente
        'inlet': """        type            fixedValue;
        value           uniform 293;""",
        'outlet': """        type            zeroGradient;""",
    }
}

def parse_boundary_file(boundary_path):
    with open(boundary_path, 'r') as f:
        content = f.read()
    patches = re.findall(r'(\w+)\s*\{\s*type\s+(\w+);', content)
    patch_dict = defaultdict(list)
    for name, patch_type in patches:
        patch_dict[patch_type].append(name)
    return patch_dict

def generate_field_file(field_name, config, patch_dict):
    header = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {config['class']};
    object      {field_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      {config['dimensions']};

internalField   {config['internalField']};

boundaryField
{{\n"""

    body = ""
    for patch_type, patch_names in patch_dict.items():
        for patch_name in patch_names:
            cond = ""
            # ⭐ LÓGICA MODIFICADA PARA TEMPERATURA (T) ⭐
            if field_name == 'T' and patch_type == 'wall':
                if patch_name.startswith('person'):
                    valor = 307
                elif patch_name.startswith('dip'):
                    valor = 293
                # table e wall têm o mesmo valor, então podemos agrupá-los
                elif patch_name.startswith('table') or patch_name.startswith('wall'):
                    valor = 300
                else:
                    # Um valor padrão para outros walls não especificados
                    valor = 300
                
                cond = f"""        type            fixedValue;
        value           uniform {valor};"""
            else:
                # Lógica original para todos os outros casos
                cond = field_conditions.get(field_name, {}).get(patch_type, "        type            zeroGradient;")
            
            body += f"    {patch_name}\n    {{\n{cond}\n    }}\n"

    footer = """}


// ************************************************************************* //
"""
    return header + body + footer

def generate_all_fields(boundary_path, output_folder="0"):
    # Verifica se o arquivo boundary existe antes de prosseguir
    if not os.path.exists(boundary_path):
        print(f"❌ Erro: Arquivo boundary não encontrado em '{boundary_path}'")
        return
        
    os.makedirs(output_folder, exist_ok=True)
    patch_dict = parse_boundary_file(boundary_path)

    for field_name, config in fields_config.items():
        content = generate_field_file(field_name, config, patch_dict)
        with open(os.path.join(output_folder, field_name), "w") as f:
            f.write(content)
        print(f"✔ Arquivo '{field_name}' gerado em '{output_folder}/'.")

# --- EXECUÇÃO DO SCRIPT ---
# Caminho do arquivo boundary (use 'r' para tratar o caminho como raw string)
boundary_file_path = r"C:\Users\pedro\Desktop\Auto_Nemos\SIM_1\constant\polyMesh\boundary"

# Pasta de saída para os arquivos gerados
# MODIFIQUE A LINHA ABAIXO:
output_dir = r"C:\Users\pedro\Desktop\Auto_Nemos\SIM_1\0" # Caminho completo para a pasta 0

generate_all_fields(boundary_file_path, output_dir)
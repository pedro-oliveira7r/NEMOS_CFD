import subprocess
import os
import time
import re
from collections import defaultdict

# ==============================================================================
# CONFIGURAÇÕES - MODIFIQUE ESTAS VARIÁVEIS
# ==============================================================================

# 1. Caminho para o executável/batch do SALOME.
CAMINHO_EXECUTAVEL_SALOME = r"c:\SALOME-9.15.0\run_salome.bat"

# 2. Caminho para o script Python que o SALOME irá executar.
CAMINHO_SCRIPT_A_EXECUTAR = r"C:\Users\pedro\Desktop\NEMOS_2026\Sim_000\script.py"

PASTA_DA_SIM = r"C:\Users\pedro\Desktop\NEMOS_2026\Sim_000"

caminho_arquivo = r"\constant\polyMesh\boundary"
caminho_boundary = PASTA_DA_SIM+caminho_arquivo

# 2. Nome do arquivo que estamos aguardando.
NOME_DO_ARQUIVO = "Mesh_1.unv"

caminho_0 = r'\0'
output_dir = PASTA_DA_SIM+caminho_0 # Caminho completo para a pasta 0

def executar_salome_batch():
    """
    Executa o SALOME em modo batch (terminal) para rodar um script Python.
    Esta é a abordagem robusta e recomendada para automação.
    """
    print("--- Iniciando o Executor SALOME em Modo Batch ---")

    # Validação dos caminhos
    if not os.path.exists(CAMINHO_EXECUTAVEL_SALOME):
        print(f"ERRO: Executável do SALOME não encontrado em: '{CAMINHO_EXECUTAVEL_SALOME}'")
        return
    if not os.path.exists(CAMINHO_SCRIPT_A_EXECUTAR):
        print(f"ERRO: Script a ser executado não encontrado em: '{CAMINHO_SCRIPT_A_EXECUTAR}'")
        return

    # Constrói o comando a ser executado.
    # A sintaxe é: <executavel_salome> -t <script_python>
    # Usar uma lista é a forma mais segura de passar argumentos para o subprocess.
    # 1. Correção da sintaxe do comando para o modo batch (-t)
    comando = f'"{CAMINHO_EXECUTAVEL_SALOME}" -t "{CAMINHO_SCRIPT_A_EXECUTAR}"'

    print(f"Executando comando: {comando}")
    print("Aguardando o processo do SALOME terminar. Isso pode levar um tempo...")

    try:
        # 2. Adição do shell=True e passagem do comando como string (mais seguro para .bat no Windows)
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            check=False,
            shell=True 
        )

        # Imprime a saída padrão do script (todos os 'print' do seu script SALOME)
        print("\n--- Saída do Script SALOME (stdout) ---")
        print(resultado.stdout if resultado.stdout else "Nenhuma saída padrão.")
        print("--------------------------------------")

        # Verifica se houve algum erro
        if resultado.returncode != 0:
            print("\n--- ERRO DETECTADO (código de saída diferente de 0) ---")
            print("--- Erros do Script SALOME (stderr) ---")
            print(resultado.stderr if resultado.stderr else "Nenhuma saída de erro.")
            print("--------------------------------------")
        else:
            print("\nMalha exportada com sucesso.")

    except FileNotFoundError:
        print(f"ERRO CRÍTICO: O comando '{CAMINHO_EXECUTAVEL_SALOME}' não pôde ser executado.")
        print("Verifique se o caminho está correto e se você tem permissão para executá-lo.")
    except Exception as e:
        print(f"Ocorreu uma exceção inesperada ao executar o subprocesso: {e}")

def gerar_arquivos(base_path):
    """
    Gera arquivos do OpenFOAM exatamente como os originais fornecidos:
    - constant/: g, thermophysicalProperties, turbulenceProperties
    - system/: controlDict, decomposeParDict, fvOptions, fvSchemes, fvSolution
    """

    # ---------------- Pastas ----------------
    pasta_constant = os.path.join(base_path, "constant")
    pasta_system = os.path.join(base_path, "system")
    os.makedirs(pasta_constant, exist_ok=True)
    os.makedirs(pasta_system, exist_ok=True)

    # ---------------- Arquivos constant ----------------
    arquivos_constant = {
        "g": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;\
    format      ascii;
    class       uniformDimensionedVectorField;
    object      g;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -2 0 0 0 0];
value           (0 -9.81 0);


// ************************************************************************* //
""",
        "thermophysicalProperties": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState Boussinesq;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        molWeight       28.9;
    }
    equationOfState
    {
        rho0            1;
        T0              300;
        beta            3e-03;
    }
    thermodynamics
    {
        Cp              1040;
        Hf              0;
    }
    transport
    {
        mu              1e-05;
        Pr              0.7;
    }
}


// ************************************************************************* //
""",
        "turbulenceProperties": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      turbulenceProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType RAS;

RAS
{
    model      kEpsilon;
}


// ************************************************************************* //
"""
    }

    for nome, conteudo in arquivos_constant.items():
        with open(os.path.join(pasta_constant, nome), "w") as f:
            f.write(conteudo)

    # ---------------- Arquivos system ----------------
    arquivos_system = {
        "controlDict": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     buoyantSimpleFoam;

startFrom       latestTime;

startTime       0;

stopAt          endTime;

endTime         3500;

deltaT          0.1;

writeControl    timeStep;

writeInterval   200;

purgeWrite      0;

writeFormat     ascii;

writePrecision  8;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable false;


// ************************************************************************* //
""",
        "decomposeParDict": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

numberOfSubdomains 4;

method          simple;

coeffs
{
    n           (1 4 1);
}


// ************************************************************************* //
""",
        "fvOptions": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvOptions;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

limitTAir
{
    type       limitTemperature;
    min        280;
    max        310;
    selectionMode all;
    active      yes;
}

dampVelocity
{
    type        velocityDampingConstraint;
    active      yes;

    velocityDampingConstraintCoeffs
    {
        selectionMode all;
        UMax 10;
    }
}


// ************************************************************************* //
""",
        "fvSchemes": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;

    div(phi,U)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss upwind;

    div(phi,k)      bounded Gauss upwind;
    div(phi,epsilon) bounded Gauss upwind;
    div(phi,K)      bounded Gauss upwind;

    div(phi,Ekp)    bounded Gauss linear;

    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;

    div(phi,age)    bounded Gauss upwind;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}


// ************************************************************************* //
""",
        "fvSolution": """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    p_rgh
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0.01;
    }

    "(U|h|k|epsilon)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }

    age
    {
        $U;
        relTol          0.001;
    }
}

SIMPLE
{
    momentumPredictor false;
    nNonOrthogonalCorrectors 0;

    residualControl
    {
        p_rgh           1e-6;
        U               1e-6;
        h               1e-6;
        "(k|epsilon)"   1e-6;
    }
}

relaxationFactors
{
    fields
    {
        p_rgh           0.7;
    }

    equations
    {
        U               0.3;
        h               0.3;
        "(k|epsilon|R)" 0.7;
        age             1;
    }
}


// ************************************************************************* //
"""
    }

    for nome, conteudo in arquivos_system.items():
        with open(os.path.join(pasta_system, nome), "w") as f:
            f.write(conteudo)

    print(f"Arquivos gerados com sucesso em:\n  {pasta_constant}\n  {pasta_system}")

def openf(caminho: str, nome_arquivo: str = '\comandos_1.sh'):

    caminho_script_windows = caminho+nome_arquivo
    caminho_script_wsl = caminho_script_windows.replace('\\', '/').replace('C:', '/mnt/c')
    caso_dir = caminho.replace('\\', '/').replace('C:', '/mnt/c')
    conteudo = f"""#!/bin/bash

# Este é o conteúdo do arquivo '{nome_arquivo}'

echo "Iniciando script dentro do WSL..."

# Carrega as variáveis de ambiente do OpenFOAM
# Usar 'source' ou '.' é a forma padrão aqui dentro do script
source /usr/lib/openfoam/openfoam2312/etc/bashrc
#source "\\\\wsl.localhost\\Ubuntu-24.04\\usr\\lib\\openfoam\\openfoam2312\\etc\\bashrc"

# Navega para o diretório de um caso de exemplo
# (Adapte este caminho para o seu caso real)
CASO_DIR={caso_dir}

cd $CASO_DIR

echo "Diretório de trabalho atual: $(pwd)"

# Executa comandos do OpenFOAM
echo "Convertendo a Malha:"
ideasUnvToFoam Mesh_1.unv

echo "Verificando a Malha:"
checkMesh

"""

    with open(caminho+nome_arquivo, "w", newline='\n') as arquivo:
        arquivo.write(conteudo)

    print(f"Arquivo '{nome_arquivo}' gerado com sucesso.")


    print(f"Executando o script: {caminho_script_wsl}")

    # Executa o script usando o bash dentro do WSL
    # Usar 'bash' garante a execução correta do script
    os.system(f'wsl bash {caminho_script_wsl}')

def rodar_sim(caminho: str, nome_arquivo: str = '\comandos_2.sh'):

    caminho_script_windows = caminho+nome_arquivo
    caminho_script_wsl = caminho_script_windows.replace('\\', '/').replace('C:', '/mnt/c')
    caso_dir = caminho.replace('\\', '/').replace('C:', '/mnt/c')
    conteudo = f"""#!/bin/bash

# Este é o conteúdo do arquivo '{nome_arquivo}'

echo "Iniciando script dentro do WSL..."

# Carrega as variáveis de ambiente do OpenFOAM
# Usar 'source' ou '.' é a forma padrão aqui dentro do script
source /usr/lib/openfoam/openfoam2312/etc/bashrc
#source "\\\\wsl.localhost\\Ubuntu-24.04\\usr\\lib\\openfoam\\openfoam2312\\etc\\bashrc"

# Navega para o diretório de um caso de exemplo
# (Adapte este caminho para o seu caso real)
CASO_DIR={caso_dir}

cd $CASO_DIR

echo "Diretório de trabalho atual: $(pwd)"

# Executa comandos do OpenFOAM
echo "Decompondo os arquivos:"
decomposePar

echo "Rodando a simulação:"
mpirun -np 4 buoyantSimpleFoam -parallel

"""

    with open(caminho+nome_arquivo, "w", newline='\n') as arquivo:
        arquivo.write(conteudo)

    print(f"Arquivo '{nome_arquivo}' gerado com sucesso.")


    print(f"Executando o script: {caminho_script_wsl}")

    # Executa o script usando o bash dentro do WSL
    # Usar 'bash' garante a execução correta do script
    os.system(f'wsl bash {caminho_script_wsl}')

def editar_boundary(caminho_arquivo="boundary"):
    """
    Abre um arquivo 'boundary' do OpenFOAM, identifica os elementos
    e altera o 'type' de 'patch' para o tipo correto com base no nome.

    Argumentos:
    caminho_arquivo (str): O caminho para o arquivo 'boundary'.
                         O padrão é 'boundary' no diretório atual.
    """
    # 1. Define as regras de mapeamento
    # Mapeia o início do nome do elemento para o tipo de fronteira desejado
    regras_mapeamento = {
        "person": "wall",
        "dip": "wall",
        "table": "wall",
        "wall": "wall",
        "inlet": "inlet",
        "outlet": "outlet"
    }

    # Verifica se o arquivo existe
    if not os.path.exists(caminho_arquivo):
        print(f"❌ Erro: O arquivo '{caminho_arquivo}' não foi encontrado.")
        return

    # 2. Lê todo o conteúdo do arquivo para a memória
    with open(caminho_arquivo, 'r') as f:
        linhas = f.readlines()

    novas_linhas = []
    bloco_atual = None

    # 3. Itera sobre cada linha para aplicar as regras
    for linha in linhas:
        linha_limpa = linha.strip()

        # Verifica se a linha é o início de um novo bloco de fronteira
        # (ex: "person1", "inlet3", etc.)
        for nome_base, tipo_novo in regras_mapeamento.items():
            # Usamos regex para garantir que o nome é seguido por um número (ou nada)
            # e não é parte de outra palavra. ^ = início da linha.
            if re.match(f'^{nome_base}[0-9]*$', linha_limpa):
                bloco_atual = nome_base
                break
        
        # Se estamos dentro de um bloco que corresponde a uma regra
        # e a linha atual define o tipo como "patch"...
        if bloco_atual and "type" in linha and "patch" in linha:
            tipo_alvo = regras_mapeamento[bloco_atual]
            # Substitui 'patch' pelo tipo correto, mantendo a formatação original
            linha_modificada = linha.replace("patch", tipo_alvo)
            novas_linhas.append(linha_modificada)
        else:
            # Caso contrário, mantém a linha original
            novas_linhas.append(linha)

        # Se a linha contém '}', significa que o bloco de definição terminou
        if "}" in linha_limpa:
            bloco_atual = None
    
    # 4. Escreve o conteúdo modificado de volta para o arquivo original
    with open(caminho_arquivo, 'w') as f:
        f.writelines(novas_linhas)

    print(f"✅ Arquivo '{caminho_arquivo}' foi atualizado com sucesso!")

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


gerar_arquivos(PASTA_DA_SIM)
executar_salome_batch()
openf(caminho=PASTA_DA_SIM)
editar_boundary(caminho_boundary)
generate_all_fields(caminho_boundary, output_dir)
rodar_sim(caminho=PASTA_DA_SIM)

print('Programa Finalizado')


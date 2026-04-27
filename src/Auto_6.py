import os
import time
import re
import ast
import copy
from collections import defaultdict
import subprocess
from pathlib import Path

class OpenFOAMCase:
    """Gerencia a estrutura de diretórios do caso."""
    def __init__(self, case_path: str):
        self.case_path = Path(case_path)
        self.constant_dir = self.case_path / "constant"
        self.polyMesh_dir = self.constant_dir / "polyMesh"
        self.zero_dir = self.case_path / "0"
        self.system_dir = self.case_path / "system"
        
        self.boundary_file = self.polyMesh_dir / "boundary"

    def gerar_arquivos_base(self):
        """
        Gera arquivos do OpenFOAM exatamente como os originais fornecidos:
        - constant/: g, thermophysicalProperties, turbulenceProperties
        - system/: controlDict, decomposeParDict, fvOptions, fvSchemes, fvSolution
        """

        # ---------------- Pastas ----------------
        pasta_constant = os.path.join(self.case_path, "constant")
        pasta_system = os.path.join(self.case_path, "system")
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


class SalomeMesher:
    """Gerencia a geração de malha via SALOME."""
    def __init__(self, salome_exe: str, script_path: str):
        self.salome_exe = Path(salome_exe)
        self.script_path = Path(script_path)

    def executar_batch(self, output_expected: str = None):
        """
        Executa o SALOME em modo batch (terminal) para rodar um script Python.
        Esta é a abordagem robusta e recomendada para automação.
        """
        print("--- Iniciando o Executor SALOME em Modo Batch ---")

        # Validação dos caminhos
        if not os.path.exists(self.salome_exe):
            print(f"ERRO: Executável do SALOME não encontrado em: '{self.salome_exe}'")
            return
        if not os.path.exists(self.script_path):
            print(f"ERRO: Script a ser executado não encontrado em: '{self.script_path}'")
            return

        # Constrói o comando a ser executado.
        # A sintaxe é: <executavel_salome> -t <script_python>
        # Usar uma lista é a forma mais segura de passar argumentos para o subprocess.
        # 1. Correção da sintaxe do comando para o modo batch (-t)
        comando = f'"{self.salome_exe}" -t "{self.script_path}"'

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
            print(f"ERRO CRÍTICO: O comando '{self.salome_exe}' não pôde ser executado.")
            print("Verifique se o caminho está correto e se você tem permissão para executá-lo.")
        except Exception as e:
            print(f"Ocorreu uma exceção inesperada ao executar o subprocesso: {e}")


class BoundaryManager:
    """Gerencia as condições de contorno e arquivos da pasta 0."""
    def __init__(self, case: OpenFOAMCase):
        self.case = case

    def editar_boundary(self):
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
        if not os.path.exists(self.case.boundary_file):
            print(f"❌ Erro: O arquivo '{self.case.boundary_file}' não foi encontrado.")
            return

        # 2. Lê todo o conteúdo do arquivo para a memória
        with open(self.case.boundary_file, 'r') as f:
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
        with open(self.case.boundary_file, 'w') as f:
            f.writelines(novas_linhas)

        print(f"✅ Arquivo '{self.case.boundary_file}' foi atualizado com sucesso!")

        # Configurações dos campos (class, dimensions, internalField)
        self.fields_config = {
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
        self.field_conditions = {
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

    def _parse_boundary_file(self, boundary_file):
        with open(boundary_file, 'r') as f:
            content = f.read()
        patches = re.findall(r'(\w+)\s*\{\s*type\s+(\w+);', content)
        patch_dict = defaultdict(list)
        for name, patch_type in patches:
            patch_dict[patch_type].append(name)
        return patch_dict

    def _generate_field_file(self, field_name: str, config: dict, patch_dict: dict):
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
                    cond = self.field_conditions.get(field_name, {}).get(patch_type, "        type            zeroGradient;")
                
                body += f"    {patch_name}\n    {{\n{cond}\n    }}\n"

        footer = """}


    // ************************************************************************* //
    """
        return header + body + footer

    def generate_all_fields(self):
        # Verifica se o arquivo boundary existe antes de prosseguir
        if not os.path.exists(self.case.boundary_file):
            print(f"❌ Erro: Arquivo boundary não encontrado em '{self.case.boundary_file}'")
            return

        os.makedirs(self.case.zero_dir, exist_ok=True)
        patch_dict = self._parse_boundary_file(self.case.boundary_file)

        for field_name, config in self.fields_config.items():
            content = self._generate_field_file(field_name, config, patch_dict)
            with open(os.path.join(self.case.zero_dir, field_name), "w") as f:
                f.write(content)
            print(f"✔ Arquivo '{field_name}' gerado em '{self.case.zero_dir}/'.")


class OpenFOAMRunner:
    """Gerencia a execução dos comandos do OpenFOAM."""
    def __init__(self, case: OpenFOAMCase):
        self.case = case

    def preparar_malha(self, script_name: str = 'comandos_1.sh'):
        caminho_script_windows = self.case.case_path / script_name
        caminho_script_wsl = str(caminho_script_windows)\
            .replace('\\', '/')\
            .replace('C:', '/mnt/c')
        caso_dir = str(self.case.case_path)\
            .replace('\\', '/')\
            .replace('C:', '/mnt/c')
        conteudo = f"""#!/bin/bash

    # Este é o conteúdo do arquivo '{script_name}'

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

        with open(caminho_script_windows, "w", newline='\n') as arquivo:
            arquivo.write(conteudo)

        print(f"Arquivo '{script_name}' gerado com sucesso.")


        print(f"Executando o script: {caminho_script_wsl}")

        # Executa o script usando o bash dentro do WSL
        # Usar 'bash' garante a execução correta do script
        os.system(f'wsl bash {caminho_script_wsl}')

    def rodar_simulacao(self, script_name: str = 'comandos_2.sh'):
        caminho_script_windows = self.case.case_path / script_name
        caminho_script_wsl = str(caminho_script_windows)\
            .replace('\\', '/')\
            .replace('C:', '/mnt/c')
        caso_dir = str(self.case.case_path)\
            .replace('\\', '/')\
            .replace('C:', '/mnt/c')
        conteudo = f"""#!/bin/bash

    # Este é o conteúdo do arquivo '{script_name}'

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

        with open(caminho_script_windows, "w", newline='\n') as arquivo:
            arquivo.write(conteudo)

        print(f"Arquivo '{script_name}' gerado com sucesso.")


        print(f"Executando o script: {caminho_script_wsl}")

        # Executa o script usando o bash dentro do WSL
        # Usar 'bash' garante a execução correta do script
        os.system(f'wsl bash {caminho_script_wsl}')


class Supervisor:
    """Lê script do usuário, guarda dados de simulação e gera script de máquina."""

    DEFAULT_SIMULATION_CONFIG = {
        "case": {
            "name": "default_case",
            "description": "Caso padrão gerado automaticamente",
        },
        "solver": {
            "application": "buoyantSimpleFoam",
            "parallel_cores": 4,
            "turbulence_model": "kEpsilon",
        },
        "time": {
            "startTime": 0,
            "endTime": 3500,
            "deltaT": 0.1,
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

    SIMULATION_INLINE_KEYS = {
        "T_face",
        "metabolic_heat_W",
        "species_source",
        "supply_T_C",
        "supply_velocity_m_s",
        "flow_profile",
        "material",
        "emissivity",
    }

    def __init__(self, user_script_path: str):
        self.user_script_path = Path(user_script_path)
        self.simulation_config = copy.deepcopy(self.DEFAULT_SIMULATION_CONFIG)
        self.object_simulation = {}
        self.machine_script = ""
        self._loaded = False

    def _merge_dicts(self, base: dict, override: dict):
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

    def _find_matching_brace(self, text: str, open_idx: int):
        depth = 0
        in_single = False
        in_double = False
        escape = False

        for idx in range(open_idx, len(text)):
            char = text[idx]

            if escape:
                escape = False
                continue

            if (in_single or in_double) and char == "\\":
                escape = True
                continue

            if in_single:
                if char == "'":
                    in_single = False
                continue

            if in_double:
                if char == '"':
                    in_double = False
                continue

            if char == "'":
                in_single = True
                continue

            if char == '"':
                in_double = True
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return idx

        return -1

    def _extract_assigned_dict(self, source_text: str, var_name: str):
        pattern = re.compile(rf"(?m)^\s*{re.escape(var_name)}\s*=\s*\{{")
        match = pattern.search(source_text)
        if not match:
            return None, None, None

        dict_start = source_text.find("{", match.start())
        dict_end = self._find_matching_brace(source_text, dict_start)

        if dict_end == -1:
            raise ValueError(f"Bloco de '{var_name}' não foi fechado corretamente.")

        literal_text = source_text[dict_start:dict_end + 1]
        parsed = ast.literal_eval(literal_text)
        if not isinstance(parsed, dict):
            raise ValueError(f"{var_name} deve ser um dicionário.")

        block_start = source_text.rfind("\n", 0, match.start()) + 1
        block_end = dict_end + 1
        while block_end < len(source_text) and source_text[block_end] in " \t":
            block_end += 1
        while block_end < len(source_text) and source_text[block_end] in "\r\n":
            block_end += 1

        return block_start, block_end, parsed

    def _split_top_level_commas(self, text: str):
        parts = []
        current = []
        depth_paren = 0
        depth_bracket = 0
        depth_brace = 0
        in_single = False
        in_double = False
        escape = False

        for char in text:
            if escape:
                current.append(char)
                escape = False
                continue

            if (in_single or in_double) and char == "\\":
                current.append(char)
                escape = True
                continue

            if in_single:
                current.append(char)
                if char == "'":
                    in_single = False
                continue

            if in_double:
                current.append(char)
                if char == '"':
                    in_double = False
                continue

            if char == "'":
                in_single = True
                current.append(char)
                continue

            if char == '"':
                in_double = True
                current.append(char)
                continue

            if char == "(":
                depth_paren += 1
            elif char == ")":
                depth_paren -= 1
            elif char == "[":
                depth_bracket += 1
            elif char == "]":
                depth_bracket -= 1
            elif char == "{":
                depth_brace += 1
            elif char == "}":
                depth_brace -= 1

            if (
                char == ","
                and depth_paren == 0
                and depth_bracket == 0
                and depth_brace == 0
            ):
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)

        remaining = "".join(current).strip()
        if remaining:
            parts.append(remaining)
        return parts

    def _parse_simulation_token(self, token: str):
        stripped = token.strip()
        if not stripped:
            return None, None

        if ":" in stripped and "=" not in stripped:
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
        elif "=" in stripped:
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            if key not in self.SIMULATION_INLINE_KEYS:
                return None, None
        else:
            return None, None

        raw_value = raw_value.strip()
        try:
            value = ast.literal_eval(raw_value)
        except Exception:
            value = raw_value
        return key, value

    def _sanitize_object_line(self, line: str):
        pattern = re.compile(
            r"^(\s*)([A-Za-z_]\w*)\s*=\s*nemos\.(\w+)\((.*)\)\s*$"
        )
        match = pattern.match(line)
        if not match:
            return line

        indent, var_name, class_name, args_text = match.groups()
        tokens = self._split_top_level_commas(args_text)

        kept_tokens = []
        inline_sim = {}

        for token in tokens:
            sim_key, sim_value = self._parse_simulation_token(token)
            if sim_key is not None:
                inline_sim[sim_key] = sim_value
            else:
                kept_tokens.append(token)

        if inline_sim:
            existing = self.object_simulation.get(var_name, {})
            existing.update(inline_sim)
            self.object_simulation[var_name] = existing

        args_clean = ", ".join(t for t in kept_tokens if t)
        return f"{indent}{var_name} = nemos.{class_name}({args_clean})"

    def _build_machine_script(self, source_text: str):
        sim_start, sim_end, _ = self._extract_assigned_dict(
            source_text, "simulation_config"
        )
        if sim_start is not None:
            source_wo_sim = source_text[:sim_start] + source_text[sim_end:]
        else:
            source_wo_sim = source_text

        self.object_simulation = {}
        sanitized_lines = []
        for line in source_wo_sim.splitlines():
            sanitized_lines.append(self._sanitize_object_line(line))

        return "\n".join(sanitized_lines).strip() + "\n"

    def read_user_script(self):
        if not self.user_script_path.exists():
            raise FileNotFoundError(
                f"Script do usuário não encontrado: {self.user_script_path}"
            )

        source_text = self.user_script_path.read_text(encoding="utf-8")

        _, _, user_sim_cfg = self._extract_assigned_dict(
            source_text, "simulation_config"
        )
        if user_sim_cfg is None:
            user_sim_cfg = {}

        self.simulation_config = self._merge_dicts(
            self.DEFAULT_SIMULATION_CONFIG,
            user_sim_cfg,
        )
        self.machine_script = self._build_machine_script(source_text)
        self._loaded = True

        return {
            "simulation_config": self.simulation_config,
            "object_simulation": self.object_simulation,
            "machine_script": self.machine_script,
        }

    def generate_machine_script(self):
        if not self._loaded:
            self.read_user_script()
        return self.machine_script

    def write_machine_script(self, output_path: str):
        script = self.generate_machine_script()
        output_file = Path(output_path)
        output_file.write_text(script, encoding="utf-8")
        return output_file


if __name__ == "__main__":
    # Fluxo legado de execução direta do Auto_6.
    case = OpenFOAMCase(r"C:\Users\pedro\Desktop\TCC1\Sim_000")
    mesher = SalomeMesher(
        r"c:\SALOME-9.15.0\run_salome.bat",
        r"C:\Users\pedro\Desktop\TCC1\Sim_000\script.py",
    )
    boundary_manager = BoundaryManager(case)
    runner = OpenFOAMRunner(case)

    # case.gerar_arquivos_base()
    # mesher.executar_batch()
    runner.preparar_malha()
    boundary_manager.editar_boundary()
    boundary_manager.generate_all_fields()
    runner.rodar_simulacao()

    print('Programa Finalizado')
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

    def gerar_arquivos_base(self, simulation_config=None):
        """
        Gera arquivos do OpenFOAM exatamente como os originais fornecidos:
        - constant/: g, thermophysicalProperties, turbulenceProperties
        - system/: controlDict, decomposeParDict, fvOptions, fvSchemes, fvSolution
        """

        simulation_config = simulation_config or {}
        control_cfg = simulation_config.get("controlDict", {}) or {}
        decompose_cfg = simulation_config.get("decomposeParDict", {}) or {}

        start_time = control_cfg.get("startTime", 0)
        end_time = control_cfg.get("endTime", 3500)
        delta_t = control_cfg.get("delta", control_cfg.get("deltaT", 0.1))
        write_interval = control_cfg.get("writeInterval", 200)

        parallel_flag = str(decompose_cfg.get("parallel", "Y")).strip().upper().startswith("Y")

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

        # Parametriza apenas os comandos solicitados, mantendo o restante intacto.
        control_text = arquivos_system.get("controlDict", "")
        control_text = re.sub(
            r"(?m)^(\s*startTime\s+).*(;\s*)$",
            r"\g<1>" + str(start_time) + r"\g<2>",
            control_text,
        )
        control_text = re.sub(
            r"(?m)^(\s*endTime\s+).*(;\s*)$",
            r"\g<1>" + str(end_time) + r"\g<2>",
            control_text,
        )
        control_text = re.sub(
            r"(?m)^(\s*deltaT\s+).*(;\s*)$",
            r"\g<1>" + str(delta_t) + r"\g<2>",
            control_text,
        )
        control_text = re.sub(
            r"(?m)^(\s*writeInterval\s+).*(;\s*)$",
            r"\g<1>" + str(write_interval) + r"\g<2>",
            control_text,
        )
        arquivos_system["controlDict"] = control_text

        # Se o usuário escolher serial, não gera decomposeParDict.
        if not parallel_flag:
            arquivos_system.pop("decomposeParDict", None)

        for nome, conteudo in arquivos_system.items():
            with open(os.path.join(pasta_system, nome), "w") as f:
                f.write(conteudo)

        print(f"Arquivos gerados com sucesso em:\n  {pasta_constant}\n  {pasta_system}")


class SalomeMesher:
    """Gerencia a geração de malha via SALOME."""
    def __init__(self, salome_exe: str, script_path: str = None, supervisor=None):
        self.salome_exe = Path(salome_exe)
        self.script_path = Path(script_path) if script_path else None
        self.supervisor = supervisor

    def _ensure_machine_script(self):
        if self.supervisor is None:
            return

        # Ensure Supervisor is loaded.
        self.supervisor.generate_machine_script()

        if self.script_path is None:
            user_path = getattr(self.supervisor, "user_script_path", None)
            if user_path is None:
                raise ValueError("Supervisor não possui user_script_path para inferir o caminho do script de máquina")
            self.script_path = user_path.with_name(user_path.stem + "_machine.py")

        script_text = self.supervisor.machine_script
        self.script_path.write_text(script_text, encoding="utf-8")

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

        # Se um Supervisor foi fornecido, garante que o script de máquina exista.
        if self.supervisor is not None:
            self._ensure_machine_script()

        if self.script_path is None or not os.path.exists(self.script_path):
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
    def __init__(self, case: OpenFOAMCase, supervisor=None):
        self.case = case
        self.supervisor = supervisor

        if self.supervisor is not None:
            # Make sure we have configs/types available.
            try:
                self.supervisor.read_user_script()
            except Exception:
                # Keep lazy behavior; errors will surface when used.
                pass

    def _get_simulation_config(self) -> dict:
        if self.supervisor is None:
            return {}
        return getattr(self.supervisor, "simulation_config", {}) or {}

    def _infer_semantic_type(self, patch_name: str):
        """Returns semantic types like person/dip/table/wall/inlet/outlet."""
        if patch_name == "wall":
            return "wall"
        if patch_name == "outlet":
            return "outlet"
        if patch_name.startswith("inlet_"):
            return "inlet"

        if self.supervisor is not None:
            obj_types = getattr(self.supervisor, "object_types", {}) or {}
            if patch_name in obj_types:
                return obj_types[patch_name]

        # Legacy fallback (old patch naming scheme)
        if patch_name.startswith("wall"):
            return "wall"
        if patch_name.startswith("inlet"):
            return "inlet"
        if patch_name.startswith("outlet"):
            return "outlet"
        if patch_name.startswith("person"):
            return "person"
        if patch_name.startswith("dip"):
            return "dip"
        if patch_name.startswith("table"):
            return "table"

        return None

    def _infer_boundary_type(self, patch_name: str):
        """Returns OpenFOAM boundary type: wall/inlet/outlet or None."""
        semantic = self._infer_semantic_type(patch_name)
        if semantic in ("person", "dip", "table", "wall"):
            return "wall"
        if semantic in ("inlet", "outlet"):
            return semantic
        return None

    def _as_uniform_scalar(self, value, fallback: float):
        if value is None:
            return f"uniform {fallback}"
        if isinstance(value, (int, float)):
            return f"uniform {value}"
        s = str(value).strip()
        if not s:
            return f"uniform {fallback}"
        return s

    def _extract_uniform_scalar_value(self, uniform_str: str, fallback: float):
        if uniform_str is None:
            return fallback
        s = str(uniform_str)
        m = re.search(r"uniform\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if not m:
            return fallback
        try:
            return float(m.group(1))
        except Exception:
            return fallback

    def _inlet_velocity_value(self):
        cfg = self._get_simulation_config()
        u_cfg = (cfg.get("fields", {}) or {}).get("U", {}) or {}
        raw = u_cfg.get("value", None)

        if isinstance(raw, (int, float)):
            return f"uniform (0 {raw} 0)"

        if raw is None:
            return "uniform (0 -1 0)"

        s = str(raw).strip()
        if not s:
            return "uniform (0 -1 0)"
        return s

    def _default_t_face(self):
        cfg = self._get_simulation_config()
        t_cfg = (cfg.get("fields", {}) or {}).get("T", {}) or {}
        # accept a few aliases for global face temperature
        for key in ("T_Face", "faceValue", "wallValue", "value"):
            if key in t_cfg:
                return float(t_cfg[key]) if isinstance(t_cfg[key], (int, float)) else self._extract_uniform_scalar_value(t_cfg[key], 300.0)
        internal = t_cfg.get("internalField", "uniform 300")
        return self._extract_uniform_scalar_value(internal, 300.0)

    def _default_t_flow(self):
        cfg = self._get_simulation_config()
        t_cfg = (cfg.get("fields", {}) or {}).get("T", {}) or {}
        for key in ("T_Flow", "flowValue", "inletValue"):
            if key in t_cfg:
                return float(t_cfg[key]) if isinstance(t_cfg[key], (int, float)) else self._extract_uniform_scalar_value(t_cfg[key], 293.0)
        return 293.0

    def _object_sim_value(self, var_name: str, key: str):
        if self.supervisor is None:
            return None
        obj_sim = getattr(self.supervisor, "object_simulation", {}) or {}
        return (obj_sim.get(var_name, {}) or {}).get(key)

    def editar_boundary(self):
        """
        Abre um arquivo 'boundary' do OpenFOAM, identifica os elementos
        e altera o 'type' de 'patch' para o tipo correto com base no nome.

        Argumentos:
        caminho_arquivo (str): O caminho para o arquivo 'boundary'.
                            O padrão é 'boundary' no diretório atual.
        """
        # Verifica se o arquivo existe
        if not os.path.exists(self.case.boundary_file):
            print(f"❌ Erro: O arquivo '{self.case.boundary_file}' não foi encontrado.")
            return

        # 2. Lê todo o conteúdo do arquivo para a memória
        with open(self.case.boundary_file, 'r') as f:
            linhas = f.readlines()

        novas_linhas = []
        bloco_atual = None

        for idx, linha in enumerate(linhas):
            linha_limpa = linha.strip()

            # Detecta início de bloco: uma linha só com o nome do patch, seguida de "{"
            if re.match(r"^[A-Za-z_]\w*$", linha_limpa):
                j = idx + 1
                while j < len(linhas) and linhas[j].strip() == "":
                    j += 1
                if j < len(linhas) and linhas[j].strip().startswith("{"):
                    bloco_atual = linha_limpa

            if bloco_atual and re.search(r"\btype\b", linha) and ";" in linha:
                tipo_alvo = self._infer_boundary_type(bloco_atual)
                if tipo_alvo is not None:
                    linha = re.sub(
                        r"(\btype\s+)\w+(\s*;)",
                        rf"\1{tipo_alvo}\2",
                        linha,
                    )

            novas_linhas.append(linha)

            if "}" in linha_limpa:
                bloco_atual = None
        
        # 4. Escreve o conteúdo modificado de volta para o arquivo original
        with open(self.case.boundary_file, 'w') as f:
            f.writelines(novas_linhas)

        print(f"✅ Arquivo '{self.case.boundary_file}' foi atualizado com sucesso!")

        # Configurações dos campos (class, dimensions, internalField)
        cfg = self._get_simulation_config()
        fields_cfg = (cfg.get("fields", {}) or {})

        t_internal = self._as_uniform_scalar(fields_cfg.get("T", {}).get("internalField", None), 300)
        p_internal = self._as_uniform_scalar(fields_cfg.get("p", {}).get("internalField", None), 101325)
        k_internal = self._as_uniform_scalar(fields_cfg.get("k", {}).get("internalField", None), 0.001)
        eps_internal = self._as_uniform_scalar(fields_cfg.get("epsilon", {}).get("internalField", None), 1e-5)

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
                'internalField': eps_internal,
            },
            'k': {
                'class': 'volScalarField',
                'dimensions': '[0 2 -2 0 0 0 0]',
                'internalField': k_internal,
            },
            'nut': {
                'class': 'volScalarField',
                'dimensions': '[0 2 -1 0 0 0 0]',
                'internalField': 'uniform 0',
            },
            'p': {
                'class': 'volScalarField',
                'dimensions': '[1 -1 -2 0 0 0 0]',
                'internalField': p_internal,
            },
            'p_rgh': {
                'class': 'volScalarField',
                'dimensions': '[1 -1 -2 0 0 0 0]',
                'internalField': p_internal,
            },
            'T': {
                'class': 'volScalarField',
                'dimensions': '[0 0 0 1 0 0 0]',
                'internalField': t_internal,
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
                value           $internalField;""",
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
                if field_name == 'T':
                    if patch_type == 'inlet':
                        # Per-inlet temperature: inlet_<dipVar> -> uses dip's T_Flow.
                        valor = self._default_t_flow()
                        if patch_name.startswith('inlet_'):
                            var = patch_name[len('inlet_'):]
                            v = self._object_sim_value(var, 'T_Flow')
                            if v is not None:
                                try:
                                    valor = float(v)
                                except Exception:
                                    pass

                        cond = f"""        type            fixedValue;
            value           uniform {valor};"""
                    elif patch_type == 'wall':
                        semantic = self._infer_semantic_type(patch_name)
                        default_face = self._default_t_face()

                        valor = default_face
                        if semantic in ('person', 'table'):
                            v = self._object_sim_value(patch_name, 'T_Face')
                            if v is not None:
                                try:
                                    valor = float(v)
                                except Exception:
                                    pass
                        elif semantic == 'dip':
                            v = self._object_sim_value(patch_name, 'T_Flow')
                            if v is not None:
                                try:
                                    valor = float(v)
                                except Exception:
                                    pass
                            else:
                                valor = self._default_t_flow()
                        elif semantic == 'wall':
                            valor = default_face

                        cond = f"""        type            fixedValue;
            value           uniform {valor};"""
                    else:
                        cond = self.field_conditions.get(field_name, {}).get(patch_type, "        type            zeroGradient;")

                elif field_name == 'U' and patch_type == 'inlet':
                    value_str = self._inlet_velocity_value()
                    if patch_name.startswith('inlet_'):
                        var = patch_name[len('inlet_'):]
                        v = self._object_sim_value(var, 'V_Flow')
                        if v is not None:
                            try:
                                value_str = f"uniform (0 {float(v)} 0)"
                            except Exception:
                                pass

                    cond = f"""        type            fixedValue;
                value           {value_str};"""
                else:
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
    def __init__(self, case: OpenFOAMCase, supervisor=None):
        self.case = case
        self.supervisor = supervisor

        self.parallel_flag = True
        if self.supervisor is not None:
            try:
                self.supervisor.read_user_script()
            except Exception:
                pass
            cfg = getattr(self.supervisor, "simulation_config", {}) or {}
            decompose_cfg = cfg.get("decomposeParDict", {}) or {}
            self.parallel_flag = str(decompose_cfg.get("parallel", "Y")).strip().upper().startswith("Y")

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
    {"" if not self.parallel_flag else "echo \"Decompondo os arquivos:\"\n    decomposePar\n"}

    echo "Rodando a simulação:"
    {"buoyantSimpleFoam" if not self.parallel_flag else "mpirun -np 4 buoyantSimpleFoam -parallel"}

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
        # These defaults must allow the entire simulation_config block
        # (everything above `import nemos1_06 as nemos`) to be omitted.
        "controlDict": {
            "startTime": 0,
            "endTime": 3500,
            # Prefer OpenFOAM's conventional naming.
            "deltaT": 0.1,
            "writeInterval": 200,
        },
        # Minimal switch (Y/N) for parallel runs.
        "decomposeParDict": {
            "parallel": "N",
        },
        # Minimal field defaults.
        "fields": {
            "U": {
                "value": "uniform (0 -1 0)",
            },
            "T": {
                "internalField": "uniform 300",
            },
            "p": {
                "internalField": "uniform 101325",
            },
            "k": {
                "internalField": "uniform 0.001",
            },
            "epsilon": {
                "internalField": "uniform 1e-5",
            },
        },
    }

    SIMULATION_INLINE_KEYS = {
        "T_face",
        "T_Face",
        "metabolic_heat_W",
        "species_source",
        "supply_T_C",
        "supply_velocity_m_s",
        "T_Flow",
        "V_Flow",
        "flow_profile",
        "material",
        "emissivity",
    }

    def __init__(self, user_script_path: str):
        self.user_script_path = Path(user_script_path)
        self.simulation_config = copy.deepcopy(self.DEFAULT_SIMULATION_CONFIG)
        self.user_simulation_config = {}
        self.object_simulation = {}
        # Maps variable name -> semantic geometry type (e.g. "person", "dip", "table", "room").
        # This is used later to keep boundary/BC logic stable even when patches are
        # named after user variables (e.g. "c", "e").
        self.object_types = {}
        # Maps variable name -> instantiated class name (e.g. "Person_seated").
        self.object_classes = {}
        self.machine_script = ""
        self._loaded = False

    def _class_to_object_type(self, class_name: str):
        if not class_name:
            return None
        if class_name == "Room":
            return "room"
        if class_name.startswith("Person"):
            return "person"
        if class_name.startswith("Dip"):
            return "dip"
        if class_name.startswith("Table"):
            return "table"
        return None

    @property
    def controlDict(self) -> dict:
        if not self._loaded:
            self.read_user_script()
        return self.simulation_config.get("controlDict", {})

    @property
    def decomposeParDict(self) -> dict:
        if not self._loaded:
            self.read_user_script()
        return self.simulation_config.get("decomposeParDict", {})

    @property
    def fields(self) -> dict:
        if not self._loaded:
            self.read_user_script()
        return self.simulation_config.get("fields", {})

    def _merge_dicts(self, base: dict, override: dict):
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

    def _normalize_simulation_config(self, cfg: dict) -> dict:
        """Normaliza aliases e garante chaves mínimas para uso interno."""
        cfg = copy.deepcopy(cfg) if cfg is not None else {}

        control = cfg.setdefault("controlDict", {})
        # Accept user-friendly alias `delta` used in the user_script and expose
        # the conventional OpenFOAM key `deltaT` as well.
        if "delta" in control and "deltaT" not in control:
            control["deltaT"] = control["delta"]
        if "deltaT" in control and "delta" not in control:
            control["delta"] = control["deltaT"]

        cfg.setdefault("decomposeParDict", {})
        cfg.setdefault("fields", {})

        # Ensure expected field dicts exist (so downstream code can assume keys).
        fields = cfg["fields"]
        fields.setdefault("U", {})
        fields.setdefault("T", {})
        fields.setdefault("p", {})
        fields.setdefault("k", {})
        fields.setdefault("epsilon", {})

        return cfg

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

        self.object_classes[var_name] = class_name
        inferred_type = self._class_to_object_type(class_name)
        if inferred_type is not None:
            self.object_types[var_name] = inferred_type
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
        self.object_types = {}
        self.object_classes = {}
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

        self.user_simulation_config = user_sim_cfg

        merged = self._merge_dicts(self.DEFAULT_SIMULATION_CONFIG, user_sim_cfg)
        self.simulation_config = self._normalize_simulation_config(merged)
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

    user_script_path = case.case_path / "user_script.py"
    supervisor = None
    if user_script_path.exists():
        supervisor = Supervisor(str(user_script_path))
        supervisor.read_user_script()
        # Gera arquivos base já parametrizados.
        case.gerar_arquivos_base(supervisor.simulation_config)

    mesher = SalomeMesher(
        r"c:\SALOME-9.15.0\run_salome.bat",
        str(case.case_path / "script.py"),
        supervisor=supervisor,
    )
    boundary_manager = BoundaryManager(case, supervisor=supervisor)
    runner = OpenFOAMRunner(case, supervisor=supervisor)

    # mesher.executar_batch()
    runner.preparar_malha()
    boundary_manager.editar_boundary()
    boundary_manager.generate_all_fields()
    runner.rodar_simulacao()

    print('Programa Finalizado')
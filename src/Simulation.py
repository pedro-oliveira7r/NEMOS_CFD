import os
import shutil
import time
import re
import ast
import copy
import json
from collections import defaultdict
import subprocess
from pathlib import Path

_ACTIVE_SIMULATION = None
DEFAULT_SALOME_EXE = r"c:\SALOME-9.15.0\run_salome.bat"
STATE_FILE = ".nemos_state.json"

# Traducao das strings amigaveis de Mesh.check_quality (usadas nos scripts do
# usuario) para as constantes SMESH que so existem dentro do SALOME.
_ELEMENT_TYPE_MAP = {
    "FACE": "SMESH.FACE",
    "VOLUME": "SMESH.VOLUME",
}

_COMPARISON_MAP = {
    ">": "SMESH.FT_MoreThan",
    "<": "SMESH.FT_LessThan",
    "=": "SMESH.FT_EqualTo",
    "==": "SMESH.FT_EqualTo",
}

# Bloco inserido no inicio do machine script (roda dentro do SALOME) para gerar
# um resumo .txt legivel a partir do DataFrame retornado por Mesh.check_quality.
_QUALITY_SUMMARY_HELPER = [
    "import SMESH",
    "def _nemos_quality_summary(df, name_metric, out_dir):",
    "    import os",
    "    path = os.path.join(out_dir, str(name_metric) + '_summary.txt')",
    "    lines = []",
    "    lines.append('Metric: ' + str(name_metric))",
    "    lines.append('Elements flagged: %d / %d' % (int(df['flag'].sum()), len(df)))",
    "    vals = df['value'].dropna()",
    "    if len(vals):",
    "        lines.append('Value min / max: %s / %s' % (vals.min(), vals.max()))",
    "    flagged = df[df['flag']]",
    "    if len(flagged):",
    "        lines.append('')",
    "        lines.append('Flagged elements per region:')",
    "        for region, count in flagged['region'].value_counts().items():",
    "            lines.append('  %s: %d' % (region, count))",
    "    with open(path, 'w') as f:",
    "        f.write('\\n'.join(lines) + '\\n')",
]


def _set_active_simulation(simulation):
    global _ACTIVE_SIMULATION
    _ACTIVE_SIMULATION = simulation


def _get_active_simulation():
    if _ACTIVE_SIMULATION is None:
        raise RuntimeError("Simulation nao foi inicializada.")
    return _ACTIVE_SIMULATION

class OpenFOAMCase:
    """Gerencia a estrutura de diretórios do caso."""
    def __init__(self, case_path: str):
        self.case_path = Path(case_path)
        self.constant_dir = self.case_path / "constant"
        self.polyMesh_dir = self.constant_dir / "polyMesh"
        self.zero_dir = self.case_path / "0"
        self.system_dir = self.case_path / "system"
        
        self.boundary_file = self.polyMesh_dir / "boundary"

    # ---- Detectores de estagio (para retomar de onde parou) ----
    def mesh_geometry_ready(self) -> bool:
        """True se a malha (Mesh_1.unv) ja foi gerada/importada."""
        return (self.case_path / "Mesh_1.unv").exists()

    def mesh_converted(self) -> bool:
        """True se a malha ja foi convertida para o formato OpenFOAM."""
        return self.boundary_file.exists()

    def fields_ready(self) -> bool:
        """True se os campos da pasta 0/ ja foram gerados."""
        return (self.zero_dir / "T").exists() and (self.zero_dir / "U").exists()

    def decomposed(self) -> bool:
        """True se o caso ja foi decomposto para execucao paralela."""
        return (self.case_path / "processor0").exists()

    def done_marker(self) -> Path:
        """Arquivo marcador escrito quando o caso termina com sucesso."""
        return self.case_path / ".nemos_done"

    def is_complete(self) -> bool:
        return self.done_marker().exists()

    def gerar_arquivos_base(self, simulation_config=None):
        """
        Gera arquivos do OpenFOAM:
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
    def __init__(self, salome_exe: str, script_path: str = None, simulation=None):
        self.salome_exe = Path(salome_exe)
        self.script_path = Path(script_path) if script_path else None
        self.simulation = simulation

    def _ensure_machine_script(self):
        if self.simulation is None:
            return

        # Ensure Simulation is loaded.
        self.simulation.generate_machine_script()

        user_path = getattr(self.simulation, "user_script_path", None)

        if self.script_path is None:
            if user_path is None:
                raise ValueError("Simulation nao possui user_script_path para inferir o caminho do script de maquina")
            self.script_path = user_path.with_name(user_path.stem + "_machine.py")

        script_text = self.simulation.machine_script
        self.script_path.write_text(script_text, encoding="utf-8")

        # Also store a stable copy inside the case folder.
        # Convention: <case_dir>/machine_script.py
        if user_path is not None:
            machine_copy_path = user_path.parent / "machine_script.py"
            machine_copy_path.write_text(script_text, encoding="utf-8")

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

        # Se uma Simulation foi fornecida, garante que o script de máquina exista.
        if self.simulation is not None:
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
    def __init__(self, case: OpenFOAMCase, simulation=None):
        self.case = case
        self.simulation = simulation

        if self.simulation is not None:
            # Make sure we have configs/types available.
            try:
                self.simulation.read_user_script()
            except Exception:
                # Keep lazy behavior; errors will surface when used.
                pass

    def _get_simulation_config(self) -> dict:
        if self.simulation is None:
            return {}
        return getattr(self.simulation, "simulation_config", {}) or {}

    def _infer_semantic_type(self, patch_name: str):
        """Returns semantic types like person/dip/table/wall/inlet/outlet."""
        if patch_name == "wall":
            return "wall"
        if patch_name == "outlet":
            return "outlet"
        if patch_name.startswith("inlet_"):
            return "inlet"

        if self.simulation is not None:
            obj_types = getattr(self.simulation, "object_types", {}) or {}
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
        room_value = self._room_t_face()
        if room_value is not None:
            return room_value
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
        if self.simulation is None:
            return None
        obj_sim = getattr(self.simulation, "object_simulation", {}) or {}
        return (obj_sim.get(var_name, {}) or {}).get(key)

    def _room_t_face(self):
        if self.simulation is None:
            return None
        obj_classes = getattr(self.simulation, "object_classes", {}) or {}
        if not obj_classes:
            return None
        obj_sim = getattr(self.simulation, "object_simulation", {}) or {}
        for obj_name, class_name in obj_classes.items():
            if class_name != "Room":
                continue
            sim_cfg = obj_sim.get(obj_name, {}) or {}
            if "T_Face" in sim_cfg:
                value = sim_cfg.get("T_Face")
            else:
                value = sim_cfg.get("T_face")

            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            return self._extract_uniform_scalar_value(value, 300.0)
        return None

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
            print(f"Erro: O arquivo '{self.case.boundary_file}' não foi encontrado.")
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

        print(f"Arquivo '{self.case.boundary_file}' foi atualizado com sucesso!")

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
                'internalField': 'uniform 101325',
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
            print(f"Erro: Arquivo boundary não encontrado em '{self.case.boundary_file}'")
            return

        os.makedirs(self.case.zero_dir, exist_ok=True)
        patch_dict = self._parse_boundary_file(self.case.boundary_file)

        for field_name, config in self.fields_config.items():
            content = self._generate_field_file(field_name, config, patch_dict)
            with open(os.path.join(self.case.zero_dir, field_name), "w") as f:
                f.write(content)
            print(f"Arquivo '{field_name}' gerado em '{self.case.zero_dir}/'.")


class ResidualPlotter:
    """Faz o parsing do stdout do solver OpenFOAM e plota os residuais em tempo real.

    Alimentado linha a linha (feed_line) enquanto o processo do solver roda.
    Cada bloco "Time = X" fecha o timestep anterior, empurrando os residuais
    pendentes para o histórico e redesenhando o gráfico (eixo Y log-scale).
    """

    _TIME_RE = re.compile(r"^Time\s*=\s*([0-9.eE+\-]+)\s*$")
    _RESIDUAL_RE = re.compile(
        r"Solving for (?P<field>[\w()|]+),\s*Initial residual = (?P<initial>[0-9.eE+\-]+)"
    )

    def __init__(self, title: str = "Residual convergence"):
        self.history = defaultdict(list)
        self._pending = {}
        self._current_time = None
        self._lines = {}
        self.live = False
        self._mpl_available = False

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return

        try:
            plt.ion()
            self._plt = plt
            self._fig, self._ax = plt.subplots()
            self._ax.set_xlabel("Timestep")
            self._ax.set_ylabel("Initial residual")
            self._ax.set_yscale("log")
            self._ax.set_title(title)
            try:
                self._fig.canvas.manager.set_window_title("NEMOS - Residuals")
            except Exception:
                pass
            self._mpl_available = True
            self.live = True
        except Exception:
            self.live = False

    def feed_line(self, line: str):
        stripped = line.rstrip("\n")

        time_match = self._TIME_RE.match(stripped)
        if time_match:
            self._commit_pending()
            self._current_time = float(time_match.group(1))
            self._pending = {}
            return

        res_match = self._RESIDUAL_RE.search(stripped)
        if res_match and self._current_time is not None:
            # Se o mesmo campo for resolvido mais de uma vez no timestep
            # (ex.: correctors), o ultimo valor prevalece.
            self._pending[res_match.group("field")] = float(res_match.group("initial"))

    def _commit_pending(self):
        if self._current_time is None or not self._pending:
            return
        for field, value in self._pending.items():
            self.history[field].append((self._current_time, value))
        self._redraw()

    def _redraw(self):
        if not self.live:
            return
        try:
            new_field = False
            for field, points in self.history.items():
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                line = self._lines.get(field)
                if line is None:
                    (line,) = self._ax.plot(xs, ys, label=field)
                    self._lines[field] = line
                    new_field = True
                else:
                    line.set_data(xs, ys)
            if new_field:
                self._ax.legend(loc="upper right")
            self._ax.relim()
            self._ax.autoscale_view()
            self._fig.canvas.draw_idle()
            self._fig.canvas.flush_events()
            self._plt.pause(0.001)
        except Exception:
            self.live = False

    def finish(self, png_path: Path):
        self._commit_pending()

        if self.live:
            try:
                self._plt.close(self._fig)
            except Exception:
                pass

        if not self.history:
            return None

        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg

            fig = Figure()
            FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)
            for field, points in self.history.items():
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                ax.plot(xs, ys, label=field)
            ax.set_xlabel("Timestep")
            ax.set_ylabel("Initial residual")
            ax.set_yscale("log")
            ax.set_title("Residual convergence")
            ax.legend(loc="upper right")
            fig.savefig(png_path)
            return Path(png_path)
        except Exception:
            return None


class OpenFOAMRunner:
    """Gerencia a execução dos comandos do OpenFOAM."""
    def __init__(self, case: OpenFOAMCase, simulation=None):
        self.case = case
        self.simulation = simulation

        self.parallel_flag = True
        self.plot_residuals = True
        self.mesh_process = None  # Track the mesh preparation process
        self.simulation_process = None  # Track the simulation process
        self.residual_history = None
        self.residual_log_path = None
        self.residual_plot_path = None

        if self.simulation is not None:
            try:
                self.simulation.read_user_script()
            except Exception:
                pass
            cfg = getattr(self.simulation, "simulation_config", {}) or {}
            decompose_cfg = cfg.get("decomposeParDict", {}) or {}
            self.parallel_flag = str(decompose_cfg.get("parallel", "Y")).strip().upper().startswith("Y")
            monitoring_cfg = cfg.get("monitoring", {}) or {}
            self.plot_residuals = bool(monitoring_cfg.get("plot_residuals", True))

    def preparar_malha(self, script_name: str = 'comandos_1.sh', wait: bool = False):
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

        # Executa o script usando subprocess.Popen para execução não-bloqueante
        # subprocess.Popen retorna imediatamente, permitindo que o código continue
        try:
            self.mesh_process = subprocess.Popen(
                f'wsl bash {caminho_script_wsl}',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Processo de preparação de malha iniciado com PID: {self.mesh_process.pid}")
            
            if wait:
                # Se wait=True, aguarda a conclusão (comportamento similar ao os.system)
                stdout, stderr = self.mesh_process.communicate()
                print("Preparação de malha concluída.")
                if stdout:
                    print("STDOUT:", stdout)
                if stderr:
                    print("STDERR:", stderr)
                return self.mesh_process.returncode == 0
            else:
                # Se wait=False, retorna imediatamente
                print("Preparação de malha rodando em background. Use wait_mesh() para aguardar conclusão.")
                return False
        except Exception as e:
            print(f"Erro ao executar o script: {e}")
            raise

    def rodar_simulacao(self, script_name: str = 'comandos_2.sh', wait: bool = False):
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
    {"" if not self.parallel_flag else "if [ ! -d processor0 ]; then\n      echo \"Decompondo os arquivos:\"\n      decomposePar\n    else\n      echo \"Decomposicao ja existe, retomando da ultima iteracao.\"\n    fi\n"}

    echo "Rodando a simulação:"
    {"stdbuf -oL -eL buoyantSimpleFoam" if not self.parallel_flag else "stdbuf -oL -eL mpirun -np 4 buoyantSimpleFoam -parallel"}

    """

        with open(caminho_script_windows, "w", newline='\n') as arquivo:
            arquivo.write(conteudo)

        print(f"Arquivo '{script_name}' gerado com sucesso.")
        print(f"Executando o script: {caminho_script_wsl}")

        if self.plot_residuals:
            return self._rodar_simulacao_com_plot(caminho_script_wsl, wait)

        # Executa o script usando subprocess.Popen para execução não-bloqueante
        # subprocess.Popen retorna imediatamente, permitindo que o código continue
        try:
            self.simulation_process = subprocess.Popen(
                f'wsl bash {caminho_script_wsl}',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Processo de simulação iniciado com PID: {self.simulation_process.pid}")

            if wait:
                # Se wait=True, aguarda a conclusão (comportamento similar ao os.system)
                stdout, stderr = self.simulation_process.communicate()
                print("Simulação concluída.")
                if stdout:
                    print("STDOUT:", stdout)
                if stderr:
                    print("STDERR:", stderr)
                return self.simulation_process.returncode == 0
            else:
                # Se wait=False, retorna imediatamente
                print("Simulação rodando em background. Use wait_simulation() para aguardar conclusão.")
                return False
        except Exception as e:
            print(f"Erro ao executar o script: {e}")
            raise

    def _rodar_simulacao_com_plot(self, caminho_script_wsl: str, wait: bool) -> bool:
        """Executa o solver acompanhando o stdout linha a linha para plotar
        os residuais em tempo real. Como isso exige drenar o pipe continuamente,
        esta chamada é sempre sincrona (bloqueia ate o solver terminar),
        independente do parametro `wait`.
        """
        if not wait:
            print(
                "Aviso: plot_residuals=True torna a execucao sincrona; "
                "o parametro wait=False sera ignorado."
            )

        try:
            self.simulation_process = subprocess.Popen(
                f'wsl bash {caminho_script_wsl}',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            print(f"Erro ao executar o script: {e}")
            raise

        print(f"Processo de simulação iniciado com PID: {self.simulation_process.pid}")

        self.residual_log_path = self.case.case_path / "log.simulation"
        plotter = ResidualPlotter()

        with open(self.residual_log_path, "w", encoding="utf-8") as log_file:
            for line in self.simulation_process.stdout:
                print(line, end="")
                log_file.write(line)
                plotter.feed_line(line)

        self.simulation_process.wait()
        returncode = self.simulation_process.returncode
        print(f"Processo de simulação finalizado com código de retorno: {returncode}")

        self.residual_plot_path = plotter.finish(self.case.case_path / "residuals.png")
        self.residual_history = dict(plotter.history)

        return returncode == 0

    def wait_mesh(self, timeout: int = None) -> bool:
        """
        Aguarda a conclusão do processo de preparação de malha.
        
        Args:
            timeout: Tempo máximo de espera em segundos (None = sem limite)
            
        Returns:
            True se o processo terminou com sucesso, False caso contrário
        """
        if self.mesh_process is None:
            print("Nenhum processo de preparação de malha em andamento.")
            return False
        
        try:
            stdout, stderr = self.mesh_process.communicate(timeout=timeout)
            returncode = self.mesh_process.returncode
            print(f"Processo de malha finalizado com código de retorno: {returncode}")
            if stdout:
                print("STDOUT:", stdout)
            if stderr:
                print("STDERR:", stderr)
            return returncode == 0
        except subprocess.TimeoutExpired:
            print(f"Timeout ao aguardar processo de malha (timeout={timeout}s)")
            return False

    def wait_simulation(self, timeout: int = None) -> bool:
        """
        Aguarda a conclusão do processo de simulação.
        
        Args:
            timeout: Tempo máximo de espera em segundos (None = sem limite)
            
        Returns:
            True se o processo terminou com sucesso, False caso contrário
        """
        if self.simulation_process is None:
            print("Nenhum processo de simulação em andamento.")
            return False
        
        try:
            stdout, stderr = self.simulation_process.communicate(timeout=timeout)
            returncode = self.simulation_process.returncode
            print(f"Processo de simulação finalizado com código de retorno: {returncode}")
            if stdout:
                print("STDOUT:", stdout)
            if stderr:
                print("STDERR:", stderr)
            return returncode == 0
        except subprocess.TimeoutExpired:
            print(f"Timeout ao aguardar processo de simulação (timeout={timeout}s)")
            return False

    def is_mesh_running(self) -> bool:
        """Retorna True se o processo de preparação de malha está em andamento."""
        if self.mesh_process is None:
            return False
        return self.mesh_process.poll() is None

    def is_simulation_running(self) -> bool:
        """Retorna True se o processo de simulação está em andamento."""
        if self.simulation_process is None:
            return False
        return self.simulation_process.poll() is None

    def kill_mesh(self) -> bool:
        """Encerra o processo de preparação de malha."""
        if self.mesh_process is None:
            print("Nenhum processo de preparação de malha em andamento.")
            return False
        try:
            self.mesh_process.terminate()
            print(f"Processo de malha (PID: {self.mesh_process.pid}) foi terminado.")
            return True
        except Exception as e:
            print(f"Erro ao encerrar processo de malha: {e}")
            return False

    def kill_simulation(self) -> bool:
        """Encerra o processo de simulação."""
        if self.simulation_process is None:
            print("Nenhum processo de simulação em andamento.")
            return False
        try:
            self.simulation_process.terminate()
            print(f"Processo de simulação (PID: {self.simulation_process.pid}) foi terminado.")
            return True
        except Exception as e:
            print(f"Erro ao encerrar processo de simulação: {e}")
            return False


class Simulation:
    """Guarda dados de simulacao, registra chamadas e gera script de maquina."""

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
        # Real-time convergence monitoring.
        "monitoring": {
            "plot_residuals": True,
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

    def __init__(self, user_script_path: str = None, case_path: str = None, **kwargs):
        self.user_script_path = Path(user_script_path) if user_script_path else None
        self.case_path = Path(case_path) if case_path else None
        self.simulation_config = copy.deepcopy(self.DEFAULT_SIMULATION_CONFIG)
        self.user_simulation_config = {}
        self.object_simulation = {}
        self.mesh_import_path = None
        # Maps variable name -> semantic geometry type (e.g. "person", "dip", "table", "room").
        # This is used later to keep boundary/BC logic stable even when patches are
        # named after user variables (e.g. "c", "e").
        self.object_types = {}
        # Maps variable name -> instantiated class name (e.g. "Person_seated").
        self.object_classes = {}
        self.machine_script = ""
        self._loaded = False
        self._recording_enabled = self.user_script_path is None
        self._machine_lines = ["import GeoMesh as nemos"]
        self._object_var_names = {}
        self._used_var_names = set()
        self._var_counter = 0
        self._salome_env_recorded = False
        self._quality_helper_recorded = False

        if kwargs:
            self.simulation_config = self._apply_simulation_kwargs(kwargs)
            self._loaded = True

        _set_active_simulation(self)

    @staticmethod
    def Import_mesh(mesh_path: str):
        sim = _get_active_simulation()
        if sim.case_path is None:
            raise ValueError("Simulation precisa de case_path para importar a malha")
        if mesh_path is None:
            raise ValueError("mesh_path nao pode ser None")

        mesh_file = Path(mesh_path)
        if mesh_file.is_dir():
            mesh_file = mesh_file / "Mesh_1.unv"

        if mesh_file.name != "Mesh_1.unv":
            raise ValueError("O arquivo de malha deve se chamar 'Mesh_1.unv'")
        if not mesh_file.exists():
            raise FileNotFoundError(f"Arquivo de malha nao encontrado: {mesh_file}")

        sim.mesh_import_path = mesh_file
        return mesh_file

    def _ensure_imported_mesh(self):
        if not self.mesh_import_path:
            return None
        if self.case_path is None:
            raise ValueError("Simulation precisa de case_path para importar a malha")

        source = Path(self.mesh_import_path)
        if source.is_dir():
            source = source / "Mesh_1.unv"
        if not source.exists():
            raise FileNotFoundError(f"Arquivo de malha nao encontrado: {source}")

        dest = Path(self.case_path) / "Mesh_1.unv"
        os.makedirs(self.case_path, exist_ok=True)

        try:
            if source.resolve() == dest.resolve():
                return dest
        except Exception:
            pass

        shutil.copy2(source, dest)
        return dest

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

    def _apply_simulation_kwargs(self, kwargs: dict) -> dict:
        cfg = copy.deepcopy(self.DEFAULT_SIMULATION_CONFIG)

        control = cfg.setdefault("controlDict", {})
        decompose = cfg.setdefault("decomposeParDict", {})
        fields = cfg.setdefault("fields", {})
        monitoring = cfg.setdefault("monitoring", {})

        direct_maps = {
            "startTime": (control, "startTime"),
            "endTime": (control, "endTime"),
            "delta": (control, "delta"),
            "deltaT": (control, "deltaT"),
            "writeInterval": (control, "writeInterval"),
            "parallel": (decompose, "parallel"),
            "plot_residuals": (monitoring, "plot_residuals"),
        }

        field_aliases = {
            "U_internalField": ("U", "internalField"),
            "U_Field": ("U", "internalField"),
            "T_internalField": ("T", "internalField"),
            "T_Field": ("T", "internalField"),
            "p_internalField": ("p", "internalField"),
            "p_Field": ("p", "internalField"),
            "k_internalField": ("k", "internalField"),
            "k_Field": ("k", "internalField"),
            "epsilon_internalField": ("epsilon", "internalField"),
            "epsilon_Field": ("epsilon", "internalField"),
        }

        for key, value in kwargs.items():
            if key in direct_maps:
                target, target_key = direct_maps[key]
                target[target_key] = value
                continue

            if key in field_aliases:
                field_name, field_key = field_aliases[key]
                fields.setdefault(field_name, {})[field_key] = value
                continue

            if key in ("controlDict", "decomposeParDict", "fields", "monitoring") and isinstance(value, dict):
                cfg[key] = self._merge_dicts(cfg.get(key, {}), value)

        return self._normalize_simulation_config(cfg)

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

        cfg.setdefault("monitoring", {}).setdefault("plot_residuals", True)

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

    def _reserve_var_name(self, base: str):
        if not base:
            self._var_counter += 1
            base = f"obj_{self._var_counter}"

        base = re.sub(r"\W|^(?=\d)", "_", str(base))
        if not base:
            self._var_counter += 1
            base = f"obj_{self._var_counter}"

        candidate = base
        idx = 2
        while candidate in self._used_var_names:
            candidate = f"{base}_{idx}"
            idx += 1

        self._used_var_names.add(candidate)
        return candidate

    def _format_value(self, value):
        if isinstance(value, _RecordedObject):
            return value._var_name
        if isinstance(value, list):
            inner = ", ".join(self._format_value(v) for v in value)
            return f"[{inner}]"
        if isinstance(value, tuple):
            inner = ", ".join(self._format_value(v) for v in value)
            if len(value) == 1:
                inner = inner + ","
            return f"({inner})"
        if isinstance(value, dict):
            parts = []
            for key, val in value.items():
                parts.append(f"{repr(key)}: {self._format_value(val)}")
            return "{" + ", ".join(parts) + "}"
        return repr(value)

    def _format_args_kwargs(self, args, kwargs):
        parts = [self._format_value(arg) for arg in args]
        for key, value in kwargs.items():
            parts.append(f"{key}={self._format_value(value)}")
        return ", ".join(parts)

    def _default_mesh_export_path(self):
        if self.case_path is None:
            return None
        return str(Path(self.case_path) / "Mesh_1.unv")

    def _create_mesh_exports_unv(self, args, kwargs):
        if kwargs.get("export") is True:
            return True
        return len(args) >= 2 and args[1] is True

    def _create_mesh_has_export_path(self, args, kwargs):
        if len(args) >= 3 and args[2]:
            return True
        return bool(kwargs.get("caminho"))

    def _with_default_mesh_export_path(self, args, kwargs):
        kwargs = dict(kwargs)
        if (
            self._create_mesh_exports_unv(args, kwargs)
            and not self._create_mesh_has_export_path(args, kwargs)
        ):
            export_path = self._default_mesh_export_path()
            if export_path is not None:
                kwargs["caminho"] = export_path
        return kwargs

    def _register_object(self, obj, class_name: str, args, kwargs):
        if not self._recording_enabled:
            return None


        kwargs = dict(kwargs)
        name_value = kwargs.get("name")

        required_name = class_name in {
            "Room",
            "Person_seated",
            "Person_standing",
            "Dip_type_00",
            "Dip_type_01",
            "Dip_type_02",
            "Dip_type_03",
            "Table_retangular",
            "Table_circular",
        }
        if required_name and not name_value:
            raise ValueError("Todos os objetos devem receber name=...")

        object_key = str(name_value).strip() if name_value is not None else None

        if object_key:
            self.object_classes[object_key] = class_name
            inferred_type = self._class_to_object_type(class_name)
            if inferred_type is not None:
                self.object_types[object_key] = inferred_type

            inline_sim = {}
            for key in list(kwargs.keys()):
                if key in self.SIMULATION_INLINE_KEYS:
                    inline_sim[key] = kwargs.pop(key)
            if inline_sim:
                existing = self.object_simulation.get(object_key, {})
                existing.update(inline_sim)
                self.object_simulation[object_key] = existing

        if class_name == "Salome_Env":
            var_name = self._reserve_var_name("a")
        else:
            var_name = self._reserve_var_name(object_key or class_name.lower())

        args_str = self._format_args_kwargs(args, kwargs)
        self._record_line(f"{var_name} = nemos.{class_name}({args_str})")
        self._object_var_names[obj] = var_name
        return var_name

    def _record_method(self, obj, method_name: str, args, kwargs):
        if not self._recording_enabled:
            return
        var_name = self._object_var_names.get(obj)
        if not var_name:
            return
        if obj._class_name == "Mesh" and method_name == "check_quality":
            self._record_check_quality(var_name, args, kwargs)
            return
        if obj._class_name == "Mesh" and method_name == "create_mesh":
            kwargs = self._with_default_mesh_export_path(args, kwargs)
        args_str = self._format_args_kwargs(args, kwargs)
        self._record_line(f"{var_name}.{method_name}({args_str})")

    def _ensure_quality_helper(self):
        """Insere (uma vez) 'import SMESH' + o helper de resumo logo apos o
        cabecalho 'import GeoMesh as nemos' do machine script."""
        if self._quality_helper_recorded:
            return
        self._machine_lines[1:1] = _QUALITY_SUMMARY_HELPER
        self._quality_helper_recorded = True

    def _record_check_quality(self, var_name: str, args, kwargs):
        """Traduz Mesh.check_quality(strings amigaveis) para a chamada com
        constantes SMESH, injeta out_dir = pasta do caso e emite tambem a
        geracao do resumo .txt. Espelha a injecao de caminho de create_mesh."""
        args = list(args)
        kwargs = dict(kwargs)

        def _take(pos, key, default=None):
            if key in kwargs:
                return kwargs[key]
            if len(args) > pos:
                return args[pos]
            return default

        # Ordem posicional segue a assinatura de GeoMesh.Mesh.check_quality:
        # (name_metric, element_type, filter_type, comparison, threshold, create_group)
        name_metric = _take(0, "name_metric")
        element_type = _take(1, "element_type", "FACE")
        comparison = _take(3, "comparison", ">")
        threshold = _take(4, "threshold")
        create_group = _take(5, "create_group", False)

        if name_metric is None or threshold is None:
            # Dados insuficientes: grava a chamada crua para nao mascarar o erro.
            args_str = self._format_args_kwargs(tuple(args), kwargs)
            self._record_line(f"{var_name}.check_quality({args_str})")
            return

        element_token = _ELEMENT_TYPE_MAP.get(str(element_type).strip().upper(), "SMESH.FACE")
        comparison_token = _COMPARISON_MAP.get(str(comparison).strip(), "SMESH.FT_MoreThan")
        filter_token = "SMESH.FT_" + str(name_metric)
        out_dir = str(self.case_path) if self.case_path is not None else None

        self._ensure_quality_helper()

        call_parts = [
            repr(str(name_metric)),
            element_token,
            filter_token,
            comparison_token,
            repr(threshold),
        ]
        if create_group:
            call_parts.append(f"create_group={repr(bool(create_group))}")
        if out_dir is not None:
            call_parts.append(f"out_dir={repr(out_dir)}")

        self._record_line(f"_nemos_q = {var_name}.check_quality({', '.join(call_parts)})")
        self._record_line(
            f"_nemos_quality_summary(_nemos_q, {repr(str(name_metric))}, {repr(out_dir or '')})"
        )

    def _record_line(self, line: str):
        if not self._recording_enabled:
            return
        self._machine_lines.append(line)

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
        name_value = None

        for token in tokens:
            sim_key, sim_value = self._parse_simulation_token(token)
            if sim_key is not None:
                inline_sim[sim_key] = sim_value
            else:
                name_match = re.match(r"^\s*name\s*=\s*(.+)\s*$", token)
                if name_match:
                    raw_name = name_match.group(1).strip()
                    try:
                        name_value = ast.literal_eval(raw_name)
                    except Exception:
                        name_value = raw_name
                kept_tokens.append(token)

        object_key = str(name_value).strip() if name_value is not None else var_name

        self.object_classes[object_key] = class_name
        inferred_type = self._class_to_object_type(class_name)
        if inferred_type is not None:
            self.object_types[object_key] = inferred_type

        if inline_sim:
            existing = self.object_simulation.get(object_key, {})
            existing.update(inline_sim)
            self.object_simulation[object_key] = existing

        args_clean = ", ".join(t for t in kept_tokens if t)
        return f"{indent}{var_name} = nemos.{class_name}({args_clean})"

    def _inject_default_create_mesh_path(self, line: str):
        export_path = self._default_mesh_export_path()
        if export_path is None or ".create_mesh(" not in line:
            return line

        pattern = re.compile(r"^(\s*[A-Za-z_]\w*\.create_mesh\()(.*)(\)\s*)$")
        match = pattern.match(line)
        if not match:
            return line

        prefix, args_text, suffix = match.groups()
        tokens = self._split_top_level_commas(args_text)
        has_export = any(re.match(r"^\s*export\s*=\s*True\s*$", token) for token in tokens)
        has_export = has_export or (len(tokens) >= 2 and tokens[1].strip() == "True")
        has_caminho = any(re.match(r"^\s*caminho\s*=", token) for token in tokens)

        if not has_export or has_caminho:
            return line

        tokens.append(f"caminho={repr(export_path)}")
        return f"{prefix}{', '.join(tokens)}{suffix}"

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
            sanitized_line = self._sanitize_object_line(line)
            sanitized_line = self._inject_default_create_mesh_path(sanitized_line)
            sanitized_lines.append(sanitized_line)

        return "\n".join(sanitized_lines).strip() + "\n"

    def read_user_script(self):
        if self.user_script_path is None:
            self._loaded = True
            return {
                "simulation_config": self.simulation_config,
                "object_simulation": self.object_simulation,
                "machine_script": self.generate_machine_script(),
            }
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
        if self._recording_enabled:
            self.machine_script = "\n".join(self._machine_lines).strip() + "\n"
            return self.machine_script
        if not self._loaded:
            self.read_user_script()
        return self.machine_script

    def build_machine_script(self, output_path: str = None):
        if output_path is None:
            if self.case_path is not None:
                output_path = self.case_path / "machine_script.py"
            else:
                output_path = "machine_script.py"
        return self.write_machine_script(str(output_path))

    def write_machine_script(self, output_path: str):
        script = self.generate_machine_script()
        output_file = Path(output_path)
        output_file.write_text(script, encoding="utf-8")
        return output_file

    def save_state(self, path: str = None):
        """Persiste a configuracao/metadados do caso para permitir retomar
        a simulacao apenas apontando para a pasta do caso (ver `resume`)."""
        if self.case_path is None:
            return None
        if not self._loaded:
            self.read_user_script()
        state_path = Path(path) if path else Path(self.case_path) / STATE_FILE
        data = {
            "simulation_config": self.simulation_config,
            "object_simulation": self.object_simulation,
            "object_types": self.object_types,
            "object_classes": self.object_classes,
        }
        os.makedirs(self.case_path, exist_ok=True)
        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return state_path

    @classmethod
    def load_state(cls, case_path: str):
        """Reconstroi uma Simulation a partir do estado salvo em `case_path`."""
        case_path = Path(case_path)
        state_path = case_path / STATE_FILE
        if not state_path.exists():
            raise FileNotFoundError(
                f"Estado nao encontrado: {state_path}. "
                "Rode a simulacao original ao menos uma vez antes de retomar."
            )
        data = json.loads(state_path.read_text(encoding="utf-8"))
        # user_script_path=None -> modo de gravacao; nao le nenhum script.
        sim = cls(case_path=str(case_path))
        sim.simulation_config = data.get("simulation_config", sim.simulation_config)
        sim.object_simulation = data.get("object_simulation", {})
        sim.object_types = data.get("object_types", {})
        sim.object_classes = data.get("object_classes", {})
        sim._loaded = True
        return sim


class _RecordedObject:
    def __init__(self, class_name: str, *args, **kwargs):
        self._simulation = _get_active_simulation()
        self._class_name = class_name
        self._var_name = self._simulation._register_object(self, class_name, args, kwargs)

    def __getattr__(self, name: str):
        def _method(*args, **kwargs):
            self._simulation._record_method(self, name, args, kwargs)
            return None

        return _method


class Salome_Env(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Salome_Env", *args, **kwargs)


class Room(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Room", *args, **kwargs)


class Person_seated(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Person_seated", *args, **kwargs)


class Person_standing(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Person_standing", *args, **kwargs)


class Dip_type_00(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Dip_type_00", *args, **kwargs)


class Dip_type_01(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Dip_type_01", *args, **kwargs)


class Dip_type_02(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Dip_type_02", *args, **kwargs)


class Dip_type_03(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Dip_type_03", *args, **kwargs)


class Table_retangular(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Table_retangular", *args, **kwargs)


class Table_circular(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Table_circular", *args, **kwargs)


class Mesh(_RecordedObject):
    def __init__(self, *args, **kwargs):
        super().__init__("Mesh", *args, **kwargs)


def salome_update():
    sim = _get_active_simulation()
    sim._record_line("nemos.salome_update()")


def setup_workflow(simulation, salome_exe: str = DEFAULT_SALOME_EXE, script_path: str = None):
    if simulation is None:
        raise ValueError("Simulation nao pode ser None")
    if simulation.case_path is None:
        raise ValueError("Simulation precisa de case_path")

    case = OpenFOAMCase(str(simulation.case_path))
    simulation.read_user_script()
    simulation.write_machine_script(str(case.case_path / "machine_script.py"))
    case.gerar_arquivos_base(simulation.simulation_config)

    if script_path is None:
        script_path = str(case.case_path / "machine_script.py")

    mesher = SalomeMesher(salome_exe, script_path, simulation=simulation)
    boundary_manager = BoundaryManager(case, simulation=simulation)
    runner = OpenFOAMRunner(case, simulation=simulation)

    return case, mesher, boundary_manager, runner


def run(simulation, salome_exe: str = DEFAULT_SALOME_EXE, script_path: str = None):
    """Executa o fluxo completo do caso.

    O fluxo e idempotente: cada estagio so roda se seu artefato ainda nao
    existe na pasta do caso, de modo que rodar de novo apos uma interrupcao
    retoma de onde parou (ver detectores em OpenFOAMCase e a funcao `resume`).
    """
    case, mesher, boundary_manager, runner = setup_workflow(
        simulation,
        salome_exe=salome_exe,
        script_path=script_path,
    )

    # Guarda o estado do caso para permitir retomar so com a pasta do caso.
    if simulation is not None:
        simulation.save_state()

    # --- Estagio: geracao/importacao da malha (SALOME) ---
    if case.mesh_geometry_ready():
        print("[resume] Malha (Mesh_1.unv) ja existe, pulando SALOME.")
    elif simulation is not None and getattr(simulation, "mesh_import_path", None):
        simulation._ensure_imported_mesh()
    else:
        mesher.executar_batch()

    # --- Estagio: conversao da malha (ideasUnvToFoam + checkMesh) ---
    if case.mesh_converted():
        print("[resume] Malha ja convertida (polyMesh), pulando conversao.")
    else:
        mesh_ok = runner.preparar_malha(wait=True)
        if not mesh_ok:
            raise RuntimeError("A preparacao da malha falhou. Verifique a saida do comandos_1.sh.")
    if not case.boundary_file.exists():
        raise FileNotFoundError(f"Arquivo boundary nao encontrado em '{case.boundary_file}'")

    # --- Estagio: condicoes de contorno e campos da pasta 0/ ---
    if case.fields_ready():
        print("[resume] Campos da pasta 0/ ja existem, pulando geracao.")
    else:
        boundary_manager.editar_boundary()
        boundary_manager.generate_all_fields()

    # --- Estagio: solver (decomposePar guardado no bash; solver retoma
    # da ultima iteracao via 'startFrom latestTime' no controlDict) ---
    solver_ok = runner.rodar_simulacao()

    case.residual_log_path = runner.residual_log_path
    case.residual_plot_path = runner.residual_plot_path
    case.residual_history = runner.residual_history

    if solver_ok:
        case.done_marker().write_text("ok\n", encoding="utf-8")

    return case


def resume(case_path, salome_exe: str = DEFAULT_SALOME_EXE):
    """Retoma uma simulacao individual apontando apenas para a pasta do caso.

    Reconstroi a Simulation a partir do estado salvo (.nemos_state.json) e
    reexecuta o fluxo idempotente. Requer que a malha geometrica ja exista
    (Mesh_1.unv) — o caso comum de interrupcao durante o solver. Para
    interrupcoes antes da malha, rode novamente o script de geometria original.
    """
    case_path = Path(case_path)
    if (case_path / ".nemos_done").exists():
        print(f"[resume] Caso ja concluido: {case_path}")
        return None
    simulation = Simulation.load_state(case_path)
    return run(simulation, salome_exe=salome_exe)


if __name__ == "__main__":
    # Fluxo legado de execução direta do Auto_6.
    case = OpenFOAMCase(r"C:\Users\pedro\Desktop\TCC1\Sim_000")

    user_script_path = case.case_path / "user_script.py"
    simulation = None
    if user_script_path.exists():
        simulation = Simulation(str(user_script_path))
        simulation.read_user_script()
        simulation.write_machine_script(str(case.case_path / "machine_script.py"))
        # Gera arquivos base já parametrizados.
        case.gerar_arquivos_base(simulation.simulation_config)

    mesher = SalomeMesher(
        r"c:\SALOME-9.15.0\run_salome.bat",
        str(case.case_path / "machine_script.py"),
        simulation=simulation,
    )
    boundary_manager = BoundaryManager(case, simulation=simulation)
    runner = OpenFOAMRunner(case, simulation=simulation)

    mesher.executar_batch()
    mesh_ok = runner.preparar_malha(wait=True)
    if not mesh_ok:
        raise RuntimeError("A preparacao da malha falhou. Verifique a saida do comandos_1.sh.")
    if not case.boundary_file.exists():
        raise FileNotFoundError(f"Arquivo boundary nao encontrado em '{case.boundary_file}'")
    boundary_manager.editar_boundary()
    boundary_manager.generate_all_fields()
    runner.rodar_simulacao()

    print('Programa Finalizado')

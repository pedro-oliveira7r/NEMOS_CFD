import os

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


# ---------------- Exemplo de uso ----------------
# Substitua pelo caminho da pasta do seu caso OpenFOAM
gerar_arquivos(r"C:\Users\pedro\Desktop\Auto_Nemos\Nova pasta")


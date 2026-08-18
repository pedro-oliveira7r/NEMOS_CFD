"""Gate A pre-execution checks for the NEMOS validation layer.

Implements sections 2.1 to 2.5 of docs/guardrail_architecture.md:

    check_environment        E-ENV-01..07, W-ENV-08..10, I-ENV-11   (§2.1)
    check_simulation_kwargs  E-CFG-01                               (§2.2)
    check_control_config     E-CFG-02, E-CFG-03, W-CFG-06,
                             W-CFG-07, I-CFG-08                     (§2.2)
    check_field_config       E-CFG-04, E-CFG-05                     (§2.2)
    check_inline_keys        W-CFG-09                               (§2.2)
    shape_extent             (shape-spec table, no codes)           (§2.3)
    check_geometry_structure E-GEO-01, 02, 03, 06, 07               (§2.3)
    check_geometry_placement E-GEO-04, 05, 08..12, W-GEO-13, 14     (§2.3)
    check_mesh_params        E-MSH-01..03, W-MSH-04..06             (§2.4)
    check_physics            W-PHY-01..09, I-PHY-10                 (§2.5)

Every public function is pure, returns a list of Issue, never raises and never
prints. When a check cannot be performed the failure degrades to a single
W-INT-01 warning saying so: a validation layer that crashes is worse than no
validation layer at all.

Host-side only. Standard library plus validation_core, nothing else, so this
module imports cleanly on a machine with neither SALOME nor WSL.
"""

from __future__ import annotations

import math
import re

from validation_core import (
    Issue,
    error,
    warn,
    info,
    ERROR,
    WARN,
    INFO,
    GeometryModel,
    ObjectRecord,
    MethodRecord,
    Extent,
    EnvProbe,
    as_float,
    is_number,
    format_number,
    suggest,
    plural,
    LIMIT_TEMPERATURE_MIN,
    LIMIT_TEMPERATURE_MAX,
    VELOCITY_DAMPING_UMAX,
    BOUSSINESQ_T0,
    BOUSSINESQ_RHO0,
    BOUSSINESQ_BETA,
    MU,
    PR,
    CP,
    NU,
    P_RGH_INTERNAL,
    INLET_K,
    INLET_MIXING_LENGTH,
    RESIDUAL_CONTROL,
    DECOMPOSE_SUBDOMAINS,
    DIP_CEILING_OFFSET,
    ROOM_AREA_FACTOR,
    OPENING_AREA_FRACTION_MAX,
    OPENFOAM_BASHRC,
    REQUIRED_FOAM_BINARIES,
    RESERVED_OBJECT_NAMES,
)

# --------------------------------------------------------------------------
# Code used when a check itself fails
# --------------------------------------------------------------------------

#: Emitted instead of an exception when a check cannot be completed.
INTERNAL_CODE = "W-INT-01"


# --------------------------------------------------------------------------
# What Simulation() really honours  (Simulation._apply_simulation_kwargs)
# --------------------------------------------------------------------------

#: Keys of `direct_maps` in Simulation._apply_simulation_kwargs.
_DIRECT_KWARGS = (
    "startTime",
    "endTime",
    "delta",
    "deltaT",
    "writeInterval",
    "parallel",
    "plot_residuals",
    "accept_unconverged",
)

#: Keys of `field_aliases` in Simulation._apply_simulation_kwargs.
_FIELD_ALIAS_KWARGS = (
    "U_internalField",
    "U_Field",
    "T_internalField",
    "T_Field",
    "p_internalField",
    "p_Field",
    "k_internalField",
    "k_Field",
    "epsilon_internalField",
    "epsilon_Field",
)

#: Whole config sections accepted as a dict.
_SECTION_KWARGS = ("controlDict", "decomposeParDict", "fields", "monitoring")

#: Named parameters of Simulation.__init__ plus the validation policy switch.
_POSITIONAL_KWARGS = ("case_path", "user_script_path", "validate")

#: Every kwarg Simulation(...) actually honours. Anything else is dropped on
#: the floor by _apply_simulation_kwargs without a word (failure F1).
VALID_SIMULATION_KWARGS = frozenset(
    _DIRECT_KWARGS + _FIELD_ALIAS_KWARGS + _SECTION_KWARGS + _POSITIONAL_KWARGS
)

#: Value each dropped kwarg would silently fall back to, for the E-CFG-01 text.
_SIMULATION_KWARG_DEFAULTS = {
    "startTime": 0,
    "endTime": 3500,
    "delta": 0.1,
    "deltaT": 0.1,
    "writeInterval": 200,
    "parallel": "N",
    "plot_residuals": True,
    "accept_unconverged": False,
    "U_internalField": "uniform (0 -1 0)",
    "U_Field": "uniform (0 -1 0)",
    "T_internalField": "uniform 300",
    "T_Field": "uniform 300",
    "p_internalField": "uniform 101325",
    "p_Field": "uniform 101325",
    "k_internalField": "uniform 0.001",
    "k_Field": "uniform 0.001",
    "epsilon_internalField": "uniform 1e-5",
    "epsilon_Field": "uniform 1e-5",
}


# --------------------------------------------------------------------------
# Inline boundary-condition keys  (Simulation.SIMULATION_INLINE_KEYS)
# --------------------------------------------------------------------------

#: Mirrors Simulation.SIMULATION_INLINE_KEYS. Kept as a literal rather than an
#: import so that this module has no dependency on Simulation.py.
SIMULATION_INLINE_KEYS = frozenset(
    {
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
)

#: The only inline keys BoundaryManager ever reads.
IMPLEMENTED_INLINE_KEYS = frozenset({"T_Face", "T_face", "T_Flow", "V_Flow"})

#: Accepted, recorded, and then never read by anything (failure F4).
UNIMPLEMENTED_INLINE_KEYS = frozenset(SIMULATION_INLINE_KEYS - IMPLEMENTED_INLINE_KEYS)

#: Which implemented inline key BoundaryManager reads for which object type.
#: A key outside this set is stored in object_simulation and then ignored.
_INLINE_KEYS_BY_TYPE = {
    "room": frozenset({"T_Face", "T_face"}),
    "person": frozenset({"T_Face"}),
    "table": frozenset({"T_Face"}),
    "dip": frozenset({"T_Flow", "V_Flow"}),
}


# --------------------------------------------------------------------------
# Geometry constructor signatures  (GeoMesh.py)
# --------------------------------------------------------------------------


def _geometry_kwargs(*names: str) -> frozenset:
    """Constructor parameters + the inline BC keys + `name`."""
    return frozenset(set(names) | set(SIMULATION_INLINE_KEYS) | {"name"})


#: Per class, every keyword the class actually accepts. GeoMesh.Object.__init__
#: pops only `name` out of **kwargs and throws the rest away, so a misspelled
#: `Thickness=0.15` never reaches the geometry (failure F2).
GEOMETRY_KWARGS = {
    "Salome_Env": _geometry_kwargs("path"),
    "Room": _geometry_kwargs("salome_env", "dx", "dy", "dz"),
    "Person_seated": _geometry_kwargs(
        "salome_env", "h", "thickness", "width", "fillet_radius", "x", "z", "theta"
    ),
    "Person_standing": _geometry_kwargs("salome_env", "x", "z", "theta"),
    "Dip_type_00": _geometry_kwargs("salome_env", "d", "x", "y", "z"),
    "Dip_type_01": _geometry_kwargs("salome_env", "d", "x", "y", "z"),
    "Dip_type_02": _geometry_kwargs("salome_env", "d", "x", "y", "z"),
    "Dip_type_03": _geometry_kwargs("salome_env", "d", "x", "y", "z"),
    "Table_retangular": _geometry_kwargs("salome_env", "dx", "dy", "dz", "x", "y", "z"),
    "Table_circular": _geometry_kwargs(
        "salome_env", "raio", "espessura", "x", "y", "z"
    ),
    "Mesh": _geometry_kwargs(
        "room", "m2DMaxSize", "m2DMinSize", "m3DMaxSize", "m3DMinSize", "fineness"
    ),
}

#: Object names must survive BoundaryManager._parse_boundary_file's
#: `(\w+)\s*\{\s*type\s+(\w+);` regex and become valid OpenFOAM patch names.
_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------

MIN_ITERATIONS_ADVISED = 500          # W-CFG-06, buoyant room case
MAX_TIME_DIRECTORIES = 50             # W-CFG-07
TIME_DIR_SIZE_MB = 25.0               # rough per-directory estimate, 8 fields
MIN_FREE_DISK_BYTES = 5 * 1024 ** 3   # W-ENV-09

CELL_COUNT_WARN = 3_000_000           # W-MSH-04
CELLS_PER_GB_RAM = 1_000_000.0        # rough tetra + fields footprint
VALID_FINENESS = (0, 1, 2, 3, 4)      # E-MSH-02
CELLS_ACROSS_FEATURE = 3              # W-MSH-05

REYNOLDS_TURBULENT_MIN = 2300.0       # W-PHY-04
ACH_MIN = 0.5                         # W-PHY-05
ACH_MAX = 20.0
OUTLET_VELOCITY_MAX = 5.0             # W-PHY-06
BOUSSINESQ_DELTA_T_MAX = 15.0         # W-PHY-07
INLET_TURBULENCE_INTENSITY = 0.05     # W-PHY-09, I = 5 %
INLET_K_FACTOR_TOLERANCE = 1.5        # W-PHY-09, report beyond this ratio
GRAVITY = 9.81

#: Two conservative extents must interpenetrate by more than
#: max(OVERLAP_ABS_TOL, OVERLAP_REL_TOL * smaller size) on every axis before
#: E-GEO-05 calls it a clash. The extents are deliberately generous - a seated
#: person is bounded by a rotation-invariant disc - so a shallow intersection
#: is an artefact of the bound, not evidence that the bodies touch.
OVERLAP_ABS_TOL = 0.05
OVERLAP_REL_TOL = 0.25

DIP_COINCIDENCE_TOL = 1e-6            # E-GEO-09, GeoMesh face matching
ROOM_CONTAINMENT_TOL = 1e-6           # E-GEO-04
MAX_REPORTED_PAIRS = 6                # keep W-GEO-14 readable

#: SALOME ViscousLayers total stack thickness per group type (GeoMesh.Mesh).
VISCOUS_LAYER_THICKNESS = {
    "wall": 0.030,
    "person": 0.010,
    "table": 0.010,
    "dip": 0.0025,
}

#: NETGEN 2D local size per group type (GeoMesh.Mesh.create_mesh).
LOCAL_MESH_SIZE = {
    "dip": 0.005,
    "person": 0.02,
    "table": 0.02,
    "wall": 0.050,
}

#: Fixed dimensions of Person_standing, read off GeoMesh.standing(). The body
#: is a 0.20 x 1.40 box extruded 0.30 either way in z; the head is a 0.115
#: sphere; everything is rotated about the vertical line through (x-0.10, z).
STANDING_HEIGHT = 1.68
STANDING_AXIS_DX = -0.10
STANDING_RADIUS = math.hypot(0.20, 0.30)

#: SMESH quality functors that exist as SMESH.FT_* constants. Simulation.py
#: builds the token as "SMESH.FT_" + name, so a name outside this list becomes
#: an AttributeError inside SALOME, forty minutes into the run.
SMESH_QUALITY_METRICS = frozenset(
    {
        "AspectRatio",
        "AspectRatio3D",
        "Warping",
        "MinimumAngle",
        "Taper",
        "Skew",
        "Area",
        "Volume3D",
        "MaxElementLength2D",
        "MaxElementLength3D",
        "Length",
        "Length2D",
        "Deflection2D",
        "BallDiameter",
        "ElemGeomType",
        "EqualVolumes",
        "NodeConnectivityNumber",
    }
)

#: Simulation._ELEMENT_TYPE_MAP / _COMPARISON_MAP. An unmapped value silently
#: degrades to SMESH.FACE / SMESH.FT_MoreThan.
VALID_ELEMENT_TYPES = frozenset({"FACE", "VOLUME"})
VALID_COMPARISONS = frozenset({">", "<", "=", "=="})


# --------------------------------------------------------------------------
# Small internal helpers
# --------------------------------------------------------------------------


def _internal(where: str, exc: Exception) -> Issue:
    """Degrade a failed check to a warning instead of an exception."""
    return warn(
        INTERNAL_CODE,
        f"The {where} check could not be performed.",
        "The validation layer hit an unexpected condition while inspecting "
        f"your script ({type(exc).__name__}: {exc}). This is a limitation of "
        "the checker, not necessarily a problem with your case, but it means "
        f"the {where} checks below are incomplete.",
        "Read the remaining messages normally, and treat the checks named "
        "above as 'not verified'.",
        where=where,
    )


def _probe_call(probe, method_name: str, *args, default=None):
    """Call one EnvProbe method, degrading to `default` on any failure."""
    method = getattr(probe, method_name, None)
    if method is None:
        return default
    try:
        return method(*args)
    except Exception:
        return default


def _resolve_name(item) -> str | None:
    """Best-effort name for an object referenced inside a recorded call."""
    if item is None:
        return None
    if isinstance(item, str):
        return item
    for attr in ("name", "_nemos_name", "_var_name"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _truthy_yes(value) -> bool:
    """Mirror of Simulation's `str(parallel).upper().startswith('Y')`."""
    if isinstance(value, bool):
        return value
    return str(value).strip().upper().startswith("Y")


def _object_label(obj: ObjectRecord) -> str:
    return f"{obj.name} ({obj.class_name})"


def _viscous_thickness(obj: ObjectRecord) -> float:
    return VISCOUS_LAYER_THICKNESS.get(obj.object_type or "", 0.0)


def _opening_records(geometry: GeometryModel) -> list[dict]:
    """Normalise every insert_*_opening call into a plain dict.

    `d` is what the user typed; MakeCircle consumes it as a RADIUS
    (GeoMesh.py:450), hence radius == d and area == pi * d**2.
    """
    records = []
    for index, call in enumerate(geometry.openings(), start=1):
        x = call.number("x", 0, None)
        z = call.number("z", 1, None)
        d = call.number("d", 2, None)
        records.append(
            {
                "index": index,
                "method": call.method,
                "label": f"{call.method} #{index}",
                "x": x,
                "z": z,
                "d": d,
                "radius": d,
                "area": math.pi * d * d if d is not None else None,
                "order": call.order,
            }
        )
    return records


def _dip_records(geometry: GeometryModel) -> list[dict]:
    """Position, throat diameter and inline BCs of every dip."""
    records = []
    for obj in geometry.of_type("dip"):
        records.append(
            {
                "obj": obj,
                "name": obj.name,
                "x": obj.number("x", 1.0),
                "y": obj.number("y", 1.2),
                "z": obj.number("z", 1.5),
                "d": obj.number("d", 0.05),
                "V_Flow": as_float(_inline_value(obj, "V_Flow"), None),
                "T_Flow": as_float(_inline_value(obj, "T_Flow"), None),
            }
        )
    return records


def _inline_value(obj: ObjectRecord, key: str):
    """Inline BC value, whether the recorder stored it in `inline` or `kwargs`."""
    if key in (obj.inline or {}):
        return obj.inline[key]
    return (obj.kwargs or {}).get(key)


def _inline_keys(obj: ObjectRecord) -> set:
    return set(obj.inline or {}) | (set(obj.kwargs or {}) & SIMULATION_INLINE_KEYS)


def _uniform_scalar(text) -> float | None:
    """Parse `uniform <scalar>`; None when the string is not that shape."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    match = re.fullmatch(
        r"\s*uniform\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*;?\s*", str(text)
    )
    return float(match.group(1)) if match else None


def _uniform_vector(text) -> tuple | None:
    """Parse `uniform (x y z)`; None when the string is not that shape."""
    match = re.fullmatch(
        r"\s*uniform\s*\(\s*([^()]+?)\s*\)\s*;?\s*", str(text)
    )
    if not match:
        return None
    parts = match.group(1).split()
    if len(parts) != 3:
        return None
    values = [as_float(part, None) for part in parts]
    if any(value is None for value in values):
        return None
    return tuple(values)


# ==========================================================================
# 2.1  Environment
# ==========================================================================


def check_environment(
    probe: EnvProbe,
    salome_exe,
    case_path,
    parallel: bool,
    plot_residuals: bool,
) -> list[Issue]:
    """Check the machine can actually run this case.

    Emits E-ENV-01, E-ENV-02, E-ENV-03, E-ENV-04, E-ENV-05, E-ENV-06,
    E-ENV-07, W-ENV-08, W-ENV-09, W-ENV-10 and I-ENV-11.

    Every query goes through `probe` so a caller can simulate a missing
    OpenFOAM binary or an absent WSL without touching the real machine.
    """
    issues: list[Issue] = []
    try:
        issues.extend(_check_salome_exe(probe, salome_exe))
        wsl_ok, wsl_issues = _check_wsl(probe)
        issues.extend(wsl_issues)
        issues.extend(_check_case_path_string(case_path))
        issues.extend(_check_resources(probe, case_path, parallel, plot_residuals, wsl_ok))
        issues.append(_environment_record(probe, salome_exe, wsl_ok))
    except Exception as exc:  # never raise from a check
        issues.append(_internal("environment", exc))
    return issues


def _check_salome_exe(probe, salome_exe) -> list[Issue]:
    """E-ENV-01."""
    if not salome_exe:
        return [
            error(
                "E-ENV-01",
                "No SALOME executable was given.",
                "NEMOS drives SALOME in batch mode to build the geometry and "
                "the mesh. Without the executable nothing can be meshed.",
                'Pass salome_exe=r"C:\\SALOME-9.15.0\\run_salome.bat" to '
                "run()/setup_workflow(), or install SALOME at that path.",
                where="salome_exe",
            )
        ]

    text = str(salome_exe)
    if not _probe_call(probe, "path_exists", text, default=False):
        return [
            error(
                "E-ENV-01",
                f"SALOME executable not found: {text}",
                "Today this only prints a message and returns, so the run "
                "carries on and fails two stages later with a missing "
                "Mesh_1.unv. The path is checked here instead, before any "
                "work is done.",
                "Correct salome_exe=..., or install SALOME 9.15 at that "
                "location. The default is C:\\SALOME-9.15.0\\run_salome.bat.",
                where="salome_exe",
                value=text,
            )
        ]

    issues = []
    if _probe_call(probe, "is_file", text, default=True) is False:
        issues.append(
            error(
                "E-ENV-01",
                f"salome_exe is a directory, not a file: {text}",
                "NEMOS runs `\"<salome_exe>\" -t <script>`, which needs the "
                "launcher itself.",
                "Point salome_exe at run_salome.bat inside that folder.",
                where="salome_exe",
                value=text,
            )
        )
    elif not text.lower().endswith((".bat", ".exe")):
        issues.append(
            error(
                "E-ENV-01",
                f"salome_exe is not a .bat or .exe launcher: {text}",
                "The batch call is built as `\"<salome_exe>\" -t <script>` and "
                "is executed by the Windows shell, which can only start a "
                ".bat or an .exe.",
                "Use the SALOME launcher, normally run_salome.bat.",
                where="salome_exe",
                value=text,
            )
        )
    return issues


def _check_wsl(probe) -> tuple[bool, list[Issue]]:
    """E-ENV-02, E-ENV-03, E-ENV-04. Returns (wsl_usable, issues)."""
    issues: list[Issue] = []

    if not _probe_call(probe, "wsl_available", default=False):
        issues.append(
            error(
                "E-ENV-02",
                "WSL is not available, or no Linux distribution is installed.",
                "Every OpenFOAM command (ideasUnvToFoam, checkMesh, "
                "decomposePar, buoyantSimpleFoam) is run through "
                "`wsl bash <script>`. Without a working WSL distribution the "
                "solver stage cannot start at all.",
                "Run `wsl --install -d Ubuntu-24.04` in PowerShell, reboot, "
                "then confirm `wsl -l -q` lists the distribution.",
                where="wsl",
            )
        )
        return (False, issues)

    if not _probe_call(probe, "wsl_test_file", OPENFOAM_BASHRC, default=False):
        issues.append(
            error(
                "E-ENV-03",
                f"OpenFOAM environment file not found in WSL: {OPENFOAM_BASHRC}",
                "The generated shell scripts start with `source "
                f"{OPENFOAM_BASHRC}`. That path is hardcoded, so a different "
                "OpenFOAM version or install prefix will not be found. The "
                "script has no `set -e`, so it carries on and every OpenFOAM "
                "command afterwards fails as 'command not found'.",
                "Install OpenFOAM v2312 in WSL "
                "(`sudo apt install openfoam2312-default`), or create the "
                "expected path so that file exists.",
                where="wsl",
                value=OPENFOAM_BASHRC,
            )
        )
        return (True, issues)

    found = _probe_call(probe, "wsl_which", REQUIRED_FOAM_BINARIES, default=None)
    if isinstance(found, dict):
        missing = sorted(name for name in REQUIRED_FOAM_BINARIES if not found.get(name))
        if missing:
            issues.append(
                error(
                    "E-ENV-04",
                    f"OpenFOAM command{'s' if len(missing) != 1 else ''} not on "
                    f"PATH after sourcing the bashrc: {', '.join(missing)}",
                    "These are the binaries the pipeline calls directly. A "
                    "partial OpenFOAM install fails silently: the bash script "
                    "has no `set -e`, so a missing ideasUnvToFoam still lets "
                    "checkMesh run on an old mesh and the return code looks "
                    "fine.",
                    "Install the full OpenFOAM v2312 package in WSL, then "
                    "verify with `wsl bash -lc 'source "
                    f"{OPENFOAM_BASHRC}; command -v {missing[0]}'`.",
                    where="wsl",
                    value=missing,
                )
            )
    return (True, issues)


def _check_case_path_string(case_path) -> list[Issue]:
    """E-ENV-05, E-ENV-06, E-ENV-07.

    The only translation NEMOS applies is
    `str(path).replace('\\\\', '/').replace('C:', '/mnt/c')`, so anything that
    is not a plain ASCII, space-free path on the literal drive `C:` reaches
    bash as a path that does not exist.
    """
    if case_path in (None, ""):
        return [
            error(
                "E-ENV-05",
                "case_path is not set.",
                "Every generated file, the mesh, the 0/ directory and the "
                "shell scripts all live under case_path. Nothing can be "
                "written without it.",
                'Pass case_path=r"C:\\...\\my_case" to Simulation(...).',
                where="case_path",
            )
        ]

    raw = str(case_path)
    issues: list[Issue] = []

    if raw.startswith("\\\\") or raw.startswith("//"):
        issues.append(
            error(
                "E-ENV-05",
                f"case_path is a UNC network path: {raw}",
                "The WSL translation only rewrites a leading drive letter "
                "(`C:` -> `/mnt/c`). A UNC path is passed to bash unchanged, "
                "the `cd` fails, and because the script has no `set -e` every "
                "later command runs in the wrong directory.",
                "Copy the case to a local folder on the C: drive, for example "
                "C:\\Users\\<you>\\Desktop\\my_case.",
                where="case_path",
                value=raw,
            )
        )
    else:
        drive = re.match(r"^([A-Za-z]):", raw)
        if drive is None:
            issues.append(
                error(
                    "E-ENV-05",
                    f"case_path has no Windows drive letter: {raw}",
                    "NEMOS translates the case path for WSL by replacing a "
                    "literal `C:` with `/mnt/c`. A relative path, or any other "
                    "form, is handed to bash unchanged and the `cd` fails "
                    "silently.",
                    "Use a full absolute path starting with C:\\ , for example "
                    "C:\\Users\\<you>\\Desktop\\my_case.",
                    where="case_path",
                    value=raw,
                )
            )
        elif drive.group(1) != "C":
            if drive.group(1) == "c":
                issues.append(
                    error(
                        "E-ENV-06",
                        f"case_path starts with a lowercase drive letter: {raw}",
                        "The translation is a literal string replacement of "
                        "`C:` and is case sensitive, so `c:\\...` is never "
                        "converted. Bash then receives a path starting with "
                        "`c:/` and the `cd` fails; the script has no `set -e`, "
                        "so it keeps going and everything downstream is "
                        "garbage.",
                        f"Write the drive letter in upper case: "
                        f"{'C' + raw[1:]}",
                        where="case_path",
                        value=raw,
                    )
                )
            else:
                issues.append(
                    error(
                        "E-ENV-05",
                        f"case_path is on drive {drive.group(1)}:, but only C: "
                        "is supported.",
                        "The WSL translation replaces the literal `C:` with "
                        f"`/mnt/c` and nothing else, so `{drive.group(1)}:` is "
                        "passed through untouched. Bash cannot find that "
                        "directory and, with no `set -e`, silently continues.",
                        "Move the case to the C: drive, for example "
                        "C:\\Users\\<you>\\Desktop\\my_case.",
                        where="case_path",
                        value=raw,
                    )
                )

    if " " in raw:
        issues.append(
            error(
                "E-ENV-07",
                f"case_path contains a space: {raw}",
                "The shell command is built as `wsl bash {path}` with no "
                "quoting, so bash reads only the text up to the first space "
                "and reports a cryptic 'No such file or directory'.",
                "Rename the folders so the whole path has no spaces, for "
                "example C:\\Users\\<you>\\Desktop\\my_case.",
                where="case_path",
                value=raw,
            )
        )

    non_ascii = sorted({char for char in raw if ord(char) > 127})
    if non_ascii:
        issues.append(
            error(
                "E-ENV-07",
                "case_path contains non-ASCII characters: "
                f"{' '.join(non_ascii)}",
                "The path crosses three encodings on its way to the solver "
                "(Python, the Windows shell, then bash inside WSL). Accented "
                "characters survive none of them reliably, and the failure "
                "shows up as a missing directory much later.",
                "Rename the folders using plain ASCII letters, digits and "
                "underscores only.",
                where="case_path",
                value=raw,
            )
        )
    return issues


def _check_resources(probe, case_path, parallel, plot_residuals, wsl_ok) -> list[Issue]:
    """W-ENV-08, W-ENV-09, W-ENV-10."""
    issues: list[Issue] = []

    if wsl_ok and _truthy_yes(parallel):
        nproc = _probe_call(probe, "wsl_nproc", default=None)
        if isinstance(nproc, int) and nproc < DECOMPOSE_SUBDOMAINS:
            issues.append(
                warn(
                    "W-ENV-08",
                    f"WSL reports {plural(nproc, 'CPU core')}, but the case is "
                    f"decomposed into {DECOMPOSE_SUBDOMAINS} subdomains.",
                    f"decomposeParDict is written with "
                    f"numberOfSubdomains {DECOMPOSE_SUBDOMAINS} and the solver "
                    f"is launched as `mpirun -np {DECOMPOSE_SUBDOMAINS}`. Both "
                    "numbers are fixed. With fewer cores than that, mpirun "
                    "usually aborts with 'There are not enough slots "
                    "available in the system'.",
                    f"Run with parallel=\"N\", or give WSL at least "
                    f"{DECOMPOSE_SUBDOMAINS} cores by setting `processors="
                    f"{DECOMPOSE_SUBDOMAINS}` under [wsl2] in "
                    "C:\\Users\\<you>\\.wslconfig and running `wsl --shutdown`.",
                    where="parallel",
                    value=nproc,
                )
            )

    if case_path:
        free = _probe_call(probe, "free_disk_bytes", str(case_path), default=None)
        if isinstance(free, int) and free < MIN_FREE_DISK_BYTES:
            free_gb = free / (1024 ** 3)
            issues.append(
                warn(
                    "W-ENV-09",
                    f"Only {format_number(free_gb, 2)} GB free on the case "
                    "drive.",
                    "Each written time directory holds all eight fields for "
                    f"every cell (roughly {format_number(TIME_DIR_SIZE_MB, 0)} "
                    "MB for a half-million-cell room case), and a parallel run "
                    f"keeps a further copy in each of the "
                    f"{DECOMPOSE_SUBDOMAINS} processor*/ folders. Running out "
                    "of space mid-solve leaves a truncated field that no "
                    "post-processing can read.",
                    f"Free up space, or lower writeInterval so fewer time "
                    "directories are written. A comfortable margin is "
                    f"{MIN_FREE_DISK_BYTES // 1024 ** 3} GB.",
                    where="case_path",
                    value=free,
                )
            )

    if plot_residuals and not _probe_call(
        probe, "module_importable", "matplotlib", default=True
    ):
        issues.append(
            warn(
                "W-ENV-10",
                "plot_residuals=True but matplotlib is not installed.",
                "The live residual plot and the residuals.png written at the "
                "end both come from matplotlib. Without it the run still "
                "solves, but you get no convergence history at all.",
                "Install it with `pip install matplotlib`, or pass "
                "plot_residuals=False to state that you do not want the plot.",
                where="plot_residuals",
            )
        )
    return issues


def _environment_record(probe, salome_exe, wsl_ok) -> Issue:
    """I-ENV-11: what this machine actually is, for the report."""
    nproc = _probe_call(probe, "wsl_nproc", default=None) if wsl_ok else None
    bashrc = (
        _probe_call(probe, "wsl_test_file", OPENFOAM_BASHRC, default=False)
        if wsl_ok
        else False
    )
    lines = [
        f"SALOME launcher : {salome_exe}",
        f"WSL available   : {'yes' if wsl_ok else 'no'}",
        f"OpenFOAM bashrc : {OPENFOAM_BASHRC} ({'found' if bashrc else 'not found'})",
        f"WSL cores       : {nproc if nproc is not None else 'unknown'}",
        f"matplotlib      : "
        f"{'yes' if _probe_call(probe, 'module_importable', 'matplotlib', default=False) else 'no'}",
    ]
    return info(
        "I-ENV-11",
        "Environment recorded for reproducibility.",
        "\n".join(lines),
        "Quote these lines when reporting a problem: most 'it does not work' "
        "reports are one of them being different from what you expected.",
        where="environment",
        value={"nproc": nproc, "bashrc": bashrc, "salome_exe": str(salome_exe)},
    )


# ==========================================================================
# 2.2  Configuration
# ==========================================================================


def check_simulation_kwargs(raw_kwargs: dict) -> list[Issue]:
    """Reject Simulation(...) keywords that would be silently dropped.

    Emits E-CFG-01.

    _apply_simulation_kwargs walks the kwargs and simply skips anything it
    does not recognise, so `endtime=20` leaves endTime at its default of 3500
    and the case runs 17 times longer than asked (failure F1).
    """
    issues: list[Issue] = []
    try:
        for key in (raw_kwargs or {}):
            if key in VALID_SIMULATION_KWARGS:
                continue
            closest = suggest(key, VALID_SIMULATION_KWARGS)
            default = _SIMULATION_KWARG_DEFAULTS.get(closest)
            detail = (
                "Unrecognised arguments are silently ignored by Simulation(), "
                "so this value never reaches the case."
            )
            if closest is not None and closest in _SIMULATION_KWARG_DEFAULTS:
                detail += f" The run would have used the default {closest}={default!r} instead."
            issues.append(
                error(
                    "E-CFG-01",
                    f"Unknown Simulation() argument: {key!r}",
                    detail,
                    f"Rename it to {closest!r}."
                    if closest
                    else "Remove it, or use one of: "
                    + ", ".join(sorted(VALID_SIMULATION_KWARGS))
                    + ".",
                    where=key,
                    value=(raw_kwargs or {}).get(key),
                )
            )
    except Exception as exc:
        issues.append(_internal("Simulation() argument", exc))
    return issues


def check_control_config(control_cfg: dict) -> list[Issue]:
    """Validate the controlDict block and the iteration budget it implies.

    Emits E-CFG-02, E-CFG-03, W-CFG-06, W-CFG-07 and I-CFG-08.
    """
    issues: list[Issue] = []
    try:
        cfg = control_cfg or {}
        start = as_float(cfg.get("startTime", 0), None)
        end = as_float(cfg.get("endTime", 3500), None)
        delta_t = as_float(cfg.get("deltaT", cfg.get("delta", 0.1)), None)
        write_interval = as_float(cfg.get("writeInterval", 200), None)

        # -- E-CFG-02: numeric, finite, ordered -----------------------------
        for label, value, raw in (
            ("startTime", start, cfg.get("startTime", 0)),
            ("endTime", end, cfg.get("endTime", 3500)),
            ("deltaT", delta_t, cfg.get("deltaT", cfg.get("delta", 0.1))),
            ("writeInterval", write_interval, cfg.get("writeInterval", 200)),
        ):
            if value is None or not math.isfinite(value):
                issues.append(
                    error(
                        "E-CFG-02",
                        f"{label} is not a finite number: {raw!r}",
                        "controlDict entries are written straight into the "
                        "OpenFOAM dictionary. A non-numeric value produces a "
                        "FOAM FATAL IO ERROR the moment the solver reads it, "
                        "after the mesh has already been built.",
                        f"Set {label} to a plain number, for example "
                        f"{label}=200.",
                        where=label,
                        value=raw,
                    )
                )

        if start is not None and end is not None and math.isfinite(start) and math.isfinite(end):
            if end <= start:
                issues.append(
                    error(
                        "E-CFG-02",
                        f"endTime ({format_number(end)}) is not greater than "
                        f"startTime ({format_number(start)}).",
                        "With `ddtSchemes default steadyState` the 'time' axis "
                        "is really the SIMPLE iteration counter, and "
                        "(endTime - startTime)/deltaT is the number of "
                        "iterations. A non-positive span means zero "
                        "iterations: the solver exits immediately and the case "
                        "is marked finished.",
                        f"Set endTime above startTime, for example "
                        f"endTime={format_number(start + 200)}.",
                        where="endTime",
                        value=end,
                    )
                )

        if delta_t is not None and math.isfinite(delta_t) and delta_t <= 0:
            issues.append(
                error(
                    "E-CFG-02",
                    f"deltaT must be greater than zero, got {format_number(delta_t)}.",
                    "deltaT is the SIMPLE iteration step. Zero or negative "
                    "makes the iteration count undefined and OpenFOAM stops "
                    "with a fatal error.",
                    "Use deltaT=0.1 (or delta=0.1, which is the same thing).",
                    where="deltaT",
                    value=delta_t,
                )
            )

        if write_interval is not None and math.isfinite(write_interval) and write_interval < 1:
            issues.append(
                error(
                    "E-CFG-02",
                    f"writeInterval must be at least 1, got "
                    f"{format_number(write_interval)}.",
                    "writeControl is timeStep, so writeInterval counts "
                    "iterations between field dumps. Below 1 OpenFOAM either "
                    "refuses to start or writes on every single iteration.",
                    "Use writeInterval=50 for a 500-iteration run, which "
                    "leaves 10 time directories.",
                    where="writeInterval",
                    value=write_interval,
                )
            )

        # -- E-CFG-03: delta vs deltaT --------------------------------------
        if "delta" in cfg and "deltaT" in cfg:
            alias = as_float(cfg.get("delta"), None)
            canonical = as_float(cfg.get("deltaT"), None)
            if (
                alias is not None
                and canonical is not None
                and not math.isclose(alias, canonical, rel_tol=1e-9, abs_tol=1e-12)
            ):
                issues.append(
                    error(
                        "E-CFG-03",
                        f"delta={format_number(alias)} and "
                        f"deltaT={format_number(canonical)} disagree.",
                        "`delta` is only a friendly alias for the OpenFOAM key "
                        "`deltaT`. When both are given, the normaliser keeps "
                        "them as written and the value that ends up in "
                        "controlDict depends on the order the keys happen to "
                        "be iterated. That is not something you should have to "
                        "reason about.",
                        f"Delete one of them. Keep deltaT="
                        f"{format_number(canonical)} if that is the step you "
                        "meant.",
                        where="deltaT",
                        value={"delta": alias, "deltaT": canonical},
                    )
                )

        # -- W-CFG-06 / W-CFG-07: what the numbers actually mean ------------
        iterations = None
        if (
            start is not None
            and end is not None
            and delta_t is not None
            and math.isfinite(start)
            and math.isfinite(end)
            and math.isfinite(delta_t)
            and delta_t > 0
            and end > start
        ):
            iterations = (end - start) / delta_t

        if iterations is not None and iterations < MIN_ITERATIONS_ADVISED:
            issues.append(
                warn(
                    "W-CFG-06",
                    f"The case will run {format_number(iterations, 0)} SIMPLE "
                    f"iterations, which is few for a buoyant room.",
                    "fvSchemes sets `ddtSchemes { default steadyState; }`, so "
                    "'time' is not seconds - it is the iteration counter. "
                    f"endTime={format_number(end)}, deltaT="
                    f"{format_number(delta_t)} gives "
                    f"({format_number(end)} - {format_number(start)}) / "
                    f"{format_number(delta_t)} = "
                    f"{format_number(iterations, 0)} iterations. Natural "
                    "convection in a room typically needs 1000 to 3000 to "
                    f"reach residualControl {format_number(RESIDUAL_CONTROL)}, "
                    "so the run will stop at endTime while still unconverged - "
                    "and today that still writes .nemos_done.",
                    f"Raise endTime. With deltaT={format_number(delta_t)}, "
                    f"endTime={format_number(start + MIN_ITERATIONS_ADVISED * delta_t * 4)} "
                    f"gives {MIN_ITERATIONS_ADVISED * 4} iterations.",
                    where="endTime",
                    value=iterations,
                )
            )

        if (
            iterations is not None
            and write_interval is not None
            and math.isfinite(write_interval)
            and write_interval >= 1
        ):
            time_dirs = iterations / write_interval
            if time_dirs > MAX_TIME_DIRECTORIES:
                size_mb = time_dirs * TIME_DIR_SIZE_MB
                issues.append(
                    warn(
                        "W-CFG-07",
                        f"This run writes about {format_number(time_dirs, 0)} "
                        "time directories.",
                        f"{format_number(iterations, 0)} iterations divided by "
                        f"writeInterval={format_number(write_interval)} is one "
                        "full 3D dump of all eight fields every "
                        f"{format_number(write_interval)} iterations - roughly "
                        f"{format_number(size_mb, 0)} MB in total for a "
                        "half-million-cell mesh, multiplied again by the "
                        f"{DECOMPOSE_SUBDOMAINS} processor*/ folders in a "
                        "parallel run. For a steady case only the last "
                        "directory is normally of interest.",
                        f"Raise writeInterval to about "
                        f"{format_number(max(1.0, iterations / 10.0), 0)} so "
                        "you keep 10 snapshots instead.",
                        where="writeInterval",
                        value=time_dirs,
                    )
                )

        # -- I-CFG-08: startTime is inert -----------------------------------
        if "startTime" in cfg:
            issues.append(
                info(
                    "I-CFG-08",
                    f"startTime={cfg.get('startTime')!r} has no effect on where "
                    "the run begins.",
                    "The generated controlDict sets `startFrom latestTime`, so "
                    "OpenFOAM always restarts from the highest time directory "
                    "present in the case folder and ignores the startTime "
                    "entry. On a fresh case that is 0/, which is why this "
                    "usually goes unnoticed; on a resumed case it is not.",
                    "Nothing to change. Just be aware that deleting the later "
                    "time directories, not editing startTime, is what makes a "
                    "case start over.",
                    where="startTime",
                    value=cfg.get("startTime"),
                )
            )
    except Exception as exc:
        issues.append(_internal("controlDict", exc))
    return issues


def check_field_config(fields_cfg: dict, decompose_cfg: dict) -> list[Issue]:
    """Validate the parallel switch and every initial field value.

    Emits E-CFG-04 and E-CFG-05.
    """
    issues: list[Issue] = []
    try:
        # -- E-CFG-04 -------------------------------------------------------
        decompose = decompose_cfg or {}
        if "parallel" in decompose:
            raw = decompose.get("parallel")
            text = str(raw).strip().upper()
            if not isinstance(raw, bool) and text not in ("Y", "N", "YES", "NO"):
                issues.append(
                    error(
                        "E-CFG-04",
                        f"parallel must be \"Y\" or \"N\", got {raw!r}.",
                        "The switch is read as "
                        "`str(parallel).upper().startswith('Y')`, so anything "
                        f"that does not begin with a Y - including {raw!r} - "
                        "quietly means serial. A case you believe is running "
                        "on four cores would run on one, four times slower, "
                        "with no message.",
                        'Use parallel="Y" to run on '
                        f"{DECOMPOSE_SUBDOMAINS} cores, or parallel=\"N\" for "
                        "a serial run.",
                        where="parallel",
                        value=raw,
                    )
                )

        # -- E-CFG-05 -------------------------------------------------------
        for field_name, field_cfg in (fields_cfg or {}).items():
            if not isinstance(field_cfg, dict):
                continue
            for key in ("internalField", "value"):
                if key not in field_cfg:
                    continue
                raw = field_cfg[key]
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    continue  # a bare number is accepted and formatted later
                wants_vector = field_name == "U"
                parsed = (
                    _uniform_vector(raw) if wants_vector else _uniform_scalar(raw)
                )
                if parsed is None and wants_vector:
                    parsed = _uniform_scalar(raw)  # U value may be a scalar
                if parsed is not None:
                    continue
                expected = (
                    "uniform (0 -1 0)" if wants_vector else "uniform 300"
                )
                issues.append(
                    error(
                        "E-CFG-05",
                        f"{field_name} {key} is not a valid OpenFOAM entry: {raw!r}",
                        "This string is copied verbatim into "
                        f"0/{field_name}. OpenFOAM expects "
                        f"`{'uniform (x y z)' if wants_vector else 'uniform <number>'}`; "
                        "anything else stops the solver with a FOAM FATAL IO "
                        "ERROR, long after the mesh has been built.",
                        f'Write it as "{expected}".',
                        where=f"{field_name}.{key}",
                        value=raw,
                    )
                )
    except Exception as exc:
        issues.append(_internal("field configuration", exc))
    return issues


def check_inline_keys(geometry: GeometryModel) -> list[Issue]:
    """Report inline BC keys that are accepted but never read.

    Emits W-CFG-09.

    Simulation.SIMULATION_INLINE_KEYS accepts eleven keys and stores them in
    object_simulation, but BoundaryManager only ever reads T_Face, T_face,
    T_Flow and V_Flow - and even those only on the object types listed in
    _INLINE_KEYS_BY_TYPE (failure F4).
    """
    issues: list[Issue] = []
    try:
        for obj in geometry.objects:
            keys = _inline_keys(obj)
            if not keys:
                continue

            dead = sorted(keys & UNIMPLEMENTED_INLINE_KEYS)
            for key in dead:
                issues.append(
                    warn(
                        "W-CFG-09",
                        f"{key} on {_object_label(obj)} has no effect.",
                        f"{key} is accepted by Simulation() and stored, but "
                        "nothing reads it back: BoundaryManager only "
                        "implements T_Face, T_Flow and V_Flow. No heat source, "
                        "no radiation and no species transport is written into "
                        "the case, so the run proceeds as if you had never "
                        "passed it.",
                        "Remove it to keep the script honest. To model a warm "
                        "body today, set its surface temperature instead, for "
                        "example T_Face=307 for skin at 34 C.",
                        where=obj.name,
                        value={key: _inline_value(obj, key)},
                    )
                )

            expected = _INLINE_KEYS_BY_TYPE.get(obj.object_type or "")
            if expected is None:
                continue
            misplaced = sorted((keys & IMPLEMENTED_INLINE_KEYS) - expected)
            for key in misplaced:
                issues.append(
                    warn(
                        "W-CFG-09",
                        f"{key} is ignored on a {obj.object_type}: "
                        f"{_object_label(obj)}",
                        "BoundaryManager reads "
                        f"{', '.join(sorted(expected))} for a "
                        f"{obj.object_type} patch and nothing else, so {key} "
                        "is stored and then dropped. The patch will fall back "
                        "to the room temperature.",
                        f"Use {' or '.join(sorted(expected))} on this object, "
                        f"or move {key} to the object that needs it.",
                        where=obj.name,
                        value={key: _inline_value(obj, key)},
                    )
                )
    except Exception as exc:
        issues.append(_internal("inline boundary key", exc))
    return issues


# ==========================================================================
# 2.3  Geometry
# ==========================================================================


def shape_extent(obj: ObjectRecord, room_dims: tuple | None) -> Extent | None:
    """Conservative axis-aligned bounding box for one recorded object.

    Emits no issues. Returns None when the extent cannot be determined - an
    unknown class, a missing room for a ceiling-mounted dip, or a non-numeric
    kwarg (a sweep list, say). Callers must skip such objects rather than
    guess, because a wrong extent is a false positive and a false positive in
    a guardrail is worse than a missing check.

    The shapes follow docs/guardrail_architecture.md 2.3, derived from the
    GeoMesh constructors:

    Room              [0,dx] x [0,dy] x [0,dz]
    Person_seated     y in [0,h]; horizontal disc of radius
                      sqrt((0.25h + thickness/2)^2 + width^2) about (x,z) -
                      rotation invariant, so theta needs no special case
    Person_standing   fixed 1.68 m tall, disc of 0.36 m about (x-0.10, z)
    Dip_type_0x       hangs from the ceiling: radius ~= d about (x,z),
                      y in [H - 0.07 - y, H - 0.07]
    Table_retangular  dx x dy x dz box centred on (x,z), bottom at y
    Table_circular    disc of raio, thickness espessura, bottom at y
    """
    try:
        if obj is None:
            return None
        class_name = obj.class_name

        if class_name == "Room":
            dx = obj.number("dx", 3.0)
            dy = obj.number("dy", 3.0)
            dz = obj.number("dz", 3.0)
            if None in (dx, dy, dz):
                return None
            return Extent(0.0, dx, 0.0, dy, 0.0, dz)

        if class_name == "Person_seated":
            h = obj.number("h", 1.700)
            thickness = obj.number("thickness", 0.200)
            width = obj.number("width", 0.225)
            x = obj.number("x", 1.0)
            z = obj.number("z", 1.5)
            if None in (h, thickness, width, x, z):
                return None
            radius = math.hypot(0.25 * h + thickness / 2.0, width)
            return Extent.column(x, z, radius, 0.0, h)

        if class_name == "Person_standing":
            x = obj.number("x", 1.0)
            z = obj.number("z", 1.5)
            if None in (x, z):
                return None
            return Extent.column(
                x + STANDING_AXIS_DX, z, STANDING_RADIUS, 0.0, STANDING_HEIGHT
            )

        if class_name.startswith("Dip_type_"):
            if not room_dims:
                return None
            height = as_float(room_dims[1], None)
            x = obj.number("x", 1.0)
            y = obj.number("y", 1.2)
            z = obj.number("z", 1.5)
            d = obj.number("d", 0.05)
            if None in (height, x, y, z, d):
                return None
            ymax = height - DIP_CEILING_OFFSET
            return Extent.column(x, z, d, ymax - y, ymax)

        if class_name == "Table_retangular":
            dx = obj.number("dx", 0.6)
            dy = obj.number("dy", 0.02)
            dz = obj.number("dz", 0.6)
            x = obj.number("x", 1.5)
            y = obj.number("y", 0.6)
            z = obj.number("z", 1.5)
            if None in (dx, dy, dz, x, y, z):
                return None
            return Extent(x - dx / 2.0, x + dx / 2.0, y, y + dy, z - dz / 2.0, z + dz / 2.0)

        if class_name == "Table_circular":
            raio = obj.number("raio", 0.35)
            espessura = obj.number("espessura", 0.02)
            x = obj.number("x", 1.5)
            y = obj.number("y", 0.6)
            z = obj.number("z", 1.5)
            if None in (raio, espessura, x, y, z):
                return None
            return Extent.column(x, z, raio, y, y + espessura)
    except Exception:
        return None
    return None


def check_geometry_structure(geometry: GeometryModel) -> list[Issue]:
    """Check the objects exist, are named, are all added, and in the right order.

    Emits E-GEO-01, E-GEO-02, E-GEO-03, E-GEO-06 and E-GEO-07.
    """
    issues: list[Issue] = []
    try:
        issues.extend(_check_room_present(geometry))
        issues.extend(_check_geometry_kwargs(geometry))
        issues.extend(_check_object_names(geometry))
        issues.extend(_check_objects_added(geometry))
        issues.extend(_check_call_order(geometry))
    except Exception as exc:
        issues.append(_internal("geometry structure", exc))
    return issues


def _check_room_present(geometry: GeometryModel) -> list[Issue]:
    """E-GEO-01."""
    rooms = geometry.rooms()
    if not rooms:
        return [
            error(
                "E-GEO-01",
                "No Room was created.",
                "Every other object is positioned relative to the room and is "
                "cut out of it. A dip in particular reads salome_env.room "
                "in its constructor, so without a Room the SALOME batch stops "
                "with 'NoneType has no attribute H'.",
                'Add the room first: a = nemos.Room(dx=3.0, dy=3.0, dz=3.0, '
                'name="Room").',
                where="Room",
            )
        ]

    issues: list[Issue] = []
    if len(rooms) > 1:
        names = ", ".join(room.name for room in rooms)
        issues.append(
            error(
                "E-GEO-01",
                f"{len(rooms)} Rooms were created: {names}",
                "The recorder keeps one active room; the last one created "
                "wins, and every object made before it is cut out of a shape "
                "that is then discarded. Only one domain can be meshed.",
                "Delete the extra Room() calls and keep a single room.",
                where=rooms[-1].name,
            )
        )

    bodies_before = [
        obj for obj in geometry.bodies() if obj.order < rooms[0].order
    ]
    if bodies_before:
        names = ", ".join(_object_label(obj) for obj in bodies_before)
        issues.append(
            error(
                "E-GEO-01",
                f"{plural(len(bodies_before), 'object')} created before the Room: "
                f"{names}",
                "A dip reads self.room = salome_env.room in its constructor "
                "and then uses room.H to hang itself from the ceiling. Created "
                "before the Room exists, that attribute is None and the SALOME "
                "batch dies with an AttributeError - after SALOME has already "
                "started, so the message is buried in its log.",
                "Move the Room(...) line above every other geometry line.",
                where=bodies_before[0].name,
            )
        )
    return issues


def _check_geometry_kwargs(geometry: GeometryModel) -> list[Issue]:
    """E-GEO-02."""
    issues: list[Issue] = []
    for obj in geometry.objects:
        allowed = GEOMETRY_KWARGS.get(obj.class_name)
        if allowed is None:
            continue
        given = set(obj.kwargs or {}) | set(obj.inline or {})
        for key in sorted(given - allowed):
            closest = suggest(key, allowed)
            issues.append(
                error(
                    "E-GEO-02",
                    f"Unknown {obj.class_name} argument: {key!r}",
                    f"{obj.class_name} passes anything it does not recognise "
                    "into **kwargs, and GeoMesh.Object.__init__ pops only "
                    f"`name` out of it. {key!r} is therefore discarded without "
                    "a word, and the object is built with the default value "
                    "instead - the geometry silently ignores what you asked "
                    "for.",
                    f"Rename it to {closest!r}."
                    if closest
                    else f"Remove it. {obj.class_name} accepts: "
                    + ", ".join(sorted(allowed - SIMULATION_INLINE_KEYS))
                    + ".",
                    where=f"{obj.name}.{key}",
                    value=(obj.kwargs or {}).get(key),
                )
            )
    return issues


def _check_object_names(geometry: GeometryModel) -> list[Issue]:
    """E-GEO-03."""
    issues: list[Issue] = []
    seen: dict[str, ObjectRecord] = {}
    for obj in geometry.objects:
        if obj.class_name not in GEOMETRY_KWARGS or obj.class_name in (
            "Mesh",
            "Salome_Env",
        ):
            continue
        name = obj.name

        if not name:
            issues.append(
                error(
                    "E-GEO-03",
                    f"A {obj.class_name} was created without name=...",
                    "The name becomes the SALOME face group and then the "
                    "OpenFOAM patch name, and it is the key under which the "
                    "inline T_Face / T_Flow / V_Flow values are stored. "
                    "Without it the object has no boundary condition of its "
                    "own.",
                    f'Add a name, for example name="{obj.class_name}_1".',
                    where=obj.class_name,
                )
            )
            continue

        if name in seen:
            issues.append(
                error(
                    "E-GEO-03",
                    f"Duplicate object name: {name!r}",
                    f"{_object_label(seen[name])} already uses it. Names are "
                    "dictionary keys in object_types and object_simulation, so "
                    "the second object overwrites the first: both patches end "
                    "up with the same boundary condition and one set of "
                    "values is lost.",
                    f'Give each object its own name, for example "{name}_2".',
                    where=name,
                )
            )
        seen[name] = obj

        if not _NAME_PATTERN.match(str(name)):
            issues.append(
                error(
                    "E-GEO-03",
                    f"Object name is not a valid patch name: {name!r}",
                    "The patch is matched later with the regular expression "
                    r"`(\w+)\s*\{\s*type\s+(\w+);`, which only accepts "
                    "letters, digits and underscores. A name with a space, a "
                    "dash or an accent is simply not matched, the patch keeps "
                    "`type patch;`, and every field falls through to "
                    "zeroGradient - a wall that is silently frictionless and "
                    "adiabatic.",
                    "Use letters, digits and underscores only, starting with a "
                    'letter: name="Person_1".',
                    where=str(name),
                )
            )

        lowered = str(name).lower()
        if lowered in {reserved.lower() for reserved in RESERVED_OBJECT_NAMES} or (
            lowered.startswith("inlet_")
        ):
            issues.append(
                error(
                    "E-GEO-03",
                    f"Object name is reserved: {name!r}",
                    "GeoMesh creates its own groups called `wall`, `outlet` "
                    "and `inlet_<dip name>`. An object with one of those names "
                    "collides with them, and the boundary type that wins is "
                    "whichever group SALOME wrote last.",
                    f'Choose a different name, for example "{name}_body".',
                    where=str(name),
                )
            )
    return issues


def _check_objects_added(geometry: GeometryModel) -> list[Issue]:
    """E-GEO-06."""
    issues: list[Issue] = []
    bodies = geometry.bodies()
    if not bodies:
        return issues

    added = geometry.added_names()
    counts: dict[str, int] = {}
    for name in added:
        counts[name] = counts.get(name, 0) + 1

    missing = [obj for obj in bodies if counts.get(obj.name, 0) == 0]
    if missing:
        names = ", ".join(_object_label(obj) for obj in missing)
        issues.append(
            error(
                "E-GEO-06",
                f"{plural(len(missing), 'object')} never passed to Room.add(): "
                f"{names}",
                "Room.add() is what cuts the bodies out of the room volume and "
                "builds their face groups. An object that is not added is "
                "created in SALOME, appears in the study tree, and then plays "
                "no part in the mesh: no patch, no boundary condition, no "
                "effect on the flow. The run completes and looks normal.",
                "Add every object in one call: a.add(["
                + ", ".join(obj.name for obj in bodies)
                + "]).",
                where=missing[0].name,
            )
        )

    repeated = sorted(name for name, count in counts.items() if count > 1)
    if repeated:
        issues.append(
            error(
                "E-GEO-06",
                f"Object added more than once: {', '.join(repeated)}",
                "Each add() call runs MakeCutList again on the already-cut "
                "room and then rebuilds every face group from scratch. Cutting "
                "the same solid twice leaves degenerate faces, and the second "
                "pass appends duplicate groups with the same patch name.",
                "Pass every object exactly once, in a single a.add([...]) "
                "call.",
                where=repeated[0],
            )
        )

    unknown = sorted(set(counts) - {obj.name for obj in geometry.objects})
    if unknown:
        issues.append(
            error(
                "E-GEO-06",
                f"Room.add() received something that is not a recorded object: "
                f"{', '.join(unknown)}",
                "add() reads obj.object off each item to cut it out of the "
                "room. Anything else raises inside the SALOME batch, where the "
                "traceback is hard to find.",
                "Pass the variables you assigned the geometry objects to, for "
                "example a.add([b, c, d]).",
                where=unknown[0],
            )
        )
    return issues


#: Required call order, as ranks. Room -> bodies -> openings -> add -> Mesh
#: -> create_mesh -> check_quality.
_ORDER_RANKS = (
    (0, "Room(...)"),
    (1, "the geometry objects"),
    (2, "insert_*_opening(...)"),
    (3, "Room.add([...])"),
    (4, "Mesh(...)"),
    (5, "mesh.create_mesh(...)"),
    (6, "mesh.check_quality(...)"),
)


def _order_events(geometry: GeometryModel) -> list[tuple]:
    """Every ordered event as (order, rank, label). Unranked events dropped."""
    events = []
    for obj in geometry.objects:
        if obj.class_name == "Room":
            events.append((obj.order, 0, f"{obj.name} = Room(...)"))
        elif obj.class_name == "Mesh":
            events.append((obj.order, 4, "Mesh(...)"))
        elif obj.object_type in ("person", "dip", "table"):
            events.append((obj.order, 1, f"{obj.name} = {obj.class_name}(...)"))
    for call in geometry.methods:
        if call.method in ("insert_ceiling_opening", "insert_floor_opening"):
            events.append((call.order, 2, f"{call.target}.{call.method}(...)"))
        elif call.method == "add":
            events.append((call.order, 3, f"{call.target}.add([...])"))
        elif call.method == "create_mesh":
            events.append((call.order, 5, f"{call.target}.create_mesh(...)"))
        elif call.method == "check_quality":
            events.append((call.order, 6, f"{call.target}.check_quality(...)"))
    events.sort(key=lambda item: item[0])
    return events


def _check_call_order(geometry: GeometryModel) -> list[Issue]:
    """E-GEO-07."""
    issues: list[Issue] = []
    events = _order_events(geometry)
    if not events:
        return issues

    rank_names = dict(_ORDER_RANKS)
    highest_rank = -1
    highest_label = ""
    for _order, rank, label in events:
        if rank < highest_rank:
            detail = (
                f"The required order is: "
                + " -> ".join(name for _rank, name in _ORDER_RANKS)
                + f". Here {label} runs after {highest_label}."
            )
            if highest_rank >= 3 and rank == 2:
                detail += (
                    " This is the damaging case: Room.add() already cut the "
                    "bodies out and built the face groups from that solid, and "
                    "insert_*_opening then replaces self.object with a freshly "
                    "partitioned shape. Every group still points at the old, "
                    "now dead, shape, so the patches come out wrong or missing "
                    "and the mesh is exported anyway."
                )
            elif rank == 1 and highest_rank >= 3:
                detail += (
                    " An object created after add() is never cut out of the "
                    "room, so it has no patch and no effect on the flow."
                )
            issues.append(
                error(
                    "E-GEO-07",
                    f"Calls are out of order: {label} comes after "
                    f"{highest_label}.",
                    detail,
                    f"Move {label} above {highest_label}. The safe order is "
                    f"{rank_names.get(rank, 'this call')} before "
                    f"{rank_names.get(highest_rank, 'that one')}.",
                    where=label,
                )
            )
            highest_rank = max(highest_rank, rank)
            continue
        if rank > highest_rank:
            highest_rank = rank
            highest_label = label
    return issues


def check_geometry_placement(geometry: GeometryModel) -> list[Issue]:
    """Check where everything sits: inside the room, apart, and reachable.

    Emits E-GEO-04, E-GEO-05, E-GEO-08, E-GEO-09, E-GEO-10, E-GEO-11,
    E-GEO-12, W-GEO-13 and W-GEO-14.
    """
    issues: list[Issue] = []
    try:
        room = geometry.room()
        room_dims = geometry.room_dims()
        if room is None or room_dims is None:
            return issues  # E-GEO-01 already covers this
        dx, dy, dz = room_dims
        room_extent = Extent(0.0, dx, 0.0, dy, 0.0, dz)

        extents: list[tuple] = []
        for obj in geometry.bodies():
            extent = shape_extent(obj, room_dims)
            if extent is not None:
                extents.append((obj, extent))

        issues.extend(_check_inside_room(extents, room_extent, room_dims))
        issues.extend(_check_overlaps(extents))
        issues.extend(_check_dips(geometry, room_dims))
        issues.extend(_check_openings(geometry, room_dims))
        issues.extend(_check_clearances(geometry, extents, room_extent))
    except Exception as exc:
        issues.append(_internal("geometry placement", exc))
    return issues


def _check_inside_room(extents, room_extent, room_dims) -> list[Issue]:
    """E-GEO-04."""
    issues: list[Issue] = []
    dx, dy, dz = room_dims
    for obj, extent in extents:
        axes = room_extent.outside_axes(extent, tol=ROOM_CONTAINMENT_TOL)
        if not axes:
            continue
        spans = {
            "x": (extent.xmin, extent.xmax, 0.0, dx),
            "y": (extent.ymin, extent.ymax, 0.0, dy),
            "z": (extent.zmin, extent.zmax, 0.0, dz),
        }
        lines = []
        for axis in axes:
            lo, hi, room_lo, room_hi = spans[axis]
            lines.append(
                f"{axis}: object spans {format_number(lo)} .. "
                f"{format_number(hi)} m, room is {format_number(room_lo)} .. "
                f"{format_number(room_hi)} m"
            )
        issues.append(
            error(
                "E-GEO-04",
                f"{_object_label(obj)} sticks out of the room on "
                f"{', '.join(axes)}.",
                "Room.add() cuts each body out of the room solid. A body that "
                "is partly outside cuts a hole through the wall, so the domain "
                "is no longer closed and NETGEN either fails or produces a "
                "mesh with an open boundary.\n" + "\n".join(lines),
                f"Move it back inside. For a "
                f"{format_number(dx)} x {format_number(dy)} x "
                f"{format_number(dz)} m room the centre is "
                f"x={format_number(dx / 2)}, z={format_number(dz / 2)}.",
                where=obj.name,
                value=[extent.xmin, extent.xmax, extent.ymin, extent.ymax,
                       extent.zmin, extent.zmax],
            )
        )
    return issues


def _penetration(a: Extent, b: Extent) -> tuple:
    """Per-axis interpenetration depth of two boxes (negative when apart)."""
    return (
        min(a.xmax, b.xmax) - max(a.xmin, b.xmin),
        min(a.ymax, b.ymax) - max(a.ymin, b.ymin),
        min(a.zmax, b.zmax) - max(a.zmin, b.zmin),
    )


def _significant_overlap(a: Extent, b: Extent) -> tuple | None:
    """Overlap depth per axis, or None when it is within the bound's slack.

    shape_extent is deliberately conservative - a seated person is bounded by
    a rotation-invariant disc that is up to 0.43 m wider than the body behind
    it - so two boxes that clip each other slightly are not evidence of a
    clash. Only an interpenetration deeper than
    max(OVERLAP_ABS_TOL, OVERLAP_REL_TOL * smaller size) on every axis is
    reported.
    """
    depths = _penetration(a, b)
    sizes_a, sizes_b = a.size, b.size
    for depth, size_a, size_b in zip(depths, sizes_a, sizes_b):
        limit = max(OVERLAP_ABS_TOL, OVERLAP_REL_TOL * min(size_a, size_b))
        if depth <= limit:
            return None
    return depths


def _check_overlaps(extents) -> list[Issue]:
    """E-GEO-05."""
    issues: list[Issue] = []
    for index, (obj_a, extent_a) in enumerate(extents):
        for obj_b, extent_b in extents[index + 1:]:
            depths = _significant_overlap(extent_a, extent_b)
            if depths is None:
                continue
            issues.append(
                error(
                    "E-GEO-05",
                    f"{_object_label(obj_a)} and {_object_label(obj_b)} occupy "
                    "the same space.",
                    "Both bodies are cut out of the room with a single "
                    "MakeCutList. Where they intersect, the cut leaves "
                    "coincident and zero-area faces, the face groups pick up "
                    "each other's faces, and the boundary conditions of the "
                    "two objects get mixed. The overlap is "
                    f"{format_number(depths[0])} m in x, "
                    f"{format_number(depths[1])} m in y and "
                    f"{format_number(depths[2])} m in z.",
                    "Move one of them. Note that the bounding volumes used "
                    "here are conservative, so this is a real, deep "
                    "intersection and not a rounding artefact.",
                    where=f"{obj_a.name} / {obj_b.name}",
                    value=list(depths),
                )
            )
    return issues


def _check_dips(geometry: GeometryModel, room_dims) -> list[Issue]:
    """E-GEO-08 and E-GEO-09."""
    issues: list[Issue] = []
    dx, dy, dz = room_dims
    dips = _dip_records(geometry)
    ceiling = dy - DIP_CEILING_OFFSET

    for dip in dips:
        y = dip["y"]
        if y is None:
            continue
        if y <= 0:
            issues.append(
                error(
                    "E-GEO-08",
                    f"{dip['name']} has y={format_number(y)} m, which is not a "
                    "length.",
                    "For a dip, `y` is how far the duct hangs down from the "
                    f"ceiling: it spans y in [H - "
                    f"{format_number(DIP_CEILING_OFFSET)} - y, H - "
                    f"{format_number(DIP_CEILING_OFFSET)}]. A zero or negative "
                    "value produces a degenerate solid that SALOME cannot "
                    "revolve.",
                    "Use a positive drop, for example y=1.0 for a duct that "
                    "hangs one metre below the ceiling.",
                    where=dip["name"],
                    value=y,
                )
            )
            continue
        if y > ceiling:
            issues.append(
                error(
                    "E-GEO-08",
                    f"{dip['name']} hangs {format_number(y)} m below the "
                    f"ceiling and reaches through the floor.",
                    f"The dip spans y from "
                    f"{format_number(ceiling - y)} m to "
                    f"{format_number(ceiling)} m, and the room floor is at 0. "
                    f"The limit is y <= H - {format_number(DIP_CEILING_OFFSET)} "
                    f"= {format_number(dy)} - "
                    f"{format_number(DIP_CEILING_OFFSET)} = "
                    f"{format_number(ceiling)} m. Below the floor the duct is "
                    "cut off, the highest matching face is no longer the "
                    "throat, and the inlet patch is attached to the wrong "
                    "face.",
                    f"Reduce y to at most {format_number(ceiling)}.",
                    where=dip["name"],
                    value=y,
                )
            )

    for index, dip in enumerate(dips):
        x, z, d = dip["x"], dip["z"], dip["d"]
        if None in (x, z):
            continue
        radius = d if d is not None else 0.0
        if not (radius < x < dx - radius) or not (radius < z < dz - radius):
            issues.append(
                error(
                    "E-GEO-09",
                    f"{dip['name']} is not fully inside the ceiling: "
                    f"(x={format_number(x)}, z={format_number(z)}), "
                    f"radius {format_number(radius)} m.",
                    f"The ceiling is {format_number(dx)} x {format_number(dz)} "
                    "m. The inlet face is found by matching a face centre "
                    "against the dip's (x, z) to within 1e-6 m; a duct that "
                    "touches or crosses a wall merges with it, no face centre "
                    "matches, and GetSubShapeID(None) fails inside SALOME.",
                    f"Keep the dip clear of the walls, for example "
                    f"x={format_number(dx / 2)}, z={format_number(dz / 2)}.",
                    where=dip["name"],
                    value=[x, z],
                )
            )
        for other in dips[index + 1:]:
            if None in (other["x"], other["z"]):
                continue
            if (
                abs(x - other["x"]) < DIP_COINCIDENCE_TOL
                and abs(z - other["z"]) < DIP_COINCIDENCE_TOL
            ):
                issues.append(
                    error(
                        "E-GEO-09",
                        f"{dip['name']} and {other['name']} share the same "
                        f"(x, z) = ({format_number(x)}, {format_number(z)}).",
                        "The inlet face of each dip is found by matching a "
                        "face centre against its (x, z) to within 1e-6 m. Two "
                        "dips on the same axis match each other's faces, so "
                        "one inlet patch ends up with the other's face - or "
                        "with none at all.",
                        "Give the two dips different positions, or delete one "
                        "of them.",
                        where=f"{dip['name']} / {other['name']}",
                        value=[x, z],
                    )
                )
    return issues


def _check_openings(geometry: GeometryModel, room_dims) -> list[Issue]:
    """E-GEO-10, E-GEO-11, E-GEO-12 and W-GEO-13."""
    issues: list[Issue] = []
    dx, dy, dz = room_dims
    openings = _opening_records(geometry)
    dips = _dip_records(geometry)

    # -- E-GEO-12 ---------------------------------------------------------
    if dips and not openings:
        issues.append(
            error(
                "E-GEO-12",
                f"{plural(len(dips), 'dip')} supply air, but the room has no "
                "opening.",
                "Every other surface is a wall, so mass is pushed in and has "
                "nowhere to leave. No steady solution exists: the continuity "
                "residual cannot fall, and the run will iterate to endTime "
                "without converging.",
                "Add at least one outlet, for example "
                "a.insert_ceiling_opening(x=0.5, z=0.5, d=0.1).",
                where="Room",
            )
        )

    # -- W-GEO-13 ---------------------------------------------------------
    usable = [rec for rec in openings if rec["d"] is not None]
    if usable:
        lines = [
            f"{rec['label']}: d={format_number(rec['d'])} means radius "
            f"{format_number(rec['radius'])} m, diameter "
            f"{format_number(2 * rec['radius'])} m, area "
            f"{format_number(rec['area'])} m2"
            for rec in usable
        ]
        total_area = sum(rec["area"] for rec in usable)
        issues.append(
            warn(
                "W-GEO-13",
                f"`d` in insert_*_opening is a RADIUS, not a diameter - "
                f"{plural(len(usable), 'opening')} totalling "
                f"{format_number(total_area)} m2.",
                "GeoMesh passes d straight to MakeCircle, whose third argument "
                "is the radius, so the hole is twice as wide as the name "
                "suggests and its area is pi*d^2, not pi*d^2/4. What you "
                "actually asked for is:\n" + "\n".join(lines),
                "If you meant those diameters, halve each d. Otherwise nothing "
                "to change - just read the areas above as the real outlet "
                "area.",
                where="insert_opening",
                value=total_area,
            )
        )

    # -- E-GEO-10 ---------------------------------------------------------
    for index, rec in enumerate(usable):
        x, z, radius = rec["x"], rec["z"], rec["radius"]
        if None in (x, z):
            continue
        if not (radius <= x <= dx - radius) or not (radius <= z <= dz - radius):
            issues.append(
                error(
                    "E-GEO-10",
                    f"{rec['label']} at (x={format_number(x)}, "
                    f"z={format_number(z)}) does not fit on the ceiling.",
                    f"The circle has radius {format_number(radius)} m (d is "
                    "used as a radius) and the ceiling is "
                    f"{format_number(dx)} x {format_number(dz)} m, so the hole "
                    "runs off the edge. MakePartition then either fails or "
                    "leaves a partial face that never becomes an outlet patch.",
                    f"Move it inside, keeping at least "
                    f"{format_number(radius)} m from each wall.",
                    where=rec["label"],
                    value=[x, z, radius],
                )
            )
        for other in usable[index + 1:]:
            if None in (other["x"], other["z"]):
                continue
            distance = math.hypot(x - other["x"], z - other["z"])
            if distance < radius + other["radius"]:
                issues.append(
                    error(
                        "E-GEO-10",
                        f"{rec['label']} and {other['label']} overlap.",
                        f"Their centres are {format_number(distance)} m apart "
                        f"but their radii sum to "
                        f"{format_number(radius + other['radius'])} m. Two "
                        "intersecting partition circles leave slivers of face "
                        "that fail the outlet area filter and end up in the "
                        "wall group instead.",
                        "Separate them, or merge them into a single larger "
                        "opening.",
                        where=f"{rec['label']} / {other['label']}",
                        value=distance,
                    )
                )
        for dip in dips:
            if None in (dip["x"], dip["z"]):
                continue
            distance = math.hypot(x - dip["x"], z - dip["z"])
            dip_radius = dip["d"] or 0.0
            if distance < radius + dip_radius:
                issues.append(
                    error(
                        "E-GEO-10",
                        f"{rec['label']} sits on top of {dip['name']}.",
                        f"Their centres are {format_number(distance)} m apart, "
                        f"less than the opening radius "
                        f"{format_number(radius)} m plus the dip radius "
                        f"{format_number(dip_radius)} m. The opening would cut "
                        "into the duct that feeds the inlet, and the inlet "
                        "face search - which matches a face centre against the "
                        "dip's (x, z) - would find the opening instead of the "
                        "throat.",
                        "Move the opening away from the dip axis.",
                        where=f"{rec['label']} / {dip['name']}",
                        value=distance,
                    )
                )

    # -- E-GEO-11 ---------------------------------------------------------
    if usable:
        total_area = sum(rec["area"] for rec in usable)
        ceiling_area = dx * dz
        limit = OPENING_AREA_FRACTION_MAX * ceiling_area
        if total_area >= limit:
            smallest = sorted([dx, dy, dz])[:2]
            issues.append(
                error(
                    "E-GEO-11",
                    f"The openings cover {format_number(total_area)} m2, "
                    f"{format_number(100 * total_area / ceiling_area, 1)} % of "
                    f"the {format_number(ceiling_area)} m2 ceiling.",
                    "A ceiling face becomes an `outlet` patch only when its "
                    "area is below Room.area = "
                    f"{format_number(ROOM_AREA_FACTOR)} * "
                    f"{format_number(smallest[0])} * "
                    f"{format_number(smallest[1])} = "
                    f"{format_number(ROOM_AREA_FACTOR * smallest[0] * smallest[1])} "
                    "m2. Punch out more than "
                    f"{format_number(100 * OPENING_AREA_FRACTION_MAX, 0)} % and "
                    "the remaining ceiling itself drops below that threshold, "
                    "so the whole ceiling - not just the holes - is turned "
                    "into one big outlet. The case still runs, and the answer "
                    "is meaningless.",
                    f"Keep the total below {format_number(limit)} m2. Remember "
                    "each opening's area is pi*d^2 because d is used as a "
                    "radius, so halving d quarters the area.",
                    where="insert_opening",
                    value=total_area,
                )
            )
    return issues


def _check_clearances(geometry: GeometryModel, extents, room_extent) -> list[Issue]:
    """W-GEO-14."""
    issues: list[Issue] = []
    mesh = geometry.mesh()
    cell_size = mesh.number("m3DMaxSize", 0.075) if mesh is not None else 0.075
    if cell_size is None:
        cell_size = 0.075
    cell_allowance = 3 * cell_size

    reported = 0
    suppressed = 0
    for index, (obj_a, extent_a) in enumerate(extents):
        for obj_b, extent_b in extents[index + 1:]:
            gap = extent_a.gap_to(extent_b)
            if gap < 0:
                continue  # E-GEO-05 owns the overlapping case
            needed = (
                _viscous_thickness(obj_a) + _viscous_thickness(obj_b) + cell_allowance
            )
            if gap >= needed:
                continue
            if reported >= MAX_REPORTED_PAIRS:
                suppressed += 1
                continue
            reported += 1
            issues.append(
                warn(
                    "W-GEO-14",
                    f"Only {format_number(gap)} m between {obj_a.name} and "
                    f"{obj_b.name}.",
                    "The mesh needs room in that gap: a viscous-layer stack of "
                    f"{format_number(_viscous_thickness(obj_a))} m on "
                    f"{obj_a.name}, {format_number(_viscous_thickness(obj_b))} "
                    f"m on {obj_b.name}, plus about three cells of "
                    f"m3DMaxSize={format_number(cell_size)} m - "
                    f"{format_number(needed)} m in total. Squeezed tighter "
                    "than that, NETGEN either collapses the layers or produces "
                    "slivers, which show up as high non-orthogonality and slow "
                    "convergence.",
                    f"Move them {format_number(needed - gap)} m further apart, "
                    f"or lower m3DMaxSize to about "
                    f"{format_number(max(0.001, (gap - _viscous_thickness(obj_a) - _viscous_thickness(obj_b)) / 3))} m "
                    "near them.",
                    where=f"{obj_a.name} / {obj_b.name}",
                    value=gap,
                )
            )

    wall_allowance = VISCOUS_LAYER_THICKNESS["wall"]
    for obj, extent in extents:
        needed = _viscous_thickness(obj) + wall_allowance + cell_allowance
        gaps = {
            "x=0": extent.xmin - room_extent.xmin,
            f"x={format_number(room_extent.xmax)}": room_extent.xmax - extent.xmax,
            "z=0": extent.zmin - room_extent.zmin,
            f"z={format_number(room_extent.zmax)}": room_extent.zmax - extent.zmax,
        }
        tight = {wall: gap for wall, gap in gaps.items() if 0 <= gap < needed}
        if not tight:
            continue
        if reported >= MAX_REPORTED_PAIRS:
            suppressed += 1
            continue
        reported += 1
        listed = ", ".join(
            f"{wall}: {format_number(gap)} m" for wall, gap in sorted(tight.items())
        )
        issues.append(
            warn(
                "W-GEO-14",
                f"{_object_label(obj)} is very close to a wall ({listed}).",
                f"A wall carries a {format_number(wall_allowance)} m viscous "
                f"stack and {obj.name} carries "
                f"{format_number(_viscous_thickness(obj))} m; with about three "
                f"cells of m3DMaxSize={format_number(cell_size)} m in between, "
                f"the gap wants to be at least {format_number(needed)} m. "
                "Narrower than that, the two layer stacks meet and NETGEN "
                "drops them.",
                "Move the object away from the wall, or accept that the "
                "boundary layer in that gap will not be resolved.",
                where=obj.name,
                value=min(tight.values()),
            )
        )

    if suppressed:
        issues.append(
            info(
                "W-GEO-14",
                f"{suppressed} further tight-gap warning"
                f"{'s were' if suppressed != 1 else ' was'} suppressed.",
                "Only the first "
                f"{MAX_REPORTED_PAIRS} are listed so the report stays "
                "readable.",
                "Fix the ones above and re-run the preflight to see the rest.",
                where="clearance",
                value=suppressed,
            )
        )
    return issues


# ==========================================================================
# 2.4  Mesh parameters
# ==========================================================================


def check_mesh_params(geometry: GeometryModel) -> list[Issue]:
    """Validate the NETGEN parameters and the check_quality call.

    Emits E-MSH-01, E-MSH-02, E-MSH-03, W-MSH-04, W-MSH-05 and W-MSH-06.
    """
    issues: list[Issue] = []
    try:
        mesh = geometry.mesh()
        if mesh is None:
            issues.append(
                error(
                    "E-MSH-03",
                    "No Mesh was created.",
                    "Without a Mesh object nothing calls NETGEN, no Mesh_1.unv "
                    "is exported, and the OpenFOAM stage has nothing to "
                    "convert.",
                    "Add the mesh after add(): mesh = nemos.Mesh(a, "
                    "m2DMaxSize=0.2, m2DMinSize=0.02, m3DMaxSize=0.075, "
                    "m3DMinSize=0.001, fineness=3), then "
                    "mesh.create_mesh(export=True).",
                    where="Mesh",
                )
            )
            return issues

        issues.extend(_check_mesh_sizes(mesh))
        issues.extend(_check_mesh_target(geometry, mesh))
        issues.extend(_check_cell_count(geometry, mesh))
        issues.extend(_check_feature_resolution(geometry, mesh))
        issues.extend(_check_quality_call(geometry))
    except Exception as exc:
        issues.append(_internal("mesh parameter", exc))
    return issues


def _check_mesh_sizes(mesh: ObjectRecord) -> list[Issue]:
    """E-MSH-01 and E-MSH-02."""
    issues: list[Issue] = []
    sizes = {
        "m2DMaxSize": mesh.number("m2DMaxSize", 0.2),
        "m2DMinSize": mesh.number("m2DMinSize", 0.02),
        "m3DMaxSize": mesh.number("m3DMaxSize", 0.075),
        "m3DMinSize": mesh.number("m3DMinSize", 0.001),
    }

    for key, value in sizes.items():
        if value is None or not math.isfinite(value) or value <= 0:
            issues.append(
                error(
                    "E-MSH-01",
                    f"{key} must be a positive length in metres, got "
                    f"{mesh.get(key)!r}.",
                    "NETGEN takes these as element sizes in metres. Zero, "
                    "negative or non-numeric makes the meshing step fail "
                    "inside SALOME, where the traceback is hard to read.",
                    f"Use a positive value, for example {key}=0.05.",
                    where=key,
                    value=mesh.get(key),
                )
            )

    for min_key, max_key in (("m2DMinSize", "m2DMaxSize"), ("m3DMinSize", "m3DMaxSize")):
        low, high = sizes[min_key], sizes[max_key]
        if low is None or high is None:
            continue
        if low > high:
            issues.append(
                error(
                    "E-MSH-01",
                    f"{min_key}={format_number(low)} is larger than "
                    f"{max_key}={format_number(high)}.",
                    "The minimum element size cannot exceed the maximum. "
                    "NETGEN is given both bounds and cannot satisfy them, so "
                    "meshing either fails or silently ignores one of them.",
                    f"Swap them, or set {min_key} below {max_key} - for "
                    f"example {min_key}={format_number(high / 10)}.",
                    where=min_key,
                    value=[low, high],
                )
            )

    fineness = mesh.number("fineness", 3)
    if fineness is None or fineness != int(fineness) or int(fineness) not in VALID_FINENESS:
        issues.append(
            error(
                "E-MSH-02",
                f"fineness must be one of "
                f"{', '.join(str(value) for value in VALID_FINENESS)}, got "
                f"{mesh.get('fineness')!r}.",
                "NETGEN's fineness is an enumeration: 0 very coarse, 1 coarse, "
                "2 moderate, 3 fine, 4 very fine. A value outside that range "
                "is rejected by SetFineness inside SALOME.",
                "Use fineness=3 (fine), which is what the example scripts use.",
                where="fineness",
                value=mesh.get("fineness"),
            )
        )
    return issues


def _check_mesh_target(geometry: GeometryModel, mesh: ObjectRecord) -> list[Issue]:
    """E-MSH-03."""
    issues: list[Issue] = []
    room = geometry.room()

    target = None
    if mesh.args:
        target = _resolve_name(mesh.args[0])
    if target is None:
        target = _resolve_name((mesh.kwargs or {}).get("room"))

    if room is not None and target is not None and target != room.name:
        issues.append(
            error(
                "E-MSH-03",
                f"Mesh() was given {target!r}, not the Room ({room.name!r}).",
                "Mesh reads room.object, room.faces_groups and "
                "room.faces_names_groups to build the NETGEN hypotheses and "
                "the patch groups. Given anything else, the mesh has no face "
                "groups at all, so every face lands in defaultFaces and no "
                "boundary condition can be applied.",
                f"Pass the room: mesh = nemos.Mesh({room.name}, ...).",
                where="Mesh",
                value=target,
            )
        )

    creates = geometry.calls("create_mesh")
    if not creates:
        issues.append(
            error(
                "E-MSH-03",
                "create_mesh() was never called.",
                "Mesh(...) only stores the parameters. NETGEN runs, and "
                "Mesh_1.unv is exported, inside create_mesh. Without it the "
                "SALOME batch finishes with no mesh file and the OpenFOAM "
                "stage fails on a missing Mesh_1.unv.",
                "Add mesh.create_mesh(export=True) after the Mesh(...) line.",
                where="create_mesh",
            )
        )
    elif len(creates) > 1:
        issues.append(
            error(
                "E-MSH-03",
                f"create_mesh() was called {len(creates)} times.",
                "Each call rebuilds the whole mesh from scratch and exports "
                "over the same Mesh_1.unv. That doubles the meshing time and "
                "makes it ambiguous which parameters produced the file that "
                "is finally used.",
                "Keep a single mesh.create_mesh(export=True) call.",
                where="create_mesh",
                value=len(creates),
            )
        )
    return issues


def _check_cell_count(geometry: GeometryModel, mesh: ObjectRecord) -> list[Issue]:
    """W-MSH-04."""
    dims = geometry.room_dims()
    size = mesh.number("m3DMaxSize", 0.075)
    if not dims or size is None or size <= 0:
        return []

    volume = dims[0] * dims[1] * dims[2]
    cells = 6 * math.sqrt(2) * volume / (size ** 3)
    if cells < CELL_COUNT_WARN:
        return []

    ram_gb = cells / CELLS_PER_GB_RAM
    return [
        warn(
            "W-MSH-04",
            f"About {format_number(cells / 1e6, 2)} million cells with "
            f"m3DMaxSize={format_number(size)} m.",
            f"A room of {format_number(volume)} m3 filled with tetrahedra of "
            f"edge {format_number(size)} m works out at roughly "
            f"6*sqrt(2)*V/h^3 = {format_number(cells, 0)} cells. Expect around "
            f"{format_number(ram_gb, 1)} GB of RAM and several hours per "
            f"thousand iterations on {DECOMPOSE_SUBDOMAINS} cores, plus "
            "NETGEN itself taking tens of minutes.",
            f"If that is not what you intended, raise m3DMaxSize. "
            f"m3DMaxSize={format_number(size * 1.5)} m would give about "
            f"{format_number(cells / 3.375 / 1e6, 2)} million cells.",
            where="m3DMaxSize",
            value=cells,
        )
    ]


def _check_feature_resolution(geometry: GeometryModel, mesh: ObjectRecord) -> list[Issue]:
    """W-MSH-05."""
    issues: list[Issue] = []
    size = mesh.number("m3DMaxSize", 0.075)
    if size is None or size <= 0:
        return issues

    features = []
    for dip in _dip_records(geometry):
        if dip["d"]:
            features.append((dip["obj"], "throat diameter", 2 * dip["d"]))
    for obj in geometry.of_class("Table_circular"):
        thickness = obj.number("espessura", 0.02)
        if thickness:
            features.append((obj, "plate thickness", thickness))
    for obj in geometry.of_class("Table_retangular"):
        thickness = obj.number("dy", 0.02)
        if thickness:
            features.append((obj, "plate thickness", thickness))

    for obj, label, feature in features:
        needed = CELLS_ACROSS_FEATURE * size
        if feature >= needed:
            continue
        local = LOCAL_MESH_SIZE.get(obj.object_type or "", size)
        if local <= feature / CELLS_ACROSS_FEATURE:
            continue  # the local surface size already resolves it
        issues.append(
            warn(
                "W-MSH-05",
                f"{_object_label(obj)}: {label} is "
                f"{format_number(feature)} m but cells are up to "
                f"{format_number(size)} m.",
                f"Three cells across the feature would need "
                f"m3DMaxSize <= {format_number(feature / CELLS_ACROSS_FEATURE)} "
                f"m. The local surface size for a {obj.object_type} is "
                f"{format_number(local)} m, which is not fine enough either, "
                "so the feature is represented by one or two cells and the "
                "flow around it is not resolved.",
                f"Lower m3DMaxSize to about "
                f"{format_number(feature / CELLS_ACROSS_FEATURE)} m, or accept "
                "that this feature is only geometrically present and not "
                "aerodynamically resolved.",
                where=obj.name,
                value=feature,
            )
        )
    return issues


def _check_quality_call(geometry: GeometryModel) -> list[Issue]:
    """W-MSH-06."""
    issues: list[Issue] = []
    for call in geometry.calls("check_quality"):
        metric = call.get("name_metric", 0)
        element_type = call.get("element_type", 1, "FACE")
        comparison = call.get("comparison", 3, ">")

        if metric is not None and str(metric) not in SMESH_QUALITY_METRICS:
            closest = suggest(str(metric), SMESH_QUALITY_METRICS)
            issues.append(
                warn(
                    "W-MSH-06",
                    f"check_quality metric {str(metric)!r} is not a known "
                    "SMESH functor.",
                    "The recorded script builds the token as "
                    f"\"SMESH.FT_\" + {str(metric)!r} = "
                    f"SMESH.FT_{metric}. If that constant does not exist, the "
                    "SALOME batch stops with an AttributeError - after NETGEN "
                    "has already spent its time meshing.",
                    f"Use {closest!r}."
                    if closest
                    else "Use one of: "
                    + ", ".join(sorted(SMESH_QUALITY_METRICS))
                    + ".",
                    where="check_quality",
                    value=metric,
                )
            )

        if str(element_type).strip().upper() not in VALID_ELEMENT_TYPES:
            issues.append(
                warn(
                    "W-MSH-06",
                    f"check_quality element_type={element_type!r} is not "
                    "recognised and silently becomes FACE.",
                    "The value is looked up in a two-entry map (FACE, VOLUME) "
                    "with SMESH.FACE as the fallback, so a typo does not raise "
                    "- it just measures the wrong kind of element and the "
                    "report you get is not the one you asked for.",
                    'Use element_type="FACE" for surface metrics or '
                    '"VOLUME" for volume metrics.',
                    where="check_quality",
                    value=element_type,
                )
            )

        if str(comparison).strip() not in VALID_COMPARISONS:
            issues.append(
                warn(
                    "W-MSH-06",
                    f"check_quality comparison={comparison!r} is not "
                    "recognised and silently becomes '>'.",
                    "The comparison is looked up in a four-entry map "
                    "(>, <, =, ==) with SMESH.FT_MoreThan as the fallback. "
                    "Asking for elements below a threshold and getting the "
                    "ones above it is a report that reads as a pass when it "
                    "is a fail.",
                    "Use one of: >, <, =.",
                    where="check_quality",
                    value=comparison,
                )
            )
    return issues


# ==========================================================================
# 2.5  Physics consistency (advisory, never blocking)
# ==========================================================================


def check_physics(geometry: GeometryModel, simulation_config: dict) -> list[Issue]:
    """Report every physical assumption the case is about to make.

    Emits W-PHY-01, W-PHY-02, W-PHY-03, W-PHY-04, W-PHY-05, W-PHY-06,
    W-PHY-07, W-PHY-08, W-PHY-09 and I-PHY-10. None of these ever blocks a
    run: they exist so the numbers are on screen before two hours of solver
    time are spent on them.
    """
    issues: list[Issue] = []
    try:
        cfg = simulation_config or {}
        fields = cfg.get("fields", {}) or {}
        dips = _dip_records(geometry)
        room_dims = geometry.room_dims()
        openings = [rec for rec in _opening_records(geometry) if rec["d"] is not None]

        temperatures = _collect_temperatures(geometry, fields)
        issues.extend(_check_temperature_window(temperatures))
        issues.extend(_check_velocity_limits(dips))
        issues.extend(_check_flow_signs(dips))
        issues.extend(_check_reynolds(dips))
        issues.extend(_check_ventilation(dips, openings, room_dims))
        issues.extend(_check_boussinesq(temperatures, room_dims))
        issues.extend(_check_pressure(fields))
        issues.extend(_check_inlet_turbulence(dips))
        issues.append(_assumption_register(temperatures, room_dims))
    except Exception as exc:
        issues.append(_internal("physics", exc))
    return issues


def _collect_temperatures(geometry: GeometryModel, fields: dict) -> list[dict]:
    """Every temperature the case will impose, with where it came from."""
    values = []
    for obj in geometry.objects:
        for key in ("T_Face", "T_face", "T_Flow"):
            raw = _inline_value(obj, key)
            if raw is None:
                continue
            value = as_float(raw, None)
            if value is None:
                continue
            values.append(
                {
                    "value": value,
                    "where": obj.name,
                    "label": f"{obj.name}.{key}",
                    "key": key,
                }
            )
    internal = _uniform_scalar((fields.get("T", {}) or {}).get("internalField"))
    if internal is not None:
        values.append(
            {
                "value": internal,
                "where": "T_internalField",
                "label": "T internalField",
                "key": "internalField",
            }
        )
    return values


def _check_temperature_window(temperatures) -> list[Issue]:
    """W-PHY-01."""
    issues: list[Issue] = []
    for item in temperatures:
        value = item["value"]
        if LIMIT_TEMPERATURE_MIN <= value <= LIMIT_TEMPERATURE_MAX:
            continue
        issues.append(
            warn(
                "W-PHY-01",
                f"{item['label']} = {format_number(value)} K is outside the "
                f"fvOptions clamp "
                f"[{format_number(LIMIT_TEMPERATURE_MIN)}, "
                f"{format_number(LIMIT_TEMPERATURE_MAX)}] K.",
                "The generated fvOptions contains a limitTemperature entry "
                "over the whole domain. The boundary value you set is applied, "
                "but the field next to it is pulled back inside the window on "
                "every iteration, so the temperature difference that drives "
                "the buoyant flow is quietly smaller than the one you "
                f"specified ({format_number(abs(value - (LIMIT_TEMPERATURE_MAX if value > LIMIT_TEMPERATURE_MAX else LIMIT_TEMPERATURE_MIN)))} K "
                "of it is removed). The run completes and looks fine.",
                f"Either bring {item['label']} inside "
                f"[{format_number(LIMIT_TEMPERATURE_MIN)}, "
                f"{format_number(LIMIT_TEMPERATURE_MAX)}] K, or widen the min "
                "and max of limitTAir in system/fvOptions to match your case.",
                where=item["where"],
                value=value,
            )
        )
    return issues


def _check_velocity_limits(dips) -> list[Issue]:
    """W-PHY-02."""
    issues: list[Issue] = []
    for dip in dips:
        velocity = dip["V_Flow"]
        if velocity is None or abs(velocity) < VELOCITY_DAMPING_UMAX:
            continue
        issues.append(
            warn(
                "W-PHY-02",
                f"{dip['name']} supplies |V_Flow| = "
                f"{format_number(abs(velocity))} m/s, at or above the "
                f"fvOptions damping ceiling of "
                f"{format_number(VELOCITY_DAMPING_UMAX)} m/s.",
                "The generated fvOptions contains a "
                "velocityDampingConstraint with "
                f"UMax {format_number(VELOCITY_DAMPING_UMAX)} applied to the "
                "whole domain. Any cell faster than that is damped every "
                "iteration, so the jet you asked for is not the jet that is "
                "solved - and nothing in the log says so.",
                f"Lower |V_Flow| below "
                f"{format_number(VELOCITY_DAMPING_UMAX)} m/s, or raise UMax in "
                "system/fvOptions. Indoor supply jets are normally 0.5 to 5 "
                "m/s.",
                where=dip["name"],
                value=velocity,
            )
        )
    return issues


def _check_flow_signs(dips) -> list[Issue]:
    """W-PHY-03."""
    issues: list[Issue] = []
    known = [dip for dip in dips if dip["V_Flow"] is not None]
    if not known:
        return issues

    upward = [dip for dip in known if dip["V_Flow"] > 0]
    for dip in upward:
        issues.append(
            warn(
                "W-PHY-03",
                f"{dip['name']} has V_Flow = "
                f"{format_number(dip['V_Flow'])} m/s, which blows upward.",
                "V_Flow is written as the y component of the inlet velocity, "
                "and y is the vertical axis. A dip hangs from the ceiling, so "
                "a positive value sucks room air up into the duct instead of "
                "supplying air downward into the room. With no other outlet "
                "the mass balance cannot close.",
                f"Use a negative value: V_Flow="
                f"{format_number(-abs(dip['V_Flow']))}.",
                where=dip["name"],
                value=dip["V_Flow"],
            )
        )

    signs = {1 if dip["V_Flow"] > 0 else -1 for dip in known if dip["V_Flow"] != 0}
    if len(signs) > 1 and not upward:
        listed = ", ".join(
            f"{dip['name']}={format_number(dip['V_Flow'])}" for dip in known
        )
        issues.append(
            warn(
                "W-PHY-03",
                "The dips do not all blow the same way.",
                f"Recorded values: {listed}. Mixed signs mean some ducts "
                "supply and others extract. That can be deliberate, but it is "
                "most often a typo, and it changes the air-change rate "
                "completely.",
                "Make every supply dip negative. If you really want one duct "
                "to extract, say so in a comment so the next reader knows it "
                "was intended.",
                where="V_Flow",
                value=listed,
            )
        )
    return issues


def _check_reynolds(dips) -> list[Issue]:
    """W-PHY-04."""
    issues: list[Issue] = []
    for dip in dips:
        velocity, d = dip["V_Flow"], dip["d"]
        if velocity is None or not d:
            continue
        reynolds = abs(velocity) * 2 * d / NU
        if reynolds >= REYNOLDS_TURBULENT_MIN:
            continue
        issues.append(
            warn(
                "W-PHY-04",
                f"Inlet Reynolds number is {format_number(reynolds, 0)} "
                f"({dip['name']}: d={format_number(d)} m, "
                f"V_Flow={format_number(velocity)} m/s), below the "
                f"~{format_number(REYNOLDS_TURBULENT_MIN, 0)} needed for the "
                "kEpsilon model with wall functions to be valid.",
                f"Re = |V| * 2d / nu with nu = mu/rho0 = "
                f"{format_number(MU)} / {format_number(BOUSSINESQ_RHO0)} = "
                f"{format_number(NU)} m2/s. constant/turbulenceProperties "
                "selects RAS kEpsilon and every wall uses wall functions, both "
                "of which assume fully turbulent flow. Below the transition "
                "the model still produces numbers, they are simply not "
                "trustworthy.",
                f"Raise |V_Flow| above "
                f"{format_number(REYNOLDS_TURBULENT_MIN * NU / (2 * d))} m/s "
                "for this diameter, use a larger d, or accept the result as "
                "qualitative and say so in the report.",
                where=dip["name"],
                value=reynolds,
            )
        )
    return issues


def _supply_flow_rate(dips) -> float:
    """Total supplied volume flow in m3/s, using A = pi*d^2 per dip."""
    total = 0.0
    for dip in dips:
        velocity, d = dip["V_Flow"], dip["d"]
        if velocity is None or not d:
            continue
        total += abs(velocity) * math.pi * d * d
    return total


def _check_ventilation(dips, openings, room_dims) -> list[Issue]:
    """W-PHY-05 and W-PHY-06."""
    issues: list[Issue] = []
    flow = _supply_flow_rate(dips)
    if flow <= 0:
        return issues

    if room_dims:
        volume = room_dims[0] * room_dims[1] * room_dims[2]
        ach = flow * 3600.0 / volume if volume > 0 else None
        if ach is not None and not (ACH_MIN <= ach <= ACH_MAX):
            direction = "far below" if ach < ACH_MIN else "far above"
            issues.append(
                warn(
                    "W-PHY-05",
                    f"The room is ventilated at {format_number(ach, 2)} air "
                    f"changes per hour, {direction} the usual "
                    f"{format_number(ACH_MIN)} to {format_number(ACH_MAX)} "
                    "range.",
                    f"ACH = sum(|V_Flow| * pi*d^2) * 3600 / (dx*dy*dz) = "
                    f"{format_number(flow, 4)} m3/s * 3600 / "
                    f"{format_number(volume)} m3. For reference, an office is "
                    "typically 4 to 8 ACH and an operating theatre about 20. "
                    "This single number decides most of the answer in a "
                    "thermal-comfort study.",
                    "Check |V_Flow| and d against the diffuser you are "
                    "modelling. Remember the inlet area is estimated as "
                    "pi*d^2; Gate B replaces it with the real patch area from "
                    "the mesh.",
                    where="ventilation",
                    value=ach,
                )
            )

    total_open = sum(rec["area"] for rec in openings)
    if total_open > 0:
        velocity = flow / total_open
        if velocity > OUTLET_VELOCITY_MAX:
            issues.append(
                warn(
                    "W-PHY-06",
                    f"Air would leave through the openings at about "
                    f"{format_number(velocity, 2)} m/s.",
                    f"{format_number(flow, 4)} m3/s of supply air divided by "
                    f"{format_number(total_open)} m2 of opening. Above "
                    f"{format_number(OUTLET_VELOCITY_MAX)} m/s the outlet "
                    "behaves like a nozzle rather than a vent: it dominates "
                    "the room flow, and the prghPressure outlet condition is "
                    "no longer a good model of it.",
                    "Enlarge the openings or add more of them. Remember the "
                    "area is pi*d^2 because d is used as a radius, so doubling "
                    "d quadruples the area.",
                    where="insert_opening",
                    value=velocity,
                )
            )
    return issues


def _rayleigh(delta_t: float, height: float) -> float:
    """Ra = g*beta*dT*L^3 / (nu*alpha), with alpha = nu/Pr."""
    alpha = NU / PR
    return GRAVITY * BOUSSINESQ_BETA * delta_t * (height ** 3) / (NU * alpha)


def _check_boussinesq(temperatures, room_dims) -> list[Issue]:
    """W-PHY-07."""
    if not temperatures:
        return []
    values = [item["value"] for item in temperatures]
    far = [
        item
        for item in temperatures
        if abs(item["value"] - BOUSSINESQ_T0) > BOUSSINESQ_DELTA_T_MAX
    ]
    if not far:
        return []

    height = room_dims[1] if room_dims else 3.0
    delta_t = max(values) - min(values)
    rayleigh = _rayleigh(delta_t, height)
    listed = ", ".join(
        f"{item['label']}={format_number(item['value'])} K" for item in far
    )
    return [
        warn(
            "W-PHY-07",
            f"{plural(len(far), 'temperature')} more than "
            f"{format_number(BOUSSINESQ_DELTA_T_MAX)} K away from the "
            f"Boussinesq reference T0 = {format_number(BOUSSINESQ_T0)} K: "
            f"{listed}",
            "constant/thermophysicalProperties uses equationOfState "
            f"Boussinesq with T0 = {format_number(BOUSSINESQ_T0)} K and beta = "
            f"{format_number(BOUSSINESQ_BETA)} 1/K, which linearises density "
            "as rho = rho0*(1 - beta*(T - T0)). That approximation is good for "
            "roughly +/- 15 K; beyond it the buoyancy force is wrong by a few "
            "per cent and grows with the difference. Over the whole case dT = "
            f"{format_number(delta_t)} K across a height of "
            f"{format_number(height)} m, so Ra = g*beta*dT*L^3/(nu*alpha) = "
            f"{format_number(rayleigh)} - firmly turbulent natural convection.",
            "Bring the boundary temperatures closer to 300 K, or switch to a "
            "full compressible thermophysical model if the spread really is "
            "that large.",
            where="Boussinesq",
            value=rayleigh,
        )
    ]


def _check_pressure(fields: dict) -> list[Issue]:
    """W-PHY-08."""
    p_internal = _uniform_scalar((fields.get("p", {}) or {}).get("internalField"))
    if p_internal is None or math.isclose(p_internal, P_RGH_INTERNAL, abs_tol=1e-9):
        return []
    difference = p_internal - P_RGH_INTERNAL
    return [
        warn(
            "W-PHY-08",
            f"p starts at {format_number(p_internal)} Pa but p_rgh is "
            f"hardcoded to {format_number(P_RGH_INTERNAL)} Pa - a "
            f"{format_number(abs(difference))} Pa mismatch.",
            "buoyantSimpleFoam solves for p_rgh and reconstructs "
            "p = p_rgh + rho*g*h. The p internalField you set is read from "
            "your configuration, but the p_rgh internalField is written as a "
            "literal 101325 that no setting can change. Starting the two "
            "fields inconsistently injects a spurious pressure transient in "
            "the first iterations, which shows up as a slow-settling "
            "continuity residual and sometimes as bounding messages.",
            f"Set p_internalField=\"uniform {format_number(P_RGH_INTERNAL)}\" "
            "so both start from the same value.",
            where="p_internalField",
            value=p_internal,
        )
    ]


def _check_inlet_turbulence(dips) -> list[Issue]:
    """W-PHY-09."""
    velocities = [abs(dip["V_Flow"]) for dip in dips if dip["V_Flow"]]
    if not velocities:
        return []

    reference = max(velocities)
    expected_k = 1.5 * (INLET_TURBULENCE_INTENSITY * reference) ** 2
    if expected_k <= 0:
        return []
    ratio = expected_k / INLET_K
    if 1.0 / INLET_K_FACTOR_TOLERANCE <= ratio <= INLET_K_FACTOR_TOLERANCE:
        return []

    return [
        warn(
            "W-PHY-09",
            f"Inlet turbulence is hardcoded: k = {format_number(INLET_K)} "
            f"m2/s2, but this jet implies k = {format_number(expected_k)} "
            f"m2/s2 ({format_number(ratio, 2)} times as much).",
            f"Every inlet patch is written with a fixed k = "
            f"{format_number(INLET_K)} and mixingLength = "
            f"{format_number(INLET_MIXING_LENGTH)} m, no matter what V_Flow "
            "you set. The usual estimate at 5 % turbulence intensity is "
            f"k = 1.5*(I*V)^2 = 1.5*(0.05*{format_number(reference)})^2 = "
            f"{format_number(expected_k)} m2/s2. Too little inlet turbulence "
            "makes the jet spread too slowly and overpredicts the throw; too "
            "much smears it out.",
            "Edit 0/k and 0/epsilon after generation if the jet matters to "
            "your result. This is a known limitation, not something a "
            "parameter can currently fix.",
            where="inlet turbulence",
            value=expected_k,
        )
    ]


def _assumption_register(temperatures, room_dims) -> Issue:
    """I-PHY-10."""
    height = room_dims[1] if room_dims else 3.0
    values = [item["value"] for item in temperatures]
    delta_t = (max(values) - min(values)) if len(values) >= 2 else 0.0
    rayleigh = _rayleigh(delta_t, height) if delta_t > 0 else 0.0

    lines = [
        f"rho0 = {format_number(BOUSSINESQ_RHO0)} kg/m3   "
        f"T0 = {format_number(BOUSSINESQ_T0)} K   "
        f"beta = {format_number(BOUSSINESQ_BETA)} 1/K",
        f"mu   = {format_number(MU)} Pa.s   Pr = {format_number(PR)}   "
        f"Cp = {format_number(CP)} J/kg/K",
        f"nu   = mu/rho0 = {format_number(NU)} m2/s",
        f"Model: RAS kEpsilon with wall functions, steadyState ddt, "
        f"residualControl {format_number(RESIDUAL_CONTROL)}",
    ]
    if delta_t > 0:
        lines.append(
            f"Case: dT = {format_number(delta_t)} K over "
            f"{format_number(height)} m gives Ra = {format_number(rayleigh)}"
        )
    lines.append(
        "Note: rho0 = 1 kg/m3 is about 15 % below air at 300 K "
        "(1.177 kg/m3), so any mass flow in kg/s, any heat rate in W and any "
        "reported pressure carries that same 15 % scaling. Velocities and "
        "temperatures are unaffected."
    )

    return info(
        "I-PHY-10",
        "Fluid properties and modelling assumptions in use.",
        "\n".join(lines),
        "Quote these values in your report. If a result is given in kg/s or "
        "W, state the rho0 = 1 caveat alongside it.",
        where="assumptions",
        value={"rho0": BOUSSINESQ_RHO0, "mu": MU, "Pr": PR, "Cp": CP},
    )

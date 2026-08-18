"""Core types for the NEMOS validation layer.

Host-side only. This module MUST stay free of heavy dependencies: no GEOM,
no SMESH, no salome, no matplotlib, no pandas, no numpy. Standard library
only, so every check remains unit-testable on a machine that has neither
SALOME nor WSL installed.

See docs/guardrail_architecture.md for the design and the check catalogue.

Layering (no import cycles):

    validation_core.py     types, report, policy, probe, constants  (no deps)
    validation_checks.py   Gate A checks           -> imports core
    validation_parsers.py  Gate B/C/D parsers      -> imports core
    Validation.py          public facade + gates   -> imports all three
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Severities and policies
# --------------------------------------------------------------------------

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

SEVERITY_ORDER = {ERROR: 0, WARN: 1, INFO: 2}

#: Aborts on ERROR. The default, because beginners are the target user.
POLICY_STRICT = "strict"
#: Reports everything, never aborts.
POLICY_WARN = "warn"
#: Skips validation entirely.
POLICY_OFF = "off"
#: Runs Gate A, reports, then stops before any expensive stage. Used by the
#: Manager sweep to validate all N configurations before running any of them.
POLICY_PREFLIGHT_ONLY = "preflight-only"

VALID_POLICIES = (POLICY_STRICT, POLICY_WARN, POLICY_OFF, POLICY_PREFLIGHT_ONLY)

ENV_POLICY_VAR = "NEMOS_VALIDATE"


def resolve_policy(explicit: str | None = None) -> str:
    """Resolve the validation policy: explicit kwarg -> env var -> "strict".

    One exception: NEMOS_VALIDATE=preflight-only always wins. It is not a
    preference but a mode imposed by a parent process - the Manager sweep
    preflight runs each generated script with it set, expecting the script to
    validate and stop. If an explicit validate= in the script could override
    it, the "preflight" pass would run all N simulations for real.
    """
    from_env = os.environ.get(ENV_POLICY_VAR)
    if from_env and str(from_env).strip().lower() == POLICY_PREFLIGHT_ONLY:
        return POLICY_PREFLIGHT_ONLY

    for candidate in (explicit, from_env):
        if candidate is None:
            continue
        value = str(candidate).strip().lower()
        if value in VALID_POLICIES:
            return value
        if value in ("true", "1", "yes", "y", "on"):
            return POLICY_STRICT
        if value in ("false", "0", "no", "n"):
            return POLICY_OFF
        raise ValueError(
            f"Invalid validate={candidate!r}. Expected one of {', '.join(VALID_POLICIES)}."
        )
    return POLICY_STRICT


# --------------------------------------------------------------------------
# Constants mirroring the generated OpenFOAM dictionaries
# --------------------------------------------------------------------------
# Single source of truth. If Simulation.gerar_arquivos_base changes one of
# these, change it here too or the advisories will quietly go stale.

LIMIT_TEMPERATURE_MIN = 280.0        # fvOptions limitTemperature
LIMIT_TEMPERATURE_MAX = 310.0
VELOCITY_DAMPING_UMAX = 10.0         # fvOptions velocityDampingConstraint

BOUSSINESQ_T0 = 300.0                # thermophysicalProperties
BOUSSINESQ_RHO0 = 1.0
BOUSSINESQ_BETA = 3.0e-3
MU = 1.0e-5
PR = 0.7
CP = 1040.0
NU = MU / BOUSSINESQ_RHO0

P_RGH_INTERNAL = 101325.0            # hardcoded in BoundaryManager.editar_boundary
INLET_K = 0.00375                    # hardcoded inlet turbulence
INLET_MIXING_LENGTH = 0.0168
RESIDUAL_CONTROL = 1.0e-6            # fvSolution SIMPLE residualControl
DECOMPOSE_SUBDOMAINS = 4             # decomposeParDict / mpirun -np 4

DIP_CEILING_OFFSET = 0.07            # GeoMesh: dip sits at room.H - 0.07 - y
ROOM_AREA_FACTOR = 0.8               # GeoMesh Room.area = 0.8 * two smallest dims
OPENING_AREA_FRACTION_MAX = 0.2      # follows from ROOM_AREA_FACTOR

MESH_FILE_NAME = "Mesh_1.unv"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2312/etc/bashrc"
REQUIRED_FOAM_BINARIES = (
    "ideasUnvToFoam",
    "checkMesh",
    "decomposePar",
    "buoyantSimpleFoam",
    "postProcess",
)

FIELD_NAMES = ("U", "T", "p", "p_rgh", "k", "epsilon", "nut", "alphat")

#: Patch names that would collide with the names GeoMesh/OpenFOAM generate.
RESERVED_OBJECT_NAMES = frozenset(
    {"wall", "outlet", "inlet", "defaultFaces", "internalField", "boundaryField"}
)


# --------------------------------------------------------------------------
# Issue and report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    """A single validation finding.

    `title` is the one-line statement of what is wrong. `detail` explains why
    it matters (this is what teaches a beginner). `hint` is always imperative
    and concrete: the reader should be able to act on it without reading the
    source.
    """

    code: str
    severity: str
    title: str
    detail: str = ""
    hint: str = ""
    where: str | None = None
    value: object = None

    def render(self) -> str:
        head = f"[{self.code}] {self.title}"
        if self.where:
            head += f"  ({self.where})"
        lines = [head]
        for block in (self.detail, self.hint):
            if not block:
                continue
            prefix = "    -> " if block is self.hint else "    "
            for i, raw in enumerate(str(block).splitlines()):
                lines.append((prefix if i == 0 else "       ") + raw)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "hint": self.hint,
            "where": self.where,
            "value": _json_safe(self.value),
        }


def error(code: str, title: str, detail: str = "", hint: str = "", where=None, value=None) -> Issue:
    return Issue(code, ERROR, title, detail, hint, where, value)


def warn(code: str, title: str, detail: str = "", hint: str = "", where=None, value=None) -> Issue:
    return Issue(code, WARN, title, detail, hint, where, value)


def info(code: str, title: str, detail: str = "", hint: str = "", where=None, value=None) -> Issue:
    return Issue(code, INFO, title, detail, hint, where, value)


class NemosValidationError(RuntimeError):
    """Raised by ValidationReport.enforce under the "strict" policy."""

    def __init__(self, report: "ValidationReport"):
        self.report = report
        super().__init__(report.summary_line())


class ValidationReport:
    """Collects issues from one gate and renders them in a single format."""

    def __init__(self, name: str = "NEMOS validation"):
        self.name = name
        self.issues: list[Issue] = []

    # -- collection --------------------------------------------------------
    def add(self, issue: Issue | None) -> "ValidationReport":
        if issue is not None:
            self.issues.append(issue)
        return self

    def extend(self, issues) -> "ValidationReport":
        for issue in issues or ():
            self.add(issue)
        return self

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        return self.extend(other.issues)

    # -- queries -----------------------------------------------------------
    def _of(self, severity: str) -> list[Issue]:
        return [i for i in self.issues if i.severity == severity]

    @property
    def errors(self) -> list[Issue]:
        return self._of(ERROR)

    @property
    def warnings(self) -> list[Issue]:
        return self._of(WARN)

    @property
    def infos(self) -> list[Issue]:
        return self._of(INFO)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == ERROR for i in self.issues)

    def codes(self) -> list[str]:
        """Every code present, in order. Convenient for assertions in tests."""
        return [i.code for i in self.issues]

    def __contains__(self, code: str) -> bool:
        return code in self.codes()

    def __len__(self) -> int:
        return len(self.issues)

    def __bool__(self) -> bool:
        return True  # a report is always truthy; use has_errors / len()

    # -- rendering ---------------------------------------------------------
    def summary_line(self) -> str:
        n_err, n_warn = len(self.errors), len(self.warnings)
        parts = []
        parts.append(f"{n_err} error{'s' if n_err != 1 else ''}")
        parts.append(f"{n_warn} warning{'s' if n_warn != 1 else ''}")
        return f"{self.name} - {', '.join(parts)}"

    def render(self, width: int = 72) -> str:
        ordered = sorted(self.issues, key=lambda i: SEVERITY_ORDER.get(i.severity, 9))
        header = f" {self.summary_line()} "
        pad = max(4, width - len(header))
        left = pad // 2
        out = ["=" * left + header + "=" * (pad - left)]
        if not ordered:
            out.append("All checks passed.")
        for issue in ordered:
            out.append(issue.render())
            out.append("")
        while out and out[-1] == "":
            out.pop()
        out.append("=" * width)
        return "\n".join(out)

    def print(self) -> "ValidationReport":
        print(self.render())
        return self

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_json(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    # -- enforcement -------------------------------------------------------
    def enforce(self, policy: str = POLICY_STRICT) -> "ValidationReport":
        """Print the report and, under "strict", raise if there are errors."""
        if policy == POLICY_OFF:
            return self
        if self.issues:
            self.print()
        if self.has_errors and policy in (POLICY_STRICT, POLICY_PREFLIGHT_ONLY):
            print(
                f"Aborting: fix the {len(self.errors)} error"
                f"{'s' if len(self.errors) != 1 else ''} above, "
                'or pass validate="warn" to continue anyway.'
            )
            raise NemosValidationError(self)
        return self


# --------------------------------------------------------------------------
# Geometry model (built by Simulation from its recorded calls)
# --------------------------------------------------------------------------


def class_to_object_type(class_name: str | None) -> str | None:
    """Mirror of Simulation._class_to_object_type."""
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
    if class_name == "Mesh":
        return "mesh"
    return None


@dataclass
class ObjectRecord:
    """One recorded `x = nemos.Class(...)` call."""

    name: str
    class_name: str
    kwargs: dict = field(default_factory=dict)
    inline: dict = field(default_factory=dict)
    order: int = 0
    args: tuple = ()

    @property
    def object_type(self) -> str | None:
        return class_to_object_type(self.class_name)

    def get(self, key, default=None):
        return self.kwargs.get(key, default)

    def number(self, key, default=None):
        """kwargs[key] as a float, or `default` if absent/non-numeric."""
        return as_float(self.kwargs.get(key), default)


@dataclass
class MethodRecord:
    """One recorded `x.method(...)` call."""

    target: str
    class_name: str
    method: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    order: int = 0

    def get(self, key, position=None, default=None):
        if key in self.kwargs:
            return self.kwargs[key]
        if position is not None and len(self.args) > position:
            return self.args[position]
        return default

    def number(self, key, position=None, default=None):
        return as_float(self.get(key, position), default)


@dataclass
class GeometryModel:
    """Everything the host recorded about the geometry, in call order."""

    objects: list[ObjectRecord] = field(default_factory=list)
    methods: list[MethodRecord] = field(default_factory=list)

    # -- lookups -----------------------------------------------------------
    def room(self) -> ObjectRecord | None:
        rooms = self.of_type("room")
        return rooms[0] if rooms else None

    def rooms(self) -> list[ObjectRecord]:
        return self.of_type("room")

    def of_type(self, *types: str) -> list[ObjectRecord]:
        wanted = set(types)
        return [o for o in self.objects if o.object_type in wanted]

    def of_class(self, *class_names: str) -> list[ObjectRecord]:
        wanted = set(class_names)
        return [o for o in self.objects if o.class_name in wanted]

    def by_name(self, name: str) -> ObjectRecord | None:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def bodies(self) -> list[ObjectRecord]:
        """Objects that are cut out of the room (everything but Room/Mesh/env)."""
        return self.of_type("person", "dip", "table")

    def mesh(self) -> ObjectRecord | None:
        meshes = self.of_class("Mesh")
        return meshes[0] if meshes else None

    # -- recorded method calls --------------------------------------------
    def calls(self, method: str) -> list[MethodRecord]:
        return [m for m in self.methods if m.method == method]

    def openings(self) -> list[MethodRecord]:
        return [
            m
            for m in self.methods
            if m.method in ("insert_ceiling_opening", "insert_floor_opening")
        ]

    def added_names(self) -> list[str]:
        """Names passed to Room.add([...]), in order, including duplicates."""
        names: list[str] = []
        for call in self.calls("add"):
            payload = call.args[0] if call.args else call.kwargs.get("obj_list")
            if payload is None:
                continue
            if not isinstance(payload, (list, tuple)):
                payload = [payload]
            for item in payload:
                resolved = _name_of(item)
                if resolved is not None:
                    names.append(resolved)
        return names

    def room_dims(self) -> tuple[float, float, float] | None:
        room = self.room()
        if room is None:
            return None
        dx = room.number("dx", 3.0)
        dy = room.number("dy", 3.0)
        dz = room.number("dz", 3.0)
        if None in (dx, dy, dz):
            return None
        return (dx, dy, dz)


def _name_of(item) -> str | None:
    """Best-effort name for an object referenced inside a recorded call."""
    if isinstance(item, str):
        return item
    for attr in ("name", "_nemos_name", "_var_name"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


# --------------------------------------------------------------------------
# Axis-aligned extents (conservative bounding volumes)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Extent:
    """A conservative axis-aligned bounding box, in metres."""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float

    @classmethod
    def from_center(cls, x, y, z, half_x, half_y, half_z) -> "Extent":
        return cls(x - half_x, x + half_x, y - half_y, y + half_y, z - half_z, z + half_z)

    @classmethod
    def column(cls, x, z, radius, ymin, ymax) -> "Extent":
        """A vertical cylinder's bounding box."""
        return cls(x - radius, x + radius, ymin, ymax, z - radius, z + radius)

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.xmax - self.xmin, self.ymax - self.ymin, self.zmax - self.zmin)

    def overlaps(self, other: "Extent", tol: float = 0.0) -> bool:
        """True if the two boxes intersect by more than `tol` on every axis."""
        return (
            min(self.xmax, other.xmax) - max(self.xmin, other.xmin) > tol
            and min(self.ymax, other.ymax) - max(self.ymin, other.ymin) > tol
            and min(self.zmax, other.zmax) - max(self.zmin, other.zmin) > tol
        )

    def contains(self, other: "Extent", tol: float = 0.0) -> bool:
        """True if `other` lies inside this box, allowing `tol` of slack."""
        return (
            other.xmin >= self.xmin - tol
            and other.xmax <= self.xmax + tol
            and other.ymin >= self.ymin - tol
            and other.ymax <= self.ymax + tol
            and other.zmin >= self.zmin - tol
            and other.zmax <= self.zmax + tol
        )

    def outside_axes(self, other: "Extent", tol: float = 0.0) -> list[str]:
        """Which axes of `other` stick out of this box. For error messages."""
        out = []
        if other.xmin < self.xmin - tol or other.xmax > self.xmax + tol:
            out.append("x")
        if other.ymin < self.ymin - tol or other.ymax > self.ymax + tol:
            out.append("y")
        if other.zmin < self.zmin - tol or other.zmax > self.zmax + tol:
            out.append("z")
        return out

    def gap_to(self, other: "Extent") -> float:
        """Shortest separation between the two boxes; negative if they overlap."""
        dx = max(self.xmin - other.xmax, other.xmin - self.xmax, 0.0)
        dy = max(self.ymin - other.ymax, other.ymin - self.ymax, 0.0)
        dz = max(self.zmin - other.zmax, other.zmin - self.zmax, 0.0)
        if dx == dy == dz == 0.0:
            return -1.0 if self.overlaps(other) else 0.0
        return math.sqrt(dx * dx + dy * dy + dz * dz)


# --------------------------------------------------------------------------
# Environment probe (the seam that makes environment checks testable)
# --------------------------------------------------------------------------


class EnvProbe:
    """Every environment query goes through this object.

    Tests inject a fake (see FakeEnvProbe in the test suite) so that missing
    binaries, absent WSL distros and failing OpenFOAM commands can be simulated
    without touching the real machine.
    """

    #: Seconds before a probe subprocess is abandoned.
    timeout = 20

    def path_exists(self, path) -> bool:
        try:
            return Path(path).exists()
        except OSError:
            return False

    def is_file(self, path) -> bool:
        try:
            return Path(path).is_file()
        except OSError:
            return False

    def module_importable(self, name: str) -> bool:
        import importlib.util

        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def free_disk_bytes(self, path) -> int | None:
        try:
            target = Path(path)
            while not target.exists() and target.parent != target:
                target = target.parent
            return shutil.disk_usage(target).free
        except OSError:
            return None

    # -- WSL ---------------------------------------------------------------
    def _run(self, args: list[str]) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return (127, "")
        return (proc.returncode, (proc.stdout or "") + (proc.stderr or ""))

    def wsl_available(self) -> bool:
        if shutil.which("wsl") is None:
            return False
        code, out = self._run(["wsl", "-l", "-q"])
        if code != 0:
            return False
        # wsl -l -q output is UTF-16-ish on some builds; nulls survive decoding.
        return bool(out.replace("\x00", "").strip())

    def wsl_test_file(self, path: str) -> bool:
        code, _ = self._run(["wsl", "test", "-f", path])
        return code == 0

    def wsl_which(self, binaries) -> dict[str, bool]:
        """Which of `binaries` resolve after sourcing the OpenFOAM bashrc.

        The script is emitted as one explicit line per binary, with no shell
        variables. A `for b in ...; do ... $b ...; done` loop looked cleaner but
        `$b` arrived empty on the WSL side, so every binary was reported missing
        - a false E-ENV-04 that would block every run under the strict policy.
        """
        names = [str(n) for n in binaries if str(n).strip()]
        if not names:
            return {}
        checks = "; ".join(
            f"command -v {name} >/dev/null 2>&1 && echo OK:{name} || echo NO:{name}"
            for name in names
        )
        script = f"source {OPENFOAM_BASHRC} >/dev/null 2>&1; {checks}"
        code, out = self._run(["wsl", "bash", "-lc", script])
        found = {name: False for name in names}
        if code != 0 and not out:
            return found
        for line in out.splitlines():
            line = line.strip().replace("\x00", "")
            if line.startswith("OK:") and line[3:] in found:
                found[line[3:]] = True
        return found

    def wsl_nproc(self) -> int | None:
        code, out = self._run(["wsl", "nproc"])
        if code != 0:
            return None
        try:
            return int(out.replace("\x00", "").strip().splitlines()[0])
        except (ValueError, IndexError):
            return None


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------


def as_float(value, default=None):
    """Coerce to float, tolerating "uniform 300" and plain numbers."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        pass
    import re

    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return default
    return default


def is_number(value) -> bool:
    return as_float(value, None) is not None


def format_number(value, digits: int = 4) -> str:
    """Compact, readable number formatting for messages.

    Trailing zeros are stripped only after a decimal point: stripping them
    unconditionally turns 200 into "2", which silently corrupts every number in
    a message formatted with digits=0.

    Scientific notation is reserved for genuinely tiny or huge magnitudes, so a
    pressure like 101322 stays readable instead of collapsing to 1.013e+05.
    """
    number = as_float(value, None)
    if number is None:
        return str(value)
    if number != 0 and (abs(number) < 1e-3 or abs(number) >= 1e9):
        return f"{number:.{max(digits, 3)}g}"
    text = f"{number:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def suggest(name: str, valid, cutoff: float = 0.6) -> str | None:
    """Closest valid name, for "did you mean" hints."""
    import difflib

    matches = difflib.get_close_matches(str(name), sorted(valid), n=1, cutoff=cutoff)
    if matches:
        return matches[0]
    lowered = str(name).lower()
    for candidate in sorted(valid):
        if candidate.lower() == lowered:
            return candidate
    return None


def plural(count: int, singular: str, suffix: str = "s") -> str:
    return f"{count} {singular}{'' if count == 1 else suffix}"


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)

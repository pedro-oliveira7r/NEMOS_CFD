import ast
import inspect
import subprocess
import sys
from pathlib import Path

_ACTIVE_SIMULATION = None


class Simulation:
    def __init__(self, script_path: str = None, case_path: str = None, **kwargs):
        self.user_script_path = Path(script_path) if script_path else None
        self.case_path = Path(case_path) if case_path else None
        self._sim_kwargs = dict(kwargs)
        self._actions = []
        self._object_var_names = {}
        self._object_classes_by_var = {}
        self._used_var_names = set()
        self._var_counter = 0
        self._list_names = self._load_list_names()
        self._sweep_lists = {}
        self._sweep_list_ids = {}
        self._sweep_length = 0
        _set_active_simulation(self)

    def _load_list_names(self):
        if not self.user_script_path or not self.user_script_path.exists():
            return set()
        source_text = self.user_script_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            return set()

        list_names = set()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    list_names.add(target.id)
        return list_names

    def _collect_sweep_lists(self, globals_dict: dict):
        sweep_lists = {}
        sweep_ids = {}
        for name in self._list_names:
            value = globals_dict.get(name)
            if isinstance(value, (list, tuple)):
                sweep_lists[name] = list(value)
                sweep_ids[id(value)] = name

        if not sweep_lists:
            raise ValueError("Nenhuma lista de parametros foi encontrada no manager_script.")

        lengths_by_name = {name: len(values) for name, values in sweep_lists.items()}
        lengths = set(lengths_by_name.values())
        if len(lengths) != 1:
            details = ", ".join(
                f"{name}={length}" for name, length in sorted(lengths_by_name.items())
            )
            raise ValueError(
                "Todas as listas devem ter o mesmo tamanho. "
                f"Tamanhos encontrados: {details}."
            )

        length = lengths.pop()
        if length == 0:
            raise ValueError("As listas de parametros nao podem estar vazias.")

        self._sweep_lists = sweep_lists
        self._sweep_list_ids = sweep_ids
        self._sweep_length = length

    def _reserve_var_name(self, base: str):
        if not base:
            self._var_counter += 1
            base = f"obj_{self._var_counter}"

        base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(base))
        if base and base[0].isdigit():
            base = f"_{base}"
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

    def _register_object(self, obj, class_name: str, args, kwargs):
        kwargs = dict(kwargs)
        name_value = kwargs.get("name")
        base_name = str(name_value).strip() if name_value is not None else class_name.lower()
        var_name = self._reserve_var_name(base_name)

        self._object_var_names[obj] = var_name
        self._object_classes_by_var[var_name] = class_name
        self._actions.append(("init", var_name, class_name, args, kwargs))
        return var_name

    def _record_method(self, obj, method_name: str, args, kwargs):
        var_name = self._object_var_names.get(obj)
        if not var_name:
            return
        self._actions.append(("method", var_name, method_name, args, dict(kwargs)))

    def _value_uses_sweep(self, value):
        if isinstance(value, _RecordedObject):
            return False

        if isinstance(value, (list, tuple)):
            if id(value) in self._sweep_list_ids:
                return True
            return any(self._value_uses_sweep(item) for item in value)

        if isinstance(value, dict):
            return any(self._value_uses_sweep(item) for item in value.values())

        return False

    def _args_kwargs_use_sweep(self, args, kwargs):
        return any(self._value_uses_sweep(arg) for arg in args) or any(
            self._value_uses_sweep(value) for value in kwargs.values()
        )

    def _mesh_uses_sweep(self):
        for action in self._actions:
            kind = action[0]
            if kind == "init":
                _, _, class_name, args, kwargs = action
                if class_name == "Mesh" and self._args_kwargs_use_sweep(args, kwargs):
                    return True
                continue

            if kind == "method":
                _, var_name, method_name, args, kwargs = action
                if (
                    self._object_classes_by_var.get(var_name) == "Mesh"
                    and method_name == "create_mesh"
                    and self._args_kwargs_use_sweep(args, kwargs)
                ):
                    return True

        return False

    def _format_value(self, value, index: int):
        if isinstance(value, _RecordedObject):
            return value._var_name

        if isinstance(value, list):
            list_name = self._sweep_list_ids.get(id(value))
            if list_name is not None:
                return self._format_value(self._sweep_lists[list_name][index], index)
            inner = ", ".join(self._format_value(v, index) for v in value)
            return f"[{inner}]"

        if isinstance(value, tuple):
            list_name = self._sweep_list_ids.get(id(value))
            if list_name is not None:
                return self._format_value(self._sweep_lists[list_name][index], index)
            inner = ", ".join(self._format_value(v, index) for v in value)
            if len(value) == 1:
                inner = inner + ","
            return f"({inner})"

        if isinstance(value, dict):
            parts = []
            for key, val in value.items():
                parts.append(f"{repr(key)}: {self._format_value(val, index)}")
            return "{" + ", ".join(parts) + "}"

        return repr(value)

    def _format_args_kwargs(self, args, kwargs, index: int):
        parts = [self._format_value(arg, index) for arg in args]
        for key, value in kwargs.items():
            parts.append(f"{key}={self._format_value(value, index)}")
        return ", ".join(parts)

    def _render_script(self, case_path: Path, index: int):
        sim_kwargs = [f"case_path={repr(str(case_path))}"]
        for key, value in self._sim_kwargs.items():
            sim_kwargs.append(f"{key}={repr(value)}")

        shared_mesh_path = self.case_path / "SIM_0" / "Mesh_1.unv"
        mesh_uses_sweep = self._mesh_uses_sweep()
        src_dir = Path(__file__).resolve().parent

        lines = [
            "import sys",
            f"sys.path.insert(0, {repr(str(src_dir))})",
            "import Simulation as nemos",
            "",
            "sim = nemos.Simulation(",
        ]
        lines.extend([f"    {item}," for item in sim_kwargs])
        lines.append(")")

        for action in self._actions:
            kind = action[0]
            if kind == "init":
                _, var_name, class_name, args, kwargs = action
                if class_name == "Mesh" and index > 0 and not mesh_uses_sweep:
                    continue
                args_str = self._format_args_kwargs(args, kwargs, index)
                lines.append(f"{var_name} = nemos.{class_name}({args_str})")
                continue

            if kind == "method":
                _, var_name, method_name, args, kwargs = action
                if (
                    self._object_classes_by_var.get(var_name) == "Mesh"
                    and method_name == "create_mesh"
                ):
                    if index == 0 or mesh_uses_sweep:
                        args_str = self._format_args_kwargs(args, kwargs, index)
                        lines.append(f"{var_name}.{method_name}({args_str})")
                    else:
                        lines.append(
                            f"{var_name} = nemos.Simulation.Import_mesh({repr(str(shared_mesh_path))})"
                        )
                    continue
                args_str = self._format_args_kwargs(args, kwargs, index)
                lines.append(f"{var_name}.{method_name}({args_str})")

        lines.extend(
            [
                "",
                "case = nemos.run(sim)",
            ]
        )

        return "\n".join(lines).rstrip() + "\n"

    def build_machine_script(self):
        if self.case_path is None:
            raise ValueError("Simulation precisa de case_path")

        caller_frame = inspect.currentframe().f_back
        caller_globals = caller_frame.f_globals if caller_frame else {}
        self._collect_sweep_lists(caller_globals)

        scripts_dir = self.case_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        script_paths = []
        for idx in range(self._sweep_length):
            sim_dir = self.case_path / f"SIM_{idx}"
            sim_dir.mkdir(parents=True, exist_ok=True)

            script_path = scripts_dir / f"script_{idx}.py"
            script_path.write_text(self._render_script(sim_dir, idx), encoding="utf-8")
            script_paths.append(script_path)

        return script_paths
    

def run_script(script_path: Path, cwd: Path) -> int:
    command = [sys.executable, str(script_path)]
    print(f"\n=== Running {script_path.name} ===")

    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )

    log_dir = cwd / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_path.stem}.log"
    log_file.write_text(
        "".join(
            [
                f"Command: {' '.join(command)}\n",
                f"Exit code: {result.returncode}\n\n",
                "--- STDOUT ---\n",
                result.stdout or "",
                "\n--- STDERR ---\n",
                result.stderr or "",
            ]
        ),
        encoding="utf-8",
    )

    if result.returncode != 0:
        print(f"[FAIL] {script_path.name} (see {log_file})")
    else:
        print(f"[OK] {script_path.name}")

    return result.returncode


def main(scripts=None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    if scripts is None:
        scripts = [
            src_dir / "user_script_base.py",
            src_dir / "user_script_classroom.py",
            src_dir / "user_script_H.py",
        ]

    missing = [str(path) for path in scripts if not path.exists()]
    if missing:
        print("Missing scripts:")
        for path in missing:
            print(f"- {path}")
        return 2

    script_paths = [Path(script) for script in scripts]
    scripts_dirs = {path.parent for path in script_paths}
    if len(scripts_dirs) == 1 and next(iter(scripts_dirs)).name == "scripts":
        scripts_dir = next(iter(scripts_dirs))
        case_root = scripts_dir.parent
        print(
            "\nQueue summary:\n"
            f"- Scripts: {len(script_paths)}\n"
            f"- Case root: {case_root}\n"
            f"- Scripts dir: {scripts_dir}"
        )
    else:
        print(f"\nQueue summary: {len(script_paths)} scripts")

    exit_code = 0
    for script_path in script_paths:
        if script_path.parent.name == "scripts":
            cwd = script_path.parent.parent
        else:
            cwd = repo_root
        result = run_script(script_path, cwd)
        if result != 0:
            exit_code = result
            break

    if exit_code == 0:
        print("\nAll runs completed successfully.")
    else:
        print("\nSome runs failed.")

    return exit_code

def _set_active_simulation(simulation):
    global _ACTIVE_SIMULATION
    _ACTIVE_SIMULATION = simulation

def _get_active_simulation():
    if _ACTIVE_SIMULATION is None:
        raise RuntimeError("Simulation nao foi inicializada.")
    return _ACTIVE_SIMULATION

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


if __name__ == "__main__":
    raise SystemExit(main())

"""`microscope_agent/` already has the shape soft-matter-agents will check when it is copied
there (docs/integration-sma.md section 9; that repository's contracts/validate.py checks 13,
16 and 82 at baf6f1e): flat src (or src/devices/<file>), flat tests, stdlib + numpy imports
only, no relative or dino_autofocus imports, no device importing a sibling."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "microscope_agent"
ALLOWED_THIRD_PARTY = {"numpy"}  # what the soft-matter-agents `mic` environment has
SKIP = {"__pycache__"}


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and not SKIP & set(p.parts))


def _imports(path: Path) -> list[tuple[str, int]]:
    """(top-level module, relative level) of every import, inside functions too."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(a.name.split(".")[0], 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(((node.module or "").split(".")[0], node.level))
    return out


def test_src_is_flat_or_devices():
    bad = []
    for p in _files(ROOT / "src"):
        rel = p.relative_to(ROOT / "src").parts
        ok = (len(rel) == 1 or (len(rel) == 2 and rel[0] == "devices")) and p.suffix == ".py"
        if not ok or p.name == "__init__.py":
            bad.append(str(p))
    assert not bad, bad
    assert list((ROOT / "src").glob("*.py")), "nothing to check"


def test_tests_are_flat_py_files():
    bad = [str(p) for p in _files(ROOT / "tests")
           if len(p.relative_to(ROOT / "tests").parts) != 1 or p.suffix != ".py"]
    assert not bad, bad


def test_imports_are_stdlib_or_numpy_and_never_relative():
    allowed = set(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY | {"__future__"}
    bad = []
    for p in [*_files(ROOT / "src"), *_files(ROOT / "tests")]:
        for mod, level in _imports(p):
            if level or mod not in allowed:
                bad.append(f"{p.name}: {'.' * level}{mod}")
    assert not bad, bad


def test_no_file_shadows_a_stdlib_module():
    stems = {p.stem for p in _files(ROOT / "src")}
    assert not stems & set(sys.stdlib_module_names)


def test_devices_import_no_sibling():
    siblings = {p.stem for p in _files(ROOT / "src")}
    bad = [f"{p.name}: {m}" for p in _files(ROOT / "src" / "devices")
           for m, _ in _imports(p) if m in siblings]
    assert not bad, bad

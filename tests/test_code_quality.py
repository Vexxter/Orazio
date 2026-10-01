"""House rules for the Python code, enforced rather than remembered.

Small, mechanical checks that keep the codebase tidy as it grows: nothing imported and forgotten,
every module says what it is for, failures never vanish into a bare `except:`.
"""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "orazio"
MODULES = sorted(PACKAGE.rglob("*.py"))


def tree_of(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_no_unused_imports(path):
    if path.name == "__init__.py":
        return                                   # package __init__ files import to re-export
    tree = tree_of(path)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    unused = sorted(name for name in imported if name not in used)
    assert not unused, f"{path.name} imports but never uses: {unused}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_every_module_explains_itself(path):
    if path.name == "__init__.py" and path.stat().st_size == 0:
        return
    assert ast.get_docstring(tree_of(path)), f"{path.name} has no module docstring"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_no_bare_except_and_no_stray_prints(path):
    tree = tree_of(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            pytest.fail(f"{path.name}:{node.lineno} bare `except:` swallows KeyboardInterrupt and real bugs alike")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            pytest.fail(f"{path.name}:{node.lineno} print() in library code")


def test_every_module_in_the_package_is_importable():
    import importlib
    for path in MODULES:
        rel = path.relative_to(PACKAGE.parent).with_suffix("")
        importlib.import_module(".".join(rel.parts if rel.name != "__init__" else rel.parts[:-1]))

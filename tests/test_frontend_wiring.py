"""Frontend wiring: the mistakes a unit test can't see because nothing runs the page.

There is no browser in this suite, so these static checks catch the typo-class bugs that otherwise
only show up as a blank panel: a script asking for an element id that isn't in index.html, an import
of a name its module doesn't export, a toolbar button with no visible caption, a rail alias with no
display name.
"""
import re
from pathlib import Path

import pytest

from orazio.constants import QUICK_INDICES

STATIC = Path(__file__).resolve().parent.parent / "static"
JS_DIR = STATIC / "js"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS_FILES = sorted(JS_DIR.glob("*.js"))


def html_ids():
    """Ids in index.html, plus ids a script creates itself (e.g. `<div id="ladder-box">` in a template)."""
    ids = set(re.findall(r'\bid="([^"]+)"', HTML))
    for path in JS_FILES:
        ids |= set(re.findall(r'\bid="([\w-]+)"', path.read_text(encoding="utf-8")))
    return ids


def read(path):
    return path.read_text(encoding="utf-8")


def exported_names(path):
    src = read(path)
    names = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+([\w$]+)", src))
    for block in re.findall(r"export\s*\{([^}]*)\}", src):
        for part in block.split(","):
            part = part.strip()
            if part:
                names.add(part.split(" as ")[-1].strip())
    return names


# ---- element ids --------------------------------------------------------------------
@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_every_element_id_a_script_looks_up_exists_in_the_page(path):
    src = read(path)
    used = set(re.findall(r"\$\('([\w-]+)'\)", src)) | set(re.findall(r"getElementById\('([\w-]+)'\)", src))
    missing = sorted(used - html_ids())
    assert not missing, f"{path.name} looks up ids that index.html does not define: {missing}"


def test_html_ids_are_unique():
    ids = re.findall(r'\bid="([^"]+)"', HTML)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate ids in index.html: {dupes}"


# ---- imports ------------------------------------------------------------------------
IMPORT_RE = re.compile(r"import\s*(?:\{([^}]*)\}\s*from\s*)?'(\./[^']+)'")


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_every_import_resolves_to_a_real_export(path):
    problems = []
    for names, target in IMPORT_RE.findall(read(path)):
        target_path = (path.parent / target).resolve()
        if not target_path.exists():
            problems.append(f"{target} does not exist")
            continue
        if not names.strip():
            continue                                                  # side-effect import: the file existing is enough
        available = exported_names(target_path)
        for part in names.split(","):
            name = part.strip().split(" as ")[0].strip()
            if name and name not in available:
                problems.append(f"{target} has no export {name!r}")
    assert not problems, f"{path.name}: " + "; ".join(problems)


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_no_unused_imports_in_scripts(path):
    src = read(path)
    unused = []
    for names, _target in IMPORT_RE.findall(src):
        for part in names.split(","):
            local = part.strip().split(" as ")[-1].strip()
            # `$` is not a regex word character, so use explicit look-arounds instead of \b
            if local and len(re.findall(rf"(?<![\w$]){re.escape(local)}(?![\w$])", src)) < 2:
                unused.append(local)
    assert not unused, f"{path.name} imports but never uses: {unused}"


def test_the_page_loads_files_that_exist():
    for ref in re.findall(r'(?:src|href)="(/[^"]+)"', HTML):
        if ref.startswith("/js/") or ref.endswith(".css"):
            assert (STATIC / ref.lstrip("/")).exists(), f"index.html references missing {ref}"


def test_every_script_is_actually_loaded_by_main():
    """A module nobody imports is dead code (or a feature that silently never starts)."""
    loaded = set(re.findall(r"import\s*'\./([^']+)'", read(JS_DIR / "main.js")))
    imported_elsewhere = set()
    for path in JS_FILES:
        imported_elsewhere |= {Path(t).name for _n, t in IMPORT_RE.findall(read(path))}
    for path in JS_FILES:
        assert path.name == "main.js" or path.name in loaded or path.name in imported_elsewhere, f"{path.name} is never loaded"


# ---- UI conventions ----------------------------------------------------------------------
def test_every_toolbar_button_has_a_visible_name_under_it():
    buttons = re.findall(r'<button[^>]*class="btn[^"]*\btool\b[^"]*"[^>]*id="([^"]+)"[^>]*>(.*?)</button>', HTML, re.S)
    assert len(buttons) >= 10, "expected the toolbar's icon buttons"
    nameless = [bid for bid, inner in buttons if not re.search(r'class="(?:cap|label)"[^>]*>\s*[^<\s]', inner)]
    assert not nameless, f"toolbar buttons without a visible caption: {nameless}"


def test_modals_have_a_close_button_and_an_accessible_title():
    for modal_id in re.findall(r'<div class="backdrop" id="([^"]+)"', HTML):
        block = HTML[HTML.index(f'id="{modal_id}"'):]
        block = block[:block.index('<div class="backdrop"', 10)] if '<div class="backdrop"' in block[10:] else block
        assert 'aria-labelledby="' in block, f"{modal_id} has no aria-labelledby"
        assert re.search(r'aria-label="Close', block), f"{modal_id} has no close button"


def test_every_rail_alias_has_a_display_name_and_group():
    rail = read(JS_DIR / "rail.js")
    meta_block = rail[rail.index("INDEX_META = {"):rail.index("};", rail.index("INDEX_META = {"))]
    keys = set(re.findall(r"\b([A-Z][A-Z0-9]*):\s*\[", meta_block))
    missing = [alias for _label, alias in QUICK_INDICES if alias not in keys]
    assert not missing, f"rail.js INDEX_META has no entry for: {missing}"
    groups = set(re.findall(r"RAIL_GROUPS = \[([^\]]*)\]", rail)[0].replace("'", "").replace(" ", "").split(","))
    used = set(re.findall(r"\],?\s*(?=[A-Z]|\n|\})", meta_block)) or groups
    for group in re.findall(r"\[\s*'[^']*',\s*'(\w+)'\s*\]", meta_block):
        assert group in groups, f"rail group {group!r} is not in RAIL_GROUPS"


def test_movers_tabs_match_the_universes_the_backend_serves():
    from orazio import constituents, global_movers, movers
    served = set(movers.UNIVERSES) | set(global_movers.UNIVERSES) | set(constituents.CONSTITUENT_ALIASES)
    tabs = set(re.findall(r'data-universe="(\w+)"', HTML))
    assert tabs <= served, f"movers tabs with no backend: {sorted(tabs - served)}"

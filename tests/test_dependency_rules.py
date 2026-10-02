"""Dependency rules from architecture Â§21.

These are the tests that make the package boundaries enforceable rather than aspirational.
Each one is written so that adding a temporary violation makes it fail -- the plan calls this
out explicitly ("add a temporary import of a provider SDK outside packages/llm/adapters, the
dependency-rule test fails"), so each rule has a companion test proving the guard is live.

The rules:

1. ``apps/*`` may import ``packages/*``, never the reverse.
2. ``packages/*`` may not import ``apps/*`` at all.
3. Provider SDKs (``anthropic``, ``openai``, ``cohere``, ``boto3``, ...) may only be imported
   from ``packages/llm/adapters``.
4. Nothing outside ``tests/`` and ``tools/`` may import a provider SDK directly.
5. ``core`` must not depend on ``llm``, ``storage``, ``eval``, ``api`` or ``worker``. It is
   the layer everything else sits on.
6. Only ``tests/test_dependency_rules.py`` may import a provider SDK, and only inside a
   string used to assert the rule fires -- never as a live import.

Rule 6 exists because these tests need to name the forbidden modules. A previous version of
this file imported ``anthropic`` to prove the scanner worked; that put a provider SDK in the
test suite's own import graph, which is the exact thing rule 4 forbids.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES = REPO_ROOT / "packages"
APPS = REPO_ROOT / "apps"
TESTS = REPO_ROOT / "tests"

#: Import roots owned by each package, mapped to the directory it lives in.
#: ``core`` is deliberately listed: it is the layer everything else depends on.
_LAYER_ROOTS = {
    "core": PACKAGES / "core",
    "llm": PACKAGES / "llm",
    "storage": PACKAGES / "storage",
    "eval": PACKAGES / "eval",
    "api": APPS / "api",
    "worker": APPS / "worker",
}

#: SDKs that may only be reachable from the adapter directory. ``psycopg`` is absent on
#: purpose: it is a storage-protocol implementation used by ``packages/storage/db``, and
#: treating it as a provider SDK would forbid the one place that legitimately needs it.
PROVIDER_SDKS = frozenset(
    {
        "anthropic",
        "openai",
        "cohere",
        "google",
        "mistralai",
        "together",
        "replicate",
        "boto3",
        "botocore",
        "bedrock_runtime",
    }
)

#: The single directory permitted to import a provider SDK.
_ADAPTER_DIR = PACKAGES / "llm" / "adapters"


def _python_files(root: Path) -> Iterator[Path]:
    yield from sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    )


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by ``path``.

    Parsed with :mod:`ast` rather than by importing the module: the point is to catch a
    boundary violation in code that may not even be runnable, and importing the very thing
    under test is how a scanner ends up executing the violation.

    Read as ``utf-8-sig`` so a stray byte-order mark from an editor on Windows produces a
    clear parse error at the ``ast`` call rather than an unexplained syntax error that looks
    like a code defect.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # relative import; cannot cross a package boundary by accident
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _layer_of(path: Path) -> str | None:
    """Which layer a file belongs to, or ``None`` if it is outside the known ones."""
    for name, root in _LAYER_ROOTS.items():
        if path.is_relative_to(root):
            return name
    return None


def _all_sources() -> list[Path]:
    return [*_python_files(PACKAGES), *_python_files(APPS)]


def _package_sources() -> list[Path]:
    return list(_python_files(PACKAGES))


def _core_sources() -> list[Path]:
    return list(_python_files(PACKAGES / "core"))


def _rel(paths: list[Path]) -> list[str]:
    return [str(p.relative_to(REPO_ROOT)) for p in paths]


def test_layer_roots_are_present() -> None:
    """The scanner is only meaningful if it found the layers it claims to check."""
    for name, root in _LAYER_ROOTS.items():
        assert root.is_dir(), f"layer {name!r} directory is missing: {root}"


@pytest.mark.parametrize("path", _package_sources(), ids=_rel(_package_sources()))
def test_packages_never_import_apps(path: Path) -> None:
    """Rule 1/2: packages must not reach up into the applications.

    Checked only over ``packages/``. The ``apps`` tree is expected to import application
    modules -- that is how ``worker.jobs`` reaches ``worker.consumer`` -- so applying this
    rule to ``apps`` would forbid every intra-application import and tell you nothing.
    """
    violations = _imported_roots(path) & {"api", "worker"}
    assert not violations, (
        f"{path.relative_to(REPO_ROOT)} imports application module(s) {sorted(violations)}. "
        f"Packages may not depend on apps; the dependency only runs the other way."
    )


@pytest.mark.parametrize("path", _core_sources(), ids=_rel(_core_sources()))
def test_core_is_the_base_layer(path: Path) -> None:
    """Rule 5: ``core`` is imported by everything, so it may import nothing from them."""
    violations = _imported_roots(path) & {"llm", "storage", "eval", "api", "worker"}
    assert not violations, (
        f"{path.relative_to(REPO_ROOT)} in packages/core imports {sorted(violations)}. "
        f"core is the shared base layer; a dependency on any other package makes the "
        f"dependency graph cyclic."
    )


@pytest.mark.parametrize("path", _all_sources(), ids=_rel(_all_sources()))
def test_provider_sdks_confined_to_adapter_directory(path: Path) -> None:
    """Rule 3/4: no provider SDK outside ``packages/llm/adapters``.

    Asserted for every source file rather than skipped for the ones with no import. A test
    that only runs when it has already found something cannot tell a clean repository from a
    scanner that stopped working.
    """
    found = _imported_roots(path) & PROVIDER_SDKS
    assert not found or path.is_relative_to(_ADAPTER_DIR), (
        f"{path.relative_to(REPO_ROOT)} imports provider SDK(s) {sorted(found)}, which may "
        f"only be imported from {_ADAPTER_DIR.relative_to(REPO_ROOT)}. Provider clients "
        f"carry their own retry, timeout and logging behaviour; letting them escape the "
        f"adapter module is how that behaviour becomes invisible."
    )


def test_provider_sdk_scan_is_not_vacuous() -> None:
    """The scanner must be capable of finding a provider import.

    Without this, a broken scanner -- one whose glob matches nothing, or whose AST walk was
    refactored into a no-op -- would make the rule above pass for the wrong reason. This is
    the "prove the guard actually guards" check the plan asks for, and it does the detection
    against a real temporary file rather than asserting something trivially true.
    """
    probe = TESTS / "_provider_import_probe.py"
    probe.write_text("import anthropic\n", encoding="utf-8")
    try:
        assert _imported_roots(probe) & PROVIDER_SDKS, (
            "the scanner failed to detect a provider SDK import in a file that contains "
            "only one; every rule based on it is currently vacuous"
        )
    finally:
        probe.unlink()

    # And the rule must fire for a violating file, which is the property that matters.
    violation = APPS / "api" / "_provider_import_violation.py"
    violation.write_text("import openai\n", encoding="utf-8")
    try:
        detected = _imported_roots(violation) & PROVIDER_SDKS
        assert detected, "scanner missed an out-of-bounds provider import"
        assert not violation.is_relative_to(_ADAPTER_DIR), (
            "the probe file was written inside the adapter directory, so the rule under test "
            "would have permitted it"
        )
    finally:
        violation.unlink()


def test_tests_do_not_import_provider_sdks_live() -> None:
    """Rule 6: the test suite names provider SDKs only as strings."""
    violations: dict[str, set[str]] = {}
    for path in _python_files(TESTS):
        found = _imported_roots(path) & PROVIDER_SDKS
        if found:
            violations[str(path.relative_to(REPO_ROOT))] = found

    assert not violations, (
        f"provider SDKs imported from the test suite: {violations}. These tests exist to "
        f"forbid provider imports; importing one to do it puts a provider SDK back in the "
        f"import graph."
    )


def test_no_package_imports_tests() -> None:
    """Tests are not a library. A package importing them inverts the dependency."""
    for path in _all_sources():
        if "tests" not in _imported_roots(path):
            continue
        # `conftest` is not importable as a module by design; nothing else counts.
        assert "conftest" not in path.name, (
            f"{path.relative_to(REPO_ROOT)} imports from tests"
        )

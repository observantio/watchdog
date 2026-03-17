import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

PROJECT_ROOTS = {
    "watchdog": REPO_ROOT / "watchdog",
    "notifier": REPO_ROOT / "notifier",
    "gateway": REPO_ROOT / "gatekeeper",
    "resolver": REPO_ROOT / "resolver",
}

CONFLICT_PREFIXES = (
    "config",
    "services",
    "models",
    "routers",
    "middleware",
    "database",
    "db_models",
    "main",
    "tests",
)
_ACTIVE_ROOT: Path | None = None


def _detect_project(path: Path) -> Path | None:
    p = str(path)
    if f"{os.sep}watchdog{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["watchdog"]
    if f"{os.sep}notifier{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["notifier"]
    if f"{os.sep}gatekeeper{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["gateway"]
    if f"{os.sep}resolver{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["resolver"]
    return None


def _set_import_root(root: Path, purge_modules: bool = True) -> None:
    global _ACTIVE_ROOT
    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)

    if purge_modules:
        to_delete = []
        for name in sys.modules:
            if name in CONFLICT_PREFIXES:
                to_delete.append(name)
                continue
            if any(name.startswith(f"{prefix}.") for prefix in CONFLICT_PREFIXES):
                to_delete.append(name)
        for name in to_delete:
            sys.modules.pop(name, None)
    _ACTIVE_ROOT = root


def pytest_pycollect_makemodule(module_path, path=None, parent=None):
    target = Path(str(module_path))
    root = _detect_project(target)
    if root is not None:
        _set_import_root(root)
    return None


def pytest_runtest_setup(item):
    root = _detect_project(Path(str(item.path)))
    if root is not None:
        _set_import_root(root, purge_modules=False)

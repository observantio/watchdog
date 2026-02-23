import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent

PROJECT_ROOTS = {
    "server": REPO_ROOT / "server",
    "benotified": REPO_ROOT / "BeNotified",
    "gateway": REPO_ROOT / "gateway-auth-service",
    "becertain": REPO_ROOT / "BeCertain",
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
    if f"{os.sep}server{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["server"]
    if f"{os.sep}BeNotified{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["benotified"]
    if f"{os.sep}gateway-auth-service{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["gateway"]
    if f"{os.sep}BeCertain{os.sep}tests{os.sep}" in p:
        return PROJECT_ROOTS["becertain"]
    return None


def _set_import_root(root: Path, purge_modules: bool = True) -> None:
    global _ACTIVE_ROOT
    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)

    if purge_modules:
        # Force module re-resolution from the currently active project root.
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
        _set_import_root(root, purge_modules=root != _ACTIVE_ROOT)

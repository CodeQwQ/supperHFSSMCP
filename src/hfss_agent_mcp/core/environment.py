from __future__ import annotations

import platform
import shutil
import sys
from importlib import util
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from hfss_agent_mcp.config import ServerConfig


def collect_environment(config: ServerConfig, backend_health: dict[str, Any]) -> dict[str, Any]:
    output_root = config.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    aedt_info = _detect_aedt(config.aedt_executable)
    package_info = {
        "mcp": _package_status("mcp"),
        "pydantic": _package_status("pydantic"),
        "pyaedt": _pyaedt_status(),
    }
    warnings = _build_warnings(aedt_info, package_info)
    return {
        "python": {
            "version": platform.python_version(),
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
            "micro": sys.version_info.micro,
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "packages": package_info,
        "aedt": aedt_info,
        "backend": {
            "configured_backend": config.backend,
            "active_backend": backend_health.get("backend"),
            "connected": backend_health.get("connected", False),
            "hfss_available": backend_health.get("hfss_available"),
            "backend_health": backend_health,
        },
        "server": {
            "name": config.name,
            "transport": config.transport,
            "host": config.host,
            "port": config.port,
            "log_level": config.log_level,
        },
        "output": {
            "root": str(output_root),
            "exists": output_root.exists(),
            "writable": _is_writable(output_root),
        },
        "warnings": warnings,
        "ready": not warnings,
    }


def _package_status(package_name: str) -> dict[str, Any]:
    spec = _find_spec(package_name)
    installed = spec is not None
    package_version: str | None = None
    if installed:
        try:
            package_version = version(package_name)
        except PackageNotFoundError:
            package_version = None
    return {"available": installed, "version": package_version}


def _pyaedt_status() -> dict[str, Any]:
    ansys_spec = _find_spec("ansys.aedt.core")
    legacy_spec = _find_spec("pyaedt")
    ansys_version = _metadata_version("ansys-aedt-core")
    legacy_version = _metadata_version("pyaedt")
    return {
        "available": ansys_spec is not None or legacy_spec is not None,
        "ansys_aedt_core": {
            "available": ansys_spec is not None,
            "version": ansys_version,
        },
        "legacy_pyaedt": {
            "available": legacy_spec is not None,
            "version": legacy_version,
        },
        "version": ansys_version or legacy_version,
    }


def _metadata_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _find_spec(module_name: str) -> Any:
    try:
        return util.find_spec(module_name)
    except (ImportError, ModuleNotFoundError):
        return None


def _detect_aedt(configured_path: Path | None) -> dict[str, Any]:
    candidates: list[tuple[str, Path]] = []
    if configured_path is not None:
        candidates.append(("configured", configured_path))
    which_path = shutil.which("ansysedt.exe") or shutil.which("ansysedt")
    if which_path:
        candidates.append(("PATH", Path(which_path)))

    for source, candidate in candidates:
        resolved = candidate.expanduser()
        if resolved.exists():
            return {
                "available": True,
                "executable": str(resolved),
                "source": source,
                "configured_executable": str(configured_path) if configured_path else None,
            }

    return {
        "available": False,
        "executable": None,
        "source": None,
        "configured_executable": str(configured_path) if configured_path else None,
    }


def _is_writable(path: Path) -> bool:
    probe = path / ".hfss_agent_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _build_warnings(aedt_info: dict[str, Any], package_info: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not aedt_info["available"]:
        warnings.append(
            "AEDT executable was not found. Set HFSS_AGENT_AEDT_EXECUTABLE or add ansysedt.exe to PATH."
        )
    if not package_info["pyaedt"]["available"]:
        warnings.append(
            "PyAEDT is not importable. Install ansys-aedt-core before using the pyaedt backend."
        )
    return warnings

"""Portable Adoptium Temurin Java 17 JRE discovery and automatic downloader."""

from __future__ import annotations

import os
import platform
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .config import find_java17, get_data_dir

ADOPTIUM_JRE17_URL = (
    "https://api.adoptium.net/v3/binary/latest/17/ga/{os_name}/x64/jre/hotspot/normal/eclipse"
)


def _portable_java_candidates(runtime_dir: Path) -> list[Path]:
    exe_name = "java.exe" if platform.system() == "Windows" else "java"
    if not runtime_dir.is_dir():
        return []
    return sorted(runtime_dir.glob(f"*/bin/{exe_name}")) + sorted(runtime_dir.glob(f"bin/{exe_name}"))


def find_portable_java17(runtime_dir: Path | None = None) -> str | None:
    rdir = runtime_dir or (get_data_dir() / "runtime")
    for cand in _portable_java_candidates(rdir):
        if cand.is_file():
            return str(cand)
    return None


def ensure_java17(
    configured_path: str = "",
    on_status: Callable[[int, str], None] | None = None,
) -> str:
    """Returns a valid Java 17 binary path, downloading portable Temurin JRE 17 if needed."""
    if configured_path and Path(configured_path).is_file():
        return configured_path

    portable = find_portable_java17()
    if portable:
        return portable

    system_java = find_java17()
    if system_java and Path(system_java).is_file():
        return system_java

    sys_name = platform.system().lower()
    if sys_name == "windows":
        os_key = "windows"
        archive_ext = ".zip"
    elif sys_name == "darwin":
        os_key = "mac"
        archive_ext = ".tar.gz"
    else:
        os_key = "linux"
        archive_ext = ".tar.gz"

    runtime_dir = get_data_dir() / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    archive_path = runtime_dir / f"temurin-jre17{archive_ext}"
    url = ADOPTIUM_JRE17_URL.format(os_name=os_key)

    if on_status:
        on_status(5, "Java 17 не найдена — скачиваю портативную Temurin JRE 17...")

    req = urllib.request.Request(url, headers={"User-Agent": "RtCoD-Launcher/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        archive_path.write_bytes(resp.read())

    if on_status:
        on_status(10, "Распаковываю портативную Java 17...")

    if archive_ext == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(runtime_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(runtime_dir)
    archive_path.unlink(missing_ok=True)

    found = find_portable_java17(runtime_dir)
    if not found:
        raise RuntimeError("Не удалось найти java после распаковки Temurin JRE 17.")

    if os_key != "windows":
        p = Path(found)
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return found

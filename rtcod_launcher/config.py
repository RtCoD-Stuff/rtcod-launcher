"""Cross-platform paths, persistent launcher settings, and Java 17 discovery."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


def get_data_dir() -> Path:
    """Returns isolated RtCoD game directory without touching default .minecraft."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "RtCoD"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "RtCoD"
    return Path.home() / ".local" / "share" / "RtCoD"


@dataclass
class LauncherConfig:
    username: str = "Player"
    ram_mb: int = 6144
    java_path: str = ""
    manifest_url: str = ""
    server_host: str = ""
    server_port: int = 25565
    auto_connect: bool = False

    @property
    def game_dir(self) -> Path:
        return get_data_dir() / "minecraft"

    @property
    def mods_dir(self) -> Path:
        return self.game_dir / "mods"


def config_file_path() -> Path:
    return get_data_dir() / "launcher_config.json"


def load_config() -> LauncherConfig:
    path = config_file_path()
    if not path.is_file():
        cfg = LauncherConfig()
        cfg.java_path = find_java17() or ""
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = LauncherConfig(
            username=str(raw.get("username", "Player")),
            ram_mb=int(raw.get("ram_mb", 6144)),
            java_path=str(raw.get("java_path", "")),
            manifest_url=str(raw.get("manifest_url", "")),
            server_host=str(raw.get("server_host", "")),
            server_port=int(raw.get("server_port", 25565)),
            auto_connect=bool(raw.get("auto_connect", False)),
        )
        if not cfg.java_path:
            cfg.java_path = find_java17() or ""
        return cfg
    except Exception:
        return LauncherConfig(java_path=find_java17() or "")


def save_config(cfg: LauncherConfig) -> Path:
    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _java_major_version(java_bin: str) -> int | None:
    try:
        proc = subprocess.run(
            [java_bin, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        for line in proc.stdout.splitlines():
            if "version" in line.lower():
                quote_parts = line.split('"')
                if len(quote_parts) >= 2:
                    ver = quote_parts[1]
                    major = ver.split(".")[0]
                    return int(major)
    except Exception:
        return None
    return None


def find_java17() -> str | None:
    """Finds a Java 17 executable (required for Forge 1.20.1)."""
    candidates: list[str] = []
    for env_key in ("JAVA_HOME",):
        val = os.environ.get(env_key)
        if val:
            candidates.append(str(Path(val) / "bin" / "java"))

    which_java = shutil.which("java")
    if which_java:
        candidates.append(which_java)

    for common in (
        "/usr/lib/jvm/java-17-openjdk/bin/java",
        "/usr/lib/jvm/java-17-temurin/bin/java",
        "/usr/lib/jvm/default/bin/java",
    ):
        if Path(common).is_file():
            candidates.append(common)

    seen: set[str] = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        if _java_major_version(cand) == 17:
            return cand
    return which_java

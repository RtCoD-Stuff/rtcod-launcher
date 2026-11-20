"""Pure-Python Minecraft 1.20.1 + Forge 47.3.0 installer and launcher engine (Beta v0.5)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

MC_VERSION = "1.20.1"
FORGE_VERSION = "47.4.28"
FORGE_VERSION_ID = f"{MC_VERSION}-forge-{FORGE_VERSION}"

MOJANG_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FORGE_INSTALLER_URL = (
    f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
    f"{MC_VERSION}-{FORGE_VERSION}/forge-{MC_VERSION}-{FORGE_VERSION}-installer.jar"
)
RESOURCES_BASE_URL = "https://resources.download.minecraft.net"


def current_os_name() -> str:
    sys_name = platform.system().lower()
    if sys_name == "windows":
        return "windows"
    if sys_name == "darwin":
        return "osx"
    return "linux"


def offline_uuid(username: str) -> str:
    """Computes standard Minecraft OfflinePlayer UUID (UUIDv3)."""
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{username}"))


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "RtCoD-Launcher/0.5"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(url: str, dest: Path, expected_sha1: str = "") -> None:
    if dest.is_file() and (not expected_sha1 or _sha1_file(dest) == expected_sha1):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "RtCoD-Launcher/0.5"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())
    if expected_sha1 and _sha1_file(dest) != expected_sha1:
        dest.unlink(missing_ok=True)
        raise ValueError(f"SHA-1 mismatch for {dest.name}")


def _rules_allow(rules: list[dict] | None, os_name: str) -> bool:
    if not rules:
        return True
    allowed = False
    for rule in rules:
        action = rule.get("action", "allow")
        os_cond = rule.get("os")
        features = rule.get("features")
        if features:
            continue
        matched = True
        if os_cond and os_cond.get("name") and os_cond["name"] != os_name:
            matched = False
        if matched:
            allowed = action == "allow"
    return allowed


def _maven_to_path(coord: str) -> Path:
    parts = coord.split(":")
    group = parts[0].replace(".", "/")
    artifact = parts[1]
    version = parts[2]
    ext = "jar"
    classifier = ""
    if "@" in version:
        version, ext = version.split("@", 1)
    if len(parts) >= 4:
        classifier = parts[3]
        if "@" in classifier:
            classifier, ext = classifier.split("@", 1)
    filename = f"{artifact}-{version}-{classifier}.{ext}" if classifier else f"{artifact}-{version}.{ext}"
    return Path(group) / artifact / version / filename


def ensure_vanilla_installed(
    game_dir: Path,
    on_status: Callable[[int, str], None] | None = None,
) -> Path:
    """Downloads Minecraft 1.20.1 client, libraries, natives, and assets if missing."""
    os_name = current_os_name()
    ver_dir = game_dir / "versions" / MC_VERSION
    ver_json_path = ver_dir / f"{MC_VERSION}.json"
    ver_jar_path = ver_dir / f"{MC_VERSION}.jar"
    libs_dir = game_dir / "libraries"
    natives_dir = ver_dir / "natives"

    def emit(pct: int, msg: str) -> None:
        if on_status:
            on_status(pct, msg)

    if not ver_json_path.is_file():
        emit(5, "Получаю манифест Minecraft 1.20.1...")
        manifest = _fetch_json(MOJANG_MANIFEST_URL)
        entry = next((v for v in manifest["versions"] if v["id"] == MC_VERSION), None)
        if not entry:
            raise RuntimeError(f"Версия {MC_VERSION} не найдена в манифесте Mojang")
        ver_data = _fetch_json(entry["url"])
        ver_dir.mkdir(parents=True, exist_ok=True)
        ver_json_path.write_text(json.dumps(ver_data, indent=2), encoding="utf-8")
    else:
        ver_data = json.loads(ver_json_path.read_text(encoding="utf-8"))

    # 1. Client jar
    client_dl = ver_data["downloads"]["client"]
    emit(12, "Проверяю клиент Minecraft 1.20.1...")
    _download_file(client_dl["url"], ver_jar_path, client_dl.get("sha1", ""))

    # 2. Libraries + natives
    dl_tasks: list[tuple[str, Path, str]] = []
    native_jars: list[Path] = []
    for lib in ver_data.get("libraries", []):
        if not _rules_allow(lib.get("rules"), os_name):
            continue
        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact and artifact.get("url") and artifact.get("path"):
            dl_tasks.append((artifact["url"], libs_dir / artifact["path"], artifact.get("sha1", "")))
        classifiers = downloads.get("classifiers", {})
        native_key = lib.get("natives", {}).get(os_name)
        if native_key and native_key in classifiers:
            nat = classifiers[native_key]
            dest = libs_dir / nat["path"]
            dl_tasks.append((nat["url"], dest, nat.get("sha1", "")))
            native_jars.append(dest)

    emit(20, f"Проверяю библиотеки ({len(dl_tasks)} шт.)...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_download_file, u, p, s) for u, p, s in dl_tasks]
        for idx, fut in enumerate(as_completed(futs), start=1):
            fut.result()
            if idx % 15 == 0 or idx == len(futs):
                pct = 20 + int((idx / max(1, len(futs))) * 25)
                emit(pct, f"Библиотеки: {idx}/{len(futs)}")

    if native_jars:
        natives_dir.mkdir(parents=True, exist_ok=True)
        for jar in native_jars:
            if jar.is_file():
                with zipfile.ZipFile(jar, "r") as zf:
                    for member in zf.namelist():
                        if member.startswith("META-INF/") or member.endswith("/"):
                            continue
                        zf.extract(member, natives_dir)

    # 3. Assets
    asset_info = ver_data["assetIndex"]
    indexes_dir = game_dir / "assets" / "indexes"
    objects_dir = game_dir / "assets" / "objects"
    index_path = indexes_dir / f"{asset_info['id']}.json"
    emit(48, "Проверяю индекс ассетов (звуки/языки)...")
    _download_file(asset_info["url"], index_path, asset_info.get("sha1", ""))

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    objects = index_data.get("objects", {})
    missing_assets: list[tuple[str, Path, str]] = []
    for obj in objects.values():
        sha1 = obj["hash"]
        dest = objects_dir / sha1[:2] / sha1
        if not dest.is_file():
            missing_assets.append((f"{RESOURCES_BASE_URL}/{sha1[:2]}/{sha1}", dest, sha1))

    if missing_assets:
        emit(50, f"Загрузка ассетов ({len(missing_assets)} файлов)...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_download_file, u, p, s) for u, p, s in missing_assets]
            for idx, fut in enumerate(as_completed(futs), start=1):
                fut.result()
                if idx % 50 == 0 or idx == len(futs):
                    pct = 50 + int((idx / max(1, len(futs))) * 25)
                    emit(pct, f"Ассеты: {idx}/{len(futs)}")

    return ver_json_path


def ensure_forge_installed(
    game_dir: Path,
    java_bin: str,
    on_status: Callable[[int, str], None] | None = None,
) -> Path:
    """Installs Forge 1.20.1-47.3.0 headless into game_dir if not yet present."""
    forge_json = game_dir / "versions" / FORGE_VERSION_ID / f"{FORGE_VERSION_ID}.json"
    if forge_json.is_file():
        return forge_json

    if on_status:
        on_status(78, f"Скачиваю инсталлер Forge {FORGE_VERSION}...")

    profiles_path = game_dir / "launcher_profiles.json"
    if not profiles_path.is_file():
        profiles_path.parent.mkdir(parents=True, exist_ok=True)
        profiles_path.write_text(json.dumps({"profiles": {}}, indent=2), encoding="utf-8")

    installer_jar = game_dir / "cache" / f"forge-{MC_VERSION}-{FORGE_VERSION}-installer.jar"
    _download_file(FORGE_INSTALLER_URL, installer_jar)

    if on_status:
        on_status(85, f"Устанавливаю Forge {FORGE_VERSION} (1–2 мин при первом запуске)...")

    proc = subprocess.run(
        [java_bin, "-jar", str(installer_jar), "--installClient", str(game_dir)],
        cwd=game_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0 or not forge_json.is_file():
        tail = "\n".join(proc.stdout.splitlines()[-12:])
        raise RuntimeError(f"Ошибка установки Forge (код {proc.returncode}):\n{tail}")

    return forge_json


def _collect_classpath(game_dir: Path, vanilla_data: dict, forge_data: dict, os_name: str) -> str:
    libs_dir = game_dir / "libraries"
    entries: list[str] = []
    seen: set[str] = set()

    def add_lib_list(libs: list[dict]) -> None:
        for lib in libs:
            if not _rules_allow(lib.get("rules"), os_name):
                continue
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact and artifact.get("path"):
                p = libs_dir / artifact["path"]
            elif lib.get("name"):
                p = libs_dir / _maven_to_path(lib["name"])
            else:
                continue
            s = str(p)
            if p.is_file() and s not in seen:
                seen.add(s)
                entries.append(s)

    add_lib_list(forge_data.get("libraries", []))
    add_lib_list(vanilla_data.get("libraries", []))
    # Do NOT append vanilla versions/1.20.1/1.20.1.jar to Forge's classpath:
    # BootstrapLauncher loads the SRG-patched Minecraft jar itself, and adding 1.20.1.jar
    # creates a duplicate automatic module `_1._20._1` causing ResolutionException.
    return os.pathsep.join(entries)


def _expand_args(raw_args: list, variables: dict[str, str], os_name: str) -> list[str]:
    result: list[str] = []
    for item in raw_args:
        if isinstance(item, str):
            val = item
            for k, v in variables.items():
                val = val.replace(f"${{{k}}}", v)
            result.append(val)
        elif isinstance(item, dict):
            if not _rules_allow(item.get("rules"), os_name):
                continue
            vals = item.get("value", [])
            if isinstance(vals, str):
                vals = [vals]
            for s in vals:
                val = s
                for k, v in variables.items():
                    val = val.replace(f"${{{k}}}", v)
                result.append(val)
    return result


def build_launch_command(
    game_dir: Path,
    java_bin: str,
    username: str,
    ram_mb: int,
    server_host: str = "",
    server_port: int = 25565,
) -> list[str]:
    """Constructs the full JVM launch command for Minecraft 1.20.1 + Forge 47.3.0."""
    os_name = current_os_name()
    vanilla_data = json.loads((game_dir / "versions" / MC_VERSION / f"{MC_VERSION}.json").read_text(encoding="utf-8"))
    forge_data = json.loads(
        (game_dir / "versions" / FORGE_VERSION_ID / f"{FORGE_VERSION_ID}.json").read_text(encoding="utf-8")
    )

    classpath = _collect_classpath(game_dir, vanilla_data, forge_data, os_name)
    natives_dir = game_dir / "versions" / MC_VERSION / "natives"
    natives_dir.mkdir(parents=True, exist_ok=True)

    variables = {
        "auth_player_name": username,
        "version_name": FORGE_VERSION_ID,
        "game_directory": str(game_dir),
        "assets_root": str(game_dir / "assets"),
        "assets_index_name": vanilla_data["assetIndex"]["id"],
        "auth_uuid": offline_uuid(username),
        "auth_access_token": "0",
        "clientid": "0",
        "auth_xuid": "0",
        "user_type": "legacy",
        "version_type": "RtCoD",
        "natives_directory": str(natives_dir),
        "launcher_name": "RtCoD-Launcher",
        "launcher_version": "0.5.0-beta",
        "classpath": classpath,
        "library_directory": str(game_dir / "libraries"),
        "classpath_separator": os.pathsep,
    }

    jvm_args = [
        f"-Xms{min(2048, ram_mb)}M",
        f"-Xmx{ram_mb}M",
        "-XX:+UseG1GC",
    ]
    jvm_args.extend(_expand_args(vanilla_data.get("arguments", {}).get("jvm", []), variables, os_name))
    jvm_args.extend(_expand_args(forge_data.get("arguments", {}).get("jvm", []), variables, os_name))

    main_class = forge_data.get("mainClass") or vanilla_data["mainClass"]
    game_args = _expand_args(vanilla_data.get("arguments", {}).get("game", []), variables, os_name)
    game_args.extend(_expand_args(forge_data.get("arguments", {}).get("game", []), variables, os_name))

    if server_host.strip():
        game_args.extend(["--quickPlayMultiplayer", f"{server_host.strip()}:{server_port}"])

    return [java_bin, *jvm_args, main_class, *game_args]

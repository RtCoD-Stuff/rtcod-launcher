"""Modpack manifest builder and SHA-256 verifier/synchronizer."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ModEntry:
    filename: str
    sha256: str
    size: int
    url: str = ""


@dataclass(frozen=True)
class SyncReport:
    downloaded: int
    verified: int
    removed: int
    errors: list[str]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_manifest(
    mods_dir: Path,
    pack_version: str = "1.0.0",
    mc_version: str = "1.20.1",
    forge_version: str = "47.4.28",
    base_download_url: str = "",
) -> dict:
    """Scans a local mods/ directory and generates a JSON manifest with SHA-256 hashes."""
    mods: list[dict] = []
    base = base_download_url.rstrip("/")
    for p in sorted(mods_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".jar", ".zip"):
            continue
        url = f"{base}/{p.name}" if base else ""
        mods.append(
            {
                "filename": p.name,
                "sha256": sha256_file(p),
                "size": p.stat().st_size,
                "url": url,
            }
        )
    return {
        "pack_name": "Return to Castle of Dark",
        "pack_version": pack_version,
        "minecraft_version": mc_version,
        "forge_version": forge_version,
        "mods_count": len(mods),
        "mods": mods,
    }


def load_manifest_source(source: str) -> dict:
    """Loads manifest JSON from either an HTTP(S) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "RtCoD-Launcher/0.1"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _download_mod(entry: ModEntry, dest: Path) -> None:
    if not entry.url:
        raise ValueError(f"Нет URL для скачивания {entry.filename}")
    if entry.url.startswith("file://"):
        src = Path(entry.url.removeprefix("file://"))
        dest.write_bytes(src.read_bytes())
    else:
        req = urllib.request.Request(entry.url, headers={"User-Agent": "RtCoD-Launcher/0.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
    actual = sha256_file(dest)
    if entry.sha256 and actual != entry.sha256:
        dest.unlink(missing_ok=True)
        raise ValueError(f"Несовпадение SHA-256 для {entry.filename}")


def sync_mods(
    manifest: dict,
    target_mods_dir: Path,
    remove_extra: bool = True,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> SyncReport:
    """Synchronizes target_mods_dir with manifest: verifies hashes, downloads missing, removes extras."""
    target_mods_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        ModEntry(
            filename=m["filename"],
            sha256=m.get("sha256", ""),
            size=int(m.get("size", 0)),
            url=m.get("url", ""),
        )
        for m in manifest.get("mods", [])
    ]
    expected_names = {e.filename for e in entries}

    removed = 0
    if remove_extra:
        for existing in list(target_mods_dir.iterdir()):
            if existing.is_file() and existing.suffix.lower() in (".jar", ".zip"):
                if existing.name not in expected_names:
                    existing.unlink()
                    removed += 1

    to_download: list[ModEntry] = []
    verified = 0
    for entry in entries:
        dest = target_mods_dir / entry.filename
        if dest.is_file() and (not entry.sha256 or sha256_file(dest) == entry.sha256):
            verified += 1
        else:
            to_download.append(entry)

    total = max(1, len(entries))
    done = verified
    if on_progress:
        on_progress(done, total, f"Проверено модов: {verified}/{len(entries)}")

    downloaded = 0
    errors: list[str] = []
    if to_download:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_download_mod, e, target_mods_dir / e.filename): e for e in to_download}
            for fut in as_completed(futures):
                entry = futures[fut]
                try:
                    fut.result()
                    downloaded += 1
                    done += 1
                    if on_progress:
                        on_progress(done, total, f"Загружен: {entry.filename}")
                except Exception as exc:
                    errors.append(f"{entry.filename}: {exc}")

    return SyncReport(downloaded=downloaded, verified=verified, removed=removed, errors=errors)

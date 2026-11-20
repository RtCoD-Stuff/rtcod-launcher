#!/usr/bin/env python3
"""Admin helper: generates manifest.json with SHA-256 hashes from your Minecraft mods/ folder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rtcod_launcher.manifest import generate_manifest

DEFAULT_MODS_DIR = Path(
    "/home/denegen/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/1.20.1/minecraft/mods"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Генератор manifest.json для RtCoD Launcher")
    parser.add_argument("--mods-dir", type=Path, default=DEFAULT_MODS_DIR, help="Папка с модами сборки")
    parser.add_argument("--version", default="1.0.0", help="Версия сборки")
    parser.add_argument(
        "--base-url",
        default="",
        help="Базовый URL для скачивания файлов (например: https://github.com/RtCoD-Server/rtcod-launcher/releases/download/v1.0.0 или file:///path/to/mods)",
    )
    parser.add_argument("--out", type=Path, default=Path("manifest.json"), help="Куда сохранить manifest.json")
    args = parser.parse_args()

    manifest = generate_manifest(
        mods_dir=args.mods_dir,
        pack_version=args.version,
        base_download_url=args.base_url,
    )
    args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✔ Создан {args.out} ({manifest['mods_count']} модов, версия {args.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

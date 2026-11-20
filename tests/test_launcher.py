"""Unit tests for RtCoD Launcher Alpha v0.1."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rtcod_launcher.engine import (
    FORGE_VERSION_ID,
    MC_VERSION,
    _maven_to_path,
    _rules_allow,
    build_launch_command,
    offline_uuid,
)
from rtcod_launcher.manifest import generate_manifest, sha256_file, sync_mods


class TestRtCoDLauncher(unittest.TestCase):
    def test_manifest_generation_and_sync_with_sha256_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_mods = tmp_path / "server_mods"
            dst_mods = tmp_path / "client_mods"
            src_mods.mkdir()
            dst_mods.mkdir()

            (src_mods / "RtCoD_Clans-1.0.0.jar").write_bytes(b"clans-jar-bytes")
            (src_mods / "RtCod_races-1.2.0.jar").write_bytes(b"races-jar-bytes")

            # Extra cheat/unknown mod and corrupted file on client
            (dst_mods / "xray_cheat.jar").write_bytes(b"bad-mod")
            (dst_mods / "RtCoD_Clans-1.0.0.jar").write_bytes(b"corrupted-bytes")

            manifest = generate_manifest(
                src_mods,
                pack_version="1.0.0",
                base_download_url=f"file://{src_mods}",
            )
            self.assertEqual(manifest["mods_count"], 2)

            report = sync_mods(manifest, dst_mods, remove_extra=True)
            self.assertEqual(report.errors, [])
            self.assertEqual(report.removed, 1)
            self.assertEqual(report.downloaded, 2)
            self.assertFalse((dst_mods / "xray_cheat.jar").exists())
            self.assertEqual(
                sha256_file(dst_mods / "RtCoD_Clans-1.0.0.jar"),
                sha256_file(src_mods / "RtCoD_Clans-1.0.0.jar"),
            )

            # Second sync should verify both without redownloading
            report2 = sync_mods(manifest, dst_mods, remove_extra=True)
            self.assertEqual(report2.verified, 2)
            self.assertEqual(report2.downloaded, 0)
            self.assertEqual(report2.removed, 0)

    def test_engine_helpers_and_launch_command(self) -> None:
        self.assertEqual(len(offline_uuid("Denegen")), 36)
        self.assertEqual(
            str(_maven_to_path("net.minecraftforge:fmlloader:1.20.1-47.3.0")),
            "net/minecraftforge/fmlloader/1.20.1-47.3.0/fmlloader-1.20.1-47.3.0.jar",
        )
        self.assertTrue(_rules_allow([{"action": "allow", "os": {"name": "linux"}}], "linux"))
        self.assertFalse(_rules_allow([{"action": "allow", "os": {"name": "windows"}}], "linux"))

        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            v_dir = game_dir / "versions" / MC_VERSION
            f_dir = game_dir / "versions" / FORGE_VERSION_ID
            lib_file = game_dir / "libraries" / "com" / "example" / "lib" / "1.0" / "lib-1.0.jar"
            v_dir.mkdir(parents=True)
            f_dir.mkdir(parents=True)
            lib_file.parent.mkdir(parents=True)
            lib_file.write_bytes(b"jar")
            (v_dir / f"{MC_VERSION}.jar").write_bytes(b"client")

            (v_dir / f"{MC_VERSION}.json").write_text(
                json.dumps(
                    {
                        "id": MC_VERSION,
                        "mainClass": "net.minecraft.client.main.Main",
                        "assetIndex": {"id": "5"},
                        "libraries": [
                            {"downloads": {"artifact": {"path": "com/example/lib/1.0/lib-1.0.jar"}}}
                        ],
                        "arguments": {
                            "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
                            "game": ["--username", "${auth_player_name}", "--gameDir", "${game_directory}"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (f_dir / f"{FORGE_VERSION_ID}.json").write_text(
                json.dumps(
                    {
                        "id": FORGE_VERSION_ID,
                        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
                        "libraries": [],
                        "arguments": {
                            "jvm": ["-DlibraryDirectory=${library_directory}"],
                            "game": ["--launchTarget", "forgeclient"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            cmd = build_launch_command(
                game_dir=game_dir,
                java_bin="/usr/bin/java",
                username="Denegen",
                ram_mb=6144,
                server_host="play.rtcod.example",
                server_port=25565,
            )
            self.assertEqual(cmd[0], "/usr/bin/java")
            self.assertIn("-Xmx6144M", cmd)
            self.assertIn("cpw.mods.bootstraplauncher.BootstrapLauncher", cmd)
            self.assertIn("Denegen", cmd)
            self.assertIn("--quickPlayMultiplayer", cmd)
            self.assertIn("play.rtcod.example:25565", cmd)


if __name__ == "__main__":
    unittest.main()

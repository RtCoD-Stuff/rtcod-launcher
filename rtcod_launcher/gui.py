"""Dark medieval fantasy GUI for RtCoD Launcher (Beta v0.5)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import LauncherConfig, load_config, save_config
from .defaults import DEFAULT_MANIFEST_URL, DISCORD_URL, TELEGRAM_URL
from .engine import build_launch_command, ensure_forge_installed, ensure_vanilla_installed
from .java_runtime import ensure_java17
from .manifest import load_manifest_source, sync_mods

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"  # type: ignore[attr-defined]
else:
    ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

LAUNCHER_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #060508;
    color: #ece6db;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
}
QFrame#Card {
    background-color: rgba(13, 12, 17, 230);
    border: 1px solid rgba(217, 167, 86, 120);
    border-radius: 6px;
}
QLabel#Title {
    font-size: 26px;
    font-weight: 800;
    color: #f4ce82;
    letter-spacing: 1px;
}
QLabel#Subtitle {
    font-size: 12px;
    color: #b7afa4;
    letter-spacing: 1px;
}
QLabel#Section {
    font-size: 11px;
    font-weight: 700;
    color: #d9a756;
    text-transform: uppercase;
}
QLineEdit, QPlainTextEdit {
    background-color: #09080c;
    border: 1px solid rgba(217, 167, 86, 85);
    border-radius: 4px;
    padding: 8px 10px;
    color: #f5efe4;
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #f4ce82;
}
QPushButton {
    background-color: #211e26;
    border: 1px solid rgba(217, 167, 86, 110);
    border-radius: 4px;
    padding: 8px 14px;
    color: #f0e8dc;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #2d2833;
    border-color: #f4ce82;
}
QPushButton#PlayBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #c9853b, stop:1 #6e3718);
    border: 1px solid #f4ce82;
    color: #fff6e6;
    font-size: 16px;
    padding: 13px 34px;
}
QPushButton#PlayBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #df9a4b, stop:1 #87451e);
}
QPushButton#PlayBtn:disabled {
    background: #2a2420;
    color: #887f76;
    border-color: #5a4d3f;
}
QProgressBar {
    background-color: #0b0a0f;
    border: 1px solid rgba(217, 167, 86, 85);
    border-radius: 4px;
    text-align: center;
    color: #f4ce82;
    height: 22px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8f4719, stop:1 #e2b15a);
}
QSlider::groove:horizontal {
    height: 6px;
    background: #1a1720;
    border: 1px solid rgba(217, 167, 86, 65);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #f4ce82;
    border: 1px solid #8f4719;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
"""


class _HeroCanvas(QWidget):
    """Paints dark fantasy hero banner with smooth dark vignette."""

    def __init__(self) -> None:
        super().__init__()
        banner = ASSETS_DIR / "hero-banner.jpg"
        self._pixmap = QPixmap(str(banner)) if banner.is_file() else QPixmap()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#060508"))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = self.width() - scaled.width()
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(6, 5, 8, 248))
        grad.setColorAt(0.45, QColor(6, 5, 8, 200))
        grad.setColorAt(1.0, QColor(6, 5, 8, 95))
        painter.fillRect(self.rect(), grad)
        super().paintEvent(event)


class _PlayWorker(QThread):
    status = Signal(int, str)
    finished_launch = Signal(bool, str, object)

    def __init__(self, cfg: LauncherConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def run(self) -> None:
        try:
            java_bin = ensure_java17(self.cfg.java_path, on_status=self.status.emit)

            # 1. Optional mod sync from manifest
            manifest_src = self.cfg.manifest_url.strip()
            if manifest_src:
                self.status.emit(12, "Проверяю обновления сборки модов...")
                manifest = load_manifest_source(manifest_src)
                report = sync_mods(
                    manifest,
                    self.cfg.mods_dir,
                    remove_extra=True,
                    on_progress=lambda d, t, m: self.status.emit(
                        12 + int((d / max(1, t)) * 12),
                        m,
                    ),
                )
                if report.errors:
                    self.finished_launch.emit(
                        False, "Ошибки загрузки модов:\n" + "\n".join(report.errors[:5]), None
                    )
                    return
                self.status.emit(
                    24,
                    f"Моды готовы (проверено: {report.verified}, загружено: {report.downloaded}, удалено: {report.removed}).",
                )

            # 2. Vanilla Minecraft 1.20.1
            ensure_vanilla_installed(self.cfg.game_dir, on_status=self.status.emit)

            # 3. Forge 47.4.28
            ensure_forge_installed(self.cfg.game_dir, java_bin, on_status=self.status.emit)

            # 4. Build JVM command and launch
            self.status.emit(95, "Запускаю Return to Castle of Dark...")
            cmd = build_launch_command(
                game_dir=self.cfg.game_dir,
                java_bin=java_bin,
                username=self.cfg.username,
                ram_mb=self.cfg.ram_mb,
                server_host=self.cfg.server_host if self.cfg.auto_connect else "",
                server_port=self.cfg.server_port,
            )
            proc = subprocess.Popen(cmd, cwd=self.cfg.game_dir)
            self.status.emit(100, "Игра запущена!")
            self.finished_launch.emit(True, "Minecraft Forge 1.20.1 запущен.", proc)
        except Exception as exc:
            self.finished_launch.emit(False, str(exc), None)


class _SettingsDialog(QDialog):
    def __init__(self, cfg: LauncherConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки RtCoD Launcher")
        self.resize(520, 310)
        self.cfg = cfg

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl_man = QLabel("URL ИЛИ ПУТЬ К MANIFEST.JSON СБОРКИ")
        lbl_man.setObjectName("Section")
        self.manifest_edit = QLineEdit(cfg.manifest_url)
        self.manifest_edit.setPlaceholderText(DEFAULT_MANIFEST_URL)
        layout.addWidget(lbl_man)
        layout.addWidget(self.manifest_edit)

        lbl_java = QLabel("ПУТЬ К JAVA 17")
        lbl_java.setObjectName("Section")
        java_row = QHBoxLayout()
        self.java_edit = QLineEdit(cfg.java_path)
        btn_java = QPushButton("Обзор...")
        btn_java.clicked.connect(self._browse_java)
        java_row.addWidget(self.java_edit, stretch=1)
        java_row.addWidget(btn_java)
        layout.addWidget(lbl_java)
        layout.addLayout(java_row)

        lbl_srv = QLabel("IP СЕРВЕРА (ДЛЯ АВТОВХОДА)")
        lbl_srv.setObjectName("Section")
        srv_row = QHBoxLayout()
        self.host_edit = QLineEdit(cfg.server_host)
        self.host_edit.setPlaceholderText("play.rtcod.example (необязательно)")
        self.port_edit = QLineEdit(str(cfg.server_port))
        self.port_edit.setFixedWidth(80)
        srv_row.addWidget(self.host_edit, stretch=1)
        srv_row.addWidget(self.port_edit)
        layout.addWidget(lbl_srv)
        layout.addLayout(srv_row)

        self.chk_autoconnect = QCheckBox("Подключаться к серверу сразу при запуске игры")
        self.chk_autoconnect.setChecked(cfg.auto_connect)
        layout.addWidget(self.chk_autoconnect)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_java(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Выбери java (Java 17)", self.java_edit.text())
        if chosen:
            self.java_edit.setText(chosen)

    def apply_to_config(self) -> None:
        self.cfg.manifest_url = self.manifest_edit.text().strip()
        self.cfg.java_path = self.java_edit.text().strip()
        self.cfg.server_host = self.host_edit.text().strip()
        try:
            self.cfg.server_port = int(self.port_edit.text().strip() or "25565")
        except ValueError:
            self.cfg.server_port = 25565
        self.cfg.auto_connect = self.chk_autoconnect.isChecked()


class RtCoDLauncherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg: LauncherConfig = load_config()
        self._game_proc: subprocess.Popen | None = None
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(2000)
        self._proc_timer.timeout.connect(self._poll_game_process)
        self.setWindowTitle(f"Return to Castle of Dark — Launcher v{__version__}")
        self.resize(900, 530)
        self._build_ui()

    def _build_ui(self) -> None:
        root = _HeroCanvas()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 24, 28, 22)
        outer.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("RETURN TO CASTLE OF DARK")
        lbl_title.setObjectName("Title")
        lbl_sub = QLabel(f"FORGE 1.20.1 • DARK FANTASY RPG • {__version__.upper()}")
        lbl_sub.setObjectName("Subtitle")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()

        self.btn_discord = QPushButton("Discord")
        self.btn_discord.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DISCORD_URL)))

        self.btn_tg = QPushButton("Telegram")
        self.btn_tg.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TELEGRAM_URL)))

        self.btn_log_toggle = QPushButton("Лог")
        self.btn_log_toggle.setCheckable(True)
        self.btn_log_toggle.toggled.connect(self._toggle_log)

        self.btn_folder = QPushButton("Папка")
        self.btn_folder.clicked.connect(self._open_game_dir)

        self.btn_settings = QPushButton("⚙ Настройки")
        self.btn_settings.clicked.connect(self._open_settings)

        header.addWidget(self.btn_discord)
        header.addWidget(self.btn_tg)
        header.addWidget(self.btn_log_toggle)
        header.addWidget(self.btn_folder)
        header.addWidget(self.btn_settings)
        outer.addLayout(header)

        outer.addStretch()

        # Compact center-left card
        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(16)

        nick_col = QVBoxLayout()
        lbl_nick = QLabel("ИГРОВОЙ НИК")
        lbl_nick.setObjectName("Section")
        self.nick_edit = QLineEdit(self.cfg.username)
        self.nick_edit.setMaxLength(16)
        self.nick_edit.setPlaceholderText("Ник в Minecraft")
        nick_col.addWidget(lbl_nick)
        nick_col.addWidget(self.nick_edit)

        ram_col = QVBoxLayout()
        self.ram_label = QLabel(f"ПАМЯТЬ: {self.cfg.ram_mb // 1024} GB ({self.cfg.ram_mb} MB)")
        self.ram_label.setObjectName("Section")
        self.ram_slider = QSlider(Qt.Orientation.Horizontal)
        self.ram_slider.setRange(4, 12)
        self.ram_slider.setValue(max(4, min(12, self.cfg.ram_mb // 1024)))
        self.ram_slider.valueChanged.connect(self._on_ram_changed)
        ram_col.addWidget(self.ram_label)
        ram_col.addWidget(self.ram_slider)

        row1.addLayout(nick_col, stretch=1)
        row1.addLayout(ram_col, stretch=1)
        card_layout.addLayout(row1)

        self.status_hint = QLabel(self._env_summary())
        self.status_hint.setStyleSheet("color: #9a928a; font-size: 12px;")
        card_layout.addWidget(self.status_hint)

        outer.addWidget(card)

        # Collapsible log box
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(120)
        self.log_box.setVisible(False)
        outer.addWidget(self.log_box)

        # Bottom progress + Play button
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Готов к запуску")

        self.btn_play = QPushButton("▶  ИГРАТЬ")
        self.btn_play.setObjectName("PlayBtn")
        self.btn_play.clicked.connect(self._start_play)

        bottom.addWidget(self.progress, stretch=1)
        bottom.addWidget(self.btn_play)
        outer.addLayout(bottom)

    def _env_summary(self) -> str:
        java_ok = "Java 17 ✔" if self.cfg.java_path else "Java 17 не найдена ✖"
        mods_cnt = len(list(self.cfg.mods_dir.glob("*.jar"))) if self.cfg.mods_dir.is_dir() else 0
        return f"{java_ok}  •  Установлено модов: {mods_cnt}  •  Папка: {self.cfg.game_dir}"

    def _toggle_log(self, checked: bool) -> None:
        self.log_box.setVisible(checked)

    def _on_ram_changed(self, gb: int) -> None:
        self.cfg.ram_mb = gb * 1024
        self.ram_label.setText(f"ПАМЯТЬ: {gb} GB ({self.cfg.ram_mb} MB)")

    def _open_settings(self) -> None:
        dlg = _SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to_config()
            save_config(self.cfg)
            self.status_hint.setText(self._env_summary())

    def _open_game_dir(self) -> None:
        self.cfg.game_dir.mkdir(parents=True, exist_ok=True)
        path = str(self.cfg.game_dir)
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _start_play(self) -> None:
        nick = self.nick_edit.text().strip()
        if len(nick) < 3:
            QMessageBox.warning(self, "RtCoD Launcher", "Введи игровой ник (от 3 символов).")
            return
        self.cfg.username = nick
        self.cfg.ram_mb = self.ram_slider.value() * 1024
        save_config(self.cfg)

        self.btn_play.setEnabled(False)
        self.btn_settings.setEnabled(False)
        self.progress.setValue(2)
        self.progress.setFormat("Подготовка к запуску...")
        self.log_box.appendPlainText(f"=== Запуск: {nick} ({self.cfg.ram_mb} MB) ===")

        self._worker = _PlayWorker(self.cfg)
        self._worker.status.connect(self._on_status)
        self._worker.finished_launch.connect(self._on_finished)
        self._worker.start()

    def _on_status(self, pct: int, msg: str) -> None:
        self.progress.setValue(max(0, min(100, pct)))
        self.progress.setFormat(f"{pct}% — {msg}")
        self.log_box.appendPlainText(msg)

    def _on_finished(self, ok: bool, msg: str, proc: subprocess.Popen | None) -> None:
        self.btn_settings.setEnabled(True)
        self.status_hint.setText(self._env_summary())
        if ok and proc is not None:
            self._game_proc = proc
            self.btn_play.setEnabled(False)
            self.btn_play.setText("Игра запущена...")
            self._proc_timer.start()
            self.progress.setValue(100)
            self.progress.setFormat("Игра запущена ✔")
            self.log_box.appendPlainText(f"✔ {msg} (PID {proc.pid})")
        else:
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶  ИГРАТЬ")
            self.progress.setFormat("Ошибка запуска")
            self.log_box.appendPlainText(f"✖ {msg}")
            self.log_box.setVisible(True)
            self.btn_log_toggle.setChecked(True)
            QMessageBox.critical(self, "Ошибка запуска RtCoD", msg)

    def _poll_game_process(self) -> None:
        if self._game_proc is not None and self._game_proc.poll() is not None:
            rc = self._game_proc.returncode
            self._game_proc = None
            self._proc_timer.stop()
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶  ИГРАТЬ")
            self.progress.setFormat("Готов к запуску")
            self.log_box.appendPlainText(f"--- Игра закрыта (код {rc}) ---")


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(LAUNCHER_QSS)
    win = RtCoDLauncherWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

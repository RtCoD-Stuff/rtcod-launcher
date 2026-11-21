<div align="center">

# ⚔ Return to Castle of Dark — Official Launcher

**Лёгкий и быстрый лаунчер тёмно-фэнтезийного RPG-сервера Minecraft Forge 1.20.1**

[![Release](https://img.shields.io/badge/Version-v1.0.0-d9a756?style=for-the-badge)](https://github.com/RtCoD-Stuff/rtcod-launcher/releases/latest)
[![Minecraft](https://img.shields.io/badge/Minecraft-1.20.1%20Forge%2047.4.28-8f4719?style=for-the-badge)](https://files.minecraftforge.net/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/9mPS3sXq)
[![Telegram](https://img.shields.io/badge/Telegram-Channel-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/RtCoD_server)

<br>

![Return to Castle of Dark](assets/hero-banner.jpg)

</div>

---

## Зачем нужен этот лаунчер?

Больше не нужно вручную скачивать 120+ модов, искать нужную версию Forge и ломать свой основной Minecraft.

| Возможность | Как это работает |
| :--- | :--- |
| **Вход в 1 клик** | Лаунчер сам устанавливает **Minecraft 1.20.1** и **Forge 47.4.28** в отдельную изолированную папку (`RtCoD`). |
| **Авто-Java 17** | Если на компьютере нет Java 17 — лаунчер сам скачает портативную **Adoptium Temurin JRE 17** в свою папку `runtime/`. |
| **Умная синхронизация модов** | При запуске проверяет **SHA-256** каждого файла сборки, докачивает только обновления и убирает лишние/конфликтующие `.jar`. |
| **Чистый интерфейс** | Стиль тёмного средневекового фэнтези: ввод ника, ползунок RAM (`4–12 GB`), защита от двойного запуска и быстрые ссылки в Discord/Telegram. |
| **Кроссплатформенность** | Готовые сборки для **Windows 10/11 (`.exe`)** и **Linux (`x64`)** в разделе [Releases](https://github.com/RtCoD-Stuff/rtcod-launcher/releases/latest). |

---

## Установка для игроков

1. Перейди в [последний релиз](https://github.com/RtCoD-Stuff/rtcod-launcher/releases/latest) и скачай файл под свою систему:
   - **Windows:** `RtCoD-Launcher-Windows.exe`
   - **Linux:** `RtCoD-Launcher-Linux` (`chmod +x RtCoD-Launcher-Linux && ./RtCoD-Launcher-Linux`)
2. Запусти лаунчер, введи свой игровой ник и выдели **6–8 GB RAM**.
3. Нажми **`▶ ИГРАТЬ`** — первый запуск займёт пару минут (загрузка ассетов, Forge и сборки), все последующие будут мгновенными.

---

## Запуск из исходников (для разработчиков)

```bash
git clone https://github.com/RtCoD-Stuff/rtcod-launcher.git
cd rtcod-launcher
pip install -r requirements.txt
python3 run_launcher.py
```

### Тесты
```bash
python3 -m unittest discover -s tests -v
```

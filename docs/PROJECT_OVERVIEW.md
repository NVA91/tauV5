# Projektübersicht

Dieses Repository enthält die quelloffene Firmware **"Enhanced Taupunkt Controller"** für einen Raspberry Pi Pico (RP2040). Die Anwendung misst mithilfe zweier Sensoren die Temperatur und Luftfeuchtigkeit, berechnet daraus den Taupunkt und visualisiert die Daten auf einem ST7789‑Display. Außerdem werden Alarme ausgelöst und Messwerte auf einer SD‑Karte protokolliert.

## Verzeichnisstruktur

```
/
├─ boot.py              # Boot-Logik für den Pico
├─ main.py              # Einstiegspunkt, startet den Controller
├─ config.json          # Gerätekonfiguration und Parameter
├─ lib/                 # Projektmodule
│  ├─ core/             # Kernfunktionen
│  │  ├─ calc.py        # Taupunktberechnung und Kalibrierung
│  │  ├─ logger.py      # SD-Logger
│  │  └─ trend.py       # Trendberechnung
│  ├─ sensors/          # Sensor-Treiber
│  │  ├─ aht20.py       # AHT20 Treiber (asynchron)
│  │  └─ sht41.py       # SHT41 Treiber (asynchron)
│  └─ ui/               # Anzeige und Alarm
│     ├─ alarm.py       # Buzzer-Steuerung
│     └─ display.py     # ST7789 Displaycontroller
└─ docs/                # Dokumentation
    └─ PROJECT_OVERVIEW.md (dieses Dokument)
```

## Module im Überblick

- **core.calc** – Stellt `TaupunktCalculator` und `SensorCalibrator` bereit.
- **core.trend** – Enthält `TrendAnalyzer` zur Kurzzeit-Trenderkennung.
- **core.logger** – Sorgt für CSV-Logging auf der SD-Karte (wenn vorhanden).
- **sensors.\*** – Asynchrone Treiber für AHT20 und SHT41.
- **ui.display** – Steuerung des ST7789 Displays.
- **ui.alarm** – Verwaltung von Summer- und Alarmmustern.

## Weitere Dateien

- **config.json** – Umfangreiche Konfigurationsdatei für Pins, Sensoren und Systemverhalten.
- **tauV5.code-workspace** – VS Code Workspace-Datei.

Dieses Dokument bildet den Ausgangspunkt für die weitere Entwicklung (Milestone 1). Weitere Informationen folgen in den kommenden Meilensteinen.

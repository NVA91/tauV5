# Enhanced Taupunkt Controller

Firmware-Projekt zur Taupunktmessung auf Basis eines Raspberry Pi Pico (RP2040).

## Setup

1. **Repository klonen** und die Dateien auf den Pico kopieren:
   ```bash
   git clone <repo-url>
   ```
   Anschließend `boot.py`, `main.py`, das Verzeichnis `lib/` und `config.json` auf das Dateisystem des Pico übertragen.

2. **Hardware anschließen**
   - Sensoren (SHT41, AHT20) über I2C
   - ST7789-Display über SPI
   - SD‑Karte, Relais und Buzzer gemäß `config.json`

3. **Konfiguration anpassen**
   - Die Datei `config.json` enthält alle Parameter wie Pins und Intervalle.
   - Standardwerte sind bereits hinterlegt.

4. **Starten**
   Der Pico lädt beim Boot `main.py` und startet die Messschleife automatisch.

## Dokumentation

Detaillierte Informationen befinden sich im Ordner `docs/`.

## Selftest

Um das System ohne angeschlossene Sensoren zu testen, kann das Skript `selftest.py` ausgeführt werden. Kopieren Sie dazu die Datei zusammen mit dem Ordner `lib/` auf den Pico und starten Sie im REPL:

```python
import selftest
selftest.run_selftest()
```

## Tests

Lokal lassen sich die Module mit `pytest` testen. Die Abhängigkeiten befinden
sich in `requirements.txt`.

```bash
pytest
```

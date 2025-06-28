# Release Packaging Guide

Dieser Leitfaden beschreibt, wie die fertige Firmware auf den Raspberry Pi Pico übertragen wird und welche Dateien zum Projekt gehören.

## Projektstruktur

```
/boot.py                # Boot-Initialisierung
/main.py                # Einstiegspunkt
/config.json            # Gerätkonfiguration
/lib/                   # Python-Module (Core, UI, Sensoren)
selftest.py             # Interner Funktionstest
/docs/                  # Dokumentation
```

## Deployment

1. **Kompilieren in .mpy-Dateien (optional)**

   Auf dem Entwicklungsrechner mit installiertem `mpy-cross`:

   ```bash
   for f in lib/**/*.py; do mpy-cross $f; done
   ```
   Die entstandenen `.mpy`-Dateien können auf den Pico kopiert werden, um RAM zu sparen.

2. **Dateien auf den Pico übertragen**

   Beispiel mit `mpremote`:

   ```bash
   mpremote connect /dev/ttyACM0 fs cp boot.py :boot.py
   mpremote connect /dev/ttyACM0 fs cp main.py :main.py
   mpremote connect /dev/ttyACM0 fs cp config.json :config.json
   mpremote connect /dev/ttyACM0 fs cp -r lib :lib
   mpremote connect /dev/ttyACM0 fs cp selftest.py :selftest.py
   ````

   Alternativ kann `rshell` verwendet werden:

   ```bash
   rshell --port /dev/ttyACM0
   rshell> cp boot.py /pyboard/boot.py
   rshell> cp main.py /pyboard/main.py
   rshell> cp config.json /pyboard/config.json
   rshell> cp -r lib /pyboard/lib
   rshell> cp selftest.py /pyboard/selftest.py
   ````

3. **Starten und Selftest ausführen**

   Nach dem Kopieren den Pico resetten oder `mpremote` REPL starten:

   ```python
   import selftest
   selftest.run_selftest()
   ```

## Versionierung

- Version der Firmware wird in `config.json` unter `system.version` gepflegt.
- Vor einem Release können optional alle Module zu `.mpy` kompiliert werden (siehe oben). Dadurch reduziert sich der Speicherverbrauch.

# END_PHASE

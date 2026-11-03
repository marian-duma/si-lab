"""Laborator 4 SI - pornește toate serviciile într-un singur terminal. Ctrl + C le oprește.

Rulare (din lab4-si, cu mediul virtual activat):
    python start_services.py                  toate serviciile
    python start_services.py --fara meteo     fără serviciul meteo (îl porniți separat)
    python start_services.py --search         serviciul meteo cu căutare de instrumente
Serverul clădirii este cel din Laboratorul 3 (../lab3-si/server.py, pe HTTP, portul 8000).
"""
import subprocess
import sys
import time
from pathlib import Path

AICI = Path(__file__).parent
LAB3 = AICI.parent / "lab3-si" / "server.py"

FARA = {sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--fara"}
SEARCH = ["--search"] if "--search" in sys.argv else []

COMENZI = [
    ("catalog", [sys.executable, "catalog.py"]),
    ("meteo", [sys.executable, "svc_meteo.py", *SEARCH]),
    ("energie", [sys.executable, "svc_energie.py"]),
]
if LAB3.exists():
    COMENZI.insert(0, ("cladire", [sys.executable, str(LAB3), "http"]))
else:
    print(f"ATENȚIE: nu găsesc {LAB3}; serviciul 'cladire' va apărea ca indisponibil.")

procese = []
for nume, cmd in COMENZI:
    if nume in FARA:
        continue
    cwd = LAB3.parent if nume == "cladire" else AICI
    procese.append((nume, subprocess.Popen(cmd, cwd=cwd)))
    print(f"pornit: {nume} (pid {procese[-1][1].pid})")

try:
    while True:
        time.sleep(1)
        for nume, p in procese:
            if p.poll() is not None:
                print(f"ATENȚIE: {nume} s-a oprit (cod {p.returncode}).")
                procese.remove((nume, p))
except KeyboardInterrupt:
    pass
finally:
    for _, p in procese:
        p.terminate()
    print("Servicii oprite.")

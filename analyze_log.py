"""Rezumă un fișier de log JSONL al agentului.
Utilizare: python analyze_log.py [logs/agent-....jsonl]   (fără argument: cel mai recent)"""
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        fisiere = sorted(Path("logs").glob("agent-*.jsonl"))
        if not fisiere:
            sys.exit("Nu există fișiere de log în folderul logs/.")
        path = fisiere[-1]

    tipuri, apeluri, erori, refuzuri = Counter(), Counter(), Counter(), 0
    durate, tokeni, stricate = [], [], 0
    with open(path, encoding="utf-8") as f:
        for linie in f:
            try:
                e = json.loads(linie)
            except json.JSONDecodeError:  # o linie stricată nu strică restul fișierului
                stricate += 1
                continue
            tipuri[e["tip"]] += 1
            if e["tip"] == "apel":
                apeluri[e["nume"]] += 1
            elif e["tip"] == "rezultat" and e.get("eroare"):
                erori[e["nume"]] += 1
            elif e["tip"] == "confirmare" and not e["aprobat"]:
                refuzuri += 1
            elif e["tip"] == "cerere_model":
                durate.append(e["durata_ms"])
                if e.get("prompt_tokens") is not None:
                    tokeni.append(e["prompt_tokens"])

    print(f"Fișier: {path}")
    print("Evenimente pe tip:", dict(tipuri))
    print("Apeluri pe instrument:", dict(apeluri) or "-")
    print("Apeluri cu eroare:", dict(erori) or "-", "| refuzuri ale utilizatorului:", refuzuri)
    if durate:
        print(f"Cereri către model: {len(durate)} | durata medie: {sum(durate) / len(durate):.0f} ms")
    if tokeni:
        print(f"Tokeni în prompt: primul {tokeni[0]}, ultimul {tokeni[-1]}, maxim {max(tokeni)}")
    if stricate:
        print(f"Atenție: {stricate} linii nu au putut fi citite.")


if __name__ == "__main__":
    main()

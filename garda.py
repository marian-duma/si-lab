"""Laborator 7 SI - garda: decide, ÎNAINTE de execuție, ce se întâmplă cu un apel de instrument.

Nu știe nimic despre model sau despre MCP: primește numele apelului, argumentele, indiciile
instrumentului și starea conversației, și întoarce o decizie:
    permis      - se execută fără întrebări;
    confirmare  - se execută doar dacă utilizatorul acceptă;
    interzis    - nu se execută; modelul primește motivul ca eroare.
Regulile stau în politica.json, nu în prompt: modelul nu le poate „convinge” să se schimbe.

Test fără servicii și fără model: python garda.py
"""
import json
from dataclasses import dataclass
from pathlib import Path

POLITICA = Path(__file__).parent / "politica.json"


@dataclass
class Decizie:
    actiune: str   # permis | confirmare | interzis
    motiv: str


class Garda:
    def __init__(self, cale: Path = POLITICA):
        self.politica = json.loads(Path(cale).read_text(encoding="utf-8"))

    def verifica(self, nume: str, args: dict, flags: dict,
                 contaminat: bool = False, modificari: int = 0) -> Decizie:
        """flags = {"read_only", "destructive"} (din adnotările MCP, ca în Lab. 2);
        contaminat = în conversație a intrat text dintr-o sursă nesigură;
        modificari = câte apeluri cu efecte au fost aprobate la întrebarea curentă."""
        p = self.politica
        regula = p["instrumente"].get(nume)

        # 1. Lista neagră: nimic nu o poate trece, nici măcar utilizatorul.
        if regula == "interzis":
            return Decizie("interzis", "instrument interzis de politică")

        # 2. Limitele argumentelor (mai stricte decât cele ale serverului).
        for arg, (minim, maxim) in p["limite"].get(nume, {}).items():
            valoare = args.get(arg)
            if not isinstance(valoare, (int, float)) or not minim <= valoare <= maxim:
                return Decizie("interzis", f"{arg}={valoare} în afara limitelor [{minim}, {maxim}]")

        if flags["read_only"]:
            # Citirea nu schimbă nimic: se permite, dacă politica nu cere altceva.
            return Decizie("confirmare" if regula == "confirmare" else "permis",
                           f"regulă: {regula}" if regula else "doar citire")

        # 3. Bugetul de acțiuni: un agent scăpat de sub control nu poate face oricât.
        maxim = p["max_modificari_pe_intrebare"]
        if modificari >= maxim:
            return Decizie("interzis", f"limita de {maxim} modificări pe întrebare a fost atinsă")

        # 4. Contaminarea: după text nesigur, cererea poate veni din acel text, nu de la utilizator.
        if contaminat and p["contaminare"]:
            if flags["destructive"]:
                return Decizie("interzis", "acțiune distructivă după conținut nesigur")
            return Decizie("confirmare", "conversația conține text dintr-o sursă nesigură")

        # 5. Regula instrumentului; fără regulă, ca în Lab. 2: întrebăm utilizatorul.
        if regula == "permis":
            return Decizie("permis", "permis de politică")
        return Decizie("confirmare", "regulă: confirmare" if regula else "fără regulă: implicit confirmare")


# Indiciile instrumentelor clădirii (Lab. 3), pentru testul de mai jos.
FLAGS = {
    "cladire_get_building_state": {"read_only": True, "destructive": False},
    "cladire_set_device_state": {"read_only": False, "destructive": False},
    "cladire_set_thermostat": {"read_only": False, "destructive": False},
    "cladire_reset_building": {"read_only": False, "destructive": True},
}

EXEMPLE = [  # (nume, argumente, contaminat, modificari)
    ("cladire_get_building_state", {}, False, 0),
    ("cladire_set_thermostat", {"temp_c": 22}, False, 0),
    ("cladire_set_thermostat", {"temp_c": 28}, False, 0),
    ("cladire_set_device_state", {"name": "radiator", "on": True}, False, 0),
    ("cladire_set_device_state", {"name": "radiator", "on": True}, True, 0),
    ("cladire_set_device_state", {"name": "radiator", "on": True}, False, 3),
    ("cladire_reset_building", {}, False, 0),
    ("cladire_reset_building", {}, True, 0),
]

if __name__ == "__main__":
    garda = Garda()
    print(f"{'apel':<58} {'contam.':<8} {'modif.':<7} {'decizie':<11} motiv")
    for nume, args, contaminat, modificari in EXEMPLE:
        d = garda.verifica(nume, args, FLAGS[nume], contaminat, modificari)
        apel = f"{nume}({json.dumps(args, ensure_ascii=False)})"
        print(f"{apel:<58} {'da' if contaminat else 'nu':<8} {modificari:<7} {d.actiune:<11} {d.motiv}")

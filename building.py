"""Laborator 3 SI - logica clădirii inteligente (date de test, inventate pentru laborator).

Modulul NU știe nimic despre MCP: este o bibliotecă Python obișnuită, care poate fi
testată direct sau expusă și altfel (REST, linie de comandă etc.).
Stratul MCP se află în server.py.
"""
from typing import Literal

Nivel = Literal["RIDICAT", "MEDIU", "NICIUNUL"]

DEVICES: dict[str, dict] = {
    "lampa_led": {"categorie": "iluminat", "putere_w": 10, "note": "Se poate regla pe trepte de intensitate."},
    "radiator": {"categorie": "încălzire", "putere_w": 1500, "note": "Controlat de termostatul camerei."},
    "aer_conditionat": {"categorie": "climatizare", "putere_w": 2000, "note": "Nu se folosește cu ferestrele deschise."},
    "jaluzele": {"categorie": "umbrire", "putere_w": 30, "note": "Motor electric, consum doar la mișcare."},
    "ventilatie": {"categorie": "ventilație", "putere_w": 120, "note": "Aduce aer proaspăt din exterior."},
}

# nivel, descriere
CONFLICTE: dict[frozenset[str], tuple[Nivel, str]] = {
    frozenset({"radiator", "aer_conditionat"}): ("RIDICAT", "Încălzire și răcire simultană, consum inutil."),
    frozenset({"aer_conditionat", "ventilatie"}): ("MEDIU", "Aerul exterior scade eficiența climatizării."),
}

TERMOSTAT_IMPLICIT = 21.0


class BuildingError(Exception):
    """Eroare de domeniu: cererea este corectă ca formă, dar nu poate fi îndeplinită."""


class Building:
    """Starea unei clădiri: dispozitivele pornite și temperatura dorită a termostatului."""

    def __init__(self) -> None:
        self.pornite: set[str] = set()
        self.termostat_c = TERMOSTAT_IMPLICIT

    # ---------- citire ----------

    def device_names(self) -> list[str]:
        return sorted(DEVICES)

    def device_info(self, name: str) -> dict:
        self._check(name)
        return {"nume": name, **DEVICES[name]}

    def energy_kwh(self, name: str, hours: float) -> float:
        self._check(name)
        return round(DEVICES[name]["putere_w"] * hours / 1000, 3)

    def conflict(self, a: str, b: str) -> tuple[Nivel, str]:
        self._check(a)
        self._check(b)
        return CONFLICTE.get(frozenset({a, b}), ("NICIUNUL", "Niciun conflict înregistrat."))

    def state(self) -> dict:
        return {"pornite": sorted(self.pornite), "termostat_c": self.termostat_c}

    # ---------- modificare ----------

    def set_device(self, name: str, on: bool) -> None:
        self._check(name)
        if on:
            for altul in sorted(self.pornite):
                nivel, descriere = self.conflict(name, altul)
                if nivel == "RIDICAT":
                    raise BuildingError(f"Nu pornesc {name}: conflict RIDICAT cu {altul}, care este pornit. {descriere}")
            self.pornite.add(name)
        else:
            self.pornite.discard(name)

    def set_thermostat(self, temp_c: float) -> None:
        if not 10 <= temp_c <= 30:
            raise BuildingError("Temperatura trebuie să fie între 10 și 30 °C.")
        self.termostat_c = temp_c

    def reset(self) -> None:
        self.pornite.clear()
        self.termostat_c = TERMOSTAT_IMPLICIT

    # ---------- intern ----------

    @staticmethod
    def _check(name: str) -> None:
        if name not in DEVICES:
            raise BuildingError(f"Dispozitiv necunoscut: {name}. Cunoscute: {', '.join(sorted(DEVICES))}.")


if __name__ == "__main__":
    # Test rapid, fără MCP: python building.py
    b = Building()
    print(b.device_info("radiator"))
    print(b.energy_kwh("radiator", 2))
    b.set_device("radiator", True)
    try:
        b.set_device("aer_conditionat", True)
    except BuildingError as e:
        print("Refuzat:", e)
    print(b.state())

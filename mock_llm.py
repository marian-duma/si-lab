"""Furnizorul "mock": un model de limbaj FALS, fără rețea și fără cheie API.

Versiunea 3 (Laboratorul 4). Față de Laboratorul 2:
  - găsește instrumentele și sub numele cu prefix (de ex. meteo_get_status);
  - are reguli și pentru serviciile meteo și energie;
  - în modul lazy, când nu are instrumentul potrivit, cere `foloseste_serviciu`, apoi reia întrebarea.
Nu citește descrierile instrumentelor: alegerea serviciului se face tot după cuvinte-cheie.
"""
import json
import re
import unicodedata
from itertools import count
from types import SimpleNamespace

DISPOZITIVE = {
    "lampa_led": ["lampa", "led"],
    "radiator": ["radiator", "calorifer"],
    "aer_conditionat": ["aer conditionat", "aerul conditionat", "aer_conditionat"],
    "jaluzele": ["jaluzele", "jaluzelele"],
    "ventilatie": ["ventilatie", "ventilatia"],
    "frigider": ["frigider", "frigiderul"],
}
# NOU (Lab. 4): ce serviciu cere mock-ul în modul lazy, după cuvintele din întrebare
SERVICII = {
    "meteo": ["vreme", "vremea", "afara", "exterior", "meteo", "prognoz", "umiditat"],
    "energie": ["tarif", "pret", "ieftin", "lei", "co2"],
    "cladire": ["consum", "porneste", "opreste", "stare", "dispozitiv", "conflict"],
}
_ids = count(1)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def gaseste_dispozitive(t: str) -> list[str]:
    gasite = []
    for nume, forme in DISPOZITIVE.items():
        poz = [m.start() for f in forme for m in re.finditer(r"\b" + re.escape(f), t)]
        if poz:
            gasite.append((min(poz), nume))
    return [nume for _, nume in sorted(gasite)]


def numar(pattern: str, t: str):
    m = re.search(pattern, t)
    return float(m.group(1).replace(",", ".")) if m else None


def rezolva(nume: str, unelte: set[str]) -> str | None:
    """NOU (Lab. 4): numele exact sau un nume cu prefix (<serviciu>_<nume>)."""
    if nume in unelte:
        return nume
    return next((u for u in sorted(unelte) if u.endswith("_" + nume)), None)


def planifica(text: str, unelte: set[str]) -> list[tuple[str, dict]]:
    t = norm(text)

    if t.startswith("apel:"):
        apeluri = []
        for parte in text.split(":", 1)[1].split(";"):
            nume, _, rest = parte.strip().partition(" ")
            apeluri.append((nume, json.loads(rest) if rest.strip() else {}))
        return apeluri

    if "bucla" in t:
        return [("list_devices", {})]

    dispozitive = gaseste_dispozitive(t)
    ore = numar(r"(\d+(?:[.,]\d+)?)\s*(?:de\s+)?or[ae]?\b", t)
    apeluri = []
    if ("conflict" in t or "acelasi timp" in t or "impreuna" in t) and len(dispozitive) >= 2:
        apeluri.append(("check_conflict", {"device_a": dispozitive[0], "device_b": dispozitive[1]}))
    if any(c in t for c in ("consum", "kwh", "energie")) and dispozitive:
        for d in dispozitive[:2]:
            apeluri.append(("estimate_energy", {"name": d, "hours": ore if ore is not None else 1.0}))
    if dispozitive and any(c in t for c in ("porneste", "aprinde", "activeaza", "deschide")):
        apeluri.append(("set_device_state", {"name": dispozitive[0], "on": True}))
    if dispozitive and any(c in t for c in ("opreste", "stinge", "inchide", "dezactiveaza")):
        apeluri.append(("set_device_state", {"name": dispozitive[0], "on": False}))
    grade = numar(r"(\d+(?:[.,]\d+)?)\s*(?:de\s+)?(?:grade|°)", t)
    if grade is not None and ("termostat" in t or "temperatura" in t or "grade" in t):
        apeluri.append(("set_thermostat", {"temp_c": grade}))
    if "reseteaza" in t or "resetare" in t:
        apeluri.append(("reset_building", {}))
    if "stare" in t or "ce este pornit" in t or "ce e pornit" in t:
        apeluri.append(("get_building_state", {}))
    if "ce dispozitive" in t or "lista" in t:
        apeluri.append(("list_devices", {}))
    if dispozitive and ("informatii" in t or "despre" in t) and not apeluri:
        apeluri.append(("get_device_info", {"name": dispozitive[0]}))
    # NOU (Lab. 4): serviciile meteo și energie
    if "prognoz" in t:
        apeluri.append(("get_forecast", {"hours": int(ore) if ore else 6}))
    elif any(c in t for c in ("vreme", "afara", "exterior", "meteo")):
        apeluri.append(("get_outdoor_conditions", {}))
    if "ieftin" in t:
        apeluri.append(("cheapest_window", {"duration_h": int(ore) if ore else 2}))
    elif "tarif" in t or "pret" in t:
        apeluri.append(("get_tariff", {}))
    if "co2" in t:
        apeluri.append(("get_co2_intensity", {}))
    # Doar instrumentele care există, sub numele lor real (eventual cu prefix).
    return [(rezolva(n, unelte), a) for n, a in apeluri if rezolva(n, unelte)]


def serviciu_potrivit(text: str) -> str | None:
    """NOU (Lab. 4): primul serviciu ale cărui cuvinte-cheie apar în întrebare."""
    t = norm(text)
    return next((s for s, cuvinte in SERVICII.items() if any(c in t for c in cuvinte)), None)


class _Apel:
    def __init__(self, nume: str, argumente: dict):
        self.id = f"mock_{next(_ids)}"
        self.type = "function"
        self.function = SimpleNamespace(name=nume, arguments=json.dumps(argumente, ensure_ascii=False))

    def model_dump(self, exclude_none=True):
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


def _raspuns(mesaje, continut=None, apeluri=None):
    mesaj = SimpleNamespace(role="assistant", content=continut, tool_calls=apeluri or None)
    chars = len(json.dumps(mesaje, ensure_ascii=False, default=str))
    usage = SimpleNamespace(prompt_tokens=chars // 4, completion_tokens=20)
    return SimpleNamespace(choices=[SimpleNamespace(message=mesaj)], usage=usage)


def _ultimele_apeluri(messages) -> list[str]:
    """Numele instrumentelor cerute în ultimul mesaj al asistentului."""
    for m in reversed(messages):
        if m["role"] == "assistant" and m.get("tool_calls"):
            return [c["function"]["name"] for c in m["tool_calls"]]
    return []


class _Completions:
    def create(self, model=None, messages=None, tools=None, tool_choice=None, **_):
        unelte = {t["function"]["name"] for t in (tools or [])}
        ultimul = messages[-1]
        ultimul_user = next(m for m in reversed(messages) if m["role"] == "user")

        if ultimul["role"] == "tool":
            if "bucla" in norm(ultimul_user["content"]) and rezolva("list_devices", unelte):
                return _raspuns(messages, apeluri=[_Apel(rezolva("list_devices", unelte), {})])
            # NOU (Lab. 4): după foloseste_serviciu, reia întrebarea cu instrumentele noi
            explicit = norm(ultimul_user["content"]).startswith("apel:")
            if "foloseste_serviciu" in _ultimele_apeluri(messages) and not explicit:
                apeluri = planifica(ultimul_user["content"], unelte)
                if apeluri:
                    return _raspuns(messages, apeluri=[_Apel(n, a) for n, a in apeluri])
            rezultate = []
            for m in reversed(messages):
                if m["role"] != "tool":
                    break
                rezultate.append(m["content"])
            linii = "\n".join(f"- {r}" for r in reversed(rezultate))
            return _raspuns(messages, continut=f"[mock] Rezultatele instrumentelor:\n{linii}")

        text = ultimul["content"]
        if tool_choice == "none":
            return _raspuns(messages, continut="[mock] (am răspuns fără instrumente, tool_choice=none)")
        try:
            apeluri = planifica(text, unelte)
        except (ValueError, json.JSONDecodeError):
            return _raspuns(messages, continut="[mock] Comandă 'apel:' invalidă. Format: apel: nume {json}")
        # NOU (Lab. 4): modul lazy - nu am instrumentul, dar pot cere un serviciu
        if not apeluri and "foloseste_serviciu" in unelte and serviciu_potrivit(text):
            apeluri = [("foloseste_serviciu", {"serviciu": serviciu_potrivit(text)})]
        if not apeluri and tool_choice == "required" and rezolva("list_devices", unelte):
            apeluri = [(rezolva("list_devices", unelte), {})]
        if not apeluri:
            return _raspuns(messages, continut="[mock] Nu am nevoie de instrumente pentru asta.")
        return _raspuns(messages, apeluri=[_Apel(n, a) for n, a in apeluri])


class MockClient:
    base_url = "mock://local"

    def __init__(self):
        self.chat = SimpleNamespace(completions=_Completions())
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id="mock-1")])

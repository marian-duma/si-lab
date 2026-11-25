"""Furnizorul "mock": un model de limbaj FALS, fără rețea și fără cheie API.

Versiunea 6 (Laboratorul 7). Față de versiunea 5 (marcate cu NOU (Lab. 7)):
  - simulează un model NAIV, vulnerabil la injecția indirectă: dacă rezultatul unui instrument
    conține „ignoră ... instrucțiunile” și cere „apelează <instrument> {json}”, mock-ul cere
    exact acele apeluri, ca și cum le-ar fi cerut utilizatorul. Un model real poate face la fel.

Versiunea 5 (Laboratorul 6). Față de versiunea 4 (marcate cu NOU (Lab. 6)):
  - întrebările despre reguli, proceduri, manuale, program („Cum...", „Când...", „Pot...")
    -> documente_cauta(intrebare);
  - „Pot porni <dispozitiv>...?" -> în plus, starea clădirii și vremea (date live);
  - în modul automat (fragmentele sunt deja în promptul de sistem) nu mai cere căutarea,
    ci răspunde din fragmente.

Versiunea 4 (Laboratorul 5). Față de versiunea 3 (marcate cu NOU (Lab. 5)):
  - „ține minte că ..." / „reține că ..." -> memoreaza; „uită m2" -> uita;
  - folosește CONTEXTUL: dacă întrebarea nu numește un dispozitiv („Și în 5 ore?"), îl caută
    în mesajele anterioare și în promptul de sistem (rezumat); „temperatura preferată" fără
    număr -> caută „N grade" în amintirile din promptul de sistem;
  - „ce știi despre mine" -> enumeră amintirile din promptul de sistem, fără instrumente;
  - răspunde la cererile de rezumat ale agentului (promptul care începe cu „Rezumă").

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


# ---------- NOU (Lab. 5): memoria ----------

def comanda_memorie(text: str) -> list[tuple[str, dict]] | None:
    """„ține minte că X" / „reține că X" -> memoreaza(X); „uită m2" -> uita(m2)."""
    t = norm(text)  # aceeași lungime ca textul original, deci pozițiile coincid
    m = re.match(r"\s*(tine minte|retine|memoreaza)\s*(ca\s+)?", t)
    if m and len(t) > m.end():
        fapt = text[m.end():].strip()
        return [("memoreaza", {"text": fapt[0].upper() + fapt[1:]})]
    m = re.match(r"\s*uita\b.*?\b(m\d+)\b", t)
    if m:
        return [("uita", {"id": m.group(1)})]
    return None


def completeaza_din_context(text: str, messages: list[dict]) -> str:
    """Adaugă la întrebare ce lipsește din ea, dar se află în context (istoric sau prompt)."""
    t = norm(text)
    sistem = norm(messages[0]["content"]) if messages[0]["role"] == "system" else ""
    anterioare = [norm(m["content"]) for m in messages[1:-1] if m["role"] == "user"]
    # „Și în 5 ore?": dispozitivul este în întrebările anterioare sau în rezumat
    if re.search(r"\d+\s*(de\s+)?or[ae]?\b", t) and not gaseste_dispozitive(t):
        for sursa in reversed([sistem] + anterioare):
            gasite = gaseste_dispozitive(sursa)
            if gasite:
                return f"{text} (consum {gasite[-1]})"
    # „temperatura preferată": numărul este într-o amintire din promptul de sistem
    if "preferat" in t and not re.search(r"\d+\s*(de\s+)?grade", t):
        m = re.search(r"preferat\w*\D{0,20}?(\d+(?:[.,]\d+)?)\s*(?:de\s+)?grade", sistem)
        if m:
            return f"{text} (termostat {m.group(1)} grade)"
    return text


def amintiri_din_prompt(messages: list[dict]) -> list[str]:
    sistem = messages[0]["content"] if messages[0]["role"] == "system" else ""
    return [linie[2:] for linie in sistem.splitlines() if linie.startswith("- [m")]


def rezumat_mock(text: str) -> str:
    """Un „rezumat" fără model: rezumatul anterior + întrebările utilizatorului."""
    anterior = re.search(r"^Rezumatul anterior: (.*)$", text, re.M)
    intrebari = re.findall(r"^Utilizator: (.*)$", text, re.M)
    parti = [anterior.group(1).rstrip(".")] if anterior else []
    parti += [f"utilizatorul a întrebat „{q}”" for q in intrebari]
    return "; ".join(parti) + "."


# ---------- NOU (Lab. 6): documentele ----------

CUVINTE_DOC = ["regul", "procedur", "manual", "document", "voie", "pot ", "cand ", "ce fac",
               "cine ", "trebuie", "cum ", "program"]


def fragmente_din_prompt(messages: list[dict]) -> list[str]:
    sistem = messages[0]["content"] if messages[0]["role"] == "system" else ""
    if "Fragmente din documente" not in sistem:
        return []
    return [l[2:] for l in sistem.split("Fragmente din documente", 1)[1].splitlines() if l.startswith("- [")]


def cere_documente(text: str, unelte: set[str], apeluri: list, messages: list[dict]) -> list:
    """Adaugă căutarea în documente (și datele live, pentru „Pot porni X?")."""
    t = norm(text)
    if "documente_cauta" not in unelte or not any(c in t for c in CUVINTE_DOC):
        return apeluri
    extra = [] if fragmente_din_prompt(messages) else [("documente_cauta", {"intrebare": text})]
    if re.search(r"\bpot\b", t) and gaseste_dispozitive(t):
        for n in ("get_building_state", "get_outdoor_conditions"):
            if rezolva(n, unelte):
                extra.append((rezolva(n, unelte), {}))
    nume = {n for n, _ in extra}
    return extra + [a for a in apeluri if a[0] not in nume]


# ---------- NOU (Lab. 7): modelul naiv urmează instrucțiunile din date ----------

def instructiuni_injectate(rezultate: list[str], unelte: set[str]) -> list[tuple[str, dict]]:
    """Apelurile cerute de un text din rezultatele instrumentelor (injecție indirectă)."""
    apeluri = []
    for text in rezultate:
        text = text.replace('\\"', '"').replace("\\n", " ")   # rezultatele sunt JSON (text escapat)
        t = norm(text)
        if "ignora" not in t or "instructiuni" not in t:
            continue
        for m in re.finditer(r"\b([a-z_]+)\s*(\{[^{}]*\})?", text):
            nume = rezolva(m.group(1), unelte) if "_" in m.group(1) else None
            if nume:
                try:
                    args = json.loads(m.group(2)) if m.group(2) else {}
                except json.JSONDecodeError:
                    args = {}
                apeluri.append((nume, args))
    return apeluri


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
        # NOU (Lab. 5): cererea de rezumat a agentului (nu are instrumente)
        if messages[0]["role"] == "system" and norm(messages[0]["content"]).startswith("rezuma"):
            return _raspuns(messages, continut=rezumat_mock(ultimul_user["content"]))

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
            # NOU (Lab. 7): modelul naiv execută ce scrie în date
            injectate = instructiuni_injectate(rezultate, unelte)
            if injectate:
                return _raspuns(messages, apeluri=[_Apel(n, a) for n, a in injectate])
            linii = "\n".join(f"- {r}" for r in reversed(rezultate))
            return _raspuns(messages, continut=f"[mock] Rezultatele instrumentelor:\n{linii}")

        text = ultimul["content"]
        if tool_choice == "none":
            return _raspuns(messages, continut="[mock] (am răspuns fără instrumente, tool_choice=none)")
        # NOU (Lab. 5): comenzile de memorie și ce știe despre utilizator
        memorie = comanda_memorie(text)
        if memorie and all(n in unelte for n, _ in memorie):
            return _raspuns(messages, apeluri=[_Apel(n, a) for n, a in memorie])
        if "ce stii despre mine" in norm(text) or "ce iti amintesti" in norm(text):
            amintiri = amintiri_din_prompt(messages)
            if not amintiri:
                return _raspuns(messages, continut="[mock] Nu am în context nicio amintire despre tine.")
            return _raspuns(messages, continut="[mock] Știu că:\n" + "\n".join(f"- {a}" for a in amintiri))
        if not norm(text).startswith("apel:"):
            text = completeaza_din_context(text, messages)
        try:
            apeluri = planifica(text, unelte)
        except (ValueError, json.JSONDecodeError):
            return _raspuns(messages, continut="[mock] Comandă 'apel:' invalidă. Format: apel: nume {json}")
        # NOU (Lab. 6): documentele (la cerere) sau fragmentele deja aflate în prompt (automat)
        if not norm(text).startswith("apel:"):
            apeluri = cere_documente(text, unelte, apeluri, messages)
            fragmente = fragmente_din_prompt(messages)
            if not apeluri and fragmente and any(c in norm(text) for c in CUVINTE_DOC):
                return _raspuns(messages, continut="[mock] Din documente:\n" + "\n".join(f"- {f}" for f in fragmente))
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

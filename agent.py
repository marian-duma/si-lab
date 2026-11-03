"""Agentul v3: descoperă singur serviciile MCP (catalog -> card -> conexiune) și le folosește
instrumentele sub nume cu prefix. Două moduri:
  - "eager": se conectează la pornire la toate serviciile active;
  - "lazy":  modelul vede doar două meta-instrumente și cere singur serviciile de care are nevoie.
Restul (fișierul de log, confirmarea, istoricul, detecția buclei) este ca în Laboratorul 2."""
import json
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from fastmcp import Client

from discovery import CatalogIndisponibil, discover
from llm import create_chat, make_client

LOG_DIR = Path(__file__).parent / "logs"

MODE = "eager"          # eager | lazy  (se poate schimba din linia de comandă: python chat.py --lazy)
MAX_STEPS = 8           # puțin mai mult decât în Lab. 2: în modul lazy, descoperirea consumă pași
MAX_REPEAT = 2
MAX_TURNS = 6
MAX_TOOL_CHARS = 1500
TOOL_CHOICE = "auto"    # auto | none | required - se aplică doar primului pas al fiecărei întrebări

SYSTEM_PROMPT = (
    "Ești asistentul unei clădiri inteligente. Răspunde concis, în limba română. "
    "Instrumentele provin din mai multe servicii; prefixul numelui arată serviciul "
    "(de exemplu meteo_..., energie_..., cladire_...). Folosește instrumentele; nu inventa date. "
    "Dacă un instrument returnează o eroare sau utilizatorul refuză un apel, spune-o clar."
)
SYSTEM_LAZY = (
    " La început nu ai instrumente de domeniu: folosește cauta_servicii pentru a afla ce servicii "
    "există, apoi foloseste_serviciu pentru a-l activa pe cel potrivit. Instrumentele lui devin "
    "disponibile la pasul următor."
)

# Meta-instrumentele modului lazy. Le execută agentul însuși, nu un server MCP.
META_TOOLS = [
    {"type": "function", "function": {
        "name": "cauta_servicii",
        "description": "Caută în catalog serviciile disponibile (nume, titlu, descriere, stare). "
                       "Cuvânt gol = toate serviciile.",
        "parameters": {"type": "object", "properties": {
            "cuvant": {"type": "string", "description": "Cuvânt căutat în nume, titlu sau descriere."}},
            "required": ["cuvant"]}}},
    {"type": "function", "function": {
        "name": "foloseste_serviciu",
        "description": "Se conectează la un serviciu din catalog și îi adaugă instrumentele "
                       "(cu prefixul serviciului) la instrumentele disponibile.",
        "parameters": {"type": "object", "properties": {
            "serviciu": {"type": "string", "description": "Numele scurt al serviciului, ex. meteo."}},
            "required": ["serviciu"]}}},
]
META = {t["function"]["name"] for t in META_TOOLS}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class JsonlLog:
    """Fișier de log în format JSONL (ca în Laboratorul 2)."""

    def __init__(self, directory: Path = LOG_DIR):
        directory.mkdir(exist_ok=True)
        self.path = directory / f"agent-{datetime.now():%Y%m%d-%H%M%S}.jsonl"

    def write(self, tip: str, **date):
        eveniment = {"ts": datetime.now().isoformat(timespec="milliseconds"), "tip": tip, **date}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(eveniment, ensure_ascii=False) + "\n")


def mcp_to_openai_tool(tool, name: str) -> dict:
    """Descrierea unui instrument MCP, în formatul modelului, sub numele cu prefix."""
    schema = getattr(tool, "input_schema", None) or tool.inputSchema
    return {"type": "function", "function": {
        "name": name, "description": tool.description or "", "parameters": schema}}


def _hint(ann, snake: str, camel: str):
    """Valoarea unui indiciu; numele câmpului diferă între versiunile SDK-ului MCP (ca în Lab. 2)."""
    if ann is None:
        return None
    for nume in (snake, camel):
        if hasattr(ann, nume):
            return getattr(ann, nume)
    return None


def tool_flags(tool) -> dict:
    """Indiciile instrumentului. Lipsa lor înseamnă: poate modifica și poate distruge."""
    ann = getattr(tool, "annotations", None)
    read_only = bool(_hint(ann, "read_only_hint", "readOnlyHint"))
    destructive = (not read_only) and _hint(ann, "destructive_hint", "destructiveHint") is not False
    return {"read_only": read_only, "destructive": destructive}


def truncate(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... trunchiat: {len(text) - limit} caractere omise]"


def trim_history(messages: list[dict], max_turns: int = MAX_TURNS) -> list[dict]:
    starts = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(starts) <= max_turns:
        return messages
    return messages[:1] + messages[starts[-max_turns]:]


class Agent:
    def __init__(self, confirm=None, mode: str = MODE):
        self.llm, self.model, self.provider = make_client()
        self.confirm = confirm
        self.mode = mode
        self.log = JsonlLog()
        self.services = {}   # cheie -> Service (din discovery.py)
        self.clients = {}    # cheie -> Client conectat
        self.routes = {}     # nume cu prefix -> (cheie serviciu, numele original al instrumentului)
        self.defs = {}       # nume cu prefix -> descrierea pentru model
        self.flags = {}      # nume cu prefix -> {"read_only", "destructive"}
        self.expira = {}     # cheie -> momentul (time.monotonic) după care lista trebuie recitită
        self.tools = []
        self.reset()

    def reset(self):
        prompt = SYSTEM_PROMPT + (SYSTEM_LAZY if self.mode == "lazy" else "")
        self.messages = [{"role": "system", "content": prompt}]
        self.log.write("reset")

    # ---------- Descoperire ----------

    async def __aenter__(self):
        await self.descopera()
        self.log.write("pornire", furnizor=self.provider, model=self.model, mod=self.mode)
        return self

    async def __aexit__(self, *exc):
        for key in list(self.clients):
            await self.deconecteaza(key)

    async def descopera(self):
        """Citește catalogul și, în modul eager, se conectează la serviciile active noi."""
        try:
            gasite = await discover()
        except CatalogIndisponibil as e:
            self.log.write("catalog_indisponibil", eroare=str(e))
            if not self.services:  # la pornire: fără catalog nu avem ce face
                raise SystemExit(str(e))
            print(f"  (atenție: {e} Păstrez lista anterioară de servicii.)")
            return
        self.services = {s.key: s for s in gasite}
        self.log.write("descoperire", servicii={k: s.stare for k, s in self.services.items()})
        for key in list(self.clients):  # servicii conectate care au dispărut sau nu mai răspund
            if self.services.get(key) is None or self.services[key].stare != "activ":
                await self.deconecteaza(key)
        if self.mode == "eager":
            for key, s in self.services.items():
                if s.stare == "activ" and key not in self.clients:
                    await self.conecteaza(key)
        self._rebuild()

    async def deconecteaza(self, key: str):
        client = self.clients.pop(key)
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass  # serverul poate fi deja oprit
        eliminate = sorted(n for n, (k, _) in self.routes.items() if k == key)
        for n in eliminate:
            del self.routes[n], self.defs[n], self.flags[n]
        self.log.write("lista_instrumente", serviciu=key, motiv="deconectare", adaugate=[], eliminate=eliminate)
        self._rebuild()

    async def conecteaza(self, key: str) -> list[str]:
        client = Client(self.services[key].url)
        await client.__aenter__()
        self.clients[key] = client
        return await self.actualizeaza(key, motiv="conectare")

    async def actualizeaza(self, key: str, motiv: str) -> list[str]:
        """Recitește tools/list pentru un serviciu (toate paginile) și actualizează rutele."""
        client, tools, cursor = self.clients[key], [], None
        while True:
            r = await client.list_tools_mcp(cursor=cursor)
            tools += r.tools
            cursor = r.next_cursor
            if cursor is None:  # un cursor gol ("") este valid; doar lipsa lui încheie lista
                break
        self.expira[key] = time.monotonic() + (r.ttl_ms or 0) / 1000

        vechi = {n for n, (k, _) in self.routes.items() if k == key}
        for n in vechi:
            del self.routes[n], self.defs[n], self.flags[n]
        for t in tools:
            nume = f"{key}_{t.name}"   # prefixul evită coliziunile (ex. meteo_get_status / energie_get_status)
            self.routes[nume] = (key, t.name)
            self.defs[nume] = mcp_to_openai_tool(t, nume)
            self.flags[nume] = tool_flags(t)
        noi = {n for n, (k, _) in self.routes.items() if k == key}
        if noi != vechi:
            self.log.write("lista_instrumente", serviciu=key, motiv=motiv,
                           adaugate=sorted(noi - vechi), eliminate=sorted(vechi - noi), ttl_ms=r.ttl_ms)
        self._rebuild()
        return sorted(noi)

    async def reimprospateaza(self):
        """Recitește listele expirate (ttlMs). Serverele noastre nu trimit notificări de schimbare."""
        for key in list(self.clients):
            if time.monotonic() >= self.expira.get(key, 0):
                try:
                    await self.actualizeaza(key, motiv="ttl")
                except Exception as e:
                    self.log.write("serviciu_indisponibil", serviciu=key, eroare=str(e)[:200])

    def _rebuild(self):
        meta = META_TOOLS if self.mode == "lazy" else []
        self.tools = meta + [self.defs[n] for n in sorted(self.defs)]

    # ---------- Meta-instrumentele (modul lazy) ----------

    async def _meta(self, nume: str, args: dict) -> tuple[str, bool]:
        if nume == "cauta_servicii":
            cuvant = norm(args.get("cuvant", ""))
            gasite = [{"serviciu": k, "titlu": s.card.get("title", ""), "descriere": s.descriere,
                       "stare": s.stare, "conectat": k in self.clients}
                      for k, s in self.services.items()
                      if cuvant in norm(f"{k} {s.card.get('title', '')} {s.descriere}")]
            return json.dumps(gasite, ensure_ascii=False), False
        key = args.get("serviciu", "")
        s = self.services.get(key)
        if s is None:
            return f"Serviciu necunoscut: {key}. Existente: {', '.join(self.services)}.", True
        if s.stare != "activ":
            return f"Serviciul {key} nu este disponibil ({s.stare}).", True
        if key in self.clients:
            noi = sorted(n for n, (k, _) in self.routes.items() if k == key)
        else:
            noi = await self.conecteaza(key)
        return f"Serviciul {key} este activ. Instrumente disponibile: {', '.join(noi)}.", False

    # ---------- Apelul unui instrument ----------

    async def call_tool(self, call, pas: int) -> str:
        nume = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError as e:
            return self._rezultat(pas, nume, {}, f"Eroare: argumentele nu sunt JSON valid ({e}).", True)
        self.log.write("apel", pas=pas, nume=nume, argumente=args)

        if self.mode == "lazy" and nume in META:
            text, eroare = await self._meta(nume, args)
            return self._rezultat(pas, nume, args, text, eroare)

        if nume not in self.routes:  # poate a apărut între timp: recitim listele o dată
            for key in list(self.clients):
                await self.actualizeaza(key, motiv="instrument_necunoscut")
        if nume not in self.routes:
            text = f"Instrument necunoscut: {nume}. Disponibile: {', '.join(sorted(self.routes))}."
            return self._rezultat(pas, nume, args, text, True)

        flags = self.flags[nume]
        if not flags["read_only"]:
            aprobat = bool(self.confirm and self.confirm(nume, args, flags["destructive"]))
            self.log.write("confirmare", pas=pas, nume=nume, aprobat=aprobat)
            if not aprobat:
                return self._rezultat(pas, nume, args, "Utilizatorul a refuzat acest apel; nu a fost executat.", True)

        key, original = self.routes[nume]
        try:
            result = await self.clients[key].call_tool(original, args)
            text = "\n".join(b.text for b in result.content if hasattr(b, "text"))
            if not text and result.structured_content is not None:  # rezultat doar structurat
                text = json.dumps(result.structured_content, ensure_ascii=False)
            eroare = False
        except Exception as e:
            text, eroare = f"Eroare la apelul {nume} (serviciul {key}): {e}", True
        return self._rezultat(pas, nume, args, text, eroare)

    def _rezultat(self, pas, nume, args, text, eroare) -> str:
        scurt = truncate(text)
        self.log.write("rezultat", pas=pas, nume=nume, eroare=eroare, text=scurt,
                       trunchiat=len(scurt) != len(text))
        print(f"  [instrument] {nume}({args}) -> {scurt[:150]}")
        return scurt

    def _final(self, text: str, **date) -> str:
        self.messages.append({"role": "assistant", "content": text})
        self.log.write("raspuns", text=text, **date)
        return text

    # ---------- Bucla agentului (ca în Laboratorul 2) ----------

    async def ask(self, text: str) -> str:
        await self.reimprospateaza()
        self.messages.append({"role": "user", "content": text})
        inainte = len(self.messages)
        self.messages = trim_history(self.messages)
        self.log.write("intrebare", text=text, mesaje_taiate=inainte - len(self.messages),
                       instrumente=len(self.tools))

        vazute: dict[tuple, int] = {}
        for pas in range(1, MAX_STEPS + 1):
            extra = {"tool_choice": TOOL_CHOICE} if pas == 1 and TOOL_CHOICE != "auto" else {}
            t0 = time.perf_counter()
            reply = create_chat(
                self.llm, model=self.model, messages=self.messages, tools=self.tools, **extra
            )
            usage = getattr(reply, "usage", None)
            self.log.write("cerere_model", pas=pas, mesaje=len(self.messages), instrumente=len(self.tools),
                           durata_ms=round((time.perf_counter() - t0) * 1000),
                           prompt_tokens=getattr(usage, "prompt_tokens", None))
            msg = reply.choices[0].message
            if not msg.tool_calls:
                return self._final(msg.content or "", pas=pas)

            chei = [(c.function.name, c.function.arguments) for c in msg.tool_calls]
            for cheie in chei:
                vazute[cheie] = vazute.get(cheie, 0) + 1
            if any(vazute[c] > MAX_REPEAT for c in chei):
                self.log.write("bucla_detectata", pas=pas, apeluri=[c[0] for c in chei])
                return self._final("(M-am oprit: modelul cere în mod repetat același apel.)", pas=pas)

            self.messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [c.model_dump(exclude_none=True) for c in msg.tool_calls],
            })
            for call in msg.tool_calls:
                rezultat = await self.call_tool(call, pas)
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": rezultat})

        self.log.write("limita_pasi", pasi=MAX_STEPS)
        return self._final("(Am atins limita de pași a agentului.)")

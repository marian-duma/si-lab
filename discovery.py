"""Laborator 4 SI - descoperirea serviciilor MCP, în trei pași:

  1. catalogul AI (/.well-known/ai-catalog.json)  -> CE servicii există
  2. cardul fiecărui server (SEP-2127)            -> UNDE și CUM ne conectăm
  3. conexiunea MCP (server/discover, tools/list) -> verificarea live și CE poate face

Cardul este doar o promisiune: ce contează este ce răspunde serverul la conectare.
"""
import asyncio
import re
from dataclasses import dataclass, field

import httpx
from fastmcp import Client

CATALOG_URL = "http://127.0.0.1:8080/.well-known/ai-catalog.json"
CARD_TYPE = "application/mcp-server-card+json"
PROTOCOL = "2026-07-28"
NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")


class CatalogIndisponibil(Exception):
    """Catalogul nu poate fi citit: fără el nu se poate descoperi nimic."""


@dataclass
class Service:
    key: str                  # identificator scurt; devine prefixul instrumentelor
    identifier: str           # din catalog, de forma urn:air:...
    sursa: str = ""           # "url" (card găsit la o adresă) sau "inline" (card inclus în catalog)
    card: dict = field(default_factory=dict)
    url: str | None = None    # adresa MCP, din card
    stare: str = "necunoscut" # activ | indisponibil | card_invalid
    probleme: list[str] = field(default_factory=list)
    server_name: str | None = None
    server_version: str | None = None
    protocol: str | None = None
    list_changed: bool | None = None

    @property
    def descriere(self) -> str:
        return self.card.get("description", "")


def fetch_catalog(url: str = CATALOG_URL) -> list[dict]:
    """Pasul 1: intrările de tip „card de server MCP” din catalogul AI."""
    r = httpx.get(url, timeout=3)
    r.raise_for_status()
    return [e for e in r.json().get("entries", []) if e.get("type") == CARD_TYPE]


def load_card(entry: dict) -> tuple[dict, str]:
    """Pasul 2: cardul, fie inclus în catalog (`data`), fie descărcat de la `url`."""
    if "data" in entry:
        return entry["data"], "inline"
    r = httpx.get(entry["url"], headers={"Accept": CARD_TYPE}, timeout=3)
    r.raise_for_status()
    return r.json(), "url"


def check_card(card: dict) -> list[str]:
    """Câteva verificări din schema cardului (nu toate)."""
    probleme = [f"lipsește câmpul '{c}'" for c in ("$schema", "name", "version", "description") if c not in card]
    if "name" in card and not NAME_RE.match(card["name"]):
        probleme.append(f"numele '{card['name']}' nu are forma spațiu/nume")
    if len(card.get("description", "")) > 100:
        probleme.append("descrierea depășește 100 de caractere")
    remote = next((r for r in card.get("remotes", []) if r.get("type") == "streamable-http"), None)
    if remote is None:
        probleme.append("nu are o adresă streamable-http")
    elif PROTOCOL not in remote.get("supportedProtocolVersions", [PROTOCOL]):
        probleme.append(f"nu declară versiunea {PROTOCOL}")
    return probleme


async def verify(s: Service) -> None:
    """Pasul 3: conectarea reală. Valorile live au prioritate față de card."""
    try:
        async with Client(s.url, timeout=5, init_timeout=3) as c:
            info, caps = c.server_info, c.server_capabilities
            s.server_name, s.server_version = info.name, info.version
            s.protocol = c.protocol_version
            s.list_changed = bool(caps.tools and caps.tools.list_changed)
    except Exception as e:  # server oprit, port greșit, protocol incompatibil...
        s.stare, s.probleme = "indisponibil", s.probleme + [str(e)[:120]]
        return
    if s.server_version != s.card.get("version"):
        s.probleme.append(f"cardul spune versiunea {s.card.get('version')}, serverul {s.server_version}")
    s.stare = "activ"


async def discover(catalog_url: str = CATALOG_URL) -> list[Service]:
    """Toți pașii, pentru toate intrările din catalog. Nu se oprește la prima eroare."""
    try:
        intrari = fetch_catalog(catalog_url)
    except (httpx.HTTPError, ValueError) as e:  # catalog oprit, adresă greșită sau JSON invalid
        raise CatalogIndisponibil(
            f"Catalogul nu poate fi citit ({catalog_url}): {type(e).__name__}. "
            "Ați pornit start_services.py?") from e
    servicii = []
    for entry in intrari:
        s = Service(key=entry["identifier"].rsplit(":", 1)[-1], identifier=entry["identifier"])
        try:
            s.card, s.sursa = load_card(entry)
        except httpx.HTTPError as e:
            s.stare, s.probleme = "indisponibil", [f"cardul nu poate fi citit: {type(e).__name__}"]
            servicii.append(s)
            continue
        s.probleme = check_card(s.card)
        remote = next((r for r in s.card.get("remotes", []) if r.get("type") == "streamable-http"), {})
        s.url = remote.get("url")
        if s.probleme or not s.url:
            s.stare = "card_invalid"
        servicii.append(s)
    await asyncio.gather(*(verify(s) for s in servicii if s.stare == "necunoscut"))
    return servicii

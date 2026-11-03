"""Laborator 4 SI - afișează pas cu pas descoperirea serviciilor.
Rulare: python discover.py   (cu serviciile pornite, vezi start_services.py)"""
import asyncio
from collections import defaultdict

from fastmcp import Client

from discovery import CATALOG_URL, CatalogIndisponibil, discover

SIMBOL = {"activ": "OK", "indisponibil": "--", "card_invalid": "!!"}


async def list_tools_paged(url: str):
    """tools/list cu paginare explicită: cerem pagini până când nu mai există `nextCursor`."""
    async with Client(url) as c:
        tools, pagini, cursor = [], 0, None
        while True:
            r = await c.list_tools_mcp(cursor=cursor)
            tools += r.tools
            pagini += 1
            cursor = r.next_cursor
            if cursor is None:  # un cursor gol ("") este valid; doar lipsa lui încheie lista
                return tools, pagini, r.ttl_ms, r.cache_scope


async def main():
    print(f"1. Catalog: {CATALOG_URL}\n")
    try:
        servicii = await discover()
    except CatalogIndisponibil as e:
        print(e)
        return

    print("2-3. Carduri și verificare live:")
    for s in servicii:
        print(f"  [{SIMBOL.get(s.stare, '??')}] {s.key:<11} card {s.sursa or '-':<6} {s.url or ''}")
        if s.stare == "activ":
            print(f"       server: {s.server_name} v{s.server_version} | protocol {s.protocol}"
                  f" | tools.listChanged={s.list_changed}")
        for p in s.probleme:
            print(f"       problemă: {p}")

    print("\n4. Instrumente (tools/list):")
    proprietari = defaultdict(list)
    for s in servicii:
        if s.stare != "activ":
            continue
        tools, pagini, ttl, scope = await list_tools_paged(s.url)
        print(f"  {s.key}: {len(tools)} instrumente | pagini: {pagini} | ttlMs={ttl} | cacheScope={scope}")
        for t in tools:
            proprietari[t.name].append(s.key)
            nume = f"{s.key}_{t.name}"
            print(f"     {nume:<32} {(t.description or '').splitlines()[0][:55]}")

    coliziuni = {n: k for n, k in proprietari.items() if len(k) > 1}
    print("\n5. Nume comune mai multor servicii (de aceea folosim prefixe):",
          ", ".join(f"{n} ({'/'.join(k)})" for n, k in coliziuni.items()) or "niciunul")


if __name__ == "__main__":
    asyncio.run(main())

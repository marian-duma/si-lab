"""Laborator 4 SI - serviciul meteo (date simulate) pentru clădirea inteligentă.

Rulare:  python svc_meteo.py            (port 8001)
         python svc_meteo.py --search   (aceleași instrumente, ascunse în spatele căutării BM25)
"""
import math
import sys
from datetime import datetime
from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from serviciu import run_http

PORT = 8001
mcp = FastMCP("ro.usv.si/meteo", version="1.0.0", cache_ttl=60)  # listele pot fi păstrate 60 s

if "--search" in sys.argv:
    from fastmcp.server.transforms.search import BM25SearchTransform
    mcp.add_transform(BM25SearchTransform(max_results=3))


class Conditii(BaseModel):
    ora: int
    temp_c: float = Field(description="Temperatura exterioară, în °C.")
    umiditate_pct: int
    vant_kmh: float
    descriere: str


def _simulare(ora: int) -> Conditii:
    """Date inventate, dar repetabile: o zi de toamnă, cu minimul la 5 și maximul la 15."""
    temp = round(9 + 6 * math.sin((ora - 9) * math.pi / 12), 1)
    umid = int(80 - 3 * (temp - 9))
    vant = round(8 + 4 * math.cos(ora * math.pi / 6), 1)
    desc = "senin" if 10 <= ora <= 16 else ("ceață" if ora < 8 else "noros")
    return Conditii(ora=ora, temp_c=temp, umiditate_pct=umid, vant_kmh=vant, descriere=desc)


@mcp.tool(annotations={"readOnlyHint": True})
def get_outdoor_conditions() -> Conditii:
    """Condițiile meteo exterioare din acest moment: temperatură, umiditate, vânt, descriere."""
    return _simulare(datetime.now().hour)


@mcp.tool(annotations={"readOnlyHint": True})
def get_forecast(
    hours: Annotated[int, Field(ge=1, le=24, description="Câte ore înainte (1-24).")],
) -> list[Conditii]:
    """Prognoza orară a condițiilor exterioare pentru următoarele ore."""
    acum = datetime.now().hour
    return [_simulare((acum + h) % 24) for h in range(1, hours + 1)]


@mcp.tool(annotations={"readOnlyHint": True})
def get_status() -> dict:
    """Starea serviciului meteo (verificare de funcționare)."""
    return {"serviciu": mcp.name, "ok": True, "ora_server": datetime.now().isoformat(timespec="seconds")}


if __name__ == "__main__":
    run_http(mcp, PORT, "Condiții meteo exterioare și prognoză orară pentru clădire.", "Meteo clădire")

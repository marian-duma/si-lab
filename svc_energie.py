"""Laborator 4 SI - serviciul de tarife la energie (date simulate) pentru clădirea inteligentă.

Rulare: python svc_energie.py   (port 8002)
Instrumentul `get_co2_intensity` este în test ("beta"): pornește dezactivat și se comută
la rulare cu o cerere POST la http://127.0.0.1:8002/admin/beta (vezi Partea B).
"""
from datetime import datetime
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from serviciu import run_http

PORT = 8002
# list_page_size=2: tools/list întoarce câte 2 instrumente pe pagină (paginare cu cursor)
mcp = FastMCP("ro.usv.si/energie", version="1.2.0", cache_ttl=30, list_page_size=2)


class Tarif(BaseModel):
    ora: int
    lei_kwh: float = Field(description="Prețul energiei, în lei/kWh.")
    zona: Literal["noapte", "zi", "vârf"]


def _tarif(ora: int) -> Tarif:
    if ora < 6 or ora >= 23:
        return Tarif(ora=ora, lei_kwh=0.62, zona="noapte")
    if 17 <= ora < 21:
        return Tarif(ora=ora, lei_kwh=1.48, zona="vârf")
    return Tarif(ora=ora, lei_kwh=0.97, zona="zi")


@mcp.tool(annotations={"readOnlyHint": True})
def get_tariff(
    hour: Annotated[int | None, Field(ge=0, le=23, description="Ora (0-23); lipsă = ora curentă.")] = None,
) -> Tarif:
    """Tariful energiei electrice (lei/kWh) la o anumită oră a zilei."""
    return _tarif(datetime.now().hour if hour is None else hour)


@mcp.tool(annotations={"readOnlyHint": True})
def cheapest_window(
    duration_h: Annotated[int, Field(ge=1, le=6, description="Durata necesară, în ore (1-6).")],
) -> dict:
    """Cel mai ieftin interval de `duration_h` ore consecutive din următoarele 24 de ore."""
    acum = datetime.now().hour
    variante = []
    for start in range(acum, acum + 24):
        ore = [(start + i) % 24 for i in range(duration_h)]
        variante.append((sum(_tarif(o).lei_kwh for o in ore) / duration_h, start % 24))
    cost, start = min(variante)
    return {"start": start, "sfarsit": (start + duration_h) % 24, "lei_kwh_mediu": round(cost, 3)}


@mcp.tool(annotations={"readOnlyHint": True})
def get_status() -> dict:
    """Starea serviciului de tarife (verificare de funcționare)."""
    return {"serviciu": mcp.name, "ok": True, "ora_server": datetime.now().isoformat(timespec="seconds")}


@mcp.tool(tags={"beta"}, annotations={"readOnlyHint": True})
def get_co2_intensity() -> dict:
    """Intensitatea estimată a emisiilor de CO2 ale energiei din rețea, în g/kWh (în test)."""
    ora = datetime.now().hour
    return {"ora": ora, "g_co2_kwh": 210 if 10 <= ora <= 16 else 290}


mcp.disable(tags={"beta"})
BETA = {"activ": False}


@mcp.custom_route("/admin/beta", methods=["POST"])
async def comuta_beta(request):
    """Rută de administrare (NU face parte din MCP): activează/dezactivează instrumentele beta."""
    BETA["activ"] = not BETA["activ"]
    (mcp.enable if BETA["activ"] else mcp.disable)(tags={"beta"})
    return JSONResponse({"beta": BETA["activ"]})


if __name__ == "__main__":
    run_http(mcp, PORT, "Tarife la energie pe ore și intervalul cel mai ieftin.", "Tarife energie")

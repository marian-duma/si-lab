"""Laborator 3 SI - serverul MCP al clădirii inteligente, versiunea 3.

Stratul MCP peste building.py: tipuri de intrare (inputSchema), tipuri de ieșire
(outputSchema + structuredContent), erori de execuție (ToolError) și două transporturi.

Pornire:
    python server.py          -> stdio (implicit; îl pornește clientul ca proces copil)
    python server.py http     -> Streamable HTTP pe http://127.0.0.1:8000/mcp
"""
import sys
from typing import Annotated, Literal, get_args

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from building import DEVICES, Building, BuildingError, Nivel

mcp = FastMCP("smart-building-demo", version="3.0")
cladire = Building()  # o singură clădire pentru tot procesul serverului

# Numele valide devin o enumerare în schema de intrare: clientul (și modelul) le vede.
DeviceName = Literal["lampa_led", "radiator", "aer_conditionat", "jaluzele", "ventilatie"]
if set(get_args(DeviceName)) != set(DEVICES):  # lista trebuie să rămână sincronizată cu building.py
    raise RuntimeError("Actualizați DeviceName în server.py după DEVICES din building.py.")

CITIRE = {"readOnlyHint": True}
MODIFICARE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}
DISTRUGERE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}


# ---------- Schemele de ieșire ----------

class DeviceInfo(BaseModel):
    nume: str
    categorie: str
    putere_w: int = Field(description="Puterea nominală, în wați.")
    note: str


class EnergyEstimate(BaseModel):
    nume: str
    ore: float
    energie_kwh: float


class ConflictCheck(BaseModel):
    nivel: Nivel
    descriere: str


class BuildingState(BaseModel):
    pornite: list[str] = Field(description="Dispozitivele pornite, în ordine alfabetică.")
    termostat_c: float = Field(description="Temperatura dorită, în °C.")


def _domeniu(fn, *args):
    """Traduce o eroare de domeniu într-o eroare de execuție MCP (isError: true)."""
    try:
        return fn(*args)
    except BuildingError as e:
        raise ToolError(str(e)) from e


# ---------- Instrumente de citire ----------

@mcp.tool(annotations=CITIRE)
def list_devices() -> list[str]:
    """Returnează numele tuturor dispozitivelor din clădire."""
    return cladire.device_names()


@mcp.tool(annotations=CITIRE)
def get_device_info(name: DeviceName) -> DeviceInfo:
    """Returnează informații despre un dispozitiv: categorie, putere în W, note."""
    return DeviceInfo(**_domeniu(cladire.device_info, name))


@mcp.tool(annotations=CITIRE)
def check_conflict(device_a: DeviceName, device_b: DeviceName) -> ConflictCheck:
    """Verifică dacă două dispozitive au un conflict de funcționare cunoscut."""
    nivel, descriere = _domeniu(cladire.conflict, device_a, device_b)
    return ConflictCheck(nivel=nivel, descriere=descriere)


@mcp.tool(annotations=CITIRE)
def estimate_energy(
    name: DeviceName,
    hours: Annotated[float, Field(gt=0, le=24, description="Durata de funcționare, în ore (0-24].")],
) -> EnergyEstimate:
    """Estimează energia consumată (kWh) de un dispozitiv care funcționează un număr de ore."""
    return EnergyEstimate(nume=name, ore=hours, energie_kwh=_domeniu(cladire.energy_kwh, name, hours))


@mcp.tool(annotations=CITIRE)
def get_building_state() -> BuildingState:
    """Returnează starea curentă a clădirii: dispozitivele pornite și termostatul."""
    return BuildingState(**cladire.state())


# ---------- Instrumente cu efecte ----------

@mcp.tool(annotations=MODIFICARE)
def set_device_state(name: DeviceName, on: bool) -> BuildingState:
    """Pornește (on=true) sau oprește (on=false) un dispozitiv și returnează noua stare.

    Refuză pornirea dacă ar crea un conflict de nivel RIDICAT cu un dispozitiv deja pornit.
    """
    _domeniu(cladire.set_device, name, on)
    return BuildingState(**cladire.state())


@mcp.tool(annotations=MODIFICARE)
def set_thermostat(
    temp_c: Annotated[float, Field(ge=10, le=30, description="Temperatura dorită, în °C (10-30).")],
) -> BuildingState:
    """Setează temperatura dorită a termostatului și returnează noua stare."""
    _domeniu(cladire.set_thermostat, temp_c)
    return BuildingState(**cladire.state())


@mcp.tool(annotations=DISTRUGERE)
def reset_building() -> BuildingState:
    """Oprește toate dispozitivele și readuce termostatul la 21 °C."""
    cladire.reset()
    return BuildingState(**cladire.state())


# ---------- Resursă și prompt (ca în laboratoarele anterioare) ----------

@mcp.resource("device://{name}/manual")
def manual(name: str) -> str:
    """Un manual (fictiv) de o linie, expus ca resursă."""
    info = DEVICES.get(name)
    return f"{name}: {info['categorie']}. {info['note']}" if info else f"Nu există manual pentru {name}."


@mcp.prompt
def energy_review(devices: str) -> str:
    """Șablon de prompt: cere unui LLM să analizeze o listă de dispozitive."""
    return (
        f"Analizează această listă de dispozitive: {devices}. "
        "Folosește instrumentele pentru a verifica conflictele și a estima consumul."
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        mcp.run(
            transport="http",
            host="127.0.0.1",             # doar local, nu 0.0.0.0
            port=8000,                    # adresa: http://127.0.0.1:8000/mcp
            host_origin_protection=True,  # verifică Host și Origin (implicit, în FastMCP, este oprită)
            show_banner=False,
        )
    else:
        mcp.run(show_banner=False)  # stdio

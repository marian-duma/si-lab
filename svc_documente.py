"""Laborator 6 SI - serverul MCP al documentelor clădirii (stdio).

Expune căutarea din rag.py ca instrument MCP, deci o poate folosi orice client MCP
(agentul, Inspector). Indexul se construiește înainte, cu: python index.py
Test în Inspector: npx @modelcontextprotocol/inspector --web --protocol-era modern python svc_documente.py
"""
import os
from typing import Annotated, Literal

os.environ.setdefault("FASTMCP_LOG_LEVEL", "WARNING")  # fără mesajul „Starting MCP server" în chat
from fastmcp import FastMCP  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from pydantic import BaseModel, Field

from rag import DOCUMENTE, Index

mcp = FastMCP("ro.usv.si/documente", version="1.0.0")
index = Index.incarca()


class Fragment(BaseModel):
    sursa: str = Field(description="Fișierul din care provine fragmentul; se citează în răspuns.")
    titlu: str
    text: str
    scor: float = Field(description="Cât de potrivit este fragmentul (mai mare = mai potrivit).")


@mcp.tool(annotations={"readOnlyHint": True})
def cauta(
    intrebare: str,
    k: Annotated[int, Field(ge=1, le=8, description="Câte fragmente se întorc.")] = 3,
    metoda: Literal["bm25", "embeddings"] = "embeddings",
) -> list[Fragment]:
    """Caută în documentele clădirii (manuale, proceduri, regulamente, program de funcționare)
    fragmentele cele mai potrivite pentru întrebare. Răspunsul trebuie să citeze sursa."""
    try:
        rezultate = index.cauta(intrebare, k=k, metoda=metoda)
    except ValueError as e:   # indexul a fost construit cu alt model de embeddings
        raise ToolError(str(e))
    return [Fragment(**{c: r[c] for c in ("sursa", "titlu", "text", "scor")}) for r in rezultate]


@mcp.resource("document://{nume}")
def document(nume: str) -> str:
    """Textul complet al unui document (ca resursa device://.../manual din Laboratorul 1)."""
    fisier = DOCUMENTE / nume
    if fisier.parent != DOCUMENTE or not fisier.exists():
        return f"Nu există documentul {nume}."
    return fisier.read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run(show_banner=False)

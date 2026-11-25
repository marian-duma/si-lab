"""Laborator 7 SI - agentul cu gardă.

Pornește de la agentul cu documente din Laboratorul 6 (agent_rag.py, neschimbat) și pune o gardă
(garda.py + politica.json) între model și instrumente. Modelul propune apelurile; garda decide.
Trei lucruri noi față de Lab. 6:
  - fiecare apel trece prin Garda.verifica() înainte de execuție (evenimentul "garda" în log);
  - agentul ține minte dacă în conversație a intrat text nesigur (contaminare);
  - agentul numără modificările făcute la fiecare întrebare (bugetul de acțiuni).
"""
import json

from agent_rag import AgentRAG
from garda import Garda


class AgentSigur(AgentRAG):
    def __init__(self, confirm=None, mode="eager", auto: bool = False):
        self.garda = Garda()
        self.intreaba = confirm          # întrebarea către utilizator (din chat.py)
        self._aprobat = False            # decizia finală pentru apelul curent
        # Agentul din Lab. 4 întreabă singur utilizatorul înainte de orice modificare.
        # Îi dăm în loc o funcție care întoarce decizia deja luată de gardă.
        super().__init__(confirm=lambda nume, args, distructiv: self._aprobat, mode=mode, auto=auto)

    def reset(self):
        super().reset()
        self.contaminat = False   # textul nesigur rămâne în istoric până la /reset
        self.modificari = 0

    async def imbogateste(self, intrebare: str):
        await super().imbogateste(intrebare)
        if self.auto:             # fragmentele din documente intră singure în prompt
            self.contaminat = True

    async def ask(self, text: str) -> str:
        self.modificari = 0       # bugetul se reînnoiește la fiecare întrebare
        return await super().ask(text)

    async def call_tool(self, call, pas: int) -> str:
        nume = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = None
        if args is None or nume not in self.flags:   # JSON invalid, meta-instrument, nume necunoscut:
            return await super().call_tool(call, pas)  # le tratează agentul din Lab. 4

        flags = self.flags[nume]
        d = self.garda.verifica(nume, args, flags, self.contaminat, self.modificari)
        self.log.write("garda", pas=pas, nume=nume, argumente=args, decizie=d.actiune,
                       motiv=d.motiv, contaminat=self.contaminat, modificari=self.modificari)

        if d.actiune == "interzis":
            self.log.write("apel", pas=pas, nume=nume, argumente=args)
            return self._rezultat(pas, nume, args, f"Blocat de politica de securitate: {d.motiv}.", True)
        if d.actiune == "confirmare":
            self._aprobat = bool(self.intreaba and self.intreaba(nume, args, flags["destructive"], d.motiv))
        else:
            self._aprobat = True

        rezultat = await super().call_tool(call, pas)   # execuția (și confirmarea) din Lab. 4
        if self._aprobat and not flags["read_only"]:
            self.modificari += 1
        if nume in self.garda.politica["surse_nesigure"]:
            self.contaminat = True
        return rezultat

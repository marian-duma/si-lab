"""Chatbot în linia de comandă, cu gardă pentru acțiunile agentului.
Rulare: python chat.py                (cu gardă: politica.json decide ce se execută)
        python chat.py --fara-garda   (agentul din Lab. 6, doar cu confirmarea din Lab. 2)
        python chat.py --auto         (documentele intră automat în prompt, ca în Lab. 6)
        python chat.py --lazy         (serviciile din catalog se descoperă la cerere, ca în Lab. 4)"""
import asyncio
import json
import sys

from openai import APIConnectionError, APIStatusError

from agent_rag import AgentRAG
from agent_sigur import AgentSigur


def cere_acord(nume: str, args: dict, distructiv: bool, motiv: str | None = None) -> bool:
    eticheta = " [DISTRUCTIV]" if distructiv else ""
    if motiv:
        print(f"  ! Garda cere confirmare: {motiv}.")
    raspuns = input(f"  ? Agentul vrea să ruleze {nume}({args}){eticheta}. Permiteți? [d/N] ")
    return raspuns.strip().lower() in ("d", "da", "y", "yes")


async def main():
    mod = "lazy" if "--lazy" in sys.argv else "eager"
    clasa = AgentRAG if "--fara-garda" in sys.argv else AgentSigur
    async with clasa(confirm=cere_acord, mode=mod, auto="--auto" in sys.argv) as agent:
        garda = getattr(agent, "garda", None)
        print(f"Furnizor: {agent.provider} | model: {agent.model} | "
              f"documente: {'automat' if agent.auto else 'la cerere'} | garda: {'DA' if garda else 'NU'}")
        print(f"Servicii conectate: {', '.join(agent.clients)}")
        print(f"Fișier de log: {agent.log.path}")
        print("Comenzi: /instrumente, /prompt, /politica, /reset, /iesire\n")
        while True:
            try:
                text = input("Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == "/iesire":
                break
            if text == "/reset":
                agent.reset()
                print("(conversație nouă)")
                continue
            if text == "/instrumente":
                print("  " + "\n  ".join(t["function"]["name"] for t in agent.tools))
                continue
            if text == "/prompt":
                print(agent.messages[0]["content"])
                continue
            if text == "/politica":
                if garda is None:
                    print("  (fără gardă)")
                else:
                    for cheie, valoare in garda.politica.items():
                        print(f"  {cheie}: {json.dumps(valoare, ensure_ascii=False)}")
                    print(f"  contaminat: {agent.contaminat} | modificări la ultima întrebare: {agent.modificari}")
                continue
            if not text:
                continue
            try:
                print("Agent:", await agent.ask(text), "\n")
            except APIStatusError as e:
                print(f"Eroare HTTP {e.status_code}: {str(e.body or e.message)[:200]}\n")
            except APIConnectionError:
                print("Nu mă pot conecta la model (server oprit sau fără internet).\n")


if __name__ == "__main__":
    asyncio.run(main())

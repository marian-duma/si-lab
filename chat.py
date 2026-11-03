"""Chatbot în linia de comandă, cu servicii descoperite dinamic.
Rulare: python chat.py          (modul eager)
        python chat.py --lazy   (modul lazy: modelul cere singur serviciile)"""
import asyncio
import sys

from openai import APIConnectionError, APIStatusError

from agent import Agent


def cere_acord(nume: str, args: dict, distructiv: bool) -> bool:
    eticheta = " [DISTRUCTIV]" if distructiv else ""
    raspuns = input(f"  ? Agentul vrea să ruleze {nume}({args}){eticheta}. Permiteți? [d/N] ")
    return raspuns.strip().lower() in ("d", "da", "y", "yes")


def afiseaza_servicii(agent: Agent):
    for key, s in agent.services.items():
        n = sum(1 for k, _ in agent.routes.values() if k == key)
        conectat = f"conectat, {n} instrumente" if key in agent.clients else "neconectat"
        print(f"  {key:<11} {s.stare:<13} {conectat:<26} {s.descriere[:50]}")


async def main():
    mod = "lazy" if "--lazy" in sys.argv else "eager"
    async with Agent(confirm=cere_acord, mode=mod) as agent:
        print(f"Furnizor: {agent.provider} | model: {agent.model} | mod: {agent.mode}")
        afiseaza_servicii(agent)
        print(f"Fișier de log: {agent.log.path}")
        print("Comenzi: /servicii, /instrumente, /descopera, /reset, /iesire\n")
        while True:
            try:
                text = input("Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == "/iesire":
                break
            if text == "/reset":
                agent.reset()
                print("(conversație nouă; serviciile conectate rămân conectate)")
                continue
            if text == "/servicii":
                afiseaza_servicii(agent)
                continue
            if text == "/instrumente":
                print("  " + "\n  ".join(t["function"]["name"] for t in agent.tools))
                continue
            if text == "/descopera":
                await agent.descopera()
                afiseaza_servicii(agent)
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

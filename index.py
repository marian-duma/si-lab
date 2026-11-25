"""Laborator 6 SI - construirea indexului și compararea căutărilor, din linia de comandă.

    python index.py                      construiește index.json din folderul documente/
    python index.py --fragmente          afișează fragmentele, fără să construiască indexul
    python index.py "Mi-e frig, ce fac?" caută cu ambele metode și afișează primele 3 fragmente
"""
import sys
import time

from rag import DOCUMENTE, EMB_PROVIDER, Index, fragmenteaza


def arata(rezultate: list[dict]):
    for r in rezultate:
        print(f"    {r['scor']:>7}  {r['id']:<28} {r['text'][:70]}...")


def main():
    if "--fragmente" in sys.argv:
        for fisier in sorted(DOCUMENTE.glob("*.md")):
            for f in fragmenteaza(fisier.read_text(encoding="utf-8"), fisier.name):
                print(f"{f['id']:<28} {len(f['text']):>4} car.  {f['titlu']}")
        return

    intrebari = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not intrebari:
        t0 = time.perf_counter()
        index = Index.construieste()
        index.salveaza()
        dim = len(index.vectori[0])
        print(f"Index: {len(index.fragmente)} fragmente din {len({f['sursa'] for f in index.fragmente})} documente")
        print(f"Embeddings: {index.embeddings}, {dim} dimensiuni, {time.perf_counter() - t0:.1f} s")
        return

    index = Index.incarca()
    for q in intrebari:
        print(f"Întrebare: {q}")
        print("  BM25 (cuvinte):")
        arata(index.cauta(q, metoda="bm25"))
        print(f"  Embeddings ({EMB_PROVIDER}):")
        try:
            arata(index.cauta(q, metoda="embeddings"))
        except ValueError as e:   # indexul a fost construit cu alt model de embeddings
            print(f"    Eroare: {e}")


if __name__ == "__main__":
    main()

"""Laborator 6 SI - recuperarea informației (RAG): fragmentare, BM25 și embeddings.

Modulul nu știe nimic despre agent: primește documente, construiește un index și caută în el.
  - fragmenteaza(): împarte un document Markdown în fragmente (după titluri, apoi după mărime);
  - BM25: căutarea lexicală (cuvinte comune, ponderate);
  - embed(): vectori de înțeles, cu Gemini sau cu varianta locală „mock" (fără rețea);
  - Index: fragmentele + vectorii lor, salvate în index.json; metoda cauta().
"""
import hashlib
import json
import math
import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AICI = Path(__file__).parent
DOCUMENTE = AICI / "documente"
FISIER_INDEX = AICI / "index.json"

MARIME = 400        # lungimea maximă a unui fragment, în caractere
SUPRAPUNERE = 80    # cam câte caractere se repetă între două fragmente consecutive (mai mic decât MARIME)

EMB_PROVIDER = os.environ.get("EMB_PROVIDER", "mock").lower()   # mock | gemini
EMB_MODEL = os.environ.get("EMB_MODEL", "gemini-embedding-001")
DIM_MOCK = 256


# ---------- Text ----------

def norm(text: str) -> str:
    """Litere mici, fără diacritice."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


# Cuvinte de legătură, prea frecvente ca să deosebească fragmentele (stop words).
STOP = set("a al ale am ar are as au ca cat ce cel cu da dar de din e este fi in la le mi nu o pe "
           "pentru pot sa sau se si sunt te un unei unui".split())


def cuvinte(text: str, fara_stop: bool = True) -> list[str]:
    """Cuvintele textului, normalizate; implicit fără cuvintele de legătură din STOP."""
    lista = re.findall(r"[a-z0-9]+", norm(text))
    return [c for c in lista if c not in STOP] if fara_stop else lista


# ---------- 1. Fragmentarea ----------

def fragmenteaza(text: str, sursa: str, marime: int = MARIME, suprapunere: int = SUPRAPUNERE) -> list[dict]:
    """Împarte un document Markdown în fragmente. Fiecare secțiune (## Titlu) devine unul sau mai
    multe fragmente de cel mult `marime` caractere, tăiate între cuvinte. Fragmentele consecutive
    ale aceleiași secțiuni repetă ultimele ~`suprapunere` caractere, ca o frază tăiată să apară
    întreagă măcar într-unul. Fragmentul păstrează titlul documentului și al secțiunii."""
    titlu_doc = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), sursa)
    sectiuni = re.split(r"^## ", text, flags=re.M)[1:] or [text]
    fragmente = []
    for s in sectiuni:
        titlu, _, corp = s.partition("\n")
        for bucata in _bucati(corp.split(), marime, suprapunere):
            fragmente.append({
                "id": f"{sursa}#{len(fragmente) + 1}",
                "sursa": sursa,
                "titlu": f"{titlu_doc} / {titlu.strip()}",
                "text": bucata,
            })
    return fragmente


def _bucati(cuv: list[str], marime: int, suprapunere: int) -> list[str]:
    """Grupează cuvintele în bucăți de cel mult `marime` caractere, cu suprapunere."""
    bucati, curent = [], []
    for c in cuv:
        if curent and len(" ".join(curent + [c])) > marime:
            bucati.append(" ".join(curent))
            pastrate = []                     # ultimele cuvinte, cât încap în `suprapunere`
            while curent and len(" ".join([curent[-1]] + pastrate)) <= suprapunere:
                pastrate.insert(0, curent.pop())
            curent = pastrate
        curent.append(c)
    if curent:
        bucati.append(" ".join(curent))
    return bucati


# ---------- 2. Căutarea lexicală: BM25 ----------

class BM25:
    """BM25 (Robertson și Zaragoza, 2009), scris de mână ca să se vadă formula.
    scor(q, d) = sumă, pe cuvintele lui q, din IDF(c) * f * (k1 + 1) / (f + k1 * (1 - b + b * |d| / L))
      f = de câte ori apare cuvântul c în fragmentul d;  |d| = lungimea lui d;  L = lungimea medie."""

    def __init__(self, texte: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [cuvinte(t) for t in texte]
        self.L = sum(map(len, self.docs)) / len(self.docs)
        n = len(self.docs)
        df = {}
        for d in self.docs:
            for c in set(d):
                df[c] = df.get(c, 0) + 1
        # IDF: un cuvânt rar (în puține fragmente) contează mai mult decât unul frecvent
        self.idf = {c: math.log(1 + (n - f + 0.5) / (f + 0.5)) for c, f in df.items()}

    def scoruri(self, intrebare: str) -> list[float]:
        q = cuvinte(intrebare)
        rezultat = []
        for d in self.docs:
            s = 0.0
            for c in q:
                f = d.count(c)
                if f:
                    s += self.idf[c] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.L))
            rezultat.append(s)
        return rezultat


# ---------- 3. Căutarea semantică: embeddings ----------

def _embed_mock(text: str) -> list[float]:
    """Vector local, fără model: numără trigramele de litere (hash în DIM_MOCK poziții).
    Seamănă texte cu litere comune, dar NU știe că „frig" și „încălzire" sunt înrudite."""
    t = f"  {norm(text)}  "
    v = [0.0] * DIM_MOCK
    for i in range(len(t) - 2):
        h = int(hashlib.md5(t[i:i + 3].encode()).hexdigest(), 16)
        v[h % DIM_MOCK] += 1.0
    return v


def _embed_gemini(texte: list[str]) -> list[list[float]]:
    """Embeddings Gemini prin API-ul compatibil OpenAI (cheia din .env, ca în Lab. 1)."""
    from openai import OpenAI
    from llm import PROVIDERS
    client = OpenAI(base_url=PROVIDERS["gemini"]["base_url"], api_key=os.environ["GEMINI_API_KEY"])
    vectori = []
    for i in range(0, len(texte), 50):             # câte 50 de texte într-o cerere
        grup = texte[i:i + 50]
        try:
            r = client.embeddings.create(model=EMB_MODEL, input=grup)
            if len(r.data) != len(grup):           # un singur vector pentru tot grupul: nu ne ajută
                raise ValueError(f"{len(r.data)} vectori pentru {len(grup)} texte")
            vectori += [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
        except Exception as e:                     # dacă lista nu este acceptată: câte un text
            print(f"  (embeddings în grup refuzate: {str(e)[:80]}; trimit câte un text)")
            for t in grup:
                vectori.append(client.embeddings.create(model=EMB_MODEL, input=t).data[0].embedding)
    return vectori


def normalizeaza(v: list[float]) -> list[float]:
    lung = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / lung for x in v]


def embed(texte: list[str]) -> list[list[float]]:
    """Vectorii (de lungime 1) pentru o listă de texte, cu furnizorul din EMB_PROVIDER."""
    if EMB_PROVIDER == "gemini":
        vectori = _embed_gemini(texte)
    else:
        vectori = [_embed_mock(t) for t in texte]
    return [normalizeaza(v) for v in vectori]


def model_embeddings() -> str:
    """Numele modelului de embeddings folosit acum, de exemplu „mock/trigrame" sau „gemini/gemini-embedding-001"."""
    return f"{EMB_PROVIDER}/{EMB_MODEL if EMB_PROVIDER == 'gemini' else 'trigrame'}"


def cosinus(a: list[float], b: list[float]) -> float:
    """Asemănarea a doi vectori de lungime 1: produsul scalar (1 = aceeași direcție)."""
    return sum(x * y for x, y in zip(a, b))


# ---------- 4. Indexul ----------

class Index:
    """Fragmentele și vectorii lor (salvați în index.json). Indexul BM25 se recalculează la încărcare."""

    def __init__(self, fragmente: list[dict], vectori: list[list[float]], embeddings: str):
        self.fragmente, self.vectori, self.embeddings = fragmente, vectori, embeddings
        self.bm25 = BM25([f"{f['titlu']} {f['text']}" for f in fragmente])

    @classmethod
    def construieste(cls, folder: Path = DOCUMENTE) -> "Index":
        fragmente = []
        for fisier in sorted(folder.glob("*.md")):
            fragmente += fragmenteaza(fisier.read_text(encoding="utf-8"), fisier.name)
        vectori = embed([f"{f['titlu']}. {f['text']}" for f in fragmente])
        return cls(fragmente, vectori, model_embeddings())

    def salveaza(self, fisier: Path = FISIER_INDEX):
        date = {"embeddings": self.embeddings, "fragmente": self.fragmente, "vectori": self.vectori}
        fisier.write_text(json.dumps(date, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def incarca(cls, fisier: Path = FISIER_INDEX) -> "Index":
        if not fisier.exists():
            raise SystemExit("Lipsește index.json. Rulați întâi: python index.py")
        date = json.loads(fisier.read_text(encoding="utf-8"))
        return cls(date["fragmente"], date["vectori"], date["embeddings"])

    def cauta(self, intrebare: str, k: int = 3, metoda: str = "embeddings") -> list[dict]:
        """Primele k fragmente, cu scorul lor. metoda: bm25 | embeddings."""
        if metoda == "bm25":
            scoruri = self.bm25.scoruri(intrebare)
        else:
            if self.embeddings != model_embeddings():  # întrebarea și fragmentele: același model
                raise ValueError(f"Indexul are embeddings {self.embeddings}, dar acum se folosește "
                                 f"{model_embeddings()}. Reconstruiți indexul: python index.py")
            q = embed([intrebare])[0]
            scoruri = [cosinus(q, v) for v in self.vectori]
        ordine = sorted(range(len(scoruri)), key=lambda i: scoruri[i], reverse=True)[:k]
        if metoda == "bm25":   # scor 0 = niciun cuvânt comun: fragmentul nu este relevant
            ordine = [i for i in ordine if scoruri[i] > 0]
        return [{**self.fragmente[i], "scor": round(scoruri[i], 3)} for i in ordine]

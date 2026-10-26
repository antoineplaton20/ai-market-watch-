"""Carte de couverture du corpus R8 : chaque méthode du lexique comptée par type de source ; puis les expressions
fréquentes du corpus qui ne correspondent à AUCUNE méthode connue (pour trouver ce qui manque)."""
import glob, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexique import METHODES
C = sys.argv[1]
docs = []
d = json.load(open(f"{C}/podcasts.json", encoding="utf-8"))
docs += [("podcasts (notes)", e["titre"] + " . " + e["notes"]) for e in d["episodes"]]
docs += [("vidéos Odysee", (v.get("title") or "") + " . " + (v.get("description") or "")[:3000])
         for v in json.load(open(f"{C}/odysee.json", encoding="utf-8"))]
for x in json.load(open(f"{C}/forums.json", encoding="utf-8")):
    s = x["source"].split("/")[0]
    s = {"reddit": "forums (Reddit)", "stackexchange": "forums (Stack Exchange)", "hackernews": "forums (Hacker News)",
         "mql5": "codes MQL5", "arxiv": "recherche (arXiv)", "maison": "grandes maisons"}.get(s, s)
    docs.append((s, x["titre"] + " . " + x["texte"]))
docs += [("Quantpedia", q["titre"] + " . " + " ".join(q["puces"])) for q in json.load(open(f"{C}/quantpedia.json", encoding="utf-8"))]
for nom in ("discours2.json", "discours.json"):
    if os.path.exists(f"{C}/{nom}"):
        docs += [("discours (PDG, investisseurs)", x["titre"] + " . " + x["texte"]) for x in json.load(open(f"{C}/{nom}", encoding="utf-8"))]
        break
if os.path.exists(f"{C}/tradingrush.json"):
    docs += [("vidéos Trading Rush (textes)", x["titre"] + " . " + x["texte"]) for x in json.load(open(f"{C}/tradingrush.json", encoding="utf-8"))]
if os.path.exists(f"{C}/tradingview.json"):
    docs += [("scripts TradingView", x["nom"] + " . " + x["description"]) for x in json.load(open(f"{C}/tradingview.json", encoding="utf-8"))]
for f in glob.glob(f"{C}/transcriptions/*.json"):
    x = json.load(open(f, encoding="utf-8"))
    docs.append(("audio transcrit (Whisper)", (x.get("titre") or "") + " . " + x["texte"]))
types = Counter(t for t, _ in docs)
print("CORPUS :", len(docs), "documents ;", ", ".join(f"{t} {n}" for t, n in types.most_common()))
motifs = {m: re.compile(r, re.I) for m, (r, _) in METHODES.items()}
compte = defaultdict(Counter)
for t, texte in docs:
    for m, rx in motifs.items():
        if rx.search(texte):
            compte[m][t] += 1
print("\nMÉTHODE (déjà testée ?) : documents qui la citent, par type de source")
for m in sorted(METHODES, key=lambda m: -sum(compte[m].values())):
    tot = sum(compte[m].values())
    print(f"{m[:44]:44} {METHODES[m][1][:28]:28} {tot:6} | " + ", ".join(f"{k.split(' ')[0]} {v}" for k, v in compte[m].most_common(4)))
# expressions inconnues
contexte = re.compile(r"strateg|system|setup|indicator|edge|backtest|signal|pattern|method|technique|rule|stratégie|méthode", re.I)
connus = re.compile("|".join(f"(?:{r})" for r, _ in METHODES.values()), re.I)
vides = set("the a an of and or to in for on with is are be how my your this that it at by from as we you i our what why when who can will do not best top new trading trade trader traders strategy strategies system systems market markets stock stocks forex crypto bitcoin price money make made using use beginners beginner simple easy guide full course part episode live day daily week weekly today 2020 2021 2022 2023 2024 2025 2026 vs one two three 1 2 3 5 10 100 it's don't get just about more than most all any into up out so if no".split())
ngr = Counter()
for t, texte in docs:
    if t.startswith("podcasts") or t.startswith("vidéos") or t.startswith("forums") or t.startswith("codes"):
        titre = texte.split(" . ")[0].lower()
        if not contexte.search(texte[:600]):
            continue
        mots = [w for w in re.findall(r"[a-zà-ÿ0-9%']+", titre)]
        for n in (2, 3):
            for i in range(len(mots) - n + 1):
                g = mots[i:i + n]
                if g[0] in vides or g[-1] in vides:
                    continue
                ex = " ".join(g)
                if not connus.search(ex):
                    ngr[ex] += 1
print("\nEXPRESSIONS FRÉQUENTES DES TITRES, HORS LEXIQUE (à relire pour trouver une méthode oubliée)")
print(" ; ".join(f"{g} ({n})" for g, n in ngr.most_common(400)))

"""Phrases « règles » des transcriptions (discours de PDG et d'investisseurs, podcasts transcrits) : pour relire ce que
disent les meilleurs, et repérer une méthode testable oubliée."""
import glob, json, re, sys
from collections import Counter
C = sys.argv[1]
docs = []
for nom in ("discours2.json", "discours.json"):
    try:
        docs += [("discours", x["titre"], x["texte"]) for x in json.load(open(f"{C}/{nom}", encoding="utf-8"))]
        break
    except FileNotFoundError:
        pass
for f in glob.glob(f"{C}/transcriptions/*.json"):
    x = json.load(open(f, encoding="utf-8"))
    docs.append(("audio", (x.get("podcast") or "") + " | " + (x.get("titre") or ""), x["texte"]))
REGLE = re.compile(r"\b(i|we) (buy|sell|enter|exit|get out|cut|add|trade|look for|wait for|only)\b|\bmy (rule|strategy|system|edge|setup|stop)\b|"
                   r"\bthe (rule|key|secret|edge) (is|was)\b|\bstop[- ]loss\b|\bposition siz|\btrend follow|\bbreakout|"
                   r"\bmean revers|\bmoving average\b|\brisk (per trade|management)\b|\bnever (average|add to a loser|risk)\b|"
                   r"\bwhen (the market|price|it) (breaks|crosses|closes)\b", re.I)
sortie = []
themes = Counter()
for typ, titre, texte in docs:
    phrases = re.split(r"(?<=[.!?])\s+", texte)
    bons = [p.strip() for p in phrases if 40 < len(p) < 400 and REGLE.search(p)]
    for p in bons[:6]:
        sortie.append((typ, titre[:70], p))
    for m in REGLE.findall(texte):
        themes[" ".join(x for x in m if x).lower()] += 1
print(len(docs), "documents ;", len(sortie), "phrases retenues")
print("thèmes les plus fréquents :", themes.most_common(40))
for typ, titre, p in sortie:
    print(f"[{typ}] {titre} :: {p}")

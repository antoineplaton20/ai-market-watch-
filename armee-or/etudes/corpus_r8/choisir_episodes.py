"""Choix des épisodes de podcasts à transcrire (Whisper) : quotas par podcast de traders et de gérants reconnus, puis
les épisodes dont le titre et les notes citent le plus de grands noms et de méthodes.

Usage : python choisir_episodes.py PODCASTS.json SORTIE.json
"""
import json, re, sys
from collections import Counter
E = json.load(open(sys.argv[1], encoding="utf-8"))["episodes"]
CIBLES = {  # podcast -> (langue, quota)
    "Chat With Traders": ("en", 30), "Top Traders Unplugged": ("en", 25), "The Meb Faber Show - Better Investing": ("en", 12),
    "Invest Like the Best with Patrick O'Shaughnessy": ("en", 10),
    "The Investor's Podcast (We Study Billionaires)  - The Investor’s Podcast Network": ("en", 8),
    "Capital Allocators – Inside the Institutional Investment Industry": ("en", 6), "Real Vision: Finance & Investing": ("en", 10),
    "The Pain Trade Podcast": ("en", 5), "Trader Mindset": ("en", 4), "The Trading Coach Podcast": ("en", 4),
    "Global Market Insights - Forex, Futures, Stocks": ("en", 5), "ITM Trading Podcast": ("en", 4),
    "SMART BOURSE": ("fr", 6), "BFM Bourse": ("fr", 4), "Tout pour investir": ("fr", 5), "La Chronique Bourse": ("fr", 3),
}
autres = [p for p in Counter(e["podcast"] for e in E) if p and re.search(
    r"better system trader|flirting with models|macro ?voices|odd lots|masters in business|excess returns|animal spirits|"
    r"market huddle|futures radio|algo|quant|systematic|trend following|market wizards", p, re.I)]
for p in autres:
    CIBLES.setdefault(p, ("en", 6))
NOMS = (r"tudor jones|druckenmiller|seykota|raschke|minervini|brandt|schwager|richard dennis|eckhardt|harding|covel|"
        r"curtis faith|hite|clenow|ernest chan|lopez de prado|carver|antonacci|faber|asness|simons|dalio|soros|livermore|"
        r"weinstein|o'neil|williams|crabel|bandy|connors|kaufman|chan|taleb|spitznagel|marks|buffett|munger|griffin|dimon|"
        r"huang|nvidia|musk")
MOTS = (r"trend follow|breakout|momentum|mean reversion|system|backtest|edge|setup|gold|forex|futures|scalp|order flow|"
        r"volume profile|vwap|price action|risk management|position siz|quant|algorithm|machine learning|volatility|carry|"
        r"macro|commodit|turtle|stratégie|trading|or |bourse")


def score(e):
    t = (e["titre"] + " " + e["notes"][:1500]).lower()
    return 3 * len(set(re.findall(NOMS, t))) + len(set(re.findall(MOTS, t)))


choix = []
for p, (langue, quota) in CIBLES.items():
    eps = sorted((e for e in E if e["podcast"] == p and e["audio"]), key=score, reverse=True)
    vus = set()
    for e in eps:
        if len([c for c in choix if c["podcast"] == p]) >= quota:
            break
        if e["titre"] in vus:
            continue
        vus.add(e["titre"])
        choix.append({"podcast": p, "titre": e["titre"], "date": e["date"], "audio": e["audio"], "langue": langue,
                      "score": score(e), "notes": e["notes"][:3000]})
json.dump(choix, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(choix), "épisodes choisis dans", len(set(c["podcast"] for c in choix)), "podcasts")

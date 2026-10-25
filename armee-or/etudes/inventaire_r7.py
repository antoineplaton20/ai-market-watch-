"""R7 (25/10/2026) : inventaire des vidéos de trading les plus vues sur YouTube et carte de couverture par famille.

1. Recherche interne de YouTube (la page de résultats, sans compte), triée par nombre de vues, 5 pages (≈ 100 vidéos)
   pour chacune des requêtes de etudes/requetes_r7.txt (anglais et français) ; vidéos dédoublonnées.
2. Chaque vidéo rangée dans une ou plusieurs familles de méthodes d'après son titre et son extrait ; les vidéos
   « non classées » les plus vues sont relues à la main pour trouver une famille oubliée.
YouTube refuse les sous-titres aux serveurs (« confirmez que vous n'êtes pas un robot ») : les règles testées sont la
version écrite la plus répandue de chaque méthode (etudes/catalogue_r7.py).

Usage : python etudes/inventaire_r7.py REQUETES.txt SORTIE.json SORTIE.csv
"""
import csv, json, re, sys, time, urllib.request
from collections import defaultdict
H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
CTX = {"client": {"clientName": "WEB", "clientVersion": "2.20251020.01.00", "hl": "en", "gl": "US"}}
def post(corps):
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
                                 data=json.dumps({"context": CTX, **corps}).encode(), headers=H)
    return json.loads(urllib.request.urlopen(req, timeout=40).read())
def extraire(x, out, cont):
    if isinstance(x, dict):
        if "videoRenderer" in x:
            v = x["videoRenderer"]
            vues = (v.get("viewCountText") or {}).get("simpleText", "")
            snip = " ".join("".join(r.get("text", "") for r in s.get("snippetText", {}).get("runs", []))
                            for s in v.get("detailedMetadataSnippets", []))
            out.append({"id": v["videoId"], "titre": "".join(r["text"] for r in v["title"]["runs"]),
                        "chaine": "".join(r["text"] for r in (v.get("ownerText") or {}).get("runs", [])),
                        "vues": int(re.sub(r"\D", "", vues) or 0), "duree": (v.get("lengthText") or {}).get("simpleText", ""),
                        "date": (v.get("publishedTimeText") or {}).get("simpleText", ""), "extrait": snip})
        if "continuationCommand" in x:
            cont.append(x["continuationCommand"]["token"])
        for y in x.values(): extraire(y, out, cont)
    elif isinstance(x, list):
        for y in x: extraire(y, out, cont)
def recherche(q, pages=5, tri="CAM="):
    res, cont = [], []
    extraire(post({"query": q, "params": tri}), res, cont)
    for _ in range(pages - 1):
        if not cont: break
        time.sleep(0.8)
        out, c2 = [], []
        extraire(post({"continuation": cont[-1]}), out, c2)
        res += out; cont = c2
    return res
FAMILLES = [
 ("hors sujet", r"nursery|kids song|cocomelon|wiggles|roblox|minecraft|resonance|wormhole|lyrical|punjabi song|fibonacci sequence|golden ratio|crash course economics|roulette|spins|casino|blackjack|adopt me|\bturtle\b(?!.*trad)|head,? shoulders,? knees"),
 ("options", r"\boption|call and put|\bf&o\b|option chain|straddle|iron condor|covered call|theta"),
 ("binaires / signaux / copie", r"binary|quotex|pocket ?option|olymp|iq option|expert ?option|signal (bot|accuracy)|copy ?trad|buy sell signal|100% (profit|win)|signals? group"),
 ("ICT / smart money", r"\bict\b|smart money|\bsmc\b|order ?block|fair value gap|\bfvg\b|liquidity|break of structure|\bbos\b|choch|change of character|silver bullet|judas|power of 3|\bamd\b|killzone|inducement|mitigation|breaker|premium.?discount|\bote\b|daily bias|market maker"),
 ("offre et demande", r"supply (and|&) demand|demand (and|&) supply|offre et demande"),
 ("chandeliers", r"candlestick|candle|engulfing|hammer|doji|pin ?bar|morning star|harami|marubozu|three white|bougie|chandelier|inside bar|outside bar|three line strike"),
 ("figures chartistes", r"chart pattern|head and shoulders|double (top|bottom)|triangle|flag pattern|wedge|cup and handle|pennant|figures? chartiste|rectangle pattern"),
 ("supports / résistances / lignes", r"support|resistance|trend ?line|key level|zone|breakout|false break|retest|fakeout|cassure|ligne de tendance"),
 ("Fibonacci / Elliott / harmoniques", r"fibonacci|fib |golden pocket|elliott|harmonic|gartley|\bbat pattern|butterfly|crab pattern|abcd"),
 ("moyennes mobiles", r"moving average|\bema\b|\bsma\b|\bdma\b|golden cross|death cross|\d+ ?ema|moyenne mobile|crossover"),
 ("MACD", r"macd"),
 ("RSI / stochastique / oscillateurs", r"\brsi\b|stochastic|divergence|oscillat|williams|\bcci\b|\bmfi\b|momentum indicator"),
 ("Bollinger / Keltner / volatilité", r"bollinger|keltner|squeeze|\batr\b|volatility|donchian"),
 ("VWAP / volume / flux d'ordres", r"vwap|volume|order ?flow|footprint|delta|tape reading|level 2|dom\b|market profile|auction"),
 ("Ichimoku / SuperTrend / SAR / ADX / Heikin Ashi", r"ichimoku|supertrend|super trend|parabolic|\bsar\b|\badx\b|heikin|heiken|renko|pivot point|cpr\b"),
 ("séances / cassure d'ouverture", r"london|new york|\bny\b|asian|session|opening range|\borb\b|9[.:]?20|first (5|15|30) min|open(ing)? (bell|drive)|market open"),
 ("Wyckoff / structure de marché", r"wyckoff|market structure|accumulation|distribution|structure de march"),
 ("Turtles / suivi de tendance", r"turtle|trend follow|donchian|suivi de tendance"),
 ("retour à la moyenne / paires", r"mean reversion|pairs? trad|arbitrage|statistical arb|cointegra"),
 ("grille / martingale / couverture", r"grid|martingale|hedg|averaging down|dca bot"),
 ("annonces / fondamental", r"\bnews\b|nfp|cpi|fomc|earnings|fundamental|interest rate|carry"),
 ("saisonnalité", r"season|halloween|monthly pattern|day of the week|turn of the month"),
 ("robots / IA / algorithmique", r"\bbot\b|robot|\bai\b|chatgpt|claude|gpt|algo|machine learning|python|pine script|expert advisor|\bea\b|automat|quant|backtest|tradingview indicator|best indicator"),
 ("multi-unités / analyse descendante", r"multi.?time ?frame|top.?down|mtf|multiple time ?frame"),
 ("gestion du risque / psychologie", r"risk|psycholog|position siz|money management|discipline|mindset|journal|gestion du risque"),
 ("scalping (général)", r"scalp"),
 ("cours généraux / débutants", r"beginner|course|full tutorial|masterclass|learn|débutant|cours|formation|how to (start|read)|explained|guide|basics|introduction|mentorship|episode|lecture|boot ?camp|part \d"),
]
def classer(v):
    t = (v["titre"] + " " + v.get("extrait", "")).lower()
    out = [nom for nom, motif in FAMILLES if re.search(motif, t)]
    if "hors sujet" in out:
        return ["hors sujet"]
    return out or ["non classé"]


if __name__ == "__main__":
    requetes = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    vus = {}
    for k, q in enumerate(requetes):
        for essai in range(3):
            try:
                for v in recherche(q):
                    if v["id"] in vus:
                        vus[v["id"]]["requetes"].append(q)
                    else:
                        v["requetes"] = [q]
                        vus[v["id"]] = v
                break
            except Exception as ex:
                print("nouvel essai", q, ex, flush=True)
                time.sleep(10 * (essai + 1))
        time.sleep(1.0)
    liste = sorted(vus.values(), key=lambda v: -v["vues"])
    vues, nb = defaultdict(int), defaultdict(int)
    for v in liste:
        v["familles"] = classer(v)
        for f in v["familles"]:
            vues[f] += v["vues"]
            nb[f] += 1
    json.dump(liste, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    with open(sys.argv[3], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "vues", "chaine", "titre", "familles"])
        for v in liste:
            w.writerow([v["id"], v["vues"], v["chaine"], v["titre"], " ; ".join(v["familles"])])
    print(f"{len(requetes)} requêtes, {len(liste)} vidéos distinctes, {sum(v['vues'] for v in liste) // 10**6} M vues")
    for f in sorted(vues, key=lambda f: -vues[f]):
        print(f"{f:48} {nb[f]:5} vidéos {vues[f] / 1e6:8.1f} M vues")

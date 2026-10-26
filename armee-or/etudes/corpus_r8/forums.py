"""Forums et sites : Reddit (flux RSS des meilleurs messages), Stack Exchange (finance quantitative), Hacker News,
codebase MQL5, arXiv (finance quantitative), pages de recherche des grandes maisons. Texte brut, source et date."""
import html, json, re, sys, time, urllib.parse, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"
def get(u, t=40, ua=UA):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": ua}), timeout=t).read().decode("utf-8", "replace")
def nettoie(x):
    x = re.sub(r"<script.*?</script>|<style.*?</style>", " ", x or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(x)))).strip()
docs = []
def ajoute(source, titre, texte, url="", date="", score=None, extra=None):
    docs.append({"source": source, "titre": titre, "texte": texte[:20000], "url": url, "date": date, "score": score,
                 **(extra or {})})
# 1. Reddit
SUBS = ["algotrading", "Daytrading", "Forex", "trading", "stocks", "wallstreetbets", "investing", "options", "Gold",
        "CryptoCurrency", "Bitcoin", "quant", "FuturesTrading", "RealDayTrading", "swingtrading", "technicalanalysis",
        "StockMarket", "ValueInvesting", "SecurityAnalysis", "Commodities", "Silverbugs", "Economics", "finance",
        "vosfinances", "Bogleheads", "thetagang", "pennystocks", "Trading212", "ICT_Trading", "Smartmoneyconcepts"]
for sub in SUBS:
    for t in ("all", "year", "month"):
        try:
            x = get(f"https://www.reddit.com/r/{sub}/top/.rss?t={t}&limit=100", ua="armee-or-recherche/1.0")
        except Exception as ex:
            print("reddit", sub, t, ex, flush=True); time.sleep(10); continue
        for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
            ti = re.search(r"<title>(.*?)</title>", e, re.S); co = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
            li = re.search(r'<link href="([^"]+)"', e); da = re.search(r"<published>(.*?)</published>", e)
            ajoute("reddit/" + sub, nettoie(ti.group(1)) if ti else "", nettoie(co.group(1)) if co else "",
                   li.group(1) if li else "", da.group(1) if da else "", extra={"fenetre": t})
        time.sleep(2.5)
    print("reddit", sub, len(docs), flush=True)
# 2. Stack Exchange
for site in ("quant", "money"):
    for page in range(1, 6):
        try:
            d = json.loads(get(f"https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&site={site}&pagesize=100&page={page}&filter=withbody"))
        except Exception as ex:
            print("stack", site, ex); break
        for q in d.get("items", []):
            ajoute("stackexchange/" + site, nettoie(q["title"]), nettoie(q.get("body", "")), q.get("link", ""),
                   str(q.get("creation_date", "")), q.get("score"))
        time.sleep(1.5)
        if not d.get("has_more"):
            break
print("stack", len(docs), flush=True)
# 3. Hacker News
for q in ("trading strategy", "algorithmic trading", "quantitative trading", "backtest", "hedge fund", "day trading",
          "trend following", "market making", "high frequency trading", "gold price", "forex", "renaissance technologies"):
    try:
        d = json.loads(get("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({"query": q, "tags": "story", "hitsPerPage": 100})))
    except Exception as ex:
        print("hn", q, ex); continue
    for h in d.get("hits", []):
        ajoute("hackernews", h.get("title") or "", nettoie(h.get("story_text") or ""), h.get("url") or "",
               h.get("created_at", ""), h.get("points"))
    time.sleep(1)
print("hn", len(docs), flush=True)
# 4. MQL5
for genre, n in (("experts", 30), ("indicators", 15)):
    for p in range(1, n + 1):
        try:
            x = get(f"https://www.mql5.com/en/code/mt5/{genre}" + (f"/page{p}" if p > 1 else ""))
        except Exception as ex:
            print("mql5", genre, p, ex); break
        for bloc in re.findall(r'<div class="code-tile.*?</div>\s*</div>\s*</div>', x, re.S) or re.findall(r'<a href="(/en/code/\d+)"[^>]*>(.*?)</a>', x, re.S):
            if isinstance(bloc, tuple):
                ajoute("mql5/" + genre, nettoie(bloc[1]), "", "https://www.mql5.com" + bloc[0])
            else:
                ajoute("mql5/" + genre, nettoie(bloc)[:200], nettoie(bloc))
        time.sleep(1.2)
print("mql5", len(docs), flush=True)
# 5. arXiv
for q in ("trading strategy", "momentum", "trend following", "mean reversion", "technical analysis", "gold",
          "foreign exchange", "cryptocurrency trading", "deep learning trading", "reinforcement learning trading",
          "high frequency", "market microstructure", "volatility", "portfolio"):
    try:
        x = get("http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": f'all:"{q}" AND (cat:q-fin.TR OR cat:q-fin.PM OR cat:q-fin.ST OR cat:q-fin.CP)',
             "max_results": 200, "sortBy": "relevance"}), t=90)
    except Exception as ex:
        print("arxiv", q, ex); continue
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        ti = re.search(r"<title>(.*?)</title>", e, re.S); ab = re.search(r"<summary>(.*?)</summary>", e, re.S)
        li = re.search(r"<id>(.*?)</id>", e); da = re.search(r"<published>(.*?)</published>", e)
        ajoute("arxiv", nettoie(ti.group(1)), nettoie(ab.group(1)) if ab else "", li.group(1) if li else "",
               da.group(1) if da else "", extra={"requete": q})
    time.sleep(3.5)
print("arxiv", len(docs), flush=True)
# 6. Grandes maisons
for nom, u in (("AQR", "https://www.aqr.com/Insights/Research"), ("Man Group", "https://www.man.com/maninstitute"),
               ("Two Sigma", "https://www.twosigma.com/articles/"),
               ("Bridgewater", "https://www.bridgewater.com/research-and-insights"),
               ("Robeco", "https://www.robeco.com/en-int/insights"),
               ("Research Affiliates", "https://www.researchaffiliates.com/publications"),
               ("GMO", "https://www.gmo.com/americas/research-library/")):
    try:
        x = get(u)
    except Exception as ex:
        print(nom, ex); continue
    liens = re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', x, re.S)
    for lien, titre in liens:
        t_ = nettoie(titre)
        if 25 <= len(t_) <= 200:
            ajoute("maison/" + nom, t_, "", urllib.parse.urljoin(u, lien))
    print(nom, len(docs), flush=True)
    time.sleep(1)
json.dump(docs, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
from collections import Counter
print(Counter(d["source"].split("/")[0] for d in docs))

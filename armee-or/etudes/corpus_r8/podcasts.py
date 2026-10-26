"""Podcasts : annuaire Apple (recherche publique), flux RSS, liste des épisodes avec leurs notes (texte gratuit)."""
import html, json, re, sys, time, urllib.parse, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"}
def get(u, t=40):
    return urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=t).read()
TERMES = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
flux = {}
for terme in TERMES:
    for pays in ("us", "fr"):
        try:
            d = json.loads(get("https://itunes.apple.com/search?" + urllib.parse.urlencode(
                {"term": terme, "entity": "podcast", "limit": 50, "country": pays})))
        except Exception as ex:
            print("échec", terme, ex, flush=True); time.sleep(5); continue
        for r in d.get("results", []):
            if r.get("feedUrl"):
                f = flux.setdefault(r["feedUrl"], {"nom": r.get("collectionName"), "auteur": r.get("artistName"),
                                                   "episodes_annonces": r.get("trackCount"), "genres": r.get("genres"),
                                                   "termes": []})
                f["termes"].append(terme)
        time.sleep(1.2)
print(len(flux), "podcasts", flush=True)
sortie = []
for k, (u, f) in enumerate(flux.items()):
    try:
        t = get(u, 60).decode("utf-8", "replace")
    except Exception as ex:
        continue
    for it in re.findall(r"<item>(.*?)</item>", t, re.S):
        def champ(nom):
            m = re.search(rf"<{nom}[^>]*>(.*?)</{nom}>", it, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        enc = re.search(r'<enclosure[^>]*url="([^"]+)"', it)
        desc = re.sub(r"<[^>]+>", " ", champ("description") or champ("itunes:summary"))
        sortie.append({"podcast": f["nom"], "auteur": f["auteur"], "flux": u, "titre": champ("title"),
                       "date": champ("pubDate"), "duree": champ("itunes:duration"),
                       "audio": html.unescape(enc.group(1)) if enc else "", "notes": re.sub(r"\s+", " ", desc)[:4000]})
    if k % 25 == 24:
        print(k + 1, "flux lus,", len(sortie), "épisodes", flush=True)
    time.sleep(0.5)
json.dump({"podcasts": flux, "episodes": sortie}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
print(len(flux), "podcasts,", len(sortie), "épisodes")

"""Bibliothèque publique de TradingView : scripts (indicateurs, stratégies) trouvés par recherche de mots-clés,
pages récentes et choix de la rédaction ; nom, description, « j'aime », auteur. Lecture lente (1,5 s entre pages)."""
import html, json, re, subprocess, sys, time
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"
def get(u):
    r = subprocess.run(["curl", "-sL", "--max-time", "40", "-A", UA, u], capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
DEC = json.JSONDecoder()
def scripts(t):
    for m in re.finditer(r'\{"id":\d+,"image_url":"[A-Za-z0-9]+","name":', t):
        try:
            obj, _ = DEC.raw_decode(t, m.start())
        except ValueError:
            continue
        if obj.get("is_script"):
            yield {"id": obj["id"], "nom": obj.get("name", ""), "description": obj.get("description", ""),
                   "jaime": obj.get("likes_count", 0), "auteur": (obj.get("user") or {}).get("username", ""),
                   "type": obj.get("script_type", ""), "date": obj.get("created_at", ""),
                   "url": obj.get("chart_url", ""), "choix": obj.get("is_picked", False)}
mots = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
tous = {}
pages = [f"https://www.tradingview.com/scripts/search/{m.replace(' ', '%20')}/" for m in mots]
pages += [f"https://www.tradingview.com/scripts/search/{m.replace(' ', '%20')}/page-2/" for m in mots[:80]]
pages += ["https://www.tradingview.com/scripts/"] + [f"https://www.tradingview.com/scripts/page-{p}/" for p in range(2, 43)]
pages += ["https://www.tradingview.com/scripts/editors-picks/"] + [f"https://www.tradingview.com/scripts/editors-picks/page-{p}/" for p in range(2, 43)]
for k, u in enumerate(pages):
    for s in scripts(get(u)):
        s2 = tous.setdefault(s["id"], {**s, "trouve_par": []})
        s2["trouve_par"].append(u.split("/scripts/")[1])
    if k % 50 == 49:
        print(k + 1, "pages,", len(tous), "scripts", flush=True)
    time.sleep(1.5)
json.dump(sorted(tous.values(), key=lambda s: -s["jaime"]), open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
print(len(tous), "scripts", flush=True)

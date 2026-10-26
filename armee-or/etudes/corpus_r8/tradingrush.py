"""Trading Rush (chaîne YouTube qui teste chaque méthode 100 à 200 fois) publie le texte de ses vidéos sur son site :
lecture par l'interface publique de WordPress (articles et pages), texte brut, titre, date, lien.

Usage : python tradingrush.py SORTIE.json
"""
import html, json, re, subprocess, sys, time
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"
docs = []
for genre in ("posts", "pages"):
    for page in range(1, 10):
        r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA,
                            f"https://tradingrush.net/wp-json/wp/v2/{genre}?per_page=100&page={page}"], capture_output=True)
        try:
            lot = json.loads(r.stdout.decode("utf-8", "replace"))
        except ValueError:
            break
        if not isinstance(lot, list) or not lot:
            break
        for x in lot:
            texte = re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", x["content"]["rendered"]))).strip()
            docs.append({"source": "tradingrush", "url": x["link"], "titre": html.unescape(x["title"]["rendered"]),
                         "date": x["date"], "texte": texte})
        time.sleep(1.5)
json.dump(docs, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
print(len(docs), "textes,", sum(len(d["texte"]) for d in docs) // 1000, "milliers de caractères")

"""Transcriptions publiées (The Singju Post) de discours, conférences, entretiens : recherche par nom ou sujet, puis
lecture de chaque page (corps de l'article seulement, sans les articles liés).

Usage : python discours.py NOMS.txt SORTIE.json
"""
import html, json, re, subprocess, sys, time, urllib.parse
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"


def get(u):
    r = subprocess.run(["curl", "-sL", "--max-time", "40", "-A", UA, u], capture_output=True)
    if r.returncode or not r.stdout:
        raise RuntimeError("échec " + u)
    return r.stdout.decode("utf-8", "replace")


def corps(t):
    m = re.search(r'<div class="[^"]*entry-content[^"]*">(.*?)<div class="(?:nv-post-navigation|sharedaddy|post-tags|'
                  r'entry-footer)', t, re.S)
    x = m.group(1) if m else ""
    x = re.sub(r"<script.*?</script>|<style.*?</style>", " ", x, flags=re.S).split("Related Posts")[0]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


noms = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
pages = {}
for nom in noms:
    for p in (1, 2, 3):
        u = "https://singjupost.com/" + (f"page/{p}/" if p > 1 else "") + "?" + urllib.parse.urlencode({"s": nom})
        try:
            t = get(u)
        except Exception:
            break
        trouves = sorted(set(re.findall(r'<a href="(https://singjupost\.com/[^"?#]+/)"[^>]*rel="bookmark"', t)))
        trouves = [x for x in trouves if "/page/" not in x and "/category/" not in x]
        for lien in trouves:
            pages.setdefault(lien, []).append(nom)
        if len(trouves) < 8:
            break
        time.sleep(1.0)
print(len(pages), "transcriptions à lire", flush=True)
docs = []
for k, (lien, recherches) in enumerate(pages.items()):
    try:
        t = get(lien)
    except Exception:
        continue
    date = re.search(r'datetime="([^"]+)"', t)
    titre = re.search(r"<title>(.*?)</title>", t, re.S)
    docs.append({"source": "singjupost", "url": lien, "recherches": recherches,
                 "titre": html.unescape(titre.group(1)).replace(" - The Singju Post", "").strip() if titre else "",
                 "date": date.group(1) if date else "", "texte": corps(t)})
    if k % 100 == 99:
        print(k + 1, "lues", flush=True)
    time.sleep(0.6)
json.dump(docs, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
print(len(docs), "transcriptions,", sum(len(d["texte"]) for d in docs) // 1000, "milliers de caractères")

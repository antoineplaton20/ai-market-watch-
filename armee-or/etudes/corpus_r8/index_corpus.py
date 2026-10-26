"""Index publiables du corpus R8 (titres, auteurs, liens, tailles ; jamais les textes) : scripts TradingView les plus
suivis, textes de Trading Rush, discours, épisodes transcrits, et le compte de chaque source.

Usage : python index_corpus.py CORPUS SORTIE_DOSSIER
"""
import csv, glob, json, os, sys
C, O = sys.argv[1], sys.argv[2]


def ecrire(nom, entetes, lignes):
    with open(os.path.join(O, nom), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(entetes)
        w.writerows(lignes)


tv = json.load(open(f"{C}/tradingview.json", encoding="utf-8"))
ecrire("tradingview_top1000.csv", ["jaime", "type", "auteur", "nom", "date", "url"],
       [(s["jaime"], s["type"], s["auteur"], s["nom"], s["date"][:10], s["url"]) for s in tv[:1000]])
tr = json.load(open(f"{C}/tradingrush.json", encoding="utf-8"))
ecrire("tradingrush_index.csv", ["date", "titre", "caracteres", "url"],
       [(x["date"][:10], x["titre"], len(x["texte"]), x["url"]) for x in sorted(tr, key=lambda x: x["date"])])
nom = "discours.json" if os.path.exists(f"{C}/discours.json") and not os.path.exists(f"{C}/discours2.json") else "discours2.json"
di = json.load(open(f"{C}/{nom}", encoding="utf-8"))
ecrire("discours_index.csv", ["date", "recherches", "titre", "caracteres", "url"],
       [(x["date"][:10], " ; ".join(x["recherches"]), x["titre"], len(x["texte"]), x["url"])
        for x in sorted(di, key=lambda x: x["date"])])
au = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(f"{C}/transcriptions/*.json"))]
ecrire("transcriptions_index.csv", ["podcast", "titre", "date", "langue", "minutes", "mots", "audio"],
       [(x.get("podcast"), x.get("titre"), x.get("date"), x.get("langue"), round(x["secondes"] / 60),
         len(x["texte"].split()), x.get("audio")) for x in au])
po = json.load(open(f"{C}/podcasts.json", encoding="utf-8"))
od = json.load(open(f"{C}/odysee.json", encoding="utf-8"))
fo = json.load(open(f"{C}/forums.json", encoding="utf-8"))
qp = json.load(open(f"{C}/quantpedia.json", encoding="utf-8"))
from collections import Counter
src = Counter(x["source"].split("/")[0] for x in fo)
compte = {"podcasts": len(po["podcasts"]), "episodes_de_podcasts": len(po["episodes"]), "videos_odysee": len(od),
          "chaines_odysee": len({v.get("channel") for v in od}), "forums_et_sites": dict(src),
          "strategies_quantpedia": len(qp), "scripts_tradingview": len(tv), "textes_trading_rush": len(tr),
          "discours_transcrits": len(di), "episodes_transcrits_whisper": len(au),
          "minutes_transcrites": round(sum(x["secondes"] for x in au) / 60)}
json.dump(compte, open(os.path.join(O, "compte_corpus.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(compte, ensure_ascii=False))

"""Odysee (beaucoup de chaînes YouTube y sont recopiées) : recherche publique, titres, descriptions, durées."""
import json, sys, time, urllib.parse, urllib.request
H = {"User-Agent": "Mozilla/5.0"}
requetes = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
vus = {}
for q in requetes:
    for page in range(0, 150, 50):
        u = "https://lighthouse.odysee.tv/search?" + urllib.parse.urlencode({"s": q, "size": 50, "from": page,
            "include": "channel,title,description,duration,release_time,effective_amount", "mediaType": "video"})
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40).read())
        except Exception as ex:
            print("échec", q, ex, flush=True); time.sleep(5); continue
        if not r:
            break
        for v in r:
            cle = v.get("claimId")
            if cle in vus:
                vus[cle]["requetes"].append(q)
            else:
                v["requetes"] = [q]
                vus[cle] = v
        time.sleep(0.7)
json.dump(list(vus.values()), open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
print(len(requetes), "requêtes,", len(vus), "vidéos")

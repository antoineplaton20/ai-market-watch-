"""R8 (26/10/2026) : les dates et séries des tests d'événements et de sentiment, depuis les sources officielles.
- fomc.json : jours de décision de la Fed 2000-2026 (federalreserve.gov : fomchistoricalAAAA.htm et fomccalendars.htm) ;
- resultats_geants.json : dépôts 8-K « item 2.02 » (résultats) de Nvidia, Apple, Microsoft, Amazon, Alphabet, Meta et
  Tesla (SEC EDGAR, data.sec.gov/submissions) ;
- fng.json : indice peur et avidité du bitcoin depuis 2018 (api.alternative.me/fng).

Usage : python etudes/telecharger_r8.py DOSSIER_MACRO
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request

DOSSIER = sys.argv[1]
UA = {"User-Agent": "armee-or recherche"}
MOIS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                     "September", "October", "November", "December"], 1)}
CIK = {"NVDA": 1045810, "AAPL": 320193, "MSFT": 789019, "AMZN": 1018724, "GOOGL": 1652044, "META": 1326801,
       "TSLA": 1318605}


def lire(url, ua=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua or UA["User-Agent"]}),
                                  timeout=60).read()


def fomc():
    dates = set()

    def ajoute(an, m_txt, j_txt):
        m_txt = m_txt.split("/")[-1].strip()
        j = j_txt.split("-")[-1].strip().rstrip("*")                # 2e jour d'une réunion de deux jours
        if m_txt in MOIS and j.isdigit():
            try:
                dates.add(dt.date(an, MOIS[m_txt], int(j)).isoformat())
            except ValueError:
                pass
    navigateur = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36"
    for an in range(2000, 2021):
        t = html.unescape(lire(f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{an}.htm",
                               navigateur).decode("utf-8", "replace"))
        for m_txt, j_txt in re.findall(r"(January|February|March|April|May|June|July|August|September|October|"
                                       r"November|December)\s+(\d{1,2}(?:-\d{1,2})?)\s*(?:\(unscheduled\))?\s*Meeting", t):
            ajoute(an, m_txt, j_txt)
        time.sleep(1)
    t = html.unescape(lire("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                           navigateur).decode("utf-8", "replace"))
    for bloc in re.split(r'<div class="panel panel-default">', t)[1:]:
        an = re.search(r"(\d{4}) FOMC Meetings", bloc)
        if an:
            for m_txt, j_txt in re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([A-Za-z/]+)</strong>.*?'
                                           r'fomc-meeting__date[^>]*>([\d\-\*]+)', bloc, re.S):
                ajoute(int(an.group(1)), m_txt, j_txt)
    return sorted(dates)


def resultats():
    out = {}
    for t, c in CIK.items():
        d = json.loads(lire(f"https://data.sec.gov/submissions/CIK{c:010d}.json"))
        blocs = [d["filings"]["recent"]]
        for f in d["filings"].get("files", []):
            time.sleep(0.3)
            blocs.append(json.loads(lire("https://data.sec.gov/submissions/" + f["name"])))
        out[t] = sorted({b["filingDate"][i] for b in blocs for i in range(len(b["form"]))
                         if b["form"][i] in ("8-K", "8-K/A") and "2.02" in (b["items"][i] or "")})
        time.sleep(0.5)
    return out


if __name__ == "__main__":
    os.makedirs(DOSSIER, exist_ok=True)
    f = fomc()
    json.dump(f, open(os.path.join(DOSSIER, "fomc.json"), "w"))
    print("Fed :", len(f), "décisions,", f[0], "→", f[-1])
    r = resultats()
    json.dump(r, open(os.path.join(DOSSIER, "resultats_geants.json"), "w"))
    print("résultats :", {t: len(x) for t, x in r.items()})
    brut = lire("https://api.alternative.me/fng/?limit=0&format=json")
    open(os.path.join(DOSSIER, "fng.json"), "wb").write(brut)
    print("peur et avidité :", len(json.loads(brut)["data"]), "jours")

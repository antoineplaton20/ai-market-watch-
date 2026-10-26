"""Bougies d'une heure Dukascopy (fichiers mensuels .bi5, compressés LZMA), téléchargées lentement avec reprise."""
import os, sys, time, urllib.request
dossier = sys.argv[1]
symboles = sys.argv[2].split(",")
a0, a1 = int(sys.argv[3]), int(sys.argv[4])
for sym in symboles:
    os.makedirs(os.path.join(dossier, sym), exist_ok=True)
    for an in range(a0, a1 + 1):
        for m in range(12):
            chemin = os.path.join(dossier, sym, f"{an}_{m + 1:02d}.bi5")
            if os.path.exists(chemin):
                continue
            url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{an}/{m:02d}/BID_candles_hour_1.bi5"
            for essai in range(6):
                try:
                    brut = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
                    open(chemin, "wb").write(brut)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        open(chemin, "wb").write(b"")
                        break
                    time.sleep(15 * (essai + 1))
                except Exception:
                    time.sleep(15 * (essai + 1))
            time.sleep(8)
        print(sym, an, flush=True)

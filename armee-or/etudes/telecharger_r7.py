"""Archives mensuelles Binance (data.binance.vision), avec leur somme de contrôle SHA-256 publiée."""
import hashlib, os, sys, time, urllib.request
dossier, sym, iv, debut, fin = sys.argv[1:6]
y, m = map(int, debut.split("-")); y2, m2 = map(int, fin.split("-"))
ok = absents = 0
while (y, m) <= (y2, m2):
    nom = f"{sym}-{iv}-{y}-{m:02d}.zip"
    url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/{iv}/{nom}"
    chemin = os.path.join(dossier, nom)
    if not os.path.exists(chemin):
        try:
            brut = urllib.request.urlopen(url, timeout=60).read()
            somme = urllib.request.urlopen(url + ".CHECKSUM", timeout=60).read().decode().split()[0]
            assert hashlib.sha256(brut).hexdigest() == somme, nom
            open(chemin, "wb").write(brut); ok += 1
        except urllib.error.HTTPError as e:
            absents += 1
        time.sleep(0.2)
    m += 1
    if m > 12: y, m = y + 1, 1
print(sym, iv, "nouveaux", ok, "absents", absents)

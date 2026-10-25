"""Import hors ligne d'un export OHLCV normalisé, jamais d'identifiants MT5.

Colonnes : ts,o,h,l,c,v ; ts = début de bougie UTC, millisecondes Unix.
L'instrument reste séparé des historiques Binance. Aucun prix inventé.
"""
import argparse
import csv
import hashlib
import math
import re
import time
from pathlib import Path
from . import base, donnees


def importer(fichier, source, tf, maintenant_ms=None):
    if not re.fullmatch(r"EXPORT_[A-Z0-9_]{1,50}", source):
        raise ValueError("source requise : EXPORT_ suivi d'un nom distinct, ex. EXPORT_MT5_XAUUSD")
    pas = donnees.MS[tf]
    maintenant_ms = time.time()*1000 if maintenant_ms is None else maintenant_ms
    p=Path(fichier)
    lignes=[]
    precedent=None
    with p.open(newline='',encoding='utf-8-sig') as f:
        lecteur=csv.DictReader(f)
        if lecteur.fieldnames != ['ts','o','h','l','c','v']:
            raise ValueError("en-tête attendu : ts,o,h,l,c,v")
        for r in lecteur:
            ts=int(r['ts']);val=[float(r[k]) for k in ('o','h','l','c','v')]
            if ts < 0 or ts % pas or (precedent is not None and ts <= precedent):
                raise ValueError("horodatage non aligné, dupliqué ou non trié")
            if ts+pas>maintenant_ms:
                raise ValueError("bougie future ou non clôturée")
            if not donnees._bougie_valide(*val):
                raise ValueError("OHLCV invalide")
            lignes.append([ts,*val]);precedent=ts
    if not lignes:
        raise ValueError("export vide")
    # Un export ne remplace pas silencieusement une bougie déjà connue.
    with base.connexion() as c:
        for r in lignes:
            ancien=c.execute('SELECT o,h,l,c,v FROM bougies WHERE source=? AND tf=? AND ts=?',
                             (source,tf,r[0])).fetchone()
            if ancien is not None and tuple(ancien)!=tuple(r[1:]):
                raise ValueError("conflit avec une bougie existante ; utiliser une source distincte")
        c.executemany('INSERT OR IGNORE INTO bougies(source,tf,ts,o,h,l,c,v) VALUES(?,?,?,?,?,?,?,?)',
                      [(source,tf,*r) for r in lignes])
    resultat={'source':source,'tf':tf,'lignes':len(lignes),'debut':lignes[0][0],'fin':lignes[-1][0],
              'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'import_ts':time.time()}
    base.ecrire(f'import:{source}:{tf}:{resultat["sha256"]}',resultat)
    return resultat


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fichier',required=True)
    p.add_argument('--source',required=True)
    p.add_argument('--tf',choices=tuple(donnees.MS),required=True)
    a=p.parse_args()
    print(importer(a.fichier,a.source,a.tf))


if __name__=='__main__':main()

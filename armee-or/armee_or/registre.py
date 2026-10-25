"""Registre local append-only : hypothèses préalables, essais et résultats séparés.
Les triggers empêchent UPDATE/DELETE via l'application ; ce n'est pas une preuve contre un administrateur.
"""
import hashlib
import json
import time
from pathlib import Path
from . import base, config


def schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS hypotheses_r3 (
        id TEXT PRIMARY KEY, specification TEXT NOT NULL, sha256 TEXT NOT NULL, date REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS essais (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hypothese TEXT NOT NULL, variante TEXT NOT NULL,
        donnees TEXT NOT NULL, periode TEXT NOT NULL, specification TEXT NOT NULL,
        commit_source TEXT NOT NULL, date REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS resultats_essais (
        id INTEGER PRIMARY KEY AUTOINCREMENT, essai INTEGER NOT NULL REFERENCES essais(id),
        resultat TEXT NOT NULL, verdict TEXT NOT NULL, date REAL NOT NULL);
    ''')
    for table in ('hypotheses_r3','essais','resultats_essais'):
        for op in ('UPDATE','DELETE'):
            c.execute(f"CREATE TRIGGER IF NOT EXISTS immuable_{table}_{op} BEFORE {op} ON {table} "
                      "BEGIN SELECT RAISE(ABORT, 'registre append-only'); END")


def catalogue():
    return json.loads((Path(__file__).parent/'hypotheses.json').read_text(encoding='utf-8'))


def initialiser():
    with base.connexion() as c:
        schema(c)
        for fiche in catalogue():
            contenu=json.dumps(fiche,ensure_ascii=False,sort_keys=True)
            c.execute('INSERT OR IGNORE INTO hypotheses_r3 VALUES (?,?,?,?)',
                      (fiche['id'],contenu,hashlib.sha256(contenu.encode()).hexdigest(),time.time()))


def declarer(hypothese,variante,donnees,periode,specification,commit_source):
    if not all(isinstance(v,str) and v.strip() for v in
               (hypothese,variante,donnees,periode,specification,commit_source)):
        raise ValueError('fiche préalable incomplète')
    initialiser()
    with base.connexion() as c:
        return c.execute('INSERT INTO essais(hypothese,variante,donnees,periode,specification,commit_source,date) '
                         'VALUES (?,?,?,?,?,?,?)',
                         (hypothese,variante,donnees,periode,specification,commit_source,time.time())).lastrowid


def conclure(essai,resultat,verdict):
    if verdict not in ('rejete','incomplet','erreur','exploratoire'):
        raise ValueError('aucun verdict de ce registre ne délivre de permis')
    contenu=json.dumps(resultat,ensure_ascii=False,allow_nan=False)
    with base.connexion() as c:
        schema(c)
        if not c.execute('SELECT id FROM essais WHERE id=?',(essai,)).fetchone():
            raise ValueError('essai non déclaré')
        c.execute('INSERT INTO resultats_essais(essai,resultat,verdict,date) VALUES (?,?,?,?)',
                  (essai,contenu,verdict,time.time()))


def resume():
    initialiser()
    with base.connexion() as c:
        n=c.execute('SELECT COUNT(*) FROM essais').fetchone()[0]
        h=c.execute('SELECT COUNT(*) FROM hypotheses_r3').fetchone()[0]
        faits=c.execute('SELECT COUNT(DISTINCT essai) FROM resultats_essais').fetchone()[0]
    return {'hypotheses':h,'essais_declares':n,'essais_avec_resultat':faits,
            'alpha_bonferroni_local':.05/max(1,n),
            'inventaire_ancien_complet':False,'permis':False}


def texte():
    r=resume()
    return (f"Registre : {r['hypotheses']} hypothèses ; {r['essais_declares']} essais déclarés, "
            f"{r['essais_avec_resultat']} avec résultat. Seuil local 0,05 / max(1,n) = "
            f"{r['alpha_bonferroni_local']:.6g}.\nLes essais antérieurs ne sont pas tous recensés : "
            "ce seuil ne valide aucune stratégie. Aucun permis délivré.")

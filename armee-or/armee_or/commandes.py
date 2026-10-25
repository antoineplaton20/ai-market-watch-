"""File persistante. Une commande dont l'exécution a commencé n'est jamais rejouée automatiquement."""
import json
import time
import uuid
from . import base


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS commandes_r3 (
        id TEXT PRIMARY KEY, texte TEXT NOT NULL, date REAL NOT NULL,
        statut TEXT NOT NULL DEFAULT 'attente', detail TEXT)''')


def ajouter(texte,identifiant=None,date=None,c=None):
    if not isinstance(texte,str) or not texte.strip() or len(texte)>256:
        raise ValueError('commande invalide')
    identifiant=identifiant or 'local:'+uuid.uuid4().hex
    if c is None:
        with base.connexion() as db:
            return ajouter(texte,identifiant,date,db)
    schema(c)
    c.execute('INSERT OR IGNORE INTO commandes_r3(id,texte,date) VALUES (?,?,?)',
              (identifiant,texte,time.time() if date is None else date))
    return identifiant


class Commande(str):
    def __new__(cls,texte,identifiant):
        x=super().__new__(cls,texte);x.identifiant=identifiant;return x


def prendre():
    with base.connexion() as c:
        schema(c)
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE commandes_r3 SET statut='expiree' WHERE statut='attente' AND date<?",(time.time()-120,))
        rows=c.execute("SELECT id,texte FROM commandes_r3 WHERE statut='attente' ORDER BY date,id LIMIT 100").fetchall()
        for r in rows:c.execute("UPDATE commandes_r3 SET statut='en_cours' WHERE id=?",(r['id'],))
    return [Commande(r['texte'],r['id']) for r in rows]


def terminer(commande,erreur=False):
    if not hasattr(commande,'identifiant'):return
    with base.connexion() as c:
        schema(c)
        c.execute("UPDATE commandes_r3 SET statut=? WHERE id=? AND statut='en_cours'",
                  ('incertaine' if erreur else 'terminee',commande.identifiant))


def reprise_apres_panne():
    with base.connexion() as c:
        schema(c)
        n=c.execute("UPDATE commandes_r3 SET statut='incertaine' WHERE statut='en_cours'").rowcount
    if n:
        base.ecrire('mt5:pause',True)
        base.ecrire('pause',True)
    return n


def etat():
    with base.connexion() as c:
        schema(c)
        return dict(c.execute('SELECT statut,COUNT(*) FROM commandes_r3 GROUP BY statut').fetchall())

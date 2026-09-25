"""ARMÉE DE RENSEIGNEMENT — service equipe-bots-renseignement. Ne passe AUCUN ordre, ne touche à aucun compte.

Une trentaine de bots cherchent en continu, jour et nuit, chacun avec sa mission et son rythme (voir
moteurs/renseignement_sources.py) : presse économique et générale, banques centrales, presse mondiale de tous les
pays (GDELT), ton de la presse mondiale, séismes, catastrophes, marchés de prédiction, réseaux sociaux, et la
presse sur chaque actif suivi par nos bots de trading.

Tout arrive dans une base partagée (runtime/renseignement.db) :
  faits    : chaque information, avec thèmes, actifs cités, ton (-2..+2) et importance (0..3)
  signaux  : synthèse toutes les 5 min — climat mondial, chaque thème, chaque secteur, chaque actif
  alertes  : chocs majeurs et pics d'attention soudains

Les bots d'achat / vente la lisent via lecture_renseignement.py (lecture seule, jamais bloquant). Ce service tourne en
priorité basse (processeur et disque) : il ne peut pas ralentir les bots qui tradent.

Lancement : python renseignement.py | test : python renseignement.py --test
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | RENSEIGNEMENT | %(message)s",
                        handlers=[RotatingFileHandler("renseignement.log", maxBytes=5_000_000, backupCount=3,
                                                      encoding="utf-8"), logging.StreamHandler()])

import hashlib
import json
import math
import os
import sqlite3
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import config
import lecture_renseignement as LR
from alertes import alerte, log
from moteurs import notation as N
from moteurs import renseignement_sources as R
from moteurs import sources_marches as S

THREADS = 4
PERIODE_SYNTHESE_S = 300
PERIODE_IA_S = 600
IA_PAR_HEURE = int(os.getenv("RENSEIGNEMENT_IA_PAR_HEURE", "4"))       # lots de 40 titres lus par l'IA, par heure
ALERTES_PAR_JOUR = int(os.getenv("RENSEIGNEMENT_ALERTES_JOUR", "8"))
RETENTION_J = 30
DEMI_VIE_H = 8                                                         # une info de 8 h pèse moitié moins
BASE_JOURS = 3                                                         # « normale » de référence : 3 derniers jours
THEME_SECTEURS = {"energie": ["Energy", "Utilities"], "alimentaire": ["Consumer Defensive"],
                  "industrie": ["Industrials", "Basic Materials"], "tech": ["Technology", "Communication Services"],
                  "banques_centrales": ["Financial Services", "Real Estate"], "defense": ["Industrials"],
                  "crypto": ["Crypto"], "matieres": ["Basic Materials"], "economie": ["Consumer Cyclical"],
                  "sante": ["Healthcare"], "wall_street": ["ETF / indices"], "europe": ["ETF / indices"]}

PROMPT_IA = """Tu analyses des titres d'actualité pour des robots d'investissement (cryptos sur Binance ; actions, ETF et
cryptos sur Trade Republic). Actifs suivis (codes) : {actifs}.
Pour chaque titre numéroté, donne :
- "ton" : effet probable sur les marchés, entier de -2 (très négatif) à 2 (très positif), 0 si neutre ou incertain ;
- "imp" : importance pour un investisseur : 0 anecdotique, 1 utile, 2 important, 3 choc majeur (guerre, krach,
  faillite systémique, piratage d'une plateforme, décision surprise d'une banque centrale, catastrophe majeure) ;
- "actifs" : codes des actifs suivis DIRECTEMENT concernés, sinon [].
Ne suppose rien qui ne soit pas dans le titre.
Titres :
{titres}
Réponds UNIQUEMENT avec un objet JSON : {{"1": {{"ton": 0, "imp": 1, "actifs": []}}, "2": ...}}"""


def _liste(x):
    return [v for v in (x or "").split(",") if v]


def _code(liste):
    return "," + ",".join(sorted(set(liste))) + "," if liste else ","


# ================================ ACTIFS SUIVIS PAR NOS BOTS ================================
def _json(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def repertoire_actifs():
    """Code d'actif -> noms qui le désignent dans la presse. Codes : « BTC » (crypto), « MC.PA » (action)."""
    rep = {c: [c, n] for c, n in R.CRYPTOS.items()}
    rep.update({t: [n] for t, n in R.GRANDS_NOMS.items()})
    for t, f in (_json("marches_etat.json").get("notes") or {}).items():
        code = LR.cle_actif(t).split(":", 1)[1]
        if code not in rep and f.get("nom"):
            rep[code] = [R.requete_actif(f["nom"]).strip('"')]
    return rep


def actifs_suivis():
    """(code, nom) de ce que nos bots détiennent ou regardent — cherchés en priorité par le bot « de près »."""
    codes = []
    for sym in (_json("etat.json").get("positions") or {}):                         # bot principal (Binance)
        codes.append(LR.cle_actif(sym).split(":", 1)[1])
    for sym in os.getenv("V17_SYMBOLS", "BTC/USDT").split(","):                     # moteur v17
        if sym.strip():
            codes.append(LR.cle_actif(sym).split(":", 1)[1])
    for sym in config.MARCHES_PORTEFEUILLE + config.MARCHES_SUIVIS + config.MARCHES_CRYPTOS:   # Trade Republic
        codes.append(LR.cle_actif(sym).split(":", 1)[1])
    notes = _json("marches_etat.json").get("notes") or {}
    for t, f in sorted(notes.items(), key=lambda x: -x[1].get("note", 0))[:15]:     # meilleures notes du jour
        codes.append(LR.cle_actif(t).split(":", 1)[1])
    rep = repertoire_actifs()
    res = []
    for c in dict.fromkeys(codes):
        noms = rep.get(c) or [(notes.get(c) or {}).get("nom") or c]
        nom = noms[-1] if c in R.CRYPTOS else noms[0]
        if nom:
            res.append((c, nom))
    return res[:40]


# ================================ BASE (un seul écrivain) ================================
class Base:
    def __init__(self, chemin=None):
        self.chemin = chemin or LR.BASE
        os.makedirs(os.path.dirname(self.chemin) or ".", exist_ok=True)
        self.c = sqlite3.connect(self.chemin, timeout=30)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(LR.SCHEMA)
        self.c.commit()

    def ajouter(self, bot, faits, repertoire):
        """Enregistre les faits nouveaux ; un même titre vu par une autre source renforce le fait existant."""
        nouveaux, maintenant = 0, time.time()
        for f in faits:
            titre = (f.get("titre") or "").strip()
            if not titre:
                continue
            h = hashlib.sha1(S._norm(titre)[:160].encode()).hexdigest()[:20]
            themes = f.get("themes") or S.themes_du_titre(titre)
            actifs = sorted(set((f.get("actifs") or []) + R.reperer_actifs(titre, repertoire)))
            importance = f.get("importance")
            ton = f.get("ton")
            if importance is None:
                importance = R.importance_lexicale(titre, themes)
                if importance >= 2 and ton is None:
                    ton = -2                                   # mot de danger : piratage, faillite, guerre...
            if ton is None:
                ton = N.ton_titre(titre)
            cur = self.c.execute(
                "INSERT OR IGNORE INTO faits(hash, ts, vu, bot, source, sources, titre, lien, themes, actifs, ton, "
                "importance) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (h, float(f.get("ts") or maintenant), maintenant, bot, f.get("source", ""), f.get("source", ""),
                 titre[:300], f.get("lien", ""), _code(themes), _code(actifs), ton, int(importance)))
            if cur.rowcount:
                nouveaux += 1
            else:
                self.c.execute("UPDATE faits SET n_sources = n_sources + 1, sources = sources || ',' || ? "
                               "WHERE hash = ? AND instr(sources, ?) = 0", (f.get("source", ""), h, f.get("source", "")))
        self.c.commit()
        return nouveaux

    def bot(self, nom, famille, ok, n, erreur, prochaine):
        self.c.execute("INSERT INTO bots(nom, famille, derniere, prochaine, ok, ko, faits, erreur) "
                       "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(nom) DO UPDATE SET derniere=excluded.derniere, "
                       "prochaine=excluded.prochaine, ok=bots.ok+excluded.ok, ko=bots.ko+excluded.ko, "
                       "faits=bots.faits+excluded.faits, erreur=excluded.erreur",
                       (nom, famille, time.time(), prochaine, int(ok), int(not ok), n, erreur))
        self.c.commit()

    def signal(self, cle, valeur, confiance=1.0, n=0, resume=""):
        self.c.execute("INSERT INTO signaux(cle, valeur, confiance, n, resume, ts) VALUES(?,?,?,?,?,?) "
                       "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur, confiance=excluded.confiance, "
                       "n=excluded.n, resume=excluded.resume, ts=excluded.ts",
                       (cle, float(valeur), float(confiance), int(n), resume[:300], time.time()))

    def lire_signal(self, cle):
        r = self.c.execute("SELECT * FROM signaux WHERE cle = ?", (cle,)).fetchone()
        return dict(r) if r else None

    def alerte(self, cle, niveau, ton, titre, sources):
        deja = self.c.execute("SELECT 1 FROM alertes WHERE titre = ? AND ts >= ?",
                              (titre[:300], time.time() - 86400)).fetchone()
        if not deja:
            self.c.execute("INSERT INTO alertes(ts, cle, niveau, ton, titre, sources) VALUES(?,?,?,?,?,?)",
                           (time.time(), cle, niveau, ton, titre[:300], sources))

    def purger(self):
        limite = time.time() - RETENTION_J * 86400
        self.c.execute("DELETE FROM faits WHERE vu < ?", (limite,))
        self.c.execute("DELETE FROM alertes WHERE ts < ?", (limite,))
        self.c.commit()


# ================================ L'ARMÉE ================================
class Armee:
    def __init__(self, base=None, ctx=None, ia=None, bots=None):
        self.base = base or Base()
        self.ctx = ctx or R.Contexte(actifs=actifs_suivis)
        self.ia = ia if ia is not None else (_ia if config.ANTHROPIC_API_KEY else None)
        self.bots = bots if bots is not None else R.armee()
        maintenant = time.time()
        self.prochaine = {b.nom: maintenant + i * 15 for i, b in enumerate(self.bots)}   # départs échelonnés
        self.echecs = {b.nom: 0 for b in self.bots}
        self.en_cours = {}
        self.derniere_synthese = self.derniere_ia = self.derniere_purge = 0.0
        self.appels_ia = []
        self.repertoire = repertoire_actifs()

    # ---------------------------------------------------------------- un bot
    def _resultat(self, bot, faits, signaux, erreur):
        maintenant = time.time()
        if erreur:
            self.echecs[bot.nom] += 1                                   # recul : 15 min, 30, 60... jusqu'à 6 h
            delai = min(bot.periode_min * 60 * 2 ** self.echecs[bot.nom], 6 * 3600)
        else:
            self.echecs[bot.nom] = 0
            delai = bot.periode_min * 60
        self.prochaine[bot.nom] = maintenant + delai
        n = self.base.ajouter(bot.nom, faits, self.repertoire) if faits else 0
        for cle, v in (signaux or {}).items():
            self.base.signal(cle, v, 1.0, 0, "")
        self.base.bot(bot.nom, bot.famille, not erreur, n, erreur, self.prochaine[bot.nom])
        return n

    def executer(self, bot):
        try:
            faits, signaux = bot.collecte(self.ctx)
            return self._resultat(bot, faits, signaux, None)
        except Exception as e:
            return self._resultat(bot, [], {}, f"{type(e).__name__}: {str(e)[:150]}")

    def passer_tout(self):
        """Tous les bots une fois, à la suite (tests et diagnostic)."""
        return {b.nom: self.executer(b) for b in self.bots}

    # ---------------------------------------------------------------- analyste IA
    def analyser_ia(self):
        maintenant = time.time()
        self.appels_ia = [t for t in self.appels_ia if maintenant - t < 3600]
        if not self.ia or len(self.appels_ia) >= IA_PAR_HEURE:
            return 0
        lignes = self.base.c.execute(
            "SELECT id, titre FROM faits WHERE analyse = 0 AND importance >= 1 AND vu >= ? "
            "ORDER BY importance DESC, vu DESC LIMIT 40", (maintenant - 6 * 3600,)).fetchall()
        if not lignes:
            return 0
        self.appels_ia.append(maintenant)
        codes = ", ".join(sorted(self.repertoire))
        j = self.ia(config.MODELE_IA_VEILLE, PROMPT_IA.format(
            actifs=codes, titres="\n".join(f"{i + 1}. {r['titre']}" for i, r in enumerate(lignes))), 3000)
        if not isinstance(j, dict):
            return 0
        n = 0
        for i, r in enumerate(lignes):
            v = j.get(str(i + 1))
            if not isinstance(v, dict):
                continue
            try:
                ton = max(-2, min(2, int(v.get("ton", 0))))
                imp = max(0, min(3, int(v.get("imp", 1))))
            except (TypeError, ValueError):
                continue
            actifs = [a for a in (v.get("actifs") or []) if a in self.repertoire]
            ancien = _liste(self.base.c.execute("SELECT actifs FROM faits WHERE id = ?", (r["id"],)).fetchone()[0])
            self.base.c.execute("UPDATE faits SET ton = ?, importance = ?, actifs = ?, ia = 1, analyse = 1 WHERE id = ?",
                                (ton, imp, _code(ancien + actifs), r["id"]))
            n += 1
        self.base.c.execute("UPDATE faits SET analyse = 1 WHERE analyse = 0 AND vu < ?", (maintenant - 6 * 3600,))
        self.base.c.commit()
        return n

    # ---------------------------------------------------------------- synthèse
    def synthese(self):
        maintenant = time.time()
        lignes = self.base.c.execute(
            "SELECT id, ts, ton, importance, themes, actifs, n_sources, titre, source FROM faits "
            "WHERE ts >= ? AND ton IS NOT NULL", (maintenant - 86400,)).fetchall()
        groupes = {}
        for r in lignes:
            poids = math.exp(-max(0.0, maintenant - r["ts"]) / 3600 / DEMI_VIE_H * math.log(2)) \
                * (1 + r["importance"]) * min(r["n_sources"], 3)
            themes, actifs = _liste(r["themes"]), _liste(r["actifs"])
            cles = ([f"theme:{t}" for t in themes] + [f"actif:{a}" for a in actifs]
                    + [f"secteur:{s}" for t in themes for s in THEME_SECTEURS.get(t, [])])
            if themes:
                cles.append("global")
            for cle in set(cles):
                groupes.setdefault(cle, []).append((poids, r["ton"], r["importance"], r["titre"]))
        alpha = min(1.0, PERIODE_SYNTHESE_S / (BASE_JOURS * 86400))
        for cle, items in groupes.items():
            total = sum(p for p, *_ in items)
            if total <= 0:
                continue
            brut = sum(p * ton for p, ton, *_ in items) / total
            confiance = min(1.0, total / 20)
            resume = max(items, key=lambda x: (x[2], x[0]))[3]
            if cle.startswith("actif:"):
                valeur = brut                                   # l'actualité d'un actif compte telle quelle
            else:                                               # climat, thèmes, secteurs : écart à la normale
                ref = self.base.lire_signal(f"base:{cle}")      # (la presse est toujours un peu négative)
                base = brut if ref is None else ref["valeur"]
                self.base.signal(f"base:{cle}", base + alpha * (brut - base), 1.0, len(items), "")
                valeur = max(-2.0, min(2.0, (brut - base) * 2))
                if cle.startswith("theme:"):
                    g = self.base.lire_signal(f"gdelt:{cle.split(':', 1)[1]}")
                    if g and maintenant - g["ts"] < 3 * 3600:
                        valeur = 0.7 * valeur + 0.3 * g["valeur"]
            self.base.signal(cle, valeur, confiance, len(items), resume)
        self._detecter(maintenant)
        self.base.c.commit()
        return len(groupes)

    def _detecter(self, maintenant):
        # 1. Chocs majeurs (importance 3)
        for r in self.base.c.execute("SELECT titre, ton, actifs, themes, n_sources FROM faits WHERE importance >= 3 "
                                     "AND vu >= ?", (maintenant - 3 * 3600,)).fetchall():
            actifs, themes = _liste(r["actifs"]), _liste(r["themes"])
            cle = f"actif:{actifs[0]}" if actifs else (f"theme:{themes[0]}" if themes else "global")
            self.base.alerte(cle, 3, r["ton"] or 0, r["titre"], r["n_sources"])
        # 2. Sans IA : la même mauvaise nouvelle sur un actif, reprise par au moins 2 sources différentes en 6 h
        par_actif = {}
        for r in self.base.c.execute("SELECT titre, sources, actifs FROM faits WHERE importance >= 2 AND ton <= -1 "
                                     "AND ts >= ? AND actifs != ','", (maintenant - 6 * 3600,)).fetchall():
            for a in _liste(r["actifs"]):
                for src in _liste(r["sources"]):
                    par_actif.setdefault(a, {}).setdefault(src, r["titre"])
        for a, sources in par_actif.items():
            if len(sources) >= 2:
                self.base.alerte(f"actif:{a}", 3, -2, f"{a} : {next(iter(sources.values()))}", len(sources))
        # 3. Pics d'attention : un thème dont on parle soudain 3 fois plus que d'habitude
        for t in S.THEMES:
            motif = f"%,{t},%"
            n1 = self.base.c.execute("SELECT COUNT(*) FROM faits WHERE vu >= ? AND themes LIKE ?",
                                     (maintenant - 3600, motif)).fetchone()[0]
            n23 = self.base.c.execute("SELECT COUNT(*) FROM faits WHERE vu >= ? AND vu < ? AND themes LIKE ?",
                                      (maintenant - 86400, maintenant - 3600, motif)).fetchone()[0]
            habituel = n23 / 23
            recent = self.base.c.execute("SELECT 1 FROM alertes WHERE cle = ? AND niveau = 2 AND ts >= ?",
                                         (f"theme:{t}", maintenant - 6 * 3600)).fetchone()
            if n1 >= 15 and n23 >= 23 and n1 >= 3 * habituel and not recent:
                s = self.base.lire_signal(f"theme:{t}") or {}
                self.base.alerte(f"theme:{t}", 2, s.get("valeur", 0),
                                 f"Pic d'attention : {S.THEMES[t]} ({n1} infos en 1 h, {habituel:.0f} d'habitude). "
                                 f"{s.get('resume', '')}", n1)

    # ---------------------------------------------------------------- sentinelle Telegram
    def sentinelle(self):
        maintenant = time.time()
        envoyees = self.base.c.execute("SELECT COUNT(*) FROM alertes WHERE envoyee = 1 AND ts >= ?",
                                       (maintenant - 86400,)).fetchone()[0]
        for r in self.base.c.execute("SELECT * FROM alertes WHERE envoyee = 0 ORDER BY niveau DESC, ts").fetchall():
            if envoyees >= ALERTES_PAR_JOUR:
                self.base.c.execute("UPDATE alertes SET envoyee = 2 WHERE id = ?", (r["id"],))
                continue
            envoyees += 1
            icone = "🚨" if r["niveau"] >= 3 else "📡"
            cible = r["cle"].split(":", 1)[-1]
            alerte(f"{icone} Renseignement ({cible}) : {r['titre'][:300]}"
                   + (f"\nSources : {r['sources']}" if r["sources"] and r["sources"] > 1 else ""),
                   important=r["niveau"] >= 3)
            self.base.c.execute("UPDATE alertes SET envoyee = 1 WHERE id = ?", (r["id"],))
        self.base.c.commit()

    # ---------------------------------------------------------------- boucle perpétuelle
    def taches_de_fond(self):
        maintenant = time.time()
        if maintenant - self.derniere_ia >= PERIODE_IA_S:
            self.derniere_ia = maintenant
            self.analyser_ia()
        if maintenant - self.derniere_synthese >= PERIODE_SYNTHESE_S:
            self.derniere_synthese = maintenant
            self.repertoire = repertoire_actifs()
            self.synthese()
            self.sentinelle()
        if maintenant - self.derniere_purge >= 86400:
            self.derniere_purge = maintenant
            self.base.purger()

    def tourner(self):
        alerte(f"🛰 Armée de renseignement déployée : {len(self.bots)} bots cherchent en continu (presse mondiale, "
               "banques centrales, géopolitique, économie, alimentation, énergie, social, catastrophes, marchés de "
               "prédiction, réseaux sociaux, et chaque actif suivi). Ils informent les bots de trading sans les "
               "ralentir. État : /renseignement", important=False)
        with ThreadPoolExecutor(max_workers=THREADS, thread_name_prefix="bot") as pool:
            while True:                                                 # perpétuel : jour et nuit, sans fin
                try:
                    self.cycle(pool)
                except Exception:                                       # base verrouillée, disque plein... :
                    log("Erreur de cycle : " + traceback.format_exc()[-1500:])   # l'armée continue
                    time.sleep(30)
                time.sleep(5)

    def cycle(self, pool):
        maintenant = time.time()
        for bot in self.bots:                                           # chaque bot repart dès que c'est son tour
            if bot.nom not in self.en_cours and maintenant >= self.prochaine[bot.nom]:
                self.en_cours[bot.nom] = (bot, pool.submit(bot.collecte, self.ctx))
        for nom, (bot, fut) in list(self.en_cours.items()):             # l'écriture reste dans ce seul fil
            if fut.done():
                del self.en_cours[nom]
                try:
                    faits, signaux = fut.result()
                    self._resultat(bot, faits, signaux, None)
                except Exception as e:
                    self._resultat(bot, [], {}, f"{type(e).__name__}: {str(e)[:150]}")
        try:
            self.taches_de_fond()
        except Exception:                                               # la synthèse ne doit jamais arrêter l'armée
            log("Erreur tâches de fond : " + traceback.format_exc()[-1500:])


def _ia(modele, prompt, max_tokens):
    from equipe import ia_json
    return ia_json(modele, prompt, max_tokens)


# ================================ TEST ================================
def mode_test(ctx=None):
    import alertes
    alertes._ACTIF = False
    import tempfile
    base = Base(os.path.join(tempfile.mkdtemp(), "essai.db"))
    armee = Armee(base, ctx or R.Contexte(actifs=actifs_suivis, pause_gdelt_s=1), ia=None)
    print(f"Test des {len(armee.bots)} bots de l'armée de renseignement (2 à 4 minutes, aucun message Telegram)...")
    ok = 0
    for bot in armee.bots:
        debut = time.time()
        n = armee.executer(bot)
        r = base.c.execute("SELECT erreur FROM bots WHERE nom = ?", (bot.nom,)).fetchone()
        erreur = r["erreur"] if r else None
        ok += not erreur
        print(f"   {'✔' if not erreur else '✖'} {bot.nom} : {n} infos ({time.time() - debut:.0f} s)"
              + (f" — {erreur}" if erreur else ""))
    armee.synthese()
    total = base.c.execute("SELECT COUNT(*) FROM faits").fetchone()[0]
    print(f"\n→ {ok}/{len(armee.bots)} bots opérationnels, {total} informations récoltées en un passage.")
    print(f"Analyste IA : {'clé Anthropic présente' if config.ANTHROPIC_API_KEY else 'pas de clé : ton lu par mots-clés'}")
    print("\n" + LR.texte_statut(base.chemin))
    print("\n✅ Armée opérationnelle." if ok >= len(armee.bots) * 0.6 else "\n❌ Trop de bots en échec : envoie une capture à Claude.")
    return 0 if ok >= len(armee.bots) * 0.6 else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(mode_test())
    try:
        Armee().tourner()
    except KeyboardInterrupt:
        log("Armée de renseignement arrêtée.")
    except Exception:
        log("Arrêt sur erreur : " + traceback.format_exc()[-2000:])
        raise

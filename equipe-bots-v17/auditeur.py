"""AUDITEUR : note chaque bot sur 10 à partir de résultats RÉELS, jamais à partir de promesses.
- Votants : comparent les trades où le bot disait OUI à ceux où il disait NON.
- Vetos   : comparent les trades exécutés aux « trades fantômes » qu'ils ont bloqués
            (on simule après coup ce qui se serait passé, avec les règles exactes du GARDIEN).
Note = 5 + 10 x (écart d'espérance en R). 5 = hasard, 8 = +0,3 R par trade, < 5 = nuisible."""
import json
import os
import sqlite3
import time
import config
from simulation import simuler_sortie, note_sur_10

BDD = "journal.db"
VETOS = ["RISK_ATR", "ANTI_HYPE", "DERIVES_VETO", "BALEINES_VETO", "CORRELATION", "VEILLE", "CONTRADICTEUR",
         "METEO", "CALENDRIER", "PEUR_AVIDITE", "LIQUIDITE_VETO", "MACRO_VETO", "POSITIONNEMENT_VETO",
         "MARCHES_MONDIAUX_VETO", "ATTENTION_VETO"]


def _cnx():
    c = sqlite3.connect(BDD)
    c.execute("""CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbole TEXT, entree REAL, sortie REAL, quantite REAL,
        pnl_pct REAL, pnl_usdt REAL, r REAL, raison TEXT, votes TEXT, ouvert REAL, ferme REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fantomes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbole TEXT, ts REAL, entree REAL, atr REAL,
        vetos TEXT, r REAL, resolu INTEGER DEFAULT 0)""")
    for colonne in ("r REAL", "mode TEXT", "risques TEXT"):      # compatibilité v1 et v14
        try:
            c.execute(f"ALTER TABLE trades ADD COLUMN {colonne}")
        except sqlite3.OperationalError:
            pass
    return c


def _filtre_mode(mode):
    """Anciennes lignes sans mode = trades stricts."""
    return ("", ()) if mode is None else (" AND COALESCE(mode,'strict') = ?", (mode,))


# ================================ TRADES ================================
def enregistrer(sym, p, sortie, raison):
    """Gain total = partie vendue en cours de route (prise partielle) + reste vendu à la sortie, frais déduits."""
    qte_init = p.get("qte_initiale", p["quantite"])
    mise = qte_init * p["entree"]
    brut = p.get("gain_partiel_usdt", 0.0) + (sortie - p["entree"]) * p["quantite"]
    pnl_usdt = brut - mise * config.FRAIS_ALLER_RETOUR_PCT / 100
    pnl_pct = pnl_usdt / mise * 100 if mise else 0.0
    risque_pct = (p["entree"] - p["stop_initial"]) / p["entree"] * 100
    r = pnl_pct / risque_pct if risque_pct > 0 else 0.0
    c = _cnx()
    with c:
        c.execute("INSERT INTO trades(symbole,entree,sortie,quantite,pnl_pct,pnl_usdt,r,raison,votes,ouvert,ferme,"
                  "mode,risques) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sym, p["entree"], sortie, p["quantite"], pnl_pct, pnl_usdt, r, raison,
                   json.dumps(p["votes"]), p["ouvert"], time.time(), p.get("mode", "strict"),
                   json.dumps(p.get("risques", []))))
    c.close()
    return pnl_pct, pnl_usdt


def pnl_depuis(horodatage, mode=None):
    f, a = _filtre_mode(mode)
    c = _cnx()
    r = c.execute("SELECT COALESCE(SUM(pnl_usdt),0) FROM trades WHERE ferme >= ?" + f, (horodatage, *a)).fetchone()[0]
    c.close()
    return float(r)


def pnl_total():
    return pnl_depuis(0)


def trades_depuis(horodatage, mode=None):
    """Liste (r, pnl_usdt) des trades clôturés depuis une date, dans l'ordre. mode : None (tous), strict, exploration."""
    f, a = _filtre_mode(mode)
    c = _cnx()
    lignes = c.execute("SELECT r, pnl_usdt FROM trades WHERE ferme >= ?" + f + " ORDER BY ferme",
                       (horodatage, *a)).fetchall()
    c.close()
    return [(r if r is not None else 0.0, u) for r, u in lignes]


# =============================== FANTÔMES ===============================
def fantome(sym, entree, atr, vetos):
    """Candidat bloqué par un ou plusieurs vetos : on le suit quand même, sur le papier."""
    c = _cnx()
    with c:
        c.execute("INSERT INTO fantomes(symbole,ts,entree,atr,vetos) VALUES (?,?,?,?,?)",
                  (sym, time.time(), entree, atr, json.dumps(vetos)))
    c.close()


def resoudre_fantomes(ex):
    """Une fois le délai max écoulé, on rejoue le fantôme avec les règles du GARDIEN."""
    c = _cnx()
    limite = time.time() - (config.DUREE_MAX_H + 0.5) * 3600
    lignes = c.execute("SELECT id, symbole, ts, entree, atr FROM fantomes WHERE resolu=0 AND ts < ? LIMIT 10",
                       (limite,)).fetchall()
    for fid, sym, ts, entree, atr in lignes:
        try:
            duree = int(config.DUREE_MAX_H * 60 / config.MINUTES[config.UNITE_BOUGIE])
            ohlcv = ex.fetch_ohlcv(sym, config.UNITE_BOUGIE, since=int(ts * 1000), limit=duree + 5)
            bougies = [(o, h, l, cl) for _, o, h, l, cl, _ in ohlcv]
            r = simuler_sortie(bougies, entree, atr, duree)[0] if bougies else None
        except Exception:
            r = None
        with c:
            c.execute("UPDATE fantomes SET r=?, resolu=1 WHERE id=?", (r, fid))
    c.close()


# ================================ NOTES =================================
def _moy(x):
    return sum(x) / len(x) if x else None


def notes_live():
    """Renvoie {bot: (note, taille de l'échantillon)} pour les bots suffisamment testés."""
    c = _cnx()
    trades = c.execute("SELECT r, votes, COALESCE(risques,'[]') FROM trades WHERE r IS NOT NULL "
                       "ORDER BY id DESC LIMIT 300").fetchall()
    fant = c.execute("SELECT r, vetos FROM fantomes WHERE resolu=1 AND r IS NOT NULL ORDER BY id DESC LIMIT 1000").fetchall()
    c.close()
    res = {}
    # Votants
    groupes = {}
    for r, votes, _ in trades:
        for nom, v in json.loads(votes).items():
            if v is None:
                continue
            g = groupes.setdefault(nom, ([], []))
            (g[0] if v >= 0.5 else g[1]).append(r)
    for nom, (oui, non) in groupes.items():
        if len(oui) + len(non) >= config.ECHANTILLON_MIN and len(oui) >= 5 and len(non) >= 5:
            res[nom] = (note_sur_10(_moy(oui) - _moy(non)), len(oui) + len(non))
    # Vetos : trades exécutés SANS enfreindre le veto, contre cas bloqués (fantômes) + trades d'exploration
    # achetés MALGRÉ lui (v14 : de vrais résultats, pas seulement des simulations)
    par_veto = {}
    for r, vetos in fant:
        for v in json.loads(vetos):
            par_veto.setdefault(v, []).append(r)
    risques_trades = [(r, set(json.loads(rq))) for r, _, rq in trades]
    for r, rq in risques_trades:
        for v in rq:
            if v in VETOS:
                par_veto.setdefault(v, []).append(r)
    for v, rs in par_veto.items():
        base = [r for r, rq in risques_trades if v not in rq]
        if len(rs) >= config.ECHANTILLON_MIN and len(base) >= 10:
            res[v] = (note_sur_10(_moy(base) - _moy(rs)), len(rs))
    return res


def notes_backtest():
    if not os.path.exists(config.FICHIER_NOTES_BACKTEST):
        return {}
    with open(config.FICHIER_NOTES_BACKTEST, encoding="utf-8") as f:
        # note retenue = note moyenne, plafonnée à 7,9 si le bot n'a pas tenu sur toutes les périodes
        return {k: (v["note_retenue"], v["n"]) for k, v in json.load(f).items()
                if v.get("n", 0) >= config.ECHANTILLON_MIN and "note_retenue" in v}


def notes():
    """Les résultats réels remplacent le backtest dès qu'ils sont assez nombreux."""
    n = notes_backtest()
    n.update(notes_live())
    return n


def poids():
    """>= 8 : fiable (x1,5) | 5 à 8 : en observation (x1) | < 5 : coupé (x0)."""
    w = {}
    for bot, (note, _) in notes().items():
        if bot in VETOS:
            continue          # un veto n'est jamais coupé automatiquement : il protège le capital
        w[bot] = 1.5 if note >= config.NOTE_FIABLE else (0.0 if note < config.NOTE_COUPURE else 1.0)
    return w


def bulletin():
    import langage as L
    n = notes()
    if not n:
        return ("📋 Notes des bots : pas encore assez de résultats. Il faut une trentaine de ventes terminées "
                "pour noter un bot (les essais 🧪 accélèrent les choses).")
    lignes = ["📋 Notes des bots (sur 10 · 5 = pas mieux que le hasard · 8 et plus = fiable)"]
    for b, (note, taille) in sorted(n.items(), key=lambda x: -x[1][0]):
        if note >= config.NOTE_FIABLE:
            etat = "fiable ✅ (sa voix compte plus)"
        elif note >= config.NOTE_COUPURE:
            etat = "en observation"
        else:
            etat = "à revoir ⚠️" if b in VETOS else "écarté ⛔ (ne vote plus)"
        nom = L.bot(b) if b not in VETOS else f"Alerte « {L.risque(b)} »"
        lignes.append(f"• {nom} : {note:.1f}/10 ({taille} cas) — {etat}")
    return "\n".join(lignes)


def rapport(mode=None):
    f, a = _filtre_mode(mode)
    c = _cnx()
    lignes = c.execute("SELECT pnl_pct, pnl_usdt, r FROM trades WHERE 1=1" + f, a).fetchall()
    c.close()
    if not lignes:
        return "aucune vente terminée pour l'instant."
    gains = [p for p, _, _ in lignes if p > 0]
    pertes = [p for p, _, _ in lignes if p <= 0]
    rs = [r for _, _, r in lignes if r is not None]
    n = len(lignes)
    import langage as L
    return (f"{L.pluriel(n, 'vente terminée', 'ventes terminées')} · {L.pourcent(len(gains) / n)} gagnantes · "
            f"gain moyen {L.pct(_moy(gains) or 0, 2)} · perte moyenne {L.pct(_moy(pertes) or 0, 2)} · "
            f"total {L.dollars(sum(u for _, u, _ in lignes), True)}")


def bilan_exploration():
    """Ce que chaque risque pris pendant les essais a rapporté : c'est la leçon pour l'équipe."""
    import langage as L
    c = _cnx()
    lignes = c.execute("SELECT r, pnl_usdt, COALESCE(risques,'[]') FROM trades WHERE r IS NOT NULL "
                       "AND COALESCE(mode,'strict')='exploration'").fetchall()
    strict = c.execute("SELECT r FROM trades WHERE r IS NOT NULL AND COALESCE(mode,'strict')='strict'").fetchall()
    c.close()
    if not lignes:
        return "Aucun essai terminé pour l'instant (un essai se termine quand la crypto est revendue)."
    rs = [r for r, _, _ in lignes]
    txt = [f"{L.pluriel(len(rs), 'essai terminé', 'essais terminés')} · {L.pourcent(sum(r > 0 for r in rs) / len(rs))} gagnants · "
           f"total {L.dollars(sum(u for _, u, _ in lignes), True)} · en moyenne {L.fois_risque(_moy(rs))}",
           L.EXPLICATION_R]
    if strict:
        txt.append(f"🎯 Bot prudent, pour comparer : {L.pluriel(len(strict), 'vente')}, en moyenne "
                   f"{L.fois_risque(_moy([r for (r,) in strict]))}")
    par = {}
    for r, _, rq in lignes:
        for x in json.loads(rq):
            par.setdefault(x, []).append(r)
    if par:
        txt.append("Ce que les essais ont appris (quand on achète malgré…) :")
        for x, lst in sorted(par.items(), key=lambda kv: -len(kv[1]))[:12]:
            m = _moy(lst)
            verdict = "ça a payé ✅" if m > 0.1 else ("ça a coûté ⚠️" if m < -0.1 else "sans effet net")
            txt.append(f"• {L.risque(x)} : {len(lst)} fois → {L.fois_risque(m)} ({verdict})")
    return "\n".join(txt)


# ================================ DUEL (v4) ================================
# Le champion trade pour de vrai ; champion ET challenger sont aussi suivis « dans l'ombre »
# (papier, mêmes règles de sortie que leurs gènes) pour les comparer à armes égales.
def _cnx_ombres():
    c = _cnx()
    c.execute("""CREATE TABLE IF NOT EXISTS ombres(
        id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, genome TEXT, symbole TEXT, ts REAL, entree REAL,
        atr REAL, params TEXT, r REAL, resolu INTEGER DEFAULT 0)""")
    return c


def ombre(role, genome_id, sym, entree, atr, params):
    c = _cnx_ombres()
    with c:
        c.execute("INSERT INTO ombres(role,genome,symbole,ts,entree,atr,params) VALUES (?,?,?,?,?,?,?)",
                  (role, genome_id, sym, time.time(), entree, atr, json.dumps(params)))
    c.close()


def resoudre_ombres(ex):
    c = _cnx_ombres()
    lignes = c.execute("SELECT id, symbole, ts, entree, atr, params FROM ombres WHERE resolu=0 LIMIT 20").fetchall()
    minutes = config.MINUTES[config.UNITE_BOUGIE]
    for oid, sym, ts, entree, atr, params in lignes:
        p = json.loads(params)
        if time.time() - ts < (p["horizon_bougies"] * minutes + 30) * 60:
            continue
        try:
            ohlcv = ex.fetch_ohlcv(sym, config.UNITE_BOUGIE, since=int(ts * 1000), limit=p["horizon_bougies"] + 5)
            bougies = [(o, h, l, cl) for _, o, h, l, cl, _ in ohlcv]
            r = simuler_sortie(bougies, entree, atr, p["horizon_bougies"], p)[0] if bougies else None
        except Exception:
            r = None
        with c:
            c.execute("UPDATE ombres SET r=?, resolu=1 WHERE id=?", (r, oid))
    c.close()


def _stats_ombres(genome_id, depuis):
    c = _cnx_ombres()
    rs = [r for (r,) in c.execute("SELECT r FROM ombres WHERE genome=? AND resolu=1 AND r IS NOT NULL AND ts>=?",
                                  (genome_id, depuis)).fetchall()]
    c.close()
    return (sum(rs) / len(rs) if rs else None), len(rs)


def duel():
    """Juge le duel. Un challenger qui gagne n'est PAS promu : il attend ton approbation (/approuver).
    Un challenger qui perd est éliminé automatiquement (réduire le changement ne demande pas d'accord)."""
    import datetime as dt
    import shutil
    import approbations
    import registre
    import strategie as S
    ch = S.charger(S.FICHIER_CHALLENGER)
    if not ch:
        return None
    champ = S.champion()
    debut = dt.datetime.fromisoformat(ch["date"]).timestamp()
    jours = (time.time() - debut) / 86400
    e_ch, n_ch = _stats_ombres(ch["genome"]["id"], debut)
    e_cp, n_cp = _stats_ombres(champ["id"], debut)
    if jours < config.DUEL_JOURS_MIN or n_ch < config.DUEL_TRADES_MIN:
        if jours > config.DUEL_JOURS_MAX:
            shutil.move(S.FICHIER_CHALLENGER, f"challenger_rejete_{ch['genome']['id']}.json")
            registre.ajouter("duel", {"challenger": ch["genome"]["id"], "verdict": "écarté faute de trades", "trades": n_ch})
            return f"🧬 Duel terminé sans assez de trades ({n_ch}) : challenger écarté, le champion reste."
        return None
    e_cp = e_cp if e_cp is not None else 0.0
    if e_ch is not None and e_ch > e_cp + config.DUEL_AVANCE_R:
        ident = f"champion-{ch['genome']['id']}"
        texte = (f"Le challenger {ch['genome']['espece']} [{ch['genome']['id']}] a gagné son duel : "
                 f"{e_ch:+.2f} R contre {e_cp:+.2f} R pour le champion, sur {n_ch} trades en {jours:.0f} jours.\n"
                 f"{S.decrire(ch['genome'])}\nLe promouvoir champion ?")
        if approbations.demander("champion", ident, texte,
                                 {"challenger_R": e_ch, "champion_R": e_cp, "trades": n_ch, "jours": round(jours, 1)}):
            registre.ajouter("duel", {"challenger": ch["genome"]["id"], "verdict": "gagné, en attente d'approbation",
                                      "challenger_R": e_ch, "champion_R": e_cp, "trades": n_ch})
        return None
    if jours > config.DUEL_JOURS_MAX or (e_ch is not None and e_ch < e_cp - config.DUEL_AVANCE_R):
        shutil.move(S.FICHIER_CHALLENGER, f"challenger_rejete_{ch['genome']['id']}.json")
        registre.ajouter("duel", {"challenger": ch["genome"]["id"], "verdict": "éliminé", "challenger_R": e_ch,
                                  "champion_R": e_cp})
        return f"🧬 Challenger éliminé : {e_ch:+.2f} R contre {e_cp:+.2f} R pour le champion. Le champion reste."
    return None


def promouvoir(demande):
    """Exécutée UNIQUEMENT après ton approbation : le challenger devient champion (échange à chaud)."""
    import datetime as dt
    import registre
    import strategie as S
    ch = S.charger(S.FICHIER_CHALLENGER)
    if not ch:
        return "Plus de challenger à promouvoir (déjà traité ?)."
    archive = []
    if os.path.exists("champions_archive.json"):
        with open("champions_archive.json", encoding="utf-8") as f:
            archive = json.load(f)
    ancien = S.charger(S.FICHIER_CHAMPION)
    if ancien:
        archive.append(ancien)
    with open("champions_archive.json.tmp", "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    os.replace("champions_archive.json.tmp", "champions_archive.json")
    ch["promu"] = dt.date.today().isoformat()
    ch["duel"] = demande.get("donnees", {})
    ch["approuve_par_operateur"] = True
    with open(S.FICHIER_CHAMPION + ".tmp", "w", encoding="utf-8") as f:
        json.dump(ch, f, indent=2, ensure_ascii=False)
    os.replace(S.FICHIER_CHAMPION + ".tmp", S.FICHIER_CHAMPION)
    os.remove(S.FICHIER_CHALLENGER)
    registre.ajouter("promotion", {"champion": ch["genome"]["id"], "espece": ch["genome"]["espece"],
                                   "genome": ch["genome"], "duel": ch["duel"]})
    return f"🏆 NOUVEAU CHAMPION : {ch['genome']['espece']} [{ch['genome']['id']}]. Échange à chaud effectué."


def refuser_challenger():
    import shutil
    import strategie as S
    ch = S.charger(S.FICHIER_CHALLENGER)
    if ch:
        shutil.move(S.FICHIER_CHALLENGER, f"challenger_rejete_{ch['genome']['id']}.json")
    return "Challenger refusé : le champion actuel reste en place."


def etat_evolution():
    import strategie as S
    champ = S.champion()
    lignes = [f"🏆 Champion [{champ['id']}] : {S.decrire(champ)}"]
    ch = S.charger(S.FICHIER_CHALLENGER)
    if ch:
        import datetime as dt
        debut = dt.datetime.fromisoformat(ch["date"]).timestamp()
        e_ch, n_ch = _stats_ombres(ch["genome"]["id"], debut)
        e_cp, n_cp = _stats_ombres(champ["id"], debut)
        lignes.append(f"🧬 Challenger [{ch['genome']['id']}] : {S.decrire(ch['genome'])}")
        lignes.append(f"Duel depuis {(time.time() - debut) / 86400:.0f} j : challenger "
                      f"{'—' if e_ch is None else f'{e_ch:+.2f} R'} ({n_ch} trades) contre champion "
                      f"{'—' if e_cp is None else f'{e_cp:+.2f} R'} ({n_cp} trades)")
    else:
        lignes.append("Pas de challenger en cours : prochaine évolution au prochain passage.")
    return "\n".join(lignes)

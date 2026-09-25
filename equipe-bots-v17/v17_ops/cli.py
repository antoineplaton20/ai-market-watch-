"""Lancement du moteur V17 : python -m v17_ops   (service equipe-bots-v17 sur le serveur).

Options utiles :
  --once --price 50000     un seul passage avec un prix injecté (test sans réseau)
  --mode paper             force le mode (sinon V17_MODE du .env, paper par défaut)
  --symbol BTC/USDT,ETH/USDT
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler

from .core.config import MODES, settings

_log = logging.getLogger("v17")


def _journal(fichier):
    # Doit être fait AVANT l'import d'alertes.py (qui configurerait sinon bot.log, le journal du bot principal)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | V17 | %(message)s",
                        handlers=[RotatingFileHandler(fichier, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
                                  logging.StreamHandler()])


RESEAU_ALERTE = 5


def _est_reseau(ex):
    """Erreurs réseau de ccxt (NetworkError et ses filles : délai dépassé, Binance indisponible...)."""
    return any(c.__name__ in ("NetworkError", "ConnectionError", "Timeout") for c in type(ex).__mro__)


CODE_VERROU = 3


def _verrou(chemin_db):
    """Une seule v17 à la fois (service systemd OU script Termius) : deux moteurs = ordres en double."""
    import fcntl
    import os
    dossier = os.path.dirname(chemin_db) or "."
    os.makedirs(dossier, exist_ok=True)
    f = open(os.path.join(dossier, "v17.lock"), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _arret(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m v17_ops")
    p.add_argument('--mode', choices=list(MODES), default=None)
    p.add_argument('--symbol', default=None, help="un ou plusieurs symboles séparés par des virgules")
    p.add_argument('--interval', type=float, default=None)
    p.add_argument('--price', type=float, default=None)
    p.add_argument('--once', action='store_true')
    a = p.parse_args(argv)

    if not a.once:
        _journal(settings.log_file)
    from .notify import Notifier
    from .workers.engine import ConfigError, OpsEngine

    verrou = _verrou(settings.ops_db)
    if verrou is None:
        _log.error("Une autre v17 tourne déjà sur cette base : arrêt (deux moteurs = ordres en double).")
        print("V17 OPS : une autre v17 tourne déjà (bots v17-etat). Arrêt.")
        return CODE_VERROU
    symboles = [x.strip().upper() for x in a.symbol.split(',') if x.strip()] if a.symbol else list(settings.symbols)
    intervalle = a.interval or settings.interval
    notifier = Notifier(enabled=settings.telegram and not a.once)
    try:
        e = OpsEngine(a.mode, symboles, settings=settings, notifier=notifier)
    except (ConfigError, RuntimeError) as ex:
        _log.error("Démarrage impossible : %s", ex)
        print(f"V17 OPS : démarrage impossible : {ex}")
        notifier.send(f"⛔ v17 non démarrée : {ex}")
        return 2
    print(f'V17 OPS mode={e.mode} symbol={",".join(e.symbols)}')
    if not a.once:
        signal.signal(signal.SIGTERM, _arret)
        from .format import MODES as NOMS_MODES
        notifier.send(f"🚀 v17 démarrée — {NOMS_MODES.get(e.mode, e.mode)}"
                      + (f" (clés : {e.origine_cles})" if e.origine_cles else "")
                      + f" · {', '.join(s.split('/')[0] for s in e.symbols)} · "
                      f"décision à chaque bougie de {settings.timeframe}. Suivi : /v17", important=False)
    derniere_purge = 0.0
    echecs_reseau = 0                      # tours consécutifs où Binance n'a pas répondu
    reseau_signale = False
    try:
        while True:
            reseau_ko = False
            for sym in list(e.symbols):
                try:
                    r = e.tick(sym, a.price)
                    if a.once:
                        print(r)
                    elif r.get('status') != 'waiting':                   # « waiting » = bougie pas encore fermée
                        _log.info("%s %s", sym, r)
                except KeyboardInterrupt:
                    raise
                except Exception as ex:                               # un symbole en erreur n'arrête pas les autres
                    if type(ex).__name__ == 'BadSymbol':
                        e.symbols.remove(sym)
                        notifier.send(f"⚠️ {sym} n'existe pas chez Binance : retiré. Corrige la liste avec "
                                      "« bots v17-symboles » dans Termius.")
                        continue
                    if a.once:
                        print({'status': 'error', 'error': str(ex)})
                    _log.warning("%s : %s", sym, ex)
                    if _est_reseau(ex):                              # coupure passagère : prévenir seulement si ça dure
                        reseau_ko = True
                    else:
                        notifier.erreur(f'tick-{type(ex).__name__}', f"❗ Problème sur {sym} : {str(ex)[:300]}")
            echecs_reseau = echecs_reseau + 1 if reseau_ko else 0
            if echecs_reseau == RESEAU_ALERTE:
                notifier.send(f"🔴 Binance ne répond plus depuis environ {RESEAU_ALERTE * intervalle / 60:.0f} min : "
                              "la v17 attend (rien n'est acheté ni vendu). Message au retour de la connexion.",
                              important=False)
            elif echecs_reseau == 0 and reseau_signale:
                notifier.send("✅ Connexion à Binance revenue.", important=False)
            reseau_signale = echecs_reseau >= RESEAU_ALERTE
            e.heartbeat({'network_failures': echecs_reseau})
            if time.time() - derniere_purge > 86400:
                derniere_purge = time.time()
                e.store.purge(90)
            if a.once:
                break
            if not e.symbols:
                notifier.send("⛔ v17 arrêtée : aucun symbole valable (bots v17-symboles).")
                return 2
            time.sleep(intervalle)
    except KeyboardInterrupt:
        _log.info("Arrêt demandé : v17 arrêtée proprement (portefeuille enregistré).")
    return 0


if __name__ == '__main__':
    sys.exit(main())

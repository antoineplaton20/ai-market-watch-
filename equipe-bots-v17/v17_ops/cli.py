"""Lancement du moteur V17 : python -m v17_ops   (service equipe-bots-v17 sur le serveur).

Options utiles :
  --once --price 50000     un seul passage avec un prix injecté (test sans réseau)
  --mode paper             force le mode (sinon V17_MODE du .env, paper par défaut)
  --symbol BTC/USDT,ETH/USDT

Robustesse (le moteur ne s'arrête que sur demande : Ctrl+C, bots v17-arreter, termius_demo_stop.sh) :
- chaque symbole et chaque tâche annexe sont isolés : une erreur n'arrête ni les autres ni la boucle ;
- réglage invalide : attente puis nouvel essai (le .env est relu au redémarrage), alerte au plus toutes les 6 h ;
- tous les symboles invalides : repli sur BTC/USDT au lieu de s'arrêter ;
- erreurs (hors coupure réseau) sur tous les symboles pendant ~1 h : sortie volontaire pour un redémarrage à neuf (systemd / superviseur) ;
- signal de vie systemd (WATCHDOG=1) : un moteur figé est tué et relancé par systemd.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import socket
import sys
import time
from logging.handlers import RotatingFileHandler

from .core.config import CORRECTIONS, MODES, settings

_log = logging.getLogger("v17")


def _journal(fichier):
    # Doit être fait AVANT l'import d'alertes.py (qui configurerait sinon bot.log, le journal du bot principal)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | V17 | %(message)s",
                        handlers=[RotatingFileHandler(fichier, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
                                  logging.StreamHandler()])


RESEAU_ALERTE = 5
DUREE_KO_AVANT_REDEMARRAGE_S = 3600     # ~1 h d'erreurs (hors coupure réseau) sur tous les symboles : redémarrage à neuf
ATTENTE_CONFIG_S = 1800                  # réglage invalide : nouvel essai dans 30 min
SYMBOLE_REPLI = "BTC/USDT"
CODE_REDEMARRAGE = 1


def sd_notify(message):
    """Signal de vie pour systemd (Type=notify / WatchdogSec). Sans systemd : ne fait rien."""
    adresse = os.environ.get("NOTIFY_SOCKET")
    if not adresse:
        return
    if adresse.startswith("@"):
        adresse = "\0" + adresse[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(adresse)
            sock.sendall(message.encode())
    except OSError:
        pass


def dormir(secondes):
    """time.sleep ; sous systemd, découpé pour que le chien de garde reçoive un signe de vie toutes les 15 s."""
    if not os.environ.get("NOTIFY_SOCKET"):
        time.sleep(secondes)
        return
    morceaux = max(1, math.ceil(secondes / 15.0))
    for _ in range(morceaux):
        sd_notify("WATCHDOG=1")
        time.sleep(secondes / morceaux)
    sd_notify("WATCHDOG=1")


def _alerte_rare(notifier, chemin_db, cle, message, fenetre_s=6 * 3600):
    """Alerte qui survit aux redémarrages : au plus une par `fenetre_s` (mémoire dans runtime/)."""
    fichier = os.path.join(os.path.dirname(chemin_db) or ".", "v17_alertes.json")
    try:
        with open(fichier, encoding="utf-8") as f:
            deja = json.load(f)
    except Exception:
        deja = {}
    if time.time() - float(deja.get(cle, 0) or 0) < fenetre_s:
        _log.warning(message)
        return
    deja[cle] = time.time()
    try:
        os.makedirs(os.path.dirname(fichier) or ".", exist_ok=True)
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(deja, f)
    except OSError:
        pass
    notifier.send(message, important=False)


def tours_avant_redemarrage(intervalle):
    return max(3, math.ceil(DUREE_KO_AVANT_REDEMARRAGE_S / max(intervalle, 1)))


def _proteger(nom, fonction, *args):
    """Tâche annexe (signe de vie, purge...) : une erreur est journalisée, jamais fatale."""
    try:
        return fonction(*args)
    except KeyboardInterrupt:
        raise
    except Exception as ex:
        _log.warning("%s : %s", nom, ex)
        return None


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
    if not a.once:
        signal.signal(signal.SIGTERM, _arret)
    try:
        e = OpsEngine(a.mode, symboles, settings=settings, notifier=notifier)
    except (ConfigError, RuntimeError, ValueError) as ex:
        _log.error("Démarrage impossible : %s", ex)
        print(f"V17 OPS : démarrage impossible : {ex}")
        if a.once:
            return 2
        _alerte_rare(notifier, settings.ops_db, "config",
                     f"⛔ v17 en attente : {ex}. Nouvel essai automatique toutes les {ATTENTE_CONFIG_S // 60} min "
                     "(corrige le .env, ou bots v17-fictif).")
        sd_notify("READY=1")
        try:
            dormir(ATTENTE_CONFIG_S)
        except KeyboardInterrupt:
            return 0
        finally:
            verrou.close()
        return 2                                  # redémarré par systemd / le superviseur : .env relu
    print(f'V17 OPS mode={e.mode} symbol={",".join(e.symbols)}')
    if not a.once:
        sd_notify("READY=1")
        for correction in CORRECTIONS:
            _alerte_rare(notifier, settings.ops_db, f"reglage-{correction.split('=')[0]}", f"⚠️ Réglage {correction}.")
        from .format import MODES as NOMS_MODES
        notifier.send(f"🚀 v17 démarrée — {NOMS_MODES.get(e.mode, e.mode)}"
                      + (f" (clés : {e.origine_cles})" if e.origine_cles else "")
                      + f" · {', '.join(s.split('/')[0] for s in e.symbols)} · "
                      f"décision à chaque bougie de {settings.timeframe}. Suivi : /v17", important=False)
    derniere_purge = 0.0
    echecs_reseau = 0                      # tours consécutifs où Binance n'a pas répondu
    reseau_signale = False
    tours_ko = 0                           # tours consécutifs sans AUCUN symbole traité (hors coupure réseau)
    tours_max = tours_avant_redemarrage(intervalle)
    try:
        while True:
            reseau_ko = False
            reussis = 0
            for sym in list(e.symbols):
                sd_notify("WATCHDOG=1")
                try:
                    r = e.tick(sym, a.price)
                    reussis += 1
                    if a.once:
                        print(r)
                    elif r.get('status') != 'waiting':                   # « waiting » = bougie pas encore fermée
                        _log.info("%s %s", sym, r)
                except KeyboardInterrupt:
                    raise
                except Exception as ex:                               # un symbole en erreur n'arrête pas les autres
                    if type(ex).__name__ == 'BadSymbol':
                        e.symbols.remove(sym)
                        _proteger("telegram", notifier.send,
                                  f"⚠️ {sym} n'existe pas chez Binance : retiré. Corrige la liste avec "
                                  "« bots v17-symboles » dans Termius.")
                        continue
                    if a.once:
                        print({'status': 'error', 'error': str(ex)})
                    _log.warning("%s : %s", sym, ex)
                    if _est_reseau(ex):                              # coupure passagère : prévenir seulement si ça dure
                        reseau_ko = True
                    else:
                        _proteger("telegram", notifier.erreur, f'tick-{type(ex).__name__}',
                                  f"❗ Problème sur {sym} : {str(ex)[:300]}")
            echecs_reseau = echecs_reseau + 1 if reseau_ko else 0
            if echecs_reseau == RESEAU_ALERTE:
                _proteger("telegram", notifier.send,
                          f"🔴 Binance ne répond plus depuis environ {RESEAU_ALERTE * intervalle / 60:.0f} min : "
                          "la v17 attend (rien n'est acheté ni vendu) et réessaie en continu. "
                          "Message au retour de la connexion.", False)
            elif echecs_reseau == 0 and reseau_signale:
                _proteger("telegram", notifier.send, "✅ Connexion à Binance revenue.", False)
            reseau_signale = echecs_reseau >= RESEAU_ALERTE
            _proteger("signe de vie", e.heartbeat, {'network_failures': echecs_reseau})
            if time.time() - derniere_purge > 86400:
                derniere_purge = time.time()
                _proteger("purge", e.store.purge, 90)
            if a.once:
                break
            if not e.symbols:                     # plus aucun symbole valable : repli, jamais d'arrêt
                e.symbols.append(SYMBOLE_REPLI)
                e.closes.setdefault(SYMBOLE_REPLI, [])
                _proteger("telegram", notifier.send,
                          f"⚠️ Aucun symbole valable : la v17 continue sur {SYMBOLE_REPLI}. "
                          "Corrige la liste avec « bots v17-symboles » dans Termius.")
            tours_ko = tours_ko + 1 if e.symbols and reussis == 0 and not reseau_ko else 0
            if tours_ko >= tours_max:
                _log.warning("Aucun symbole traité depuis %d tours : redémarrage à neuf.", tours_ko)
                _proteger("telegram", _alerte_rare, notifier, settings.ops_db, "redemarrage",
                          "♻️ v17 : erreurs continues depuis environ 1 h, redémarrage à neuf automatique.")
                return CODE_REDEMARRAGE
            dormir(intervalle)
    except KeyboardInterrupt:
        _log.info("Arrêt demandé : v17 arrêtée proprement (portefeuille enregistré).")
    return 0


if __name__ == '__main__':
    sys.exit(main())

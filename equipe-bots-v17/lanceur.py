"""CHIEN DE GARDE. Lance le bot avec : python lanceur.py   (au lieu de python main.py)
- Relance le bot s'il plante, SANS JAMAIS ABANDONNER (attente croissante : 10 s, 20 s, 40 s... plafonnée à 5 min).
- Relance le bot s'il ne donne plus signe de vie pendant 15 min (bot figé).
- Tempête de plantages : il continue de relancer et prévient au plus une fois par heure (avec la dernière erreur).
- Un autre bot tient déjà le verrou (code 3) : il attend et réessaie, il ne s'arrête pas.
- Seul un arrêt demandé l'arrête : Ctrl+C ou « bots arreter » (SIGINT/SIGTERM de systemd).
  Les stops restent actifs chez Binance."""
import os
import signal
import subprocess
import sys
import time
import config
from alertes import alerte, log
from securite import age_battement, FICHIER_BATTEMENT

CODE_VERROU = 3          # main.py renvoie 3 si un autre bot tourne déjà
ATTENTE_MAX_S = 300
ALERTE_TEMPETE_S = 3600


def _prevenir(msg, important=True):
    """Telegram ne doit JAMAIS faire tomber le chien de garde."""
    try:
        alerte(msg, important=important)
    except Exception as e:
        try:
            log(f"{msg} (Telegram indisponible : {e})")
        except Exception:
            pass


def attente_relance(n_plantages):
    return min(ATTENTE_MAX_S, 10 * 2 ** max(0, n_plantages - 1))


def _terminer(proc):
    try:
        proc.terminate()
        proc.wait(timeout=60)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=10)
        except Exception:
            pass


def main():
    plantages = []
    derniere_alerte_tempete = 0.0
    _prevenir("🐕 Surveillance démarrée : si le bot plante ou se fige, il est relancé automatiquement, sans limite.")
    while True:
        try:
            if os.path.exists(FICHIER_BATTEMENT):
                os.remove(FICHIER_BATTEMENT)
        except OSError:
            pass
        try:
            proc = subprocess.Popen([sys.executable, "main.py"])
        except Exception as e:                    # disque plein, mémoire... : on réessaie plus tard
            log(f"Lancement du bot impossible : {e}")
            time.sleep(60)
            continue
        debut = time.time()
        try:
            while proc.poll() is None:
                time.sleep(30)
                age = age_battement()
                if time.time() - debut > config.BATTEMENT_MAX_S and (age is None or age > config.BATTEMENT_MAX_S):
                    _prevenir(f"🥶 Le bot ne répondait plus depuis {config.BATTEMENT_MAX_S // 60} min : je le redémarre.")
                    try:
                        proc.kill()
                        proc.wait(timeout=30)
                    except Exception:
                        pass
                    break
        except KeyboardInterrupt:
            _terminer(proc)
            log("Arrêt demandé : bot et chien de garde arrêtés. Les stops restent actifs chez Binance.")
            return
        code = proc.returncode
        if code == CODE_VERROU:
            log("Un autre bot tient le verrou : nouvel essai dans 60 s.")
            time.sleep(60)
            continue
        maintenant = time.time()
        plantages = [t for t in plantages if maintenant - t < 3600] + [maintenant]
        attente = attente_relance(len(plantages))
        if len(plantages) > config.PLANTAGES_MAX_H:
            if maintenant - derniere_alerte_tempete >= ALERTE_TEMPETE_S:
                derniere_alerte_tempete = maintenant
                _prevenir(f"🌪 {len(plantages)} arrêts du bot en 1 h (dernier code {code}). Je continue de le relancer "
                          f"toutes les {attente // 60 or 1} min environ. Détail : « bots journal » dans Termius.")
            else:
                log(f"Bot arrêté (code {code}) : relance dans {attente} s.")
        else:
            _prevenir(f"♻️ Le bot s'est arrêté tout seul (code {code}) : je le relance dans {attente} s.",
                      important=False)
        time.sleep(attente)


def _sigterm(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _sigterm)
    try:
        main()
    except KeyboardInterrupt:
        log("Chien de garde arrêté. Les stops restent actifs chez Binance.")

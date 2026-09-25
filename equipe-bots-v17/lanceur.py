"""CHIEN DE GARDE. Lance le bot avec : python lanceur.py   (au lieu de python main.py)
- Relance le bot s'il plante (attente croissante : 10 s, 20 s, 40 s... jusqu'à 5 min).
- Relance le bot s'il ne donne plus signe de vie pendant 15 min (bot figé).
- S'arrête et prévient après 5 plantages en 1 h (mieux vaut un bot arrêté qu'un bot qui boucle).
- Ctrl+C : arrêt propre du bot et du chien de garde. Les stops restent actifs chez Binance."""
import os
import subprocess
import sys
import time
import config
from alertes import alerte, log
from securite import age_battement, FICHIER_BATTEMENT

CODE_VERROU = 3          # main.py renvoie 3 si un autre bot tourne déjà


def main():
    plantages = []
    alerte("🐕 Surveillance démarrée : si le bot plante, il sera relancé automatiquement.")
    while True:
        if os.path.exists(FICHIER_BATTEMENT):
            os.remove(FICHIER_BATTEMENT)
        proc = subprocess.Popen([sys.executable, "main.py"])
        debut = time.time()
        try:
            while proc.poll() is None:
                time.sleep(30)
                age = age_battement()
                if time.time() - debut > config.BATTEMENT_MAX_S and (age is None or age > config.BATTEMENT_MAX_S):
                    alerte(f"🥶 Le bot ne répondait plus depuis {config.BATTEMENT_MAX_S // 60} min : je le redémarre.")
                    proc.kill()
                    proc.wait()
                    break
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            log("Arrêt demandé : bot et chien de garde arrêtés. Les stops restent actifs chez Binance.")
            return
        code = proc.returncode
        if code == 0:
            log("Le bot s'est arrêté normalement.")
            return
        if code == CODE_VERROU:
            log("Un autre bot tourne déjà : le chien de garde s'arrête.")
            return
        plantages = [t for t in plantages if time.time() - t < 3600] + [time.time()]
        if len(plantages) > config.PLANTAGES_MAX_H:
            alerte(f"🛑 {len(plantages)} plantages en 1 h : j'arrête de relancer le bot. Tape « bots etat » dans Termius et envoie une capture à Claude.")
            return
        attente = min(300, 10 * 2 ** (len(plantages) - 1))
        alerte(f"♻️ Le bot s'est arrêté tout seul (code {code}) : je le relance dans {attente} s.")
        time.sleep(attente)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Chien de garde arrêté. Les stops restent actifs chez Binance.")

"""VIGIE DU COURS — le prix de l'or en direct, sans attendre : flux WebSocket Binance (données publiques, sans clé).

- XAUUSDT (contrat perpétuel qui suit l'once d'or) et PAXGUSDT (jeton adossé à 1 once physique) en parallèle ;
- chaque message met à jour le dernier prix et mesure le RETARD réel (heure de l'événement Binance -> réception) ;
- chaque bougie d'1 minute terminée est enregistrée ; à chaque (re)connexion, les minutes manquantes sont
  rattrapées par l'API REST : aucun trou silencieux ;
- si Binance ne répond plus, secours : or COMEX (Yahoo, différé, signalé comme tel) ;
- reconnexion sans fin avec attente croissante ; systemd relance le service s'il se fige (watchdog).
"""
from __future__ import annotations

import json
import logging
import threading
import time

from . import base, config, donnees

_log = logging.getLogger("or.flux")
WS = {"XAUUSDT": "wss://fstream.binance.com/ws/xauusdt@kline_1m",
      "PAXGUSDT": "wss://stream.binance.com:9443/ws/paxgusdt@kline_1m"}
REST = {"XAUUSDT": "https://fapi.binance.com/fapi/v1/klines", "PAXGUSDT": "https://api.binance.com/api/v3/klines"}
SILENCE_MAX_S = 60


def lire_message(texte, recu_ms=None):
    """Message kline Binance -> (bougie [ts,o,h,l,c,v], fermée ?, prix, retard_ms). None si message inattendu."""
    try:
        m = json.loads(texte)
        k = m["k"]
        bougie = [int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])]
        recu_ms = recu_ms if recu_ms is not None else time.time() * 1000
        return bougie, bool(k["x"]), bougie[4], max(0.0, recu_ms - float(m.get("E", recu_ms)))
    except (ValueError, KeyError, TypeError):
        return None


def rattraper(source, session=None, maintenant_ms=None):
    """Minutes manquantes depuis la dernière bougie enregistrée (au plus 1000 par appel, 3 appels)."""
    import requests
    s = session or requests
    maintenant_ms = maintenant_ms or int(time.time() * 1000)
    total = 0
    for _ in range(3):
        dernieres = donnees.charger_lignes(source, "1m", limite=1)
        depuis = dernieres[-1][0] + 60_000 if dernieres else maintenant_ms - 1000 * 60_000
        if depuis > maintenant_ms - 120_000:
            break
        r = s.get(REST[source], params={"symbol": source, "interval": "1m", "startTime": depuis, "limit": 1000},
                  timeout=20)
        r.raise_for_status()
        lignes = [[int(x[0]), *map(float, x[1:6])] for x in r.json() if int(x[0]) + 60_000 <= maintenant_ms]
        if not lignes:
            break
        total += donnees.inserer(source, "1m", lignes)
    return total


class Vigie:
    """Un fil par source : WebSocket + rattrapage + mise à jour du dernier prix."""

    def __init__(self, source):
        self.source = source
        self.dernier_message = 0.0
        self.derniere_ecriture = 0.0
        self.connexions = 0

    def _sur_message(self, _ws, texte):
        res = lire_message(texte)
        if not res:
            return
        bougie, fermee, prix, retard = res
        self.dernier_message = time.time()
        if fermee:
            donnees.inserer(self.source, "1m", [bougie])
        if fermee or self.dernier_message - self.derniere_ecriture >= 1.0:     # au plus 1 écriture par seconde
            self.derniere_ecriture = self.dernier_message
            base.ecrire(f"direct:{self.source}", {"prix": prix, "ts": time.time(), "retard_ms": retard,
                                                  "source": f"Binance {self.source} (temps réel)"})

    def tourner(self):
        import websocket
        attente = 2
        while True:
            try:
                rattraper(self.source)
            except Exception as ex:
                _log.warning("%s : rattrapage impossible (%s)", self.source, ex)
            ws = websocket.WebSocketApp(WS[self.source], on_message=self._sur_message)
            self.connexions += 1
            debut = time.time()
            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as ex:
                _log.warning("%s : flux coupé (%s)", self.source, ex)
            attente = 2 if time.time() - debut > 300 else min(attente * 2, 120)
            time.sleep(attente)


def secours_comex(session=None):
    """Dernier prix de l'or COMEX (Yahoo, différé de quelques minutes)."""
    from .marches_lies import telecharger
    ts, c = telecharger("GC=F", "1m", "1d", session)
    if len(c):
        base.ecrire("direct:GC", {"prix": float(c[-1]), "ts": time.time(), "retard_ms": (time.time() - ts[-1]) * 1000,
                                  "source": "COMEX via Yahoo (différé)"})


class VigieMT5:
    """Cours XAUUSD du courtier MT5 (démo), interrogé chaque seconde par le pont local."""

    def __init__(self):
        self.dernier_temps = None
        self.dernier_changement = 0.0
        self.dernier_message = 0.0

    def lire(self, appel=None):
        from . import mt5
        t = (appel or mt5.appel)("tick", delai=10)
        maintenant = time.time()
        if t["time_msc"] != self.dernier_temps:
            self.dernier_temps, self.dernier_changement = t["time_msc"], maintenant
        self.dernier_message = maintenant
        base.ecrire("direct:MT5", {"prix": (t["bid"] + t["ask"]) / 2, "bid": t["bid"], "ask": t["ask"],
                                   "ts": self.dernier_changement, "retard_ms": (maintenant - self.dernier_changement) * 1000,
                                   "source": f"MetaTrader 5 {config.MT5_SYMBOLE} (démo)"})

    def tourner(self):
        while True:
            try:
                self.lire()
                time.sleep(1)
            except Exception as ex:
                _log.info("MT5 : cours indisponible (%s)", ex)
                time.sleep(15)


def prix_direct():
    """Meilleur prix disponible : source principale, MT5, l'autre source Binance, sinon COMEX différé."""
    maintenant = time.time()
    for s in (config.SOURCE_PRINCIPALE, "MT5", *[x for x in config.SOURCES_DIRECT if x != config.SOURCE_PRINCIPALE], "GC"):
        d = base.lire(f"direct:{s}")
        if d and maintenant - d.get("ts", 0) < (300 if s == "GC" else SILENCE_MAX_S):
            return {**d, "cle": s, "age_s": maintenant - d["ts"]}
    return None


def main():
    from .systemd import notifier, dormir
    vigies = [Vigie(s) for s in config.SOURCES_DIRECT]
    for v in vigies:
        threading.Thread(target=v.tourner, daemon=True, name=f"vigie-{v.source}").start()
    if config.MT5_ACTIF:
        threading.Thread(target=VigieMT5().tourner, daemon=True, name="vigie-MT5").start()
    notifier("READY=1")
    while True:
        dormir(30)
        if all(time.time() - v.dernier_message > SILENCE_MAX_S * 5 for v in vigies):
            try:
                secours_comex()
            except Exception as ex:
                _log.warning("secours COMEX indisponible : %s", ex)

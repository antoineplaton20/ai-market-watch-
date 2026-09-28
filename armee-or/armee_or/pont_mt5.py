"""PONT METATRADER 5 — seul morceau de l'armée qui touche le compte MT5.

La bibliothèque officielle « MetaTrader5 » n'existe que pour Windows : ce fichier tourne donc sous Wine, avec un
Python Windows, à côté du terminal MT5 (service armee-or-mt5). Il ne dépend QUE de la bibliothèque standard et de
MetaTrader5 (il n'importe rien du reste de l'armée).

Le reste de l'armée (Linux) lui parle par 127.0.0.1 uniquement : une ligne JSON par demande, une ligne par réponse.

Sécurités appliquées ICI, au plus près du compte :
- aucun ordre si le compte connecté n'est pas un compte DÉMO ;
- seules les positions portant un numéro magique de l'armée peuvent être fermées (tes ordres manuels : jamais) ;
- volume, stop et remplissage vérifiés contre les règles du symbole avant envoi.

Usage : python pont_mt5.py              (service)
        python pont_mt5.py --verifier   (connexion, compte, cours ; code 0 si tout va bien)
"""
import datetime as dt
import json
import ntpath
import os
import socketserver
import subprocess
import sys
import threading
import time

MAGIQUE_MIN, MAGIQUE_MAX = 770000, 770099           # numéros magiques réservés à l'armée
DEMO = 0                                             # ACCOUNT_TRADE_MODE_DEMO
TIMEFRAMES = {"1m": "TIMEFRAME_M1", "15m": "TIMEFRAME_M15", "1h": "TIMEFRAME_H1", "4h": "TIMEFRAME_H4",
              "1d": "TIMEFRAME_D1"}
RETCODE_OK = (10008, 10009, 10010)                   # placé, exécuté, exécuté partiellement
RETCODE_REMPLISSAGE = 10030                          # mode de remplissage refusé


def journal(*morceaux):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "|", *morceaux, flush=True)


def lire_env(chemin):
    valeurs = {}
    try:
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne and not ligne.startswith("#") and "=" in ligne:
                    cle, val = ligne.split("=", 1)
                    valeurs[cle.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return valeurs


def _d(x):
    return x._asdict() if hasattr(x, "_asdict") else x


class ErreurPont(Exception):
    pass


class Pont:
    def __init__(self, mt5, reglages, dossier=None):
        self.mt5 = mt5
        self.r = reglages
        self.dossier = dossier                     # dossier de l'armée : runtime/activer_algo pour le lanceur
        self.derniere_demande_algo = 0.0
        self.verrou = threading.RLock()
        self.symbole = reglages.get("OR_MT5_SYMBOLE") or "XAUUSD"
        self.derniere_connexion_ok = time.time()
        self.derniere_erreur = ""

    # ------------------------------------------------------------------ connexion
    def login(self):
        try:
            return int(self.r.get("OR_MT5_LOGIN") or 0)
        except ValueError:
            return 0

    def connecte(self):
        m = self.mt5
        t, a = m.terminal_info(), m.account_info()
        return bool(t is not None and t.connected and a is not None and a.login == self.login())

    def connecter(self):
        m = self.mt5
        if self.connecte():
            self.derniere_connexion_ok = time.time()
            return True
        m.shutdown()
        options = {"login": self.login(), "password": self.r.get("OR_MT5_MOT_DE_PASSE", ""),
                   "server": self.r.get("OR_MT5_SERVEUR") or "MetaQuotes-Demo", "timeout": 120000}
        if self.r.get("OR_MT5_TERMINAL"):
            options.update(path=self.r["OR_MT5_TERMINAL"], portable=True)
        if not m.initialize(**options):
            erreur = m.last_error()
            self.derniere_erreur = f"connexion MT5 impossible : {erreur}"
            if erreur and erreur[0] == -6:                       # « Authorization failed »
                self.derniere_erreur = (f"le serveur {options['server']} REFUSE le login …{str(options['login'])[-3:]} "
                                        "et son mot de passe (mot de passe changé ou mal tapé ?). Dans Termius : "
                                        "« or mt5 compte », puis le mot de passe PRINCIPAL actuel")
            journal(self.derniere_erreur)
            return False
        m.symbol_select(self.symbole, True)
        if self.connecte():
            self.derniere_connexion_ok = time.time()
            self.derniere_erreur = ""
            journal("connecté au compte", self.login(), "serveur", options["server"])
            return True
        self.derniere_erreur = "terminal lancé mais pas encore connecté au serveur"
        return False

    def exiger(self):
        if not self.connecter():
            raise ErreurPont(self.derniere_erreur or "MT5 non connecté")

    def est_demo(self):
        a = self.mt5.account_info()
        return a is not None and a.trade_mode == DEMO

    # ------------------------------------------------------------------ lecture
    def op_etat(self, **_):
        ok = self.connecter()
        t, a = self.mt5.terminal_info(), self.mt5.account_info()
        compte = None
        if a is not None:
            compte = {k: getattr(a, k, None) for k in ("login", "server", "trade_mode", "balance", "equity", "margin",
                                                       "margin_free", "leverage", "currency", "trade_allowed")}
            compte["demo"] = a.trade_mode == DEMO
        return {"connecte": ok, "erreur": self.derniere_erreur, "compte": compte,
                "terminal": None if t is None else {k: getattr(t, k, None) for k in
                                                    ("connected", "trade_allowed", "build", "name", "ping_last")}}

    def op_tick(self, symbole=None, **_):
        self.exiger()
        t = self.mt5.symbol_info_tick(symbole or self.symbole)
        if t is None:
            raise ErreurPont(f"aucun cours pour {symbole or self.symbole} : {self.mt5.last_error()}")
        return {k: getattr(t, k) for k in ("bid", "ask", "last", "time", "time_msc")}

    def op_specs(self, symbole=None, **_):
        self.exiger()
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        i = self.mt5.symbol_info(s)
        if i is None:
            proches = [x.name for x in (self.mt5.symbols_get() or ()) if "XAU" in x.name or "GOLD" in x.name.upper()]
            raise ErreurPont(f"symbole {s} introuvable sur ce serveur (proches : {', '.join(proches[:10]) or 'aucun'})")
        return {k: getattr(i, k, None) for k in ("name", "digits", "point", "volume_min", "volume_step", "volume_max",
                                                  "trade_contract_size", "filling_mode", "trade_stops_level",
                                                  "trade_mode", "currency_profit", "spread")}

    def op_bougies(self, tf="1h", n=300, symbole=None, **_):
        self.exiger()
        r = self.mt5.copy_rates_from_pos(symbole or self.symbole, getattr(self.mt5, TIMEFRAMES[tf]), 0, int(n))
        if r is None:
            raise ErreurPont(f"bougies indisponibles : {self.mt5.last_error()}")
        return [[int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
                 float(x["tick_volume"])] for x in r]

    def op_bougies_periode(self, tf="1d", debut=0, fin=0, symbole=None, **_):
        """Historique du courtier entre deux instants (secondes, heure du SERVEUR MT5). Liste vide si le serveur
        n'a rien pour cette période (début de l'historique atteint)."""
        self.exiger()
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        r = self.mt5.copy_rates_range(s, getattr(self.mt5, TIMEFRAMES[tf]), int(debut), int(fin))
        if r is None:
            journal("historique", tf, "indisponible :", self.mt5.last_error())
            return []
        return [[int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
                 float(x["tick_volume"])] for x in r]

    def op_marge(self, sens=1, volume=0.01, prix=None, symbole=None, **_):
        self.exiger()
        s = symbole or self.symbole
        if prix is None:
            t = self.mt5.symbol_info_tick(s)
            prix = t.ask if sens > 0 else t.bid
        m = self.mt5.order_calc_margin(self.mt5.ORDER_TYPE_BUY if sens > 0 else self.mt5.ORDER_TYPE_SELL, s,
                                       float(volume), float(prix))
        if m is None:
            raise ErreurPont(f"calcul de marge impossible : {self.mt5.last_error()}")
        return float(m)

    def _positions(self, **filtre):
        return [p for p in (self.mt5.positions_get(**filtre) or ()) if MAGIQUE_MIN <= p.magic <= MAGIQUE_MAX]

    def op_positions(self, **_):
        self.exiger()
        return [{k: getattr(p, k, None) for k in ("ticket", "type", "volume", "price_open", "price_current", "sl",
                                                   "tp", "profit", "swap", "magic", "comment", "time", "symbol")}
                for p in self._positions()]

    def op_historique(self, depuis=0, **_):
        self.exiger()
        debut = dt.datetime.fromtimestamp(max(0, float(depuis) - 2 * 86400))
        fin = dt.datetime.fromtimestamp(time.time() + 2 * 86400)
        deals = self.mt5.history_deals_get(debut, fin) or ()
        return [{k: getattr(x, k, 0) for k in ("ticket", "order", "position_id", "time", "type", "entry", "volume",
                                               "price", "profit", "commission", "swap", "fee", "magic", "comment")}
                for x in deals if MAGIQUE_MIN <= x.magic <= MAGIQUE_MAX]

    # ------------------------------------------------------------------ ordres (démo seulement)
    def _remplissages(self, info):
        modes = []
        if info.filling_mode & 1:
            modes.append(self.mt5.ORDER_FILLING_FOK)
        if info.filling_mode & 2:
            modes.append(self.mt5.ORDER_FILLING_IOC)
        modes.append(self.mt5.ORDER_FILLING_RETURN)
        return modes

    def _envoyer(self, demande, info):
        resultat = None
        for mode in self._remplissages(info):
            resultat = self.mt5.order_send({**demande, "type_filling": mode})
            if resultat is None:
                raise ErreurPont(f"ordre refusé par le terminal : {self.mt5.last_error()}")
            if resultat.retcode != RETCODE_REMPLISSAGE:
                break
        return {"retcode": resultat.retcode, "ok": resultat.retcode in RETCODE_OK, "commentaire": resultat.comment,
                "ordre": resultat.order, "deal": resultat.deal, "prix": resultat.price, "volume": resultat.volume}

    def op_ouvrir(self, sens, volume, sl=0.0, magic=MAGIQUE_MIN, commentaire="armee-or", symbole=None, **_):
        self.exiger()
        if not self.est_demo():
            raise ErreurPont("REFUS : ce compte n'est pas un compte démo. L'armée ne passe aucun ordre en réel.")
        if not MAGIQUE_MIN <= int(magic) <= MAGIQUE_MAX:
            raise ErreurPont("numéro magique hors de la plage de l'armée")
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        info, tick = self.mt5.symbol_info(s), self.mt5.symbol_info_tick(s)
        if info is None or tick is None:
            raise ErreurPont(f"symbole {s} indisponible")
        pas_vol = info.volume_step or 0.01
        volume = round(int(float(volume) / pas_vol + 1e-9) * pas_vol, 8)
        if volume < info.volume_min or volume > info.volume_max:
            raise ErreurPont(f"volume {volume} hors limites ({info.volume_min} – {info.volume_max})")
        prix = tick.ask if sens > 0 else tick.bid
        sl = round(float(sl or 0), info.digits)
        ecart_min = (info.trade_stops_level or 0) * info.point
        if sl and ((sens > 0 and sl > prix - ecart_min) or (sens < 0 and sl < prix + ecart_min)):
            raise ErreurPont(f"stop {sl} trop proche ou du mauvais côté du prix {prix}")
        demande = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": s, "volume": volume,
                   "type": self.mt5.ORDER_TYPE_BUY if sens > 0 else self.mt5.ORDER_TYPE_SELL, "price": prix,
                   "sl": sl, "tp": 0.0, "deviation": 50, "magic": int(magic), "comment": str(commentaire)[:25],
                   "type_time": self.mt5.ORDER_TIME_GTC}
        r = self._envoyer(demande, info)
        journal("ouverture", "ACHAT" if sens > 0 else "VENTE", volume, s, "->", r["retcode"], r["commentaire"])
        return r

    def op_fermer(self, ticket, commentaire="armee-or fin", **_):
        self.exiger()
        if not self.est_demo():
            raise ErreurPont("REFUS : ce compte n'est pas un compte démo.")
        pos = self._positions(ticket=int(ticket))
        if not pos:
            return {"ok": True, "retcode": 0, "commentaire": "déjà fermée", "prix": 0.0, "volume": 0.0}
        p = pos[0]
        info, tick = self.mt5.symbol_info(p.symbol), self.mt5.symbol_info_tick(p.symbol)
        achat = p.type == self.mt5.POSITION_TYPE_BUY
        demande = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume, "position": p.ticket,
                   "type": self.mt5.ORDER_TYPE_SELL if achat else self.mt5.ORDER_TYPE_BUY,
                   "price": tick.bid if achat else tick.ask, "deviation": 50, "magic": p.magic,
                   "comment": str(commentaire)[:25], "type_time": self.mt5.ORDER_TIME_GTC}
        r = self._envoyer(demande, info)
        journal("fermeture", p.ticket, "->", r["retcode"], r["commentaire"])
        return r

    # ------------------------------------------------------------------ service
    def traiter(self, demande):
        op = demande.pop("op", "")
        fonction = getattr(self, "op_" + op, None)
        if fonction is None:
            return {"ok": False, "erreur": f"opération inconnue : {op}"}
        try:
            with self.verrou:
                return {"ok": True, "r": fonction(**demande)}
        except ErreurPont as ex:
            return {"ok": False, "erreur": str(ex)}
        except Exception as ex:                                        # le pont ne tombe jamais pour une demande
            return {"ok": False, "erreur": f"{type(ex).__name__}: {ex}"}

    def serveur(self, port):
        pont = self

        class Gestion(socketserver.StreamRequestHandler):
            def handle(self):
                for ligne in self.rfile:
                    try:
                        demande = json.loads(ligne)
                    except ValueError:
                        reponse = {"ok": False, "erreur": "demande illisible"}
                    else:
                        reponse = pont.traiter(demande)
                    self.wfile.write((json.dumps(reponse, default=str) + "\n").encode())
                    self.wfile.flush()

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        socketserver.ThreadingTCPServer.daemon_threads = True
        return socketserver.ThreadingTCPServer(("127.0.0.1", int(port)), Gestion)

    def verifier_algo(self, pause=60):
        """Bouton « Algo Trading » du terminal éteint (état par défaut après installation) : on demande au lanceur
        (pont_mt5.sh, côté Linux) d'appuyer sur Ctrl+E, le raccourci officiel de ce bouton. Seulement quand il est
        éteint, et au plus une fois par minute : jamais d'aller-retour."""
        t = self.mt5.terminal_info()
        if t is None or not t.connected or t.trade_allowed or not self.dossier:
            return False
        if time.time() - self.derniere_demande_algo < pause:
            return False
        self.derniere_demande_algo = time.time()
        try:
            with open(os.path.join(self.dossier, "runtime", "activer_algo"), "w") as f:
                f.write(str(time.time()))
            journal("Algo Trading éteint dans le terminal : activation demandée (Ctrl+E)")
            return True
        except OSError as ex:
            journal("demande d'activation impossible :", ex)
            return False

    def surveiller(self, delai_max=600, periode=30):
        """Garde-fou : sans connexion au serveur MT5 pendant 10 min, le pont s'arrête et systemd relance TOUT
        (pont + terminal)."""
        while True:
            time.sleep(periode)
            with self.verrou:
                try:
                    if self.connecter():
                        self.verifier_algo()
                except Exception as ex:
                    journal("surveillance :", ex)
            if time.time() - self.derniere_connexion_ok > delai_max:
                journal("aucune connexion MT5 depuis", delai_max, "s : redémarrage complet")
                os._exit(3)


def fichier_demarrage(reglages):
    """Fichier de démarrage officiel MT5 : trading algorithmique autorisé et connexion directe au compte
    (sinon un premier lancement affiche « Select a company to open an account with » et attend un clic)."""
    lignes = ["[Common]"]
    if reglages.get("OR_MT5_LOGIN"):
        lignes += [f"Login={reglages['OR_MT5_LOGIN']}", f"Password={reglages.get('OR_MT5_MOT_DE_PASSE', '')}",
                   f"Server={reglages.get('OR_MT5_SERVEUR') or 'MetaQuotes-Demo'}"]
    lignes += ["NewsEnable=0", "[Experts]", "AllowLiveTrading=1", "AllowDllImport=0", "Enabled=1", "Account=0",
               "Profile=0"]
    return "\r\n".join(lignes) + "\r\n"


def chemin_demarrage(chemin):
    """À la racine du disque (C:\\) : aucun espace dans « /config:… », que MT5 lirait mal entre guillemets."""
    lecteur = ntpath.splitdrive(chemin or "")[0]
    return lecteur + "\\armee_or_demarrage.ini" if lecteur else os.path.join(os.path.dirname(chemin),
                                                                             "armee_or_demarrage.ini")


def lancer_terminal(chemin, reglages=None):
    """Démarre le terminal en mode portable avec le fichier de démarrage, effacé dès que le terminal l'a lu."""
    if not chemin or not os.path.exists(chemin):
        return None
    ini = chemin_demarrage(chemin)
    with open(ini, "w", encoding="utf-8") as f:
        f.write(fichier_demarrage(reglages or {}))
    journal("lancement du terminal", chemin)
    processus = subprocess.Popen([chemin, "/portable", "/config:" + ini])

    minuterie = threading.Timer(90, effacer_demarrage, args=(chemin,))
    minuterie.daemon = True
    minuterie.start()
    return processus


def effacer_demarrage(chemin):
    """Le mot de passe ne reste jamais sur le disque plus longtemps que le démarrage du terminal."""
    try:
        os.remove(chemin_demarrage(chemin))
    except (OSError, TypeError):
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reglages = lire_env(os.path.join(ici, ".env"))
    import MetaTrader5 as mt5
    pont = Pont(mt5, reglages, dossier=ici)
    if "--verifier" in argv:
        lancer_terminal(reglages.get("OR_MT5_TERMINAL"), reglages)
        limite = time.time() + 240                              # 4 min au plus : l'installateur coupe à 5
        while time.time() < limite and not pont.connecter():
            time.sleep(10)
        effacer_demarrage(reglages.get("OR_MT5_TERMINAL"))
        etat = pont.op_etat()
        print(json.dumps(etat, indent=1, default=str))
        if not etat["connecte"]:
            return 1
        print(json.dumps({"cours": pont.traiter({"op": "tick"}), "symbole": pont.traiter({"op": "specs"})},
                         indent=1, default=str))
        mt5.shutdown()
        sys.stdout.flush()                                      # os._exit ne vide pas les tampons : résultat d'abord
        sys.stderr.flush()
        os._exit(0)                                             # ne pas attendre le terminal lancé pour la vérification
    lancer_terminal(reglages.get("OR_MT5_TERMINAL"), reglages)
    time.sleep(15)
    pont.connecter()
    effacer_demarrage(reglages.get("OR_MT5_TERMINAL"))
    threading.Thread(target=pont.surveiller, daemon=True).start()
    port = int(reglages.get("OR_MT5_PORT") or 18777)
    journal("pont MT5 à l'écoute sur 127.0.0.1:%d" % port)
    pont.serveur(port).serve_forever()


if __name__ == "__main__":
    sys.exit(main())

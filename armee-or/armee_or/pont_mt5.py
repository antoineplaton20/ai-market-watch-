"""PONT METATRADER 5 — seul morceau de l'armée qui touche le compte MT5.

La bibliothèque officielle « MetaTrader5 » n'existe que pour Windows : ce fichier tourne donc sous Wine, avec un
Python Windows, à côté du terminal MT5 (service armee-or-mt5). Il ne dépend QUE de la bibliothèque standard et de
MetaTrader5, et des modules autonomes demo_pont/demo_regles/equipes_pont (bibliothèque standard).

Le reste de l'armée (Linux) lui parle par 127.0.0.1 uniquement : une ligne JSON par demande, une ligne par réponse.

Sécurités appliquées ICI, au plus près du compte :
- aucun ordre si le compte connecté n'est pas un compte DÉMO ;
- seules les positions portant un numéro magique de l'armée peuvent être fermées (tes ordres manuels : jamais) ;
- volume, stop et remplissage vérifiés contre les règles du symbole avant envoi.

Usage : python pont_mt5.py              (service)
        python pont_mt5.py --verifier   (connexion, compte, cours ; code 0 si tout va bien)
        python pont_mt5.py --instance video [--verifier]
                                        (2e compte démo de l'équipe vidéo : réglages OR_VIDEO_*, port 18778,
                                         son propre terminal ; les identifiants de l'armée ne lui sont jamais passés)
"""
import datetime as dt
import json
import ntpath
import math
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
OUVERTURES_VALIDEES = False  # R3 : protocole du prompt maître non validé ; aucun bouton ne contourne ce verrou.
RISQUE_ORDRE = 0.01
RISQUE_CUMULE = 0.02
RESERVE_COUTS = 1.25
AGE_COURS_MAX = 60
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


def reglages_instance(reglages, instance=""):
    """Réglages vus par une instance du pont. « video » : les clés OR_VIDEO_* deviennent les OR_MT5_* du pont, et
    les OR_MT5_* de l'armée (son login, son mot de passe) sont retirées : chaque instance ne voit que SON compte."""
    if not instance:
        return dict(reglages)
    prefixe = f"OR_{instance.upper()}_"
    vus = {k: v for k, v in reglages.items() if not k.startswith("OR_MT5_")}
    vus.update({"OR_MT5_" + k[len(prefixe):]: v for k, v in reglages.items() if k.startswith(prefixe)})
    vus.setdefault("OR_MT5_PORT", "18778")
    return vus


def suffixe(instance):
    return f"_{instance}" if instance else ""


def _d(x):
    return x._asdict() if hasattr(x, "_asdict") else x


class ErreurPont(Exception):
    pass


AUTRES_DEVISES = ("EUR", "GBP", "AUD", "CHF", "JPY", "CNH", "SGD", "CAD", "HKD", "TRY", "ZAR", "SILVER", "XAG")


def choisir_or(noms):
    """Symbole de l'or contre dollar parmi ceux du serveur : XAUUSD d'abord, puis ses variantes, puis GOLD."""
    def rang(nom):
        n = nom.upper()
        for i, prefixe in enumerate(("XAUUSD", "GOLD")):
            if n.startswith(prefixe) and not any(d in n[len(prefixe):] for d in AUTRES_DEVISES):
                return (i, n != prefixe, len(n), n)
        return None
    candidats = sorted((r, nom) for nom in noms if (r := rang(nom)) is not None)
    return candidats[0][1] if candidats else None


try:
    from .demo_pont import DemoMixin
    from .equipes_pont import EquipesMixin
except ImportError:
    from demo_pont import DemoMixin
    from equipes_pont import EquipesMixin

# Le 2e compte (équipe vidéo) n'a droit qu'à la lecture, aux fermetures de l'armée et à son propre chemin d'ordres.
RESERVEES_ARMEE = ("ouvrir", "dimensionner", "demo_etat", "demo_mode", "demo_cycle", "marches_ouvrir")


class Pont(EquipesMixin, DemoMixin):
    def __init__(self, mt5, reglages, dossier=None, instance=""):
        self.mt5 = mt5
        self.r = reglages
        self.dossier = dossier                     # dossier de l'armée : runtime/activer_algo pour le lanceur
        self.instance = instance                   # "" : compte de l'armée ; "video" : 2e compte démo
        self.derniere_demande_algo = 0.0
        self.verrou = threading.RLock()
        self.symbole = reglages.get("OR_MT5_SYMBOLE") or "XAUUSD"
        self.derniere_connexion_ok = time.time()
        self.derniere_erreur = ""
        self.symbole_verifie = False

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
            if not self.symbole_verifie:
                self.choisir_symbole()
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
                                        f"« or {'video' if self.instance else 'mt5'} compte », puis le mot de passe "
                                        "PRINCIPAL actuel")
            journal(self.derniere_erreur)
            return False
        self.choisir_symbole()
        if self.connecte():
            self.derniere_connexion_ok = time.time()
            self.derniere_erreur = ""
            journal("connecté au compte", self.login(), "serveur", options["server"])
            return True
        self.derniere_erreur = "terminal lancé mais pas encore connecté au serveur"
        return False

    def choisir_symbole(self):
        """Chaque courtier nomme l'or à sa façon (XAUUSD, XAUUSD.a, GOLD, GOLDmicro…) : si le symbole réglé
        n'existe pas sur ce serveur, prend l'or contre dollar proposé au compte."""
        m = self.mt5
        if m.symbol_info(self.symbole) is not None:
            m.symbol_select(self.symbole, True)
            self.symbole_verifie = True
            return self.symbole
        noms = [x.name for x in (m.symbols_get() or ())]
        self.symbole_verifie = bool(noms)                      # liste vide : serveur pas encore prêt, on réessaiera
        trouve = choisir_or(noms)
        if trouve and m.symbol_select(trouve, True):
            journal(f"symbole {self.symbole} absent chez ce courtier : l'or s'appelle ici {trouve}")
            self.symbole = trouve
        return self.symbole

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
                                                       "margin_free", "leverage", "currency", "trade_allowed", "margin_mode")}
            compte["demo"] = a.trade_mode == DEMO
        return {"connecte": ok, "erreur": self.derniere_erreur, "compte": compte, "symbole": self.symbole,
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
                                                  "trade_mode", "currency_profit", "spread", "swap_mode", "swap_long",
                                                  "swap_short", "currency_base", "path", "description")}

    def op_symboles(self, **_):
        """Tous les instruments du serveur (forex, métaux, énergie, indices, actions, crypto…), en bref."""
        self.exiger()
        return [{k: getattr(x, k, None) for k in ("name", "path", "description", "trade_mode", "currency_profit")}
                for x in (self.mt5.symbols_get() or ())]

    def op_valeur_lot(self, symbole=None, **_):
        """Valeur d'UN lot dans la devise du compte (conversions de devises faites par le terminal)."""
        self.exiger()
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        t = self.mt5.symbol_info_tick(s)
        if t is None or not t.ask:
            raise ErreurPont(f"aucun cours pour {s}")
        gain = self.mt5.order_calc_profit(self.mt5.ORDER_TYPE_BUY, s, 1.0, float(t.ask), float(t.ask) * 1.01)
        if gain is None:
            raise ErreurPont(f"valeur du lot de {s} incalculable : {self.mt5.last_error()}")
        return float(gain) * 100

    def op_bougies(self, tf="1h", n=300, symbole=None, **_):
        self.exiger()
        r = self.mt5.copy_rates_from_pos(symbole or self.symbole, getattr(self.mt5, TIMEFRAMES[tf]), 0, int(n))
        if r is None:
            raise ErreurPont(f"bougies indisponibles : {self.mt5.last_error()}")
        return [[int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
                 float(x["tick_volume"])] for x in r]

    def op_bougies_periode(self, tf="1d", debut=0, fin=0, symbole=None, **_):
        """Historique du courtier entre deux instants (secondes, UTC). Liste vide si le serveur
        n'a rien pour cette période (début de l'historique atteint)."""
        self.exiger()
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        r = self.mt5.copy_rates_range(s, getattr(self.mt5, TIMEFRAMES[tf]), int(debut), int(fin))
        if r is None:
            raise ErreurPont("historique des bougies indisponible")
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
        positions = self.mt5.positions_get(**filtre)
        if positions is None:
            raise ErreurPont(f"positions indisponibles : {self.mt5.last_error()}")
        return [p for p in positions if MAGIQUE_MIN <= p.magic <= MAGIQUE_MAX]


    def op_positions(self, **_):
        self.exiger()
        return [{k: getattr(p, k, None) for k in ("ticket", "type", "volume", "price_open", "price_current", "sl",
                                                   "tp", "profit", "swap", "magic", "comment", "time", "symbol")}
                for p in self._positions()]

    def op_historique(self, depuis=0, **_):
        self.exiger()
        debut = dt.datetime.fromtimestamp(max(0, float(depuis) - 2 * 86400), dt.timezone.utc)
        fin = dt.datetime.fromtimestamp(time.time() + 2 * 86400, dt.timezone.utc)
        deals = self.mt5.history_deals_get(debut, fin)
        if deals is None:
            raise ErreurPont("historique indisponible")
        # positions de l'armée : celles qu'elle a ouvertes ; leur sortie compte même si elle porte un autre numéro
        # magique (fermeture à la main dans l'app, stop, coupure du courtier)
        armee = {x.position_id for x in deals if MAGIQUE_MIN <= x.magic <= MAGIQUE_MAX}
        return [{k: getattr(x, k, 0) for k in ("ticket", "order", "position_id", "time", "type", "entry", "volume",
                                               "price", "profit", "commission", "swap", "fee", "magic", "comment")}
                for x in deals if x.position_id in armee]

    # ------------------------------------------------------------------ ordres (démo seulement)
    def _cours_valide(self, symbole, age_max=AGE_COURS_MAX):
        tick = self.mt5.symbol_info_tick(symbole)
        if tick is None or not all(math.isfinite(x) and x > 0 for x in (tick.bid, tick.ask)) or tick.ask < tick.bid:
            raise ErreurPont("cours invalide")
        age = time.time() - tick.time
        if not -5 <= age <= age_max:
            raise ErreurPont("cours périmé ou horloge incohérente")
        return tick


    def _perte(self, sens, symbole, volume, entree, sortie):
        resultat = self.mt5.order_calc_profit(
            self.mt5.ORDER_TYPE_BUY if sens > 0 else self.mt5.ORDER_TYPE_SELL,
            symbole, volume, entree, sortie)
        if resultat is None or not math.isfinite(resultat):
            raise ErreurPont("calcul du risque indisponible")
        return max(0.0, -resultat) * RESERVE_COUTS


    def op_dimensionner(self, sens, sl, volume, symbole=None, **_):
        """Plafonne tout profil, entraînement compris, en devise du compte.

        Le plafond cumulé porte sur les pertes SUPPLÉMENTAIRES jusqu'aux stops
        depuis les cours actuels, toutes positions du compte comprises.
        """
        return self._dimensionner(sens, sl, volume, symbole or self.symbole)

    def _dimensionner(self, sens, sl, volume, s, risque_ordre=RISQUE_ORDRE, or_seul=True, age_positions=AGE_COURS_MAX):
        """Contrôle commun. Équipe multi-marchés : tout symbole, budget par ordre plus petit ; le plafond CUMULÉ
        (RISQUE_CUMULE, toutes positions du compte) reste celui de R3. age_positions : un marché déjà tenu mais
        fermé (dernier cours ancien) compte quand même dans ce plafond, depuis son dernier cours."""
        self.exiger()
        compte = self.mt5.account_info()
        if compte is None or compte.trade_mode != DEMO:
            raise ErreurPont("compte démo obligatoire")
        if getattr(compte, "margin_mode", None) != 2:
            raise ErreurPont("compte démo hedging requis pour séparer les équipes")
        if sens not in (-1, 1) or not all(math.isfinite(float(x)) and float(x) > 0 for x in (sl, volume)):
            raise ErreurPont("sens, volume ou stop invalide")
        if not all(math.isfinite(x) and x > 0 for x in (compte.equity, compte.margin_free)):
            raise ErreurPont("fonds ou marge indisponibles")
        if or_seul and s != self.symbole:
            raise ErreurPont("symbole non autorisé")
        info = self.mt5.symbol_info(s)
        if info is None or not all(math.isfinite(x) and x > 0 for x in (info.volume_min, info.volume_step, info.volume_max)):
            raise ErreurPont("spécifications de volume invalides")
        tick = self._cours_valide(s)
        prix = tick.ask if sens > 0 else tick.bid
        sl = round(float(sl), info.digits)
        ecart = max(0, info.trade_stops_level) * info.point
        if sl <= 0 or (sens > 0 and sl >= tick.bid - ecart) or (sens < 0 and sl <= tick.ask + ecart):
            raise ErreurPont("stop absent, trop proche ou du mauvais côté")
        positions = self.mt5.positions_get()
        ordres = self.mt5.orders_get()
        if positions is None or ordres is None:
            raise ErreurPont("positions ou ordres indisponibles : aucune ouverture")
        if ordres:
            raise ErreurPont("ordres en attente sur le compte : exposition non prise en charge")
        utilise = 0.0
        for p in positions:
            if not math.isfinite(p.sl) or p.sl <= 0:
                raise ErreurPont("position existante sans stop : aucune nouvelle ouverture")
            t = self._cours_valide(p.symbol, age_positions)
            sens_p = 1 if p.type == self.mt5.POSITION_TYPE_BUY else -1
            courant = t.bid if sens_p > 0 else t.ask
            if (sens_p > 0 and p.sl >= courant) or (sens_p < 0 and p.sl <= courant):
                raise ErreurPont("stop existant atteint ou incohérent : attendre la réconciliation")
            utilise += self._perte(sens_p, p.symbol, p.volume, courant, p.sl)
        budget = min(compte.equity * risque_ordre, compte.equity * RISQUE_CUMULE - utilise)
        minimum = info.volume_min
        perte_min = self._perte(sens, s, minimum, prix, sl)
        marge_min = self.mt5.order_calc_margin(self.mt5.ORDER_TYPE_BUY if sens > 0 else self.mt5.ORDER_TYPE_SELL,
                                             s, minimum, prix)
        if perte_min <= 0 or marge_min is None or not math.isfinite(marge_min) or marge_min <= 0:
            raise ErreurPont("calcul du risque ou de marge invalide")
        limite = min(float(volume), info.volume_max, max(0, budget) / perte_min * minimum,
                     0.9 * compte.margin_free / marge_min * minimum)
        lots = round(math.floor(limite / info.volume_step + 1e-9) * info.volume_step, 8)
        if lots < minimum:
            return {"volume": 0.0, "motif": "lot minimum supérieur au budget de risque ou de marge"}
        perte = self._perte(sens, s, lots, prix, sl)
        if perte > budget + 1e-8:
            return {"volume": 0.0, "motif": "risque après arrondi supérieur au budget"}
        return {"volume": lots, "risque": perte, "budget": budget, "devise": compte.currency, "prix": prix,
                "motif": f"risque estimé avec réserve {perte:.2f} {compte.currency}"}


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
        if not OUVERTURES_VALIDEES:
            raise ErreurPont("R3 observation : aucune stratégie qualifiée, nouvelles ouvertures bloquées")
        self.exiger()
        if not self.est_demo():
            raise ErreurPont("REFUS : ce compte n'est pas un compte démo. L'armée ne passe aucun ordre en réel.")
        if not MAGIQUE_MIN <= int(magic) <= MAGIQUE_MAX:
            raise ErreurPont("numéro magique hors de la plage de l'armée")
        if sens not in (-1, 1) or not math.isfinite(float(volume)) or float(volume) <= 0:
            raise ErreurPont("sens ou volume invalide")
        if any(p.magic == int(magic) for p in self._positions()):
            raise ErreurPont("une position de cette équipe existe déjà")
        s = symbole or self.symbole
        self.mt5.symbol_select(s, True)
        info, tick = self.mt5.symbol_info(s), self.mt5.symbol_info_tick(s)
        if info is None or tick is None:
            raise ErreurPont(f"symbole {s} indisponible")
        pas_vol = info.volume_step or 0.01
        volume = round(int(float(volume) / pas_vol + 1e-9) * pas_vol, 8)
        if volume < info.volume_min or volume > info.volume_max:
            raise ErreurPont(f"volume {volume} hors limites ({info.volume_min} – {info.volume_max})")
        controle = self.op_dimensionner(sens=sens, sl=sl, volume=volume, symbole=s)
        if controle["volume"] < volume:
            raise ErreurPont("ordre refusé : plafond de risque dépassé")
        prix = controle["prix"]
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
        if r["ok"] and self._positions(ticket=int(ticket)):
            r["ok"] = False
            r["commentaire"] = "fermeture partielle ou non confirmée : position toujours suivie"
        return r


    # ------------------------------------------------------------------ service
    def traiter(self, demande):
        op = demande.pop("op", "")
        if self.instance and op in RESERVEES_ARMEE:
            return {"ok": False, "erreur": f"opération {op} réservée au compte de l'armée (instance {self.instance})"}
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
            with open(os.path.join(self.dossier, "runtime", "activer_algo" + suffixe(self.instance)), "w") as f:
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


def chemin_demarrage(chemin, instance=""):
    """À la racine du disque (C:\\) : aucun espace dans « /config:… », que MT5 lirait mal entre guillemets."""
    nom = f"armee_or_demarrage{suffixe(instance)}.ini"
    lecteur = ntpath.splitdrive(chemin or "")[0]
    return lecteur + "\\" + nom if lecteur else os.path.join(os.path.dirname(chemin), nom)


def lancer_terminal(chemin, reglages=None, instance=""):
    """Démarre le terminal en mode portable avec le fichier de démarrage, effacé dès que le terminal l'a lu."""
    if not chemin or not os.path.exists(chemin):
        return None
    ini = chemin_demarrage(chemin, instance)
    with open(ini, "w", encoding="utf-8") as f:
        f.write(fichier_demarrage(reglages or {}))
    journal("lancement du terminal", chemin)
    processus = subprocess.Popen([chemin, "/portable", "/config:" + ini])

    minuterie = threading.Timer(90, effacer_demarrage, args=(chemin, instance))
    minuterie.daemon = True
    minuterie.start()
    return processus


def effacer_demarrage(chemin, instance=""):
    """Le mot de passe ne reste jamais sur le disque plus longtemps que le démarrage du terminal."""
    try:
        os.remove(chemin_demarrage(chemin, instance))
    except (OSError, TypeError):
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance = argv[argv.index("--instance") + 1] if "--instance" in argv[:-1] else ""
    if instance not in ("", "video"):
        print("instance inconnue :", instance)
        return 2
    reglages = reglages_instance(lire_env(os.path.join(ici, ".env")), instance)
    terminal = reglages.get("OR_MT5_TERMINAL")
    import MetaTrader5 as mt5
    pont = Pont(mt5, reglages, dossier=ici, instance=instance)
    if "--verifier" in argv:
        lancer_terminal(terminal, reglages, instance)
        limite = time.time() + 240                              # 4 min au plus : l'installateur coupe à 5
        while time.time() < limite and not pont.connecter():
            time.sleep(10)
        effacer_demarrage(terminal, instance)
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
    lancer_terminal(terminal, reglages, instance)
    time.sleep(15)
    pont.connecter()
    effacer_demarrage(terminal, instance)
    threading.Thread(target=pont.surveiller, daemon=True).start()
    port = int(reglages.get("OR_MT5_PORT") or 18777)
    journal("pont MT5%s à l'écoute sur 127.0.0.1:%d" % (" (" + instance + ")" if instance else "", port))
    pont.serveur(port).serve_forever()


if __name__ == "__main__":
    sys.exit(main())

"""Chemins d'ordres des deux équipes ajoutées en R5, côté pont (bibliothèque standard seulement).

- multi-marchés (770050) : compte de l'armée seulement, achat seulement, stop obligatoire chez le courtier, une position
  par symbole, 0,5 % du compte risqué au plus par ordre, et le plafond cumulé R3 (2 % de pertes jusqu'aux stops,
  toutes positions du compte comprises) inchangé ;
- vidéo (770077) : 2e compte démo seulement (instance « video »), sans stop comme dans les vidéos, 10 positions et
  95 % de la marge au plus ;
- verrou de gain multi-marchés (R6.2) : un stop 770050 ne peut que MONTER (le risque ne fait que baisser), jamais au
  contact du cours ;
- mode « capital 1 000 » (R8.1, décision du propriétaire du 26/10/2026 : la démo imite son compte de 1 000 €) : les
  plafonds se calculent sur min(1 000, équité) dans la devise du compte : 3 % par ordre, 30 % au total jusqu'aux stops
  (toutes positions du compte comprises), 10 positions multi-marchés au plus (R8.3), et chaque ordre fait EXACTEMENT
  0,01 lot (R8.2) : s'il risquerait plus, il n'est pas passé. Ces nombres sont fixés ICI : l'appelant ne peut que demander le
  mode, jamais un risque ou un volume plus grand.
Les deux refusent tout compte réel. Un refus AVANT l'envoi revient en réponse (ok False, avant_envoi True) : côté
Linux, seule une réponse perdue reste un ordre incertain.
"""
import math

MAGIQUE_MARCHES = 770050
MAGIQUE_VIDEO = 770077
RISQUE_MARCHE = 0.005               # perte jusqu'au stop, réserve de coûts comprise, par ordre multi-marchés
MAX_MARCHES = 20
VIDEO_MAX_POSITIONS = 10
VIDEO_MARGE_MAX = 0.95
AGE_POSITIONS = 7 * 86400           # marché tenu mais fermé : son dernier cours compte dans le plafond cumulé
CAPITAL_REFERENCE = 1000.0          # R8.1 : capital imité (devise du compte), plafonné par l'équité
CAPITAL_RISQUE_ORDRE = 0.03         # perte jusqu'au stop par ordre, en part de ce capital
CAPITAL_RISQUE_TOTAL = 0.30         # pertes cumulées jusqu'aux stops, toutes positions du compte (R8.3)
CAPITAL_MAX_MARCHES = 10            # R8.3 : 10 positions au plus (décision du propriétaire)
CAPITAL_LOT = 0.01                  # R8.2 : chaque trade du mode fait exactement 0,01 lot (décision du propriétaire)
NEGOCIABLE = (4,)                   # SYMBOL_TRADE_MODE_FULL
ACHAT_PERMIS = (1, 4)               # LONGONLY, FULL


def refus(motif):
    return {"ok": False, "retcode": 0, "commentaire": str(motif)[:200], "avant_envoi": True}


class EquipesMixin:
    def _demo_exige(self):
        self.exiger()
        a = self.mt5.account_info()
        if a is None or a.trade_mode != 0:
            raise RuntimeError("REFUS : ce compte n'est pas un compte démo. Aucun ordre en réel.")
        return a

    def _volume(self, info, volume):
        if not math.isfinite(float(volume)) or float(volume) <= 0:
            raise RuntimeError("volume invalide")
        pas = info.volume_step or 0.01
        v = round(int(float(volume) / pas + 1e-9) * pas, 8)
        if v < info.volume_min or v > info.volume_max:
            raise RuntimeError(f"volume {v} hors limites ({info.volume_min} – {info.volume_max})")
        return v

    def op_marches_ouvrir(self, symbole, volume, sl, sens=1, capital=False, **_):
        if self.instance:
            raise RuntimeError("multi-marchés : compte de l'armée seulement")
        try:
            a = self._demo_exige()
            mode_capital = capital is True                      # seulement le vrai booléen : rien d'autre n'élargit
            if mode_capital and not (math.isfinite(a.equity) and a.equity > 0):
                raise RuntimeError("équité indisponible")
            if sens != 1:
                raise RuntimeError("multi-marchés : achat seulement")
            if not isinstance(symbole, str) or not symbole or len(symbole) > 32:
                raise RuntimeError("symbole invalide")
            self.mt5.symbol_select(symbole, True)
            info = self.mt5.symbol_info(symbole)
            if info is None or info.trade_mode not in ACHAT_PERMIS:
                raise RuntimeError(f"{symbole} : achat non permis chez ce courtier")
            propres = [p for p in self._positions() if p.magic == MAGIQUE_MARCHES]
            if any(p.symbol == symbole for p in propres):
                raise RuntimeError(f"{symbole} : position multi-marchés déjà ouverte")
            plafond = CAPITAL_MAX_MARCHES if mode_capital else MAX_MARCHES
            if len(propres) >= plafond:
                raise RuntimeError(f"{plafond} marchés tenus au plus")
            volume = self._volume(info, CAPITAL_LOT if mode_capital else volume)   # mode : toujours 0,01 lot
            if mode_capital:                                    # plafonds en part de l'équité, pour _dimensionner
                cap = min(CAPITAL_REFERENCE, a.equity)
                controle = self._dimensionner(1, sl, volume, symbole, CAPITAL_RISQUE_ORDRE * cap / a.equity,
                                              or_seul=False, age_positions=AGE_POSITIONS,
                                              risque_cumule=CAPITAL_RISQUE_TOTAL * cap / a.equity)
            else:
                controle = self._dimensionner(1, sl, volume, symbole, RISQUE_MARCHE, or_seul=False,
                                              age_positions=AGE_POSITIONS)
            if controle["volume"] <= 0:
                return refus(controle["motif"])
            if mode_capital and abs(controle["volume"] - CAPITAL_LOT) > 1e-9:
                return refus("0,01 lot risquerait plus que le plafond du mode 1 000")
            volume = min(volume, controle["volume"])
        except Exception as ex:                                 # rien n'est parti chez le courtier
            return refus(ex)
        demande = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": symbole, "volume": volume,
                   "type": self.mt5.ORDER_TYPE_BUY, "price": controle["prix"], "sl": round(float(sl), info.digits),
                   "tp": 0.0, "deviation": 50, "magic": MAGIQUE_MARCHES, "comment": "armee-or marches",
                   "type_time": self.mt5.ORDER_TIME_GTC}
        r = self._envoyer(demande, info)
        r.update(volume_demande=volume, risque=controle["risque"], devise=a.currency)
        return r

    def op_marches_stop(self, ticket, sl, **_):
        """Remonte le stop d'une position multi-marchés (verrou de gain). Jamais vers le bas, jamais au contact."""
        if self.instance:
            raise RuntimeError("multi-marchés : compte de l'armée seulement")
        try:
            self._demo_exige()
            pos = [p for p in self._positions(ticket=int(ticket)) if p.magic == MAGIQUE_MARCHES]
            if not pos:
                raise RuntimeError("position multi-marchés introuvable")
            p = pos[0]
            info = self.mt5.symbol_info(p.symbol)
            if info is None:
                raise RuntimeError(f"{p.symbol} indisponible")
            sl = round(float(sl), info.digits)
            if not math.isfinite(sl) or sl <= 0 or sl <= p.sl:
                raise RuntimeError("le stop ne peut que monter")
            tick = self._cours_valide(p.symbol)
            if sl >= tick.bid - max(0, info.trade_stops_level) * info.point:
                raise RuntimeError("stop trop proche du cours")
        except Exception as ex:
            return refus(ex)
        r = self.mt5.order_send({"action": self.mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": p.symbol,
                                 "sl": sl, "tp": p.tp, "magic": MAGIQUE_MARCHES})
        if r is None:
            raise RuntimeError(f"modification refusée par le terminal : {self.mt5.last_error()}")
        return {"ok": r.retcode in (10008, 10009, 10010), "retcode": r.retcode, "commentaire": r.comment, "sl": sl}

    def op_video_ouvrir(self, sens, volume, symbole=None, **_):
        if self.instance != "video":
            raise RuntimeError("équipe vidéo : 2e compte démo (instance video) seulement")
        try:
            a = self._demo_exige()
            if sens not in (-1, 1):
                raise RuntimeError("sens invalide")
            s = symbole or self.symbole
            self.mt5.symbol_select(s, True)
            info, tick = self.mt5.symbol_info(s), self.mt5.symbol_info_tick(s)
            if info is None or tick is None or not tick.ask or not tick.bid:
                raise RuntimeError(f"symbole {s} indisponible")
            if info.trade_mode not in NEGOCIABLE:
                raise RuntimeError(f"{s} : ouverture non permise chez ce courtier")
            volume = self._volume(info, volume)
            if len([p for p in self._positions() if p.magic == MAGIQUE_VIDEO]) >= VIDEO_MAX_POSITIONS:
                raise RuntimeError(f"{VIDEO_MAX_POSITIONS} positions au plus par panier")
            prix = tick.ask if sens > 0 else tick.bid
            type_ordre = self.mt5.ORDER_TYPE_BUY if sens > 0 else self.mt5.ORDER_TYPE_SELL
            marge = self.mt5.order_calc_margin(type_ordre, s, volume, prix)
            if marge is None or not math.isfinite(marge) or marge > a.margin_free - (1 - VIDEO_MARGE_MAX) * a.equity:
                raise RuntimeError("marge : 95 % du compte au plus")
        except Exception as ex:
            return refus(ex)
        demande = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": s, "volume": volume, "type": type_ordre,
                   "price": prix, "sl": 0.0, "tp": 0.0, "deviation": 50, "magic": MAGIQUE_VIDEO,
                   "comment": "armee-or video", "type_time": self.mt5.ORDER_TIME_GTC}
        return self._envoyer(demande, info)

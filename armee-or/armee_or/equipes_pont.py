"""Chemins d'ordres des deux équipes ajoutées en R5, côté pont (bibliothèque standard seulement).

- multi-marchés (770050) : compte de l'armée seulement, achat seulement, stop obligatoire chez le courtier, une position
  par symbole, 0,5 % du compte risqué au plus par ordre, et le plafond cumulé R3 (2 % de pertes jusqu'aux stops,
  toutes positions du compte comprises) inchangé ;
- vidéo (770077) : 2e compte démo seulement (instance « video »), sans stop comme dans les vidéos, 10 positions et
  95 % de la marge au plus.
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

    def op_marches_ouvrir(self, symbole, volume, sl, sens=1, **_):
        if self.instance:
            raise RuntimeError("multi-marchés : compte de l'armée seulement")
        try:
            a = self._demo_exige()
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
            if len(propres) >= MAX_MARCHES:
                raise RuntimeError(f"{MAX_MARCHES} marchés tenus au plus")
            volume = self._volume(info, volume)
            controle = self._dimensionner(1, sl, volume, symbole, RISQUE_MARCHE, or_seul=False,
                                          age_positions=AGE_POSITIONS)
            if controle["volume"] <= 0:
                return refus(controle["motif"])
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

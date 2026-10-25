"""Équipe vidéo : 2e compte démo séparé, méthode des vidéos (panier sans stop, gain pris, mise relancée), loteries,
rejeu historique. Faux courtier en mémoire ; le pont de l'armée est rendu injoignable pour prouver qu'il n'est jamais
utilisé. Aucun réseau."""
import threading
from types import SimpleNamespace as NS

import numpy as np
import pytest

from armee_or import base, chef, config, pont_mt5, telegram, video

LOGIN_VIDEO = 7770001


class FauxCourtier:
    """Courtier offshore de démo : levier « illimité », compte en dollars, XAUUSDm, bougies 1 min en hausse."""
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, POSITION_TYPE_BUY = 0, 1, 0
    TRADE_ACTION_DEAL, ORDER_TIME_GTC = 1, 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TIMEFRAME_M1, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 1, 15, 16385, 16388, 16408

    def __init__(self):
        self.trade_mode, self.prix, self.solde, self.ferme = 0, 4500.0, 9.88, False
        self.positions, self.envois, self.suivant = [], [], 100

    def initialize(self, **kw):
        return True

    def shutdown(self):
        pass

    def last_error(self):
        return (1, "Success")

    def terminal_info(self):
        return NS(connected=True, trade_allowed=True, build=5000, name="MetaTrader 5", ping_last=20000)

    def _flottant(self, p):
        sens = 1 if p.type == 0 else -1
        sortie = self.prix - 0.1 if sens > 0 else self.prix + 0.1
        return (sortie - p.price_open) * p.volume * 100 * sens

    def account_info(self):
        equite = self.solde + sum(self._flottant(p) for p in self.positions)
        return NS(login=LOGIN_VIDEO, server="Courtier-MT5Trial", trade_mode=self.trade_mode, balance=self.solde,
                  equity=equite, margin=0.0, margin_free=equite, leverage=0, currency="USD", trade_allowed=True)

    def symbol_select(self, s, v):
        return s == "XAUUSDm"

    def symbol_info(self, s):
        if s != "XAUUSDm":
            return None
        return NS(name=s, digits=3, point=0.001, volume_min=0.01, volume_step=0.01, volume_max=200.0,
                  trade_contract_size=100.0, filling_mode=2, trade_stops_level=0, trade_mode=4, currency_profit="USD",
                  spread=200)

    def symbols_get(self):
        return (NS(name="XAUUSDm"), NS(name="XAUEURm"), NS(name="EURUSDm"))

    def symbol_info_tick(self, s):
        return NS(bid=self.prix - 0.1, ask=self.prix + 0.1, last=0.0, time=0, time_msc=0)

    def copy_rates_from_pos(self, s, tf, debut, n):
        r = np.zeros(n, dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                               ("tick_volume", "i8")])
        r["time"] = np.arange(n) * 60
        r["open"], r["close"] = self.prix - 1, self.prix                       # bougies vertes : panier à l'ACHAT
        r["high"], r["low"] = self.prix + 0.5, self.prix - 1.5
        return r

    def order_calc_margin(self, t, s, volume, prix):
        return 0.001 * volume                                                   # levier « illimité »

    def positions_get(self, ticket=None, symbol=None):
        for p in self.positions:
            p.profit = self._flottant(p)
        return tuple(p for p in self.positions if ticket is None or p.ticket == ticket)

    def order_send(self, d):
        self.envois.append(d)
        if d["type_filling"] != self.ORDER_FILLING_IOC:
            return NS(retcode=10030, comment="Unsupported filling mode", order=0, deal=0, price=0.0, volume=0.0)
        if self.ferme:
            return NS(retcode=10018, comment="Market closed", order=0, deal=0, price=0.0, volume=0.0)
        self.suivant += 1
        if "position" in d:
            p = next(x for x in self.positions if x.ticket == d["position"])
            self.solde += self._flottant(p)
            self.positions.remove(p)
        else:
            self.positions.append(NS(ticket=self.suivant, type=d["type"], volume=d["volume"], price_open=d["price"],
                                     price_current=d["price"], sl=d["sl"], tp=0.0, profit=0.0, swap=0.0,
                                     magic=d["magic"], comment=d["comment"], time=0, symbol=d["symbol"]))
        return NS(retcode=10009, comment="Request executed", order=self.suivant, deal=self.suivant, price=d["price"],
                  volume=d["volume"])

    def history_deals_get(self, debut, fin):
        return ()

    def stop_out(self):
        """Le courtier coupe le compte : positions fermées à la perte, presque plus rien sur le compte."""
        self.positions, self.solde = [], 0.21


@pytest.fixture
def courtier(monkeypatch):
    f = FauxCourtier()
    reglages = pont_mt5.reglages_instance({"OR_MT5_LOGIN": "5550001", "OR_MT5_MOT_DE_PASSE": "armee",
                                           "OR_VIDEO_LOGIN": str(LOGIN_VIDEO), "OR_VIDEO_MOT_DE_PASSE": "video",
                                           "OR_VIDEO_SYMBOLE": "XAUUSD"}, "video")
    pont = pont_mt5.Pont(f, reglages, instance="video")
    serveur = pont.serveur(0)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "VIDEO_PORT", serveur.server_address[1])
    monkeypatch.setattr(config, "VIDEO_ACTIF", True)
    monkeypatch.setattr(config, "MT5_PORT", 1)                 # pont de l'armée injoignable : jamais utilisé ici
    messages = []
    monkeypatch.setattr(telegram, "envoyer", lambda t, important=False, **k: messages.append(t) or True)
    f.messages = messages
    base.ecrire("video:actif", True)                           # comme après /or_video_on (R5 : éteinte par défaut)
    yield f
    serveur.shutdown()
    serveur.server_close()


def test_chaque_instance_ne_voit_que_son_compte():
    r = {"OR_MT5_LOGIN": "1", "OR_MT5_MOT_DE_PASSE": "armee", "OR_MT5_PORT": "18777", "OR_TELEGRAM_CHAT_ID": "9",
         "OR_VIDEO_LOGIN": "2", "OR_VIDEO_MOT_DE_PASSE": "video", "OR_VIDEO_SERVEUR": "Courtier-MT5Trial7"}
    v = pont_mt5.reglages_instance(r, "video")
    assert v["OR_MT5_LOGIN"] == "2" and v["OR_MT5_MOT_DE_PASSE"] == "video" and v["OR_MT5_PORT"] == "18778"
    assert "armee" not in v.values() and "1" not in v.values()                 # rien du compte de l'armée
    assert pont_mt5.reglages_instance(r) == r                                   # l'armée : inchangée
    ini = pont_mt5.fichier_demarrage(v)
    assert "Login=2" in ini and "Server=Courtier-MT5Trial7" in ini and "Login=1" not in ini
    assert pont_mt5.chemin_demarrage(r"C:\Program Files\MetaTrader 5\terminal64.exe", "video") \
        == r"C:\armee_or_demarrage_video.ini"


def test_algo_trading_demande_au_lanceur_de_l_equipe_video(tmp_path):
    (tmp_path / "runtime").mkdir(exist_ok=True)
    f = FauxCourtier()
    f.terminal_info = lambda: NS(connected=True, trade_allowed=False)
    pont = pont_mt5.Pont(f, {"OR_MT5_LOGIN": str(LOGIN_VIDEO)}, dossier=str(tmp_path), instance="video")
    assert pont.verifier_algo() is True
    assert (tmp_path / "runtime" / "activer_algo_video").exists() and not (tmp_path / "runtime" / "activer_algo").exists()


def test_taille_du_panier_comme_dans_les_videos():
    specs = {"volume_min": 0.01, "volume_step": 0.01, "volume_max": 200.0, "trade_contract_size": 100.0}
    assert video.taille_panier(2.02, 2.02, 0.001, specs) == (1, 0.01)            # lot minimum même à 2 $
    assert video.taille_panier(9.88, 9.88, 0.001, specs) == (2, 0.01)
    assert video.taille_panier(1000, 1000, 2.0, specs) == (8, 0.31)              # 0,25 $ par $ de mouvement / équité
    assert video.taille_panier(1000, 1000, 40.0, specs) == (8, 0.02)             # plafonné par la marge (levier 1:100)
    assert video.taille_panier(1.0, 1.0, 40.0, specs) == (0, 0.0)                # même 0,01 lot impossible


def test_panier_ferme_en_gain_jamais_a_perte():
    specs = {"trade_contract_size": 100.0}
    pos = [{"volume": 0.01, "profit": 1.5, "swap": 0.0}, {"volume": 0.01, "profit": 0.6, "swap": -0.05}]
    assert video.a_fermer(pos, specs, gain=1.0)                                  # 2,05 $ ≥ 1 $ × 0,02 lot × 100
    assert not video.a_fermer([{**p, "profit": p["profit"] - 0.2} for p in pos], specs, gain=1.0)
    assert not video.a_fermer([{"volume": 0.01, "profit": -50.0}], specs, gain=1.0)


def test_loterie_complete_sur_le_deuxieme_compte(courtier):
    assert video.bot_video() == "panier : 2 × 0.01 lot ACHAT"                    # loterie n°1, 9,88 $
    assert len(courtier.positions) == 2 and all(p.magic == video.MAGIQUE for p in courtier.positions)
    assert all(d["sl"] == 0.0 for d in courtier.envois)                         # aucun stop, comme les vidéos
    assert "loterie n°1" in courtier.messages[0]
    courtier.prix += 0.9                                                         # +0,70 $ par once : pas assez
    assert video.bot_video().startswith("panier ouvert")
    courtier.prix += 0.5                                                         # +1,20 $ par once : panier gagné
    assert video.bot_video().startswith("panier fermé en gain")
    e = video.lire()
    assert e["paniers"] == 1 and e["loterie"]["paniers"] == 1 and courtier.solde == pytest.approx(9.88 + 2.4)
    assert video.bot_video() == "panier : 3 × 0.01 lot ACHAT"                    # mise relancée : 12,28 $
    courtier.prix -= 30                                                          # chute : perte flottante gardée
    assert video.bot_video().startswith("panier ouvert") and len(courtier.positions) == 3
    courtier.stop_out()
    assert video.bot_video() == "loterie ruinée"
    assert "RUINÉE" in courtier.messages[-1] and "1 paniers gagnés" in courtier.messages[-1]
    assert video.lire()["ruines"] == 1 and video.lire()["loterie"] is None
    assert video.bot_video().startswith("en attente")                           # rien sans nouveau solde
    courtier.solde = 10.0                                                        # solde du compte démo remis
    assert video.bot_video().startswith("panier")
    assert video.lire()["loterie"]["n"] == 2 and "loterie n°2" in courtier.messages[-1]
    assert "Loteries terminées : 1 (1 ruinées)" in video.texte_video()


def test_marche_ferme_ni_rafale_d_ordres_ni_perte_du_panier(courtier):
    import time
    m = time.time()
    courtier.ferme = True                                                        # week-end
    assert video.bot_video(maintenant=m) == "marché fermé : nouvel essai dans 5 min"
    envois = len(courtier.envois)
    assert video.bot_video(maintenant=m + 1) == "ordres en attente (marché fermé ou refus)"
    assert len(courtier.envois) == envois                                       # aucun ordre pendant 5 min
    courtier.ferme = False
    assert video.bot_video(maintenant=m + 301).startswith("panier : ")          # réouverture : le panier part
    courtier.prix += 2
    courtier.ferme = True
    assert video.bot_video(maintenant=m + 302) == "marché fermé : nouvel essai dans 5 min"
    assert len(courtier.positions) == 2                                          # panier gardé, refermé plus tard
    courtier.ferme = False
    assert video.bot_video(maintenant=m + 603).startswith("panier fermé en gain") and courtier.positions == []


def test_pont_video_injoignable_alerte_espacee(courtier, monkeypatch):
    monkeypatch.setattr(config, "VIDEO_PORT", 1)
    alertes = []
    monkeypatch.setattr(telegram, "alerte_rare", lambda cle, texte, *a, **k: alertes.append(cle) or True)
    bot = chef.Bot("Équipe vidéo (2e compte démo)", "execution", 1, video.bot_video)
    assert bot.executer(None) is False and "armee-or-mt5-video" in bot.derniere_erreur and alertes == ["video-pont"]


def test_aucun_ordre_sur_un_compte_reel(courtier):
    courtier.trade_mode = 2
    assert video.bot_video() == "compte réel : aucun ordre" and courtier.envois == []


def test_pilotage_de_l_equipe_video_depuis_telegram(courtier, monkeypatch):
    video.bot_video()
    monkeypatch.setattr(telegram, "commandes", lambda: ["/or_video_gain_2", "/or_video_off", "/or_video_gain_x",
                                                        "/or_video", "/or_video_fermer"])
    chef.bot_commandes(type("Chef", (), {"pause": False})())
    assert video.gain_par_once() == 2.0 and not video.actif()
    assert any("Gain inconnu" in t for t in courtier.messages)
    assert any(t.startswith("🎰 Équipe vidéo — 2e compte DÉMO") for t in courtier.messages)
    assert courtier.positions == [] and "2/2 positions fermées" in courtier.messages[-1]
    assert video.bot_video() == "équipe vidéo désactivée (/or_video_on)" and courtier.positions == []
    assert any(n == "or_video" for n, _ in telegram.MENU)


def test_r5_eteinte_par_defaut_puis_activation_explicite(courtier, monkeypatch):
    base.ecrire("video:actif", None)
    assert not video.actif() and video.bot_video() == "équipe vidéo désactivée (/or_video_on)"
    assert courtier.envois == [] and "DÉSACTIVÉE" in video.texte_video()
    base.ecrire("pause", True)
    courtier.trade_mode = 2                                                      # compte réel : activation refusée
    assert "NON activée" in video.commande("/or_video_on") and not video.actif()
    courtier.trade_mode = 0
    monkeypatch.setattr(telegram, "commandes", lambda: ["/or_video_on"])
    le_chef = type("Chef", (), {"pause": True})()
    chef.bot_commandes(le_chef)
    assert video.actif() and not le_chef.pause and base.lire("pause") is False
    assert any("ACTIVÉE" in t and "99,98 %" in t for t in courtier.messages)
    assert video.bot_video(chef=le_chef).startswith("panier : ")


def test_le_pont_de_l_armee_refuse_le_chemin_video_et_inversement():
    f = FauxCourtier()
    armee = pont_mt5.Pont(f, {"OR_MT5_LOGIN": str(LOGIN_VIDEO), "OR_MT5_SYMBOLE": "XAUUSDm"})
    r = armee.traiter({"op": "video_ouvrir", "sens": 1, "volume": 0.01})
    assert not r["ok"] and "instance video" in r["erreur"] and f.envois == []
    vid = pont_mt5.Pont(f, {"OR_MT5_LOGIN": str(LOGIN_VIDEO), "OR_MT5_SYMBOLE": "XAUUSDm"}, instance="video")
    for op in ("ouvrir", "dimensionner", "demo_mode", "demo_cycle", "marches_ouvrir"):
        r = vid.traiter({"op": op, "sens": 1, "volume": 0.01, "sl": 1.0, "symbole": "XAUUSDm", "actif": True})
        assert not r["ok"] and "réservée au compte de l'armée" in r["erreur"], op
    assert f.envois == []
    for _ in range(10):
        assert vid.traiter({"op": "video_ouvrir", "sens": 1, "volume": 0.01})["r"]["ok"]
    r = vid.traiter({"op": "video_ouvrir", "sens": 1, "volume": 0.01})["r"]                  # 10 positions au plus
    assert not r["ok"] and r["avant_envoi"] and "10 positions" in r["commentaire"]
    f.positions = []
    f.order_calc_margin = lambda t, s, v, p: 9.5                                           # 96 % de 9,88 $ : refusé
    r = vid.traiter({"op": "video_ouvrir", "sens": -1, "volume": 0.01})["r"]
    assert not r["ok"] and "95 %" in r["commentaire"]
    f.trade_mode = 2
    r = vid.traiter({"op": "video_ouvrir", "sens": 1, "volume": 0.01})["r"]
    assert not r["ok"] and "démo" in r["commentaire"] and len(f.envois) == 10              # rien envoyé en réel


def test_equipe_video_absente_sans_reglage(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_ACTIF", False)
    assert video.bot_video() == "équipe vidéo non configurée (or video installer)"
    assert "or video installer" in video.texte_video() and "167 040 loteries" in video.texte_video()


def test_rejeu_historique_avec_les_memes_regles():
    n = 300
    o = 4000.0 + np.arange(n) * 1.5                                              # hausse régulière…
    c, h, l = o + 1.5, o + 1.6, o - 0.1
    o[200:], c[200:], h[200:], l[200:] = 3900.0, 3900.0, 3900.1, 3800.0          # … puis une chute de 100 $
    issue, equite, gagnes = video.simuler(o, h, l, c, 1, 9.88, cible=1e12)
    assert issue == "ruine" and gagnes > 50 and equite > 9.88                   # des paniers gagnés, puis la ruine
    issue, equite, _ = video.simuler(o, h, l, c, 1, 9.88, cible=100.0)
    assert issue == "cible" and equite >= 100
    bougies = [[i * 60, o[i], h[i], l[i], c[i], 1.0] for i in range(n)]
    r = video.rejouer(bougies, 9.88, 1e12, pas=20)
    assert r["departs"] == 12 and r["ruines"] == 12 and r["meilleur"] > 1
    assert "ruinés 12 sur 12" in video.texte_rejeu(r, 9.88, 1e12)


def test_chemin_video_au_hasard_reste_dans_ses_limites():
    import random
    rnd = random.Random(5)
    f = FauxCourtier()
    vid = pont_mt5.Pont(f, {"OR_MT5_LOGIN": str(LOGIN_VIDEO), "OR_MT5_SYMBOLE": "XAUUSDm"}, instance="video")
    for _ in range(400):
        f.order_calc_margin = (lambda m: (lambda t, s, v, p: m * v))(rnd.choice([0.001, 1.0, 50.0, 1e6]))
        r = vid.traiter({"op": "video_ouvrir", "sens": rnd.choice([1, -1, 0, 3]),
                         "volume": rnd.choice([0.01, 0.02, 1.0, 1e6, -1, float("nan"), "x"]),
                         "symbole": rnd.choice([None, "XAUUSDm", "EURUSDm", ""])})
        assert r["ok"] is True
        assert len([p for p in f.positions if p.magic == video.MAGIQUE]) <= 10
        assert all(d["sl"] == 0.0 and d["magic"] == video.MAGIQUE for d in f.envois)
        if rnd.random() < 0.1:
            f.positions = []
    assert f.envois

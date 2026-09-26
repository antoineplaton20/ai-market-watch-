"""Branchement MetaTrader 5 : pont (avec un faux terminal MT5), client, exécutant, commandes. Aucun réseau."""
import threading
import time
from types import SimpleNamespace as NS

import numpy as np
import pytest

from armee_or import base, chef, config, executant, flux, mt5, pont_mt5

LOGIN = 5550001


class FauxMT5:
    """Imite la bibliothèque MetaTrader5 : compte démo, XAUUSD, positions, historique des transactions."""
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, POSITION_TYPE_BUY = 0, 1, 0
    TRADE_ACTION_DEAL, ORDER_TIME_GTC = 1, 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TIMEFRAME_M1, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 1, 15, 16385, 16388, 16408

    def __init__(self):
        self.trade_mode, self.algo, self.prix, self.solde = 0, True, 4000.0, 100_000.0
        self.positions, self.deals, self.envois = [], [], []
        self.suivant, self.temps = 1000, 1_700_000_000_000

    def initialize(self, **kw):
        self.options = kw
        return True

    def shutdown(self):
        pass

    def last_error(self):
        return (1, "Success")

    def terminal_info(self):
        return NS(connected=True, trade_allowed=self.algo, build=4000, name="MetaTrader 5", ping_last=30000)

    def account_info(self):
        marge = sum(p.volume * 100 * p.price_open / 100 for p in self.positions)
        return NS(login=LOGIN, server="MetaQuotes-Demo", trade_mode=self.trade_mode, balance=self.solde,
                  equity=self.solde, margin=marge, margin_free=self.solde - marge, leverage=100, currency="USD",
                  trade_allowed=True)

    def symbol_select(self, s, v):
        return s == "XAUUSD"

    def symbol_info(self, s):
        if s != "XAUUSD":
            return None
        return NS(name=s, digits=2, point=0.01, volume_min=0.01, volume_step=0.01, volume_max=100.0,
                  trade_contract_size=100.0, filling_mode=2, trade_stops_level=0, trade_mode=4, currency_profit="USD",
                  spread=20)

    def symbols_get(self):
        return (NS(name="XAUUSD"), NS(name="XAUEUR"))

    def symbol_info_tick(self, s):
        self.temps += 1000
        return NS(bid=self.prix - 0.1, ask=self.prix + 0.1, last=0.0, time=self.temps // 1000, time_msc=self.temps)

    def copy_rates_from_pos(self, s, tf, debut, n):
        r = np.zeros(n, dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                               ("tick_volume", "i8")])
        r["time"] = np.arange(n) * 3600
        r["open"] = r["close"] = self.prix
        r["high"], r["low"] = self.prix + 5, self.prix - 5                 # ATR = 10
        return r

    def order_calc_margin(self, t, s, volume, prix):
        return volume * 100 * prix / 100

    def positions_get(self, ticket=None, symbol=None):
        return tuple(p for p in self.positions if ticket is None or p.ticket == ticket)

    def order_send(self, d):
        self.envois.append(d)
        if d["type_filling"] != self.ORDER_FILLING_IOC:
            return NS(retcode=10030, comment="Unsupported filling mode", order=0, deal=0, price=0.0, volume=0.0)
        self.suivant += 1
        prix = d["price"]
        if "position" in d:
            p = next(x for x in self.positions if x.ticket == d["position"])
            sens = 1 if p.type == 0 else -1
            profit = (prix - p.price_open) * p.volume * 100 * sens
            self.positions.remove(p)
            self.solde += profit
            self.deals.append(NS(ticket=self.suivant, order=self.suivant, position_id=p.ticket, time=0, type=d["type"],
                                 entry=1, volume=p.volume, price=prix, profit=profit, commission=-0.5, swap=0.0,
                                 fee=0.0, magic=p.magic, comment=d["comment"]))
        else:
            self.positions.append(NS(ticket=self.suivant, type=d["type"], volume=d["volume"], price_open=prix,
                                     price_current=prix, sl=d["sl"], tp=0.0, profit=0.0, swap=0.0, magic=d["magic"],
                                     comment=d["comment"], time=0, symbol=d["symbol"]))
            self.deals.append(NS(ticket=self.suivant, order=self.suivant, position_id=self.suivant, time=0,
                                 type=d["type"], entry=0, volume=d["volume"], price=prix, profit=0.0, commission=-0.5,
                                 swap=0.0, fee=0.0, magic=d["magic"], comment=d["comment"]))
        return NS(retcode=10009, comment="Request executed", order=self.suivant, deal=self.suivant, price=prix,
                  volume=d["volume"])

    def history_deals_get(self, debut, fin):
        return tuple(self.deals)


@pytest.fixture
def faux(monkeypatch):
    f = FauxMT5()
    pont = pont_mt5.Pont(f, {"OR_MT5_LOGIN": str(LOGIN), "OR_MT5_MOT_DE_PASSE": "x", "OR_MT5_SYMBOLE": "XAUUSD"})
    serveur = pont.serveur(0)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "MT5_PORT", serveur.server_address[1])
    monkeypatch.setattr(config, "MT5_ACTIF", True)
    monkeypatch.setattr(config, "MT5_PROFIL", "pro 1 % risqué")
    monkeypatch.setattr(config, "MT5_ENTRAINEMENT", True)
    yield f
    serveur.shutdown()
    serveur.server_close()


def _chef(pause=False):
    return type("Chef", (), {"pause": pause, "bots": []})()


def _prono(tf, sens, p=0.6):
    ms = executant.MS[tf]
    base.ecrire(f"prono:{tf}", {"ts": int(time.time() * 1000) - ms - 60_000, "p": p, "sens": sens})


# ------------------------------------------------------------------ pont
def test_pont_etat_cours_symbole(faux):
    e = mt5.appel("etat")
    assert e["connecte"] and e["compte"]["demo"] and e["compte"]["login"] == LOGIN
    t = mt5.appel("tick")
    assert t["ask"] > t["bid"]
    assert mt5.appel("specs")["trade_contract_size"] == 100
    assert len(mt5.appel("bougies", tf="4h", n=50)) == 50
    with pytest.raises(mt5.ErreurMT5, match="XAUEUR"):
        mt5.appel("specs", symbole="GOLD")                           # propose les symboles proches


def test_pont_ouvre_arrondit_trouve_le_remplissage_et_ferme(faux):
    r = mt5.appel("ouvrir", sens=1, volume=0.019, sl=3900, magic=770004)
    assert r["ok"] and faux.positions[0].volume == 0.01                # arrondi au pas, jamais au-dessus
    assert [d["type_filling"] for d in faux.envois] == [faux.ORDER_FILLING_IOC]
    assert mt5.appel("fermer", ticket=faux.positions[0].ticket)["ok"] and not faux.positions


def test_pont_refuse_tout_ordre_sur_compte_reel(faux):
    faux.trade_mode = 2
    with pytest.raises(mt5.ErreurMT5, match="démo"):
        mt5.appel("ouvrir", sens=1, volume=0.01, sl=3900, magic=770004)
    assert not faux.envois


def test_pont_ne_touche_jamais_aux_ordres_manuels(faux):
    faux.positions.append(NS(ticket=42, type=0, volume=1.0, price_open=4000, price_current=4000, sl=0, tp=0, profit=0,
                             swap=0, magic=0, comment="manuel", time=0, symbol="XAUUSD"))
    assert mt5.appel("positions") == []
    assert mt5.appel("fermer", ticket=42)["commentaire"] == "déjà fermée" and len(faux.positions) == 1
    with pytest.raises(mt5.ErreurMT5, match="magique"):
        mt5.appel("ouvrir", sens=1, volume=0.01, sl=3900, magic=12345)


def test_pont_refuse_un_stop_du_mauvais_cote(faux):
    with pytest.raises(mt5.ErreurMT5, match="stop"):
        mt5.appel("ouvrir", sens=1, volume=0.01, sl=4100, magic=770004)


def test_pont_injoignable(monkeypatch):
    monkeypatch.setattr(config, "MT5_PORT", 1)
    with pytest.raises(mt5.ErreurMT5, match="injoignable"):
        mt5.appel("etat", delai=2)


# ------------------------------------------------------------------ taille des ordres
def test_volume_selon_profil_et_marge():
    specs = {"trade_contract_size": 100, "volume_step": 0.01, "volume_min": 0.01, "volume_max": 100}
    assert mt5.volume("pro 1 % risqué", 100_000, 4000, 3880, specs, 4000, 100_000)[0] == pytest.approx(0.08)
    assert mt5.volume("pro 1 % risqué", 10_000, 4000, 3880, specs, 4000, 10_000)[0] == 0      # < lot minimum
    assert mt5.volume("x20 (max. UE)", 10_000, 4000, 3880, specs, 4000, 10_000)[0] == pytest.approx(0.5)
    assert mt5.volume("x50 (max. Binance)", 10_000, 4000, 3880, specs, 4000, 1_000)[0] == pytest.approx(0.22)
    assert mt5.nom_profil("x20") == "x20 (max. UE)" and mt5.nom_profil("pro") == "pro 1 % risqué"
    assert mt5.nom_profil("x1000") is None


# ------------------------------------------------------------------ exécutant
def test_decision_4h_executee_une_seule_fois_puis_fermee_a_l_horizon(faux):
    _prono("4h", 1)
    msg = executant.bot_mt5(_chef())
    assert "ACHAT" in msg and len(faux.positions) == 1
    p = faux.positions[0]
    assert p.magic == 770004 and p.volume == pytest.approx(0.33)      # 1 % de 100 000 $ pour 3 ATR (30 $)
    assert p.sl == pytest.approx(4000.1 - 30, abs=0.01)
    executant.bot_mt5(_chef())
    assert len(faux.positions) == 1                                   # même décision : aucun second ordre
    suivi = base.lire("mt5:suivi")
    for s in suivi.values():
        s["fin"] = time.time() - 1
    base.ecrire("mt5:suivi", suivi)
    faux.prix = 4010
    msg = executant.bot_mt5(_chef())
    assert "horizon" in msg and not faux.positions
    with base.connexion() as c:
        actions = [r["action"] for r in c.execute("SELECT action FROM ordres_mt5 ORDER BY id")]
    assert actions == ["ouverture", "fermeture"]
    r = executant.resultats(force=True)["equipes"]["4h"]
    assert r["trades"] == 1 and r["gagnants"] == 1 and r["pnl"] > 0


def test_entrainement_au_lot_minimum_dans_le_sens_du_consensus(faux):
    _prono("1h", 0, p=0.47)
    executant.bot_mt5(_chef())
    assert len(faux.positions) == 1
    p = faux.positions[0]
    assert p.magic == 770001 and p.type == faux.ORDER_TYPE_SELL and p.volume == 0.01


def test_aucun_ordre_en_pause_sur_compte_reel_ou_sans_trading_algo(faux):
    _prono("4h", 1)
    assert "pause" in executant.bot_mt5(_chef(pause=True)) and not faux.positions
    faux.trade_mode = 2
    assert "réel" in executant.bot_mt5(_chef()) and not faux.envois
    faux.trade_mode, faux.algo = 0, False
    assert "algorithmique" in executant.bot_mt5(_chef()) and not faux.envois


def test_decision_perimee_ignoree(faux):
    base.ecrire("prono:4h", {"ts": int(time.time() * 1000) - 3 * executant.MS["4h"], "p": 0.7, "sens": 1})
    executant.bot_mt5(_chef())
    assert not faux.positions


def test_stop_touche_detecte(faux):
    _prono("1d", -1, p=0.3)
    executant.bot_mt5(_chef())
    assert faux.positions and faux.positions[0].magic == 770024
    faux.positions.clear()                                            # stop exécuté par le serveur
    assert "stop" in executant.bot_mt5(_chef()) and base.lire("mt5:suivi") == {}


def test_commandes_mt5_fermer_profil_entrainement(faux):
    _prono("4h", 1)
    executant.bot_mt5(_chef())
    assert faux.positions
    ch = _chef()
    (config.RACINE / "runtime" / "commandes.txt").write_text("mt5_fermer\nmt5_profil x20\nmt5_entrainement off\n")
    chef.bot_commandes(ch)
    assert not faux.positions and base.lire("mt5:pause") is True
    assert executant.profil_actif() == "x20 (max. UE)" and executant.entrainement_actif() is False
    _prono("1d", 1)
    assert "pause" in executant.bot_mt5(ch) and not faux.positions
    (config.RACINE / "runtime" / "commandes.txt").write_text("mt5_reprendre\n")
    chef.bot_commandes(ch)
    executant.bot_mt5(ch)
    assert len(faux.positions) == 1 and faux.positions[0].volume == pytest.approx(4.99)   # x20 de 100 000 $


def test_rapport_mt5(faux):
    _prono("4h", 1)
    executant.bot_mt5(_chef())
    texte = executant.rapport_mt5()
    assert "DÉMO" in texte and "décisions 4 h" in texte and "…001" in texte and "5550001" not in texte


def test_vigie_mt5_et_priorite_du_cours(faux):
    v = flux.VigieMT5()
    v.lire()
    d = flux.prix_direct()
    assert d["cle"] == "MT5" and d["prix"] == pytest.approx(4000)
    base.ecrire("direct:XAUUSDT", {"prix": 4001, "ts": time.time(), "retard_ms": 30, "source": "x"})
    assert flux.prix_direct()["cle"] == "XAUUSDT"


def test_bot_mt5_inactif_sans_reglage(monkeypatch):
    monkeypatch.setattr(config, "MT5_ACTIF", False)
    assert executant.bot_mt5(_chef()) == "MT5 non configuré"
    assert "non branché" in executant.rapport_mt5()


def test_le_chef_isole_une_panne_du_pont(monkeypatch):
    monkeypatch.setattr(config, "MT5_ACTIF", True)
    monkeypatch.setattr(config, "MT5_PORT", 1)
    bot = chef.Bot("Exécutant MT5 (démo)", "execution", 20, executant.bot_mt5)
    assert bot.executer(_chef()) is False and "injoignable" in bot.derniere_erreur


def test_le_pont_reste_autonome_et_ne_contient_aucun_identifiant():
    import os
    import re
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    texte = open(os.path.join(racine, "armee_or", "pont_mt5.py"), encoding="utf-8").read()
    assert not re.search(r"(?m)^\s*(from \.|from armee_or|import armee_or)", texte)       # stdlib + MetaTrader5 seulement
    assert "127.0.0.1" in texte and "0.0.0.0" not in texte                                  # jamais exposé au réseau
    for fichier in ("installer_mt5.sh", "installer_or.sh", "or"):
        contenu = open(os.path.join(racine, fichier), encoding="utf-8").read()
        assert not re.search(r"OR_MT5_(LOGIN|MOT_DE_PASSE)=\d|MOT_DE_PASSE=[^$\n]", contenu), fichier

"""Armée multi-marchés : inventaire de tous les symboles MT5, archive journalière, banc d'essai à deux moitiés, permis
contre « toujours acheter », taille selon la volatilité et le capital, équipe à part de l'exécutant de l'or.
Faux courtier multi-symboles en mémoire ; aucun réseau."""
import threading
import time
from types import SimpleNamespace as NS

import numpy as np
import pytest

from armee_or import base, config, executant, marches, pont_mt5, telegram, video

JOUR = 86400
DEBUT = 1_500_000_000 - 1_500_000_000 % JOUR


def serie_tendance(n, graine, crise=True):
    """Hausses longues entrecoupées de krachs : la règle des 200 jours sort pendant les krachs."""
    rng = np.random.default_rng(graine)
    r = rng.normal(0.0006, 0.009, n)
    if crise:
        for debut in range(450, n, 900):
            r[debut:debut + 120] = rng.normal(-0.006, 0.012, min(120, n - debut))
    return 100 * np.exp(np.cumsum(r))


def serie_sans_tendance(n, graine):
    """Marché qui revient sans cesse vers 100 : la règle des 200 jours y entre et sort à contretemps."""
    rng = np.random.default_rng(graine)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.97 * x[i - 1] + rng.normal(0, 1.2)
    return 100 + x


def bruit(n, graine, amplitude=0.01):
    return 1 + amplitude * np.sin(np.arange(n) * (1.3 + graine))


class FauxMulti:
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, POSITION_TYPE_BUY = 0, 1, 0
    TRADE_ACTION_DEAL, ORDER_TIME_GTC = 1, 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TIMEFRAME_M1, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 1, 15, 16385, 16388, 16408

    def __init__(self, series):
        self.series = series                                          # {symbole: (chemin, contrat, closes)}
        self.positions, self.envois, self.suivant, self.solde = [], [], 500, 100_000.0

    def initialize(self, **kw):
        return True

    def shutdown(self):
        pass

    def last_error(self):
        return (1, "Success")

    def terminal_info(self):
        return NS(connected=True, trade_allowed=True, build=5000, name="MetaTrader 5", ping_last=20000)

    def prix(self, s):
        return float(self.series[s][2][-1])

    def account_info(self):
        return NS(login=1, server="MetaQuotes-Demo", trade_mode=0, balance=self.solde, equity=self.solde, margin=0.0,
                  margin_free=self.solde, leverage=100, currency="USD", trade_allowed=True, margin_mode=2)

    def symbol_select(self, s, v):
        return s in self.series

    def symbol_info(self, s):
        if s not in self.series:
            return None
        chemin, contrat, _ = self.series[s]
        return NS(name=s, digits=5, point=0.00001 if "Forex" in chemin else 0.01, volume_min=0.01, volume_step=0.01,
                  volume_max=100.0, trade_contract_size=contrat, filling_mode=2, trade_stops_level=0, trade_mode=4,
                  currency_profit="USD", spread=15, swap_mode=1, swap_long=-3.0, swap_short=0.5, currency_base="EUR",
                  path=chemin, description=s)

    def symbols_get(self):
        return tuple(NS(name=s, path=v[0], description=s, trade_mode=4, currency_profit="USD")
                     for s, v in self.series.items()) + (NS(name="EURUSD.ferme", path="Forex", description="",
                                                             trade_mode=0, currency_profit="USD"),)

    def symbol_info_tick(self, s):
        p = self.prix(s if s in self.series else "XAUUSD")
        return NS(bid=p * 0.9999, ask=p * 1.0001, last=0.0, time=int(time.time()), time_msc=0)

    def _barres(self, s, indices):
        c = self.series[s][2]
        r = np.zeros(len(indices), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                                          ("tick_volume", "i8")])
        r["time"] = DEBUT + np.array(indices) * JOUR
        r["close"] = c[indices]
        r["open"] = np.concatenate(([c[indices[0]]], c[np.array(indices[:-1])])) if len(indices) else []
        r["high"], r["low"] = r["close"] * 1.004, r["close"] * 0.996
        return r

    def copy_rates_from_pos(self, s, tf, debut, n):
        total = len(self.series[s][2])
        return self._barres(s, list(range(max(0, total - n), total)))

    def copy_rates_range(self, s, tf, debut, fin):
        total = len(self.series[s][2])
        return self._barres(s, [i for i in range(total) if debut <= DEBUT + i * JOUR <= fin])

    def order_calc_margin(self, t, s, volume, prix):
        return volume * self.series[s][1] * prix / 100

    def order_calc_profit(self, t, s, volume, ouverture, cloture):
        return (cloture - ouverture) * volume * self.series[s][1]

    def positions_get(self, ticket=None, symbol=None):
        for p in self.positions:
            p.profit = (self.prix(p.symbol) - p.price_open) * p.volume * self.series[p.symbol][1]
        return tuple(p for p in self.positions if ticket is None or p.ticket == ticket)

    def order_send(self, d):
        self.envois.append(d)
        if d["type_filling"] != self.ORDER_FILLING_IOC:
            return NS(retcode=10030, comment="Unsupported filling mode", order=0, deal=0, price=0.0, volume=0.0)
        self.suivant += 1
        if "position" in d:
            self.positions = [p for p in self.positions if p.ticket != d["position"]]
        else:
            self.positions.append(NS(ticket=self.suivant, type=d["type"], volume=d["volume"], price_open=d["price"],
                                     price_current=d["price"], sl=d["sl"], tp=0.0, profit=0.0, swap=0.0,
                                     magic=d["magic"], comment=d["comment"], time=0, symbol=d["symbol"]))
        return NS(retcode=10009, comment="Request executed", order=self.suivant, deal=self.suivant, price=d["price"],
                  volume=d["volume"])

    def orders_get(self):
        return ()

    def history_deals_get(self, debut, fin):
        return ()


def activer():
    """Ce que fait /or_marches_on quand le compte est confirmé : équipe active, pause MT5 levée."""
    base.ecrire("marches:actif", True)
    base.ecrire("mt5:pause", False)


@pytest.fixture
def courtier(monkeypatch):
    n = 900
    f = FauxMulti({
        "EURUSD": ("Forex\\Majors\\EURUSD", 100_000.0, (1.0 + 0.0004 * np.arange(n)) * bruit(n, 1, 0.004)),
        "USDJPY": ("Forex\\Majors\\USDJPY", 100_000.0, (160.0 - 0.05 * np.arange(n)) * bruit(n, 2, 0.004)),
        "XAUUSD": ("Metals\\XAUUSD", 100.0, (1500.0 + 3.0 * np.arange(n)) * bruit(n, 3)),        # lot trop gros
        "US500": ("Indices\\US500", 1.0, (4000.0 + 2.0 * np.arange(n)) * bruit(n, 4)),
    })
    pont = pont_mt5.Pont(f, {"OR_MT5_LOGIN": "1", "OR_MT5_SYMBOLE": "XAUUSD"})
    serveur = pont.serveur(0)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "MT5_PORT", serveur.server_address[1])
    monkeypatch.setattr(config, "MT5_ACTIF", True)
    messages = []
    monkeypatch.setattr(telegram, "envoyer", lambda t, important=False, **k: messages.append(t) or True)
    f.messages = messages
    base.ecrire("mt5:etat", {"connecte": True, "compte": {"equity": 2700.0, "currency": "USD", "demo": True,
                                                         "margin_free": 2700.0, "login": 1,
                                                         "server": "MetaQuotes-Demo"}, "ts": 9e12})
    yield f
    serveur.shutdown()
    serveur.server_close()


def test_un_symbole_par_marche_chez_n_importe_quel_courtier():
    noms = ["EURUSD.a", "EURUSD", "GBPUSDm", "XAUUSD", "XAGUSD", "USTEC", "US500.cash", "GER40", "BTCUSD", "USOIL",
            "EURUSDJPY", "FRA40"]
    choix = marches.choisir_univers([{"name": x, "trade_mode": 4} for x in noms] + [{"name": "ETHUSD", "trade_mode": 0}])
    assert choix["EURUSD"]["famille"] == "forex" and "EURUSD.a" not in choix          # le nom exact d'abord
    assert choix["GBPUSDm"]["nom"] == "GBPUSD" and choix["XAUUSD"]["famille"] == "métaux"
    assert choix["US500.cash"]["nom"] == "S&P 500" and choix["USOIL"]["famille"] == "énergie"
    assert choix["BTCUSD"]["famille"] == "crypto" and "ETHUSD" not in choix            # non négociable : écarté
    assert {v["famille"] for v in choix.values()} == {"forex", "métaux", "indices", "crypto", "énergie"}


def test_couts_lus_chez_le_courtier():
    c = marches.couts({"point": 0.00001, "spread": 15, "swap_mode": 1, "swap_long": -7.0}, "forex", 1.10)
    assert c["ecart"] == pytest.approx(15 * 0.00001 / 1.10 / 2)
    assert c["swap_long"] == pytest.approx(-7.0 * 0.00001 / 1.10 * 7 / 5)
    d = marches.couts({}, "crypto", 60_000)                                              # illisible : prudence
    assert d["ecart"] == pytest.approx(0.0005) and d["swap_long"] == pytest.approx(-0.03 / 365 * 7 / 5)


def test_regle_200_jours_stop_de_catastrophe_et_reamorcage():
    hausse = 100 * 1.002 ** np.arange(400)
    baisse = hausse[-1] * 0.99 ** np.arange(1, 151)
    reprise = baisse[-1] * 1.003 ** np.arange(1, 351)
    c = np.concatenate((hausse, baisse, reprise)) * bruit(900, 0, 0.003)
    o, h, l = c.copy(), c * 1.002, c * 0.998
    o[310], l[310] = c[309] * 0.6, c[309] * 0.59                                         # krach à l'ouverture : stop sauté
    assert marches.signal(c, "sma200")[250] == 1 and marches.signal(c, "sma200")[530] == 0
    net, entrees = marches.simuler_marche(o, h, l, c, "sma200", {"ecart": 0.0001, "swap_long": 0.0})
    assert net[310] < -0.1 and np.all(net[311:400] == 0)                                # sorti au trou, pas rentré…
    assert entrees == 2 and net[800:].sum() > 0                                          # … jusqu'au signal suivant


def test_banc_permis_seulement_si_meilleur_que_tout_acheter():
    cout = {"ecart": 0.0001, "swap_long": -0.00005}

    def marche(c, graine):
        return {"ts": (DEBUT + np.arange(len(c)) * JOUR) * 1000, "o": c, "h": c * 1.004, "l": c * 0.996, "c": c,
                "cout": cout}
    tendances = {f"M{i}": marche(serie_tendance(2400, i), i) for i in range(8)}
    res = marches.banc(tendances)
    p = marches.permis(res)
    assert p["sma200"]["ok"], p["sma200"]
    assert res["sma200"]["tout"]["pire_baisse"] > res["toujours_acheter"]["tout"]["pire_baisse"]
    cout = {"ecart": 0.002, "swap_long": -0.0001}                                       # frais réels d'un CFD
    sans_tendance = {f"S{i}": marche(serie_sans_tendance(2400, 100 + i), i) for i in range(8)}
    assert not marches.permis(marches.banc(sans_tendance))["sma200"]["ok"]
    assert not marches.permis(marches.banc(dict(list(tendances.items())[:3])))["sma200"]["ok"]   # trop peu de marchés


def test_taille_selon_volatilite_et_lot_minimum_trop_gros():
    budget = marches.budget_risque(10)
    assert budget == pytest.approx(0.10 / np.sqrt(10 * (1 + 9 * 0.15)))
    forex = {"volume_min": 0.01, "volume_step": 0.01}
    lots, _ = marches.lots_marche(2700, 110_000, 0.07, budget, forex)
    assert lots == 0.01                                                                  # 1 100 pour ~800 visés : accepté
    lots, note = marches.lots_marche(2700, 400_000, 0.16, budget, forex)
    assert lots == 0 and "trop gros" in note                                             # or : 4 000 pour ~350 visés
    garde, b, exclus = marches.selection({"EURUSD": (110_000, 0.07, forex), "XAUUSD": (400_000, 0.16, forex),
                                          "US500": (4_000, 0.18, forex)}, 2700)
    assert set(garde) == {"EURUSD", "US500"} and "XAUUSD" in exclus and b == marches.budget_risque(2)


def test_equipe_multi_marches_sous_permis_et_activation(courtier):
    assert executant.PAR_MAGIC.get(marches.MAGIQUE) is None                               # l'exécutant de l'or n'y touche pas
    assert marches.bot_marches().endswith("pas de permis")
    assert courtier.envois == [] and marches.lire()["univers"]["EURUSD"]["famille"] == "forex"
    base.ecrire("marches:permis", {"sma200": {"ok": True, "sharpe": (0.3, 0.5)}})
    e = marches.lire()
    e["vu"] = {}                                                                         # nouvelle journée : bougie neuve
    marches.ecrire(e)
    assert "désactivée" in marches.bot_marches() and courtier.envois == []               # R5 : désactivée par défaut
    assert set(marches.lire()["intentions"]) == {"EURUSD", "US500"}                      # … mais montre ce qu'elle ferait
    assert "Achats qu'elle ferait" in marches.texte_marches()
    activer()
    marches.bot_marches()
    achats = {p.symbol: p for p in courtier.positions}
    assert set(achats) == {"EURUSD", "US500"}                                            # USDJPY sous sa 200 j, or trop gros
    assert all(p.magic == marches.MAGIQUE and 0 < p.sl < p.price_open for p in achats.values())
    annonce = [t for t in courtier.messages if "ACHAT" in t]
    assert len(annonce) == 1 and "EURUSD" in annonce[0] and "US500" in annonce[0]        # un seul message
    assert "XAUUSD" in marches.lire()["exclus"]
    marches.bot_marches()
    assert len(courtier.positions) == 2                                                  # une décision par bougie
    eur = courtier.series["EURUSD"]
    courtier.series["EURUSD"] = (eur[0], eur[1], np.concatenate((eur[2], eur[2][-1] * 0.97 ** np.arange(1, 41))))
    marches.bot_marches()
    assert {p.symbol for p in courtier.positions} == {"US500"} and any("sortie" in t for t in courtier.messages)
    assert "Positions : US500" in marches.texte_marches()


def test_marche_ferme_nouvel_essai_plus_tard(courtier, monkeypatch):
    base.ecrire("marches:permis", {"sma200": {"ok": True, "sharpe": (0.3, 0.5)}})
    activer()
    envoi = courtier.order_send
    courtier.order_send = lambda d: (NS(retcode=10018, comment="Market closed", order=0, deal=0, price=0.0, volume=0.0)
                                     if d["symbol"] == "US500" else envoi(d))
    marches.bot_marches(maintenant=1_000_000)
    assert {p.symbol for p in courtier.positions} == {"EURUSD"}
    n = len(courtier.envois)
    marches.bot_marches(maintenant=1_000_300)
    assert len(courtier.envois) == n                                                     # pas de nouvel essai avant 30 min
    courtier.order_send = envoi
    marches.bot_marches(maintenant=1_002_000)
    assert {p.symbol for p in courtier.positions} == {"EURUSD", "US500"} and not base.lire(marches.INCERTAIN)


def test_coupe_circuit_aucun_achat(courtier):
    base.ecrire("marches:permis", {"sma200": {"ok": True, "sharpe": (0.3, 0.5)}})
    activer()
    base.ecrire("risque:etat", {"coupe": True, "raison": "baisse de 5 %"})                # frein central de l'armée
    assert "COUPE-CIRCUIT" in marches.bot_marches() and courtier.positions == []


def test_archive_journaliere_puis_banc(courtier):
    marches.bot_marches()                                                                # inventaire
    for _ in range(6):
        marches.archiver(par_passage=4)
    d = marches.charger_marches()
    assert set(d) == {"EURUSD", "USDJPY", "XAUUSD", "US500"} and all(len(v["c"]) == 900 for v in d.values())
    assert marches.bot_banc().startswith("sma200")


def test_pilotage_multi_marches_depuis_telegram(courtier, monkeypatch):
    from armee_or import chef
    base.ecrire("pause", True)
    base.ecrire("mt5:pause", True)
    monkeypatch.setattr(telegram, "commandes", lambda: ["/or_marches_on"])
    le_chef = type("Chef", (), {"pause": True})()
    chef.bot_commandes(le_chef)
    assert marches.actif() and not le_chef.pause and base.lire("mt5:pause") is False      # comme /or_demo_on
    assert any("ACTIVÉ" in t and "2 %" in t for t in courtier.messages)
    monkeypatch.setattr(telegram, "commandes", lambda: ["/or_marches_off", "/or_marches"])
    chef.bot_commandes(le_chef)
    assert not marches.actif() and any(t.startswith("🌍 Armée multi-marchés") for t in courtier.messages)
    assert any(n == "or_marches" for n, _ in telegram.MENU)
    base.ecrire("r2:compte_change", True)                                                # incident R2 : refus
    assert "NON activé" in marches.commande("/or_marches_on") and not marches.actif()


def test_equipe_video_sur_un_autre_marche(monkeypatch):
    e = {}
    monkeypatch.setattr(video, "appel", lambda op, **k: [{"name": "EURUSDm"}, {"name": "EURUSDm.x"}, {"name": "XAUUSDm"}])
    assert video.resoudre(e, "eurusdm") == "EURUSDm" and video.resoudre(e, "or") is None
    assert video.resoudre(e, "inconnu") == ""
    specs = {"volume_min": 0.01, "volume_step": 0.01, "trade_contract_size": 100_000.0}
    # même part du prix que sur l'or : 0,25 × 10 $ × 4 000 / 108 000 (valeur d'un lot EURUSD) ≈ 0,09 lot
    assert video.taille_panier(10, 10, 0.001, specs, valeur_lot=108_000) == (8, 0.01)
    assert video.a_fermer([{"volume": 0.08, "profit": 2.2}], specs, gain=1.0, valeur_lot=108_000)   # seuil 2,16
    assert not video.a_fermer([{"volume": 0.08, "profit": 2.0}], specs, gain=1.0, valeur_lot=108_000)
    assert video.commande("/or_video_symbole_eurusdm").startswith("✅") and base.lire("video:symbole") == "eurusdm"
    assert "retour à l'or" in video.commande("/or_video_symbole_or") and base.lire("video:symbole") is None


def test_chemin_d_ordres_multi_marches_garde_les_plafonds_r3(courtier):
    pont = pont_mt5.Pont(courtier, {"OR_MT5_LOGIN": "1", "OR_MT5_SYMBOLE": "XAUUSD"})

    def ouvrir(**k):
        return pont.traiter({"op": "marches_ouvrir", **k})["r"]
    prix = courtier.prix("EURUSD")
    r = ouvrir(symbole="EURUSD", volume=0.01, sl=prix * 0.95, sens=-1)
    assert not r["ok"] and r["avant_envoi"] and "achat seulement" in r["commentaire"]
    r = ouvrir(symbole="EURUSD", volume=0.01, sl=prix * 1.01)
    assert not r["ok"] and "stop" in r["commentaire"]                                    # stop du mauvais côté
    assert courtier.envois == []
    r = ouvrir(symbole="EURUSD", volume=100.0, sl=prix * 0.95)                           # 0,5 % du compte au plus
    assert r["ok"] and r["risque"] <= 0.005 * courtier.solde + 1e-6 and courtier.positions[0].volume < 100
    deja = r["risque"]
    r = ouvrir(symbole="EURUSD", volume=0.01, sl=prix * 0.95)
    assert not r["ok"] and "déjà ouverte" in r["commentaire"]                            # une position par marché
    us = courtier.prix("US500")                         # plafond cumulé R3 (2 %) : la démo R4 (770090) compte aussi
    courtier.positions.append(NS(ticket=9, type=0, volume=1.0, price_open=us, price_current=us, sl=us - 1040.0, tp=0.0,
                                 profit=0.0, swap=0.0, magic=770090, comment="demo R4", time=0, symbol="US500"))
    r = ouvrir(symbole="XAUUSD", volume=100.0, sl=courtier.prix("XAUUSD") * 0.95)
    reste = 0.02 * courtier.solde - deja - 1040.0 * pont_mt5.RESERVE_COUTS
    assert r["ok"] and r["volume"] < 100 and r["risque"] <= reste + 1.0
    r = ouvrir(symbole="USDJPY", volume=0.01, sl=courtier.prix("USDJPY") * 0.99)
    assert not r["ok"] and "budget" in r["commentaire"]
    assert {p.magic for p in courtier.positions} == {marches.MAGIQUE, 770090}
    video_pont = pont_mt5.Pont(courtier, {"OR_MT5_LOGIN": "1"}, instance="video")
    assert not video_pont.traiter({"op": "marches_ouvrir", "symbole": "EURUSD", "volume": 0.01, "sl": 1.0})["ok"]
    courtier.symbol_info_tick = lambda s: NS(bid=1.0, ask=1.0001, last=0.0, time=0, time_msc=0)
    courtier.positions = []
    r = ouvrir(symbole="EURUSD", volume=0.01, sl=0.9)
    assert not r["ok"] and "périmé" in r["commentaire"]                                  # marché fermé : rien envoyé


def test_ordre_incertain_verrouille_puis_reconciliation(courtier, monkeypatch):
    from armee_or import mt5
    base.ecrire("marches:permis", {"sma200": {"ok": True, "sharpe": (0.3, 0.5)}})
    activer()
    vrai = mt5.appel

    def perdu(op, *a, **k):
        if op == "marches_ouvrir":
            vrai(op, *a, **k)                                                            # l'ordre part…
            raise mt5.ErreurMT5("pont MT5 injoignable (timeout)")                        # … la réponse se perd
        return vrai(op, *a, **k)
    monkeypatch.setattr(mt5, "appel", perdu)
    marches.bot_marches(maintenant=2_000_000)
    i = base.lire(marches.INCERTAIN)
    assert i["equipe"] == "marches" and base.lire("mt5:pause") is True
    assert len(courtier.positions) == 1                                                  # aucune autre entrée
    assert any("INCERTAIN" in t for t in courtier.messages)
    monkeypatch.setattr(mt5, "appel", vrai)
    marches.bot_marches(maintenant=2_000_300)
    assert base.lire(marches.INCERTAIN) is None and i["symbole"] in marches.lire()["positions"]
    assert len(courtier.positions) == 1 and base.lire("mt5:pause") is True               # reprise : /or_marches_on
    base.ecrire(marches.INCERTAIN, {"ts": 2_000_000, "equipe": "marches", "symbole": "US500"})
    marches.bot_marches(maintenant=2_000_100)
    assert base.lire(marches.INCERTAIN)                                                  # trop tôt pour conclure
    marches.bot_marches(maintenant=2_000_700)
    assert base.lire(marches.INCERTAIN) is None                                          # jamais exécuté : levé
    base.ecrire(marches.INCERTAIN, {"ts": 1, "equipe": "1d"})                            # incident d'une autre équipe
    assert "incident" in marches.bot_marches(maintenant=2_001_000) and base.lire(marches.INCERTAIN)


def test_deployer_r5_pause_les_equipes_et_refuse_le_retour_avec_positions(tmp_path, monkeypatch):
    import json
    import sqlite3
    import deployer
    (tmp_path / "runtime").mkdir(exist_ok=True)
    with sqlite3.connect(tmp_path / "runtime/or.db") as c:
        c.execute("CREATE TABLE kv(cle TEXT PRIMARY KEY, valeur TEXT, maj REAL)")
        c.execute("INSERT INTO kv VALUES ('marches:actif','true',0),('video:actif','true',0)")
    deployer.pause(tmp_path)
    with sqlite3.connect(tmp_path / "runtime/or.db") as c:
        kv = dict(c.execute("SELECT cle, valeur FROM kv").fetchall())
    assert json.loads(kv["marches:actif"]) is False and json.loads(kv["video:actif"]) is False
    assert json.loads(kv["pause"]) is True and json.loads(kv["mt5:pause"]) is True
    (tmp_path / ".env").write_text("OR_MT5_PORT=18777\nOR_VIDEO_LOGIN=7\nOR_VIDEO_PORT=18778\n")
    reponses = {18777: [{"magic": 770050}], 18778: []}

    class Sock:
        def __init__(self, port):
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def sendall(self, b):
            pass

        def recv(self, n):
            return json.dumps({"ok": True, "r": reponses[self.port]}).encode() + b"\n"
    monkeypatch.setattr(deployer.socket, "create_connection", lambda adresse, **k: Sock(adresse[1]))
    with pytest.raises(RuntimeError, match="multi-marchés"):
        deployer.verifier_retour(tmp_path)
    reponses.update({18777: [], 18778: [{"magic": 770077}]})
    with pytest.raises(RuntimeError, match="panier vidéo"):
        deployer.verifier_retour(tmp_path)
    reponses[18778] = []
    deployer.verifier_retour(tmp_path)
    assert "armee-or-mt5-video.service" not in deployer.SERVICES                          # jamais exigé pour valider
    with pytest.raises(RuntimeError):
        deployer.service("stop", "equipe-bots.service")
    monkeypatch.setattr(deployer, "appeler", lambda args, **k: args)
    assert deployer.service("stop", "armee-or-mt5-video.service") == ["systemctl", "stop", "armee-or-mt5-video.service"]
    import os
    assert deployer.pont_multi_instance(__import__("pathlib").Path(os.path.dirname(os.path.dirname(__file__))))
    (tmp_path / "armee_or").mkdir()
    (tmp_path / "armee_or/pont_mt5.py").write_text("def main(): pass\n")                 # code R4 : pas d'instance
    assert not deployer.pont_multi_instance(tmp_path)

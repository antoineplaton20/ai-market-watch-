"""v14 : scan de toutes les paires + mode EXPLORATION (démo uniquement) et son apprentissage — sans réseau."""
import json
import time

import pytest

import auditeur
import config
import disjoncteur as D
import equipe as E
import exploration as X
import gardien as G
import main
import paliers
import strategie as S
from fausse_binance import FausseBinance


@pytest.fixture
def messages(monkeypatch):
    recus = []
    for module in (main, G, D, paliers):
        monkeypatch.setattr(module, "alerte", lambda m, important=True: recus.append(m))
    import alertes
    monkeypatch.setattr(alertes, "alerte", lambda m, important=True: recus.append(m))
    return recus


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(config, "EXPLORATION_AUTORISEE", True)
    monkeypatch.setattr(config, "REEL", False)


def _sans_reseau(monkeypatch, ia_muette=True):
    import donnees
    for nom, valeur in {"peur_avidite": lambda: 55, "fundings": lambda: {"SOLUSDT": 0.0001, "ETHUSDT": 0.001},
                        "open_interest": lambda s: [100, 101, 104], "actualites": lambda: [],
                        "tendances": lambda: set(), "annuaire": lambda: {}, "commits_4_semaines": lambda b: None,
                        "stablecoins_7j": lambda: 0.8, "macro": lambda: (True, False),
                        "positionnement": lambda s: (1.4, 1.9), "marches_mondiaux": lambda: (True, False, 17.0),
                        "attention": lambda: 1.1}.items():
        monkeypatch.setattr(donnees, nom, valeur)
    if ia_muette:                                    # clé IA configurée mais IA muette : le champion strict s'abstient
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "cle-test")
        monkeypatch.setattr(main.E, "contradicteur", lambda *a: (None, "IA indisponible"))


def _champ(**vetos):
    g = S.genome_defaut()
    g.update({f"veto_{v}": False for v in S.VETOS})
    g.update({f"veto_{k}": v for k, v in vetos.items()})
    g["seuil_vote"] = 0.70
    return g


def _res(score=0.8, vetos=(), mtf=4, espece=True, F=None):
    checks = dict(zip(("4h", "1h", "15m", "5m"), [True] * mtf + [False] * (4 - mtf)))
    return {"vetos": list(vetos), "decisions": {"champion": (False, score)}, "mtf_checks": checks,
            "espece_ok": espece, "F": {"hausse_24h": 2.0, **(F or {})}}


# ------------------------------ verrou démo ------------------------------
def test_exploration_impossible_en_argent_reel(monkeypatch):
    etat = G.charger_etat()
    etat["exploration_niveau"] = 3
    monkeypatch.setattr(config, "EXPLORATION_AUTORISEE", False)
    assert X.niveau(etat) == 0 and "DÉMO" in X.regler(etat, 3) and etat["exploration_niveau"] == 0
    monkeypatch.setattr(config, "EXPLORATION_AUTORISEE", True)
    monkeypatch.setattr(config, "REEL", True)                   # double verrou
    etat["exploration_niveau"] = 3
    assert X.niveau(etat) == 0


def test_reglage_des_niveaux(demo):
    etat = G.charger_etat()
    assert "audacieux" in X.regler(etat, 3) and X.niveau(etat) == 3
    assert "Écris" in X.regler(etat, 7) and X.niveau(etat) == 3
    assert "arrêtés" in X.regler(etat, 0) and X.niveau(etat) == 0


# ------------------------------ règles de décision ------------------------------
def test_veille_bloque_toujours_meme_en_agressif():
    assert not X.evaluer(_res(vetos=["VEILLE"]), _champ(), 3)[0]


def test_vetos_durs_respectes_puis_ignores_au_niveau_3():
    r = _res(vetos=["BALEINES_VETO"])
    assert not X.evaluer(r, _champ(), 2)[0]
    ok, risques = X.evaluer(r, _champ(), 3)
    assert ok and "BALEINES_VETO" in risques


def test_seuls_les_vetos_actifs_du_genome_comptent_comme_risque():
    r = _res(vetos=["ANTI_HYPE"], F={"veto_ANTI_HYPE": True, "veto_CALENDRIER": True})
    ok, risques = X.evaluer(r, _champ(ANTI_HYPE=True), 2)
    assert ok and "ANTI_HYPE" in risques and "CALENDRIER" not in risques      # le champion n'utilise pas CALENDRIER
    ok, risques = X.evaluer(r, _champ(ANTI_HYPE=True, CALENDRIER=True), 2)
    assert "CALENDRIER" in risques


def test_vote_unites_et_espece_selon_le_niveau():
    champ = _champ()
    assert not X.evaluer(_res(score=0.50), champ, 2)[0]                  # sous seuil − 0,15
    ok, risques = X.evaluer(_res(score=0.60), champ, 2)
    assert ok and "VOTE_FAIBLE" in risques
    assert not X.evaluer(_res(mtf=1), champ, 2)[0] and X.evaluer(_res(mtf=2), champ, 2)[0]
    assert "MTF_0/4" in X.evaluer(_res(mtf=0), champ, 3)[1]
    assert not X.evaluer(_res(espece=False), champ, 1)[0]                # prudent : espèce du champion exigée
    assert "HORS_ESPECE" in X.evaluer(_res(espece=False), champ, 2)[1]


def test_couts_bloquent_le_prudent_et_sont_notes_sinon():
    opp = type("O", (), {"allowed": False, "net_potential_pct": -0.3})()
    assert not X.evaluer(_res(mtf=3), _champ(), 1, opportunite=lambda: opp)[0]
    ok, risques = X.evaluer(_res(), _champ(), 2, opportunite=lambda: opp)
    assert ok and "COUTS" in risques


def test_pump_refuse_sauf_au_niveau_3():
    r = _res(F={"hausse_24h": 60.0})
    assert not X.evaluer(r, _champ(), 2)[0]
    assert "PUMP" in X.evaluer(r, _champ(), 3)[1]


def test_garantie_d_activite():
    etat = {"dernier_achat_ts": time.time() - 5 * 3600}
    assert X.garantie_due(etat, 2) and not X.garantie_due(etat, 1)
    faible = _res(score=0.50, mtf=0, espece=False)
    assert not X.evaluer(faible, _champ(), 2)[0]
    ok, risques = X.evaluer(faible, _champ(), 2, garantie=True)
    assert ok and "GARANTIE" in risques
    assert not X.evaluer(_res(score=0.30), _champ(), 2, garantie=True)[0]


def test_limites_propres_a_l_exploration():
    etat = G.charger_etat()
    assert X.peut_explorer(etat, 2, 100, 0.0)[0]
    etat["disjoncteur"] = {"raison": "test"}                            # le disjoncteur STRICT ne bloque pas l'exploration
    assert X.peut_explorer(etat, 2, 100, 0.0)[0]
    assert not X.peut_explorer(etat, 2, 100, -11.0)[0]                  # budget de perte du jour (10 %)
    etat["positions"] = {"A/USDT": {"mode": "exploration"}, "B/USDT": {"mode": "exploration"}}
    assert "position" in X.peut_explorer(etat, 2, 100, 0.0)[1]
    etat["positions"] = {}
    for _ in range(8):
        X.noter_achat(etat)
    assert "achats" in X.peut_explorer(etat, 2, 100, 0.0)[1]
    etat["arret_manuel"] = True
    assert "arrêt manuel" in X.peut_explorer(etat, 3, 100, 0.0)[1]


# ------------------------------ cycle complet ------------------------------
def test_le_champion_s_abstient_l_exploration_achete(monkeypatch, messages, demo):
    _sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    etat["exploration_niveau"] = 2
    main.cycle_achat(ex, etat, 1000, 1.0)
    explo = {s: p for s, p in etat["positions"].items() if p["mode"] == "exploration"}
    assert explo and all(p["mode"] == "exploration" for p in etat["positions"].values())
    assert len(explo) <= X.NIVEAUX[2]["max_positions"]
    assert all("IA_INDISPONIBLE" in p["risques"] for p in explo.values())
    assert any("ACHAT D'ESSAI" in m and "Pourquoi c'est un essai" in m and "l'IA relectrice n'a pas répondu" in m for m in messages)
    assert X.achats_du_jour(etat) == len(explo)


def test_exploration_desactivee_aucun_achat(monkeypatch, messages, demo):
    _sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    etat["exploration_niveau"] = 0
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert not etat["positions"]


def test_exploration_continue_quand_le_disjoncteur_strict_est_declenche(monkeypatch, messages, demo):
    _sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    etat["exploration_niveau"] = 2
    etat["disjoncteur"] = {"raison": "test", "date": "2026-09-25T10:00"}
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert etat["positions"] and all(p["mode"] == "exploration" for p in etat["positions"].values())


def test_taille_reduite_pour_l_exploration(monkeypatch, messages, demo):
    _sans_reseau(monkeypatch)
    vus = []
    original = main.calculer_ordre
    monkeypatch.setattr(main, "calculer_ordre", lambda ex, s, d, c, m=1.0, st=None: vus.append(m) or original(ex, s, d, c, m, st))
    ex, etat = FausseBinance(), G.charger_etat()
    etat["exploration_niveau"] = 2
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert vus and all(m == pytest.approx(X.RISQUE_PAR_TRADE_PCT / config.RISQUE_PAR_TRADE_PCT) for m in vus)


# ------------------------------ scan de toutes les paires ------------------------------
def test_toutes_les_paires_sont_scannees(monkeypatch):
    paires = tuple(f"C{i}" for i in range(200)) + ("BTC",)
    ex = FausseBinance(paires=paires)
    monkeypatch.setattr(config, "SCOUT_MAX", 0)
    assert len(E.scout(ex)) == 201
    monkeypatch.setattr(config, "SCOUT_MAX", 150)
    assert len(E.scout(ex)) == 150


def test_niveau_3_elargit_la_liquidite_pas_le_champion(monkeypatch):
    monkeypatch.setattr(config, "VOLUME_24H_MIN", 20_000_000)          # la fausse Binance échange 10 M
    ex = FausseBinance()
    c = {"symbole": "SOL/USDT", "ticker": ex.fetch_tickers()["SOL/USDT"]}
    assert E.filtre(ex, c, 2)[2] is None                                 # trop peu liquide, même en exploration 2
    garde, raisons, d = E.filtre(ex, c, 3)
    assert not garde and d["explorable"] and "volume" in raisons[0]      # explorable au niveau 3, jamais strict


def test_scan_trop_long_interrompu_puis_repris(monkeypatch, messages):
    _sans_reseau(monkeypatch, ia_muette=False)
    vus = []
    original = E.filtre
    monkeypatch.setattr(main.E, "filtre", lambda ex, c, n=0: vus.append(c["symbole"]) or original(ex, c, n))
    ex = FausseBinance(paires=("BTC", "SOL", "ETH", "ADA", "XRP"))
    ordre = [c["symbole"] for c in E.scout(ex)]
    etat = G.charger_etat()
    monkeypatch.setattr(config, "SCAN_DUREE_MAX_FRAC", 0.0)             # aucun temps : interrompu d'emblée
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert vus == [] and etat["scan_reprise"] == 0
    monkeypatch.setattr(config, "SCAN_DUREE_MAX_FRAC", 0.8)
    etat["scan_reprise"] = 2                                             # un scan précédent s'était arrêté à la 3e paire
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert vus[0] == ordre[2] and len(vus) == 5 and etat["scan_reprise"] == 0


def test_positions_surveillees_pendant_un_long_scan(monkeypatch, messages):
    _sans_reseau(monkeypatch, ia_muette=False)
    monkeypatch.setattr(config, "INTERVALLE_BOUCLE_S", 0)
    appels = []
    monkeypatch.setattr(main, "surveiller", lambda ex, etat: appels.append(1))
    main.cycle_achat(FausseBinance(), G.charger_etat(), 1000, 1.0)
    assert len(appels) >= 3


# ------------------------------ apprentissage et protections ------------------------------
def _trade(pnl, mode="strict", risques=()):
    p = {"entree": 100.0, "quantite": 1.0, "stop_initial": 99.0, "ouvert": time.time(), "votes": {},
         "mode": mode, "risques": list(risques)}
    auditeur.enregistrer("SOL/USDT", p, 100.0 + pnl, "test")


def test_trades_marques_et_comptes_separes():
    _trade(+1)
    _trade(-1, "exploration", ["ANTI_HYPE"])
    assert len(auditeur.trades_depuis(0)) == 2
    assert len(auditeur.trades_depuis(0, "strict")) == 1 and len(auditeur.trades_depuis(0, "exploration")) == 1
    assert auditeur.pnl_depuis(0, "exploration") < 0 < auditeur.pnl_depuis(0, "strict")


def test_pertes_d_exploration_ne_declenchent_ni_pause_ni_disjoncteur(messages):
    etat = G.charger_etat()
    for _ in range(10):
        _trade(-1, "exploration", ["VOTE_FAIBLE"])
    D.verifier(etat)
    assert not etat.get("disjoncteur") and time.time() >= etat.get("pause_jusqua", 0)


def test_paliers_ignorent_les_gains_d_exploration(monkeypatch, messages):
    etat = G.charger_etat()
    etat["palier_depuis"] = time.time() - 30 * 86400
    for _ in range(40):
        _trade(+2, "exploration")
    assert not paliers.proposer(etat)


def test_les_risques_pris_nourrissent_la_note_des_vetos(monkeypatch):
    monkeypatch.setattr(config, "ECHANTILLON_MIN", 5)
    for _ in range(12):
        _trade(+1)                                                       # sans enfreindre le veto : gagnant
    for _ in range(6):
        _trade(-1, "exploration", ["ANTI_HYPE"])                         # malgré le veto : perdant
    note, n = auditeur.notes_live()["ANTI_HYPE"]
    assert n == 6 and note > 8                                           # le veto avait raison : il est bien noté


def test_bilan_exploration_par_risque():
    _trade(+1, "exploration", ["MTF_2/4"])
    _trade(-1, "exploration", ["ANTI_HYPE", "MTF_2/4"])
    texte = auditeur.bilan_exploration()
    assert "2 essais terminés" in texte and "seulement 2 horizons de temps sur 4 à la hausse : 2 fois" in texte \
        and "emballement soudain (volume anormal) : 1 fois" in texte and "MTF_" not in texte


def test_coupe_circuit_de_l_exploration(messages, demo):
    etat = G.charger_etat()
    etat["exploration_niveau"], etat["exploration_depuis"] = 2, 0
    for _ in range(5):
        _trade(-10, "exploration")
    X.verifier_coupe_circuit(etat, 100)
    assert etat.get("exploration_coupee") and not X.peut_explorer(etat, 2, 100, 0.0)[0]
    X.regler(etat, 2)
    assert not etat.get("exploration_coupee")


def test_commande_telegram_exploration(monkeypatch, messages, demo):
    etat = G.charger_etat()
    monkeypatch.setattr(main, "commandes", lambda: ["/exploration 3", "/exploration"])
    main.traiter_commandes(None, etat)
    assert X.niveau(etat) == 3 and any("audacieux" in m for m in messages)
    assert any("Essais : niveau 3" in m for m in messages)

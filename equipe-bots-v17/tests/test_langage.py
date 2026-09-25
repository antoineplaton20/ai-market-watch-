"""Messages Telegram en langage simple : aucun code technique ne doit apparaître."""
import re
import langage as L
import strategie as S


def test_chaque_veto_et_risque_a_une_phrase_simple():
    codes = set(S.VETOS) | {"BALEINES_VETO", "CORRELATION", "RECHERCHE_VETO", "CONTRADICTEUR", "IA_INDISPONIBLE",
                            "VEILLE", "OPPORTUNITE_VETO", "VOTE_FAIBLE", "HORS_ESPECE", "COUTS", "GARANTIE", "PUMP"}
    for c in codes:
        texte = L.risque(c)
        assert texte in L.RISQUES.values() and not re.search(r"[A-Z]{3,}_|_VETO", texte), c


def test_horizons_de_temps():
    assert L.risque("MTF_3/4") == "seulement 3 horizons de temps sur 4 à la hausse"
    assert L.risque("MTF_1/4") == "seulement 1 horizon de temps sur 4 à la hausse"
    assert "aucun" in L.risque("MTF_0/4")


def test_chaque_bot_a_un_nom_simple():
    for v in S.VOTANTS:
        assert L.bot(v) in L.BOTS.values()


def test_nombres_a_la_francaise():
    assert L.prix(1581.39) == "1 581,39" and L.prix(0.00012346) == "0,0001235"
    assert L.dollars(-0.4) == "−0,40 $" and L.dollars(3.2, True) == "+3,20 $"
    assert L.pct(-0.7) == "−0,7 %" and L.pourcent(0.82) == "82 %"
    assert L.pluriel(1, "achat") == "1 achat" and L.pluriel(2, "signal", "signaux") == "2 signaux"
    assert L.toutes_les_heures(1) == "chaque heure" and L.toutes_les_heures(4) == "toutes les 4 h"

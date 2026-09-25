"""Bot principal et veilles increvables : démarrage sans Binance, tâches annexes isolées, état abîmé."""
import pytest

import main


def test_demarrage_reessaie_tant_que_binance_ne_repond_pas(monkeypatch):
    essais, attentes, messages = [], [], []

    def connecter():
        essais.append(1)
        if len(essais) < 5:
            raise ConnectionError("binance injoignable")
        return "EXCHANGE"
    monkeypatch.setattr(main, "connecter", connecter)
    monkeypatch.setattr(main.time, "sleep", attentes.append)
    monkeypatch.setattr(main, "alerte", lambda m, important=True: messages.append(m))
    monkeypatch.setattr(main.securite, "battement", lambda *a: None)
    assert main.demarrer_connexion() == "EXCHANGE"
    assert len(essais) == 5 and len(attentes) == 4 and max(attentes) <= 300
    assert sum("injoignable" in m for m in messages) == 1 and "joignable" in messages[-1]


def test_une_tache_annexe_en_panne_ne_coupe_pas_le_trading(monkeypatch):
    messages = []
    monkeypatch.setattr(main, "alerte", lambda m, important=True: messages.append(m))
    monkeypatch.setattr(main, "_derniers_signalements", {})

    def panne():
        raise RuntimeError("évolution cassée")
    assert main._etape("évolution", panne) is None
    assert main._etape("évolution", panne) is None                  # répété : pas de nouveau message
    assert len(messages) == 1 and "le trading continue" in messages[0]
    assert main._etape("ok", lambda x: x * 2, 21) == 42


def test_ctrl_c_traverse_les_etapes(monkeypatch):
    def interruption():
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        main._etape("commandes", interruption)


def test_telegram_en_panne_ne_fait_pas_tomber_le_bot(monkeypatch):
    def panne(*a, **k):
        raise RuntimeError("Telegram HS")
    monkeypatch.setattr(main, "alerte", panne)
    main._prevenir("message")                                         # aucune exception


@pytest.mark.parametrize("contenu", ["{abîmé", "[1, 2, 3]", "null", "\x00\x01"])
def test_etat_des_veilles_abime_repart_a_neuf(tmp_path, monkeypatch, contenu):
    import veille_marches
    import veille_tr
    f = tmp_path / "etat.json"
    f.write_text(contenu, encoding="utf-8")
    assert veille_marches.charger_etat(str(f))["notes"] == {}
    monkeypatch.setattr(veille_tr, "FICHIER_ETAT", str(f))
    assert veille_tr.charger_etat()["suivis"] == {}

"""CHIEN DE GARDE : relance après plantage SANS JAMAIS ABANDONNER ; seul un arrêt demandé (Ctrl+C / systemd) l'arrête."""
import pytest
import lanceur


class FauxProcessus:
    def __init__(self, code):
        self.returncode = code

    def poll(self):
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass


def _lancer(monkeypatch, codes):
    """Rejoue les codes de sortie donnés, puis simule un arrêt demandé (Ctrl+C / systemctl stop)."""
    lances, messages, attentes = [], [], []
    suite = iter(codes)

    def popen(*a, **k):
        try:
            code = next(suite)
        except StopIteration:
            raise KeyboardInterrupt
        lances.append(1)
        return FauxProcessus(code)

    monkeypatch.setattr(lanceur.subprocess, "Popen", popen)
    monkeypatch.setattr(lanceur.time, "sleep", attentes.append)
    monkeypatch.setattr(lanceur, "alerte", lambda m, important=True: messages.append(m))
    with pytest.raises(KeyboardInterrupt):
        lanceur.main()
    return len(lances), messages, attentes


def test_relance_apres_plantage(monkeypatch):
    n, messages, _ = _lancer(monkeypatch, [1, 1, 0])
    assert n == 3 and sum("je le relance" in m for m in messages) == 3


def test_attend_si_un_autre_bot_tourne_puis_reessaie(monkeypatch):
    n, messages, attentes = _lancer(monkeypatch, [lanceur.CODE_VERROU, lanceur.CODE_VERROU, 1])
    assert n == 3 and 60 in attentes
    assert not any("je le relance" in m for m in messages[:-1] if "code 3" in m)


def test_n_abandonne_jamais_meme_apres_une_tempete_de_plantages(monkeypatch):
    n, messages, attentes = _lancer(monkeypatch, [1] * 40)
    assert n == 40                                                   # relancé 40 fois, sans abandon
    assert not any("j'arrête" in m for m in messages)
    assert sum("🌪" in m for m in messages) == 1                     # une seule alerte de tempête par heure
    assert max(attentes) <= lanceur.ATTENTE_MAX_S


def test_telegram_en_panne_ne_fait_pas_tomber_le_chien_de_garde(monkeypatch):
    def panne(*a, **k):
        raise RuntimeError("Telegram HS")
    suite = iter([1, 1])

    def popen(*a, **k):
        try:
            return FauxProcessus(next(suite))
        except StopIteration:
            raise KeyboardInterrupt
    monkeypatch.setattr(lanceur.subprocess, "Popen", popen)
    monkeypatch.setattr(lanceur.time, "sleep", lambda s: None)
    monkeypatch.setattr(lanceur, "alerte", panne)
    with pytest.raises(KeyboardInterrupt):                           # fin du scénario, pas l'erreur Telegram
        lanceur.main()


def test_attente_croissante_plafonnee():
    assert [lanceur.attente_relance(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 80]
    assert lanceur.attente_relance(50) == lanceur.ATTENTE_MAX_S

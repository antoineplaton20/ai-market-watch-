"""CHIEN DE GARDE : relance après plantage, s'arrête sur arrêt normal ou en cas de boucle de plantages."""
import lanceur


class FauxProcessus:
    def __init__(self, code):
        self.returncode = code

    def poll(self):
        return self.returncode

    def kill(self):
        pass

    def wait(self):
        pass


def _lancer(monkeypatch, codes):
    lances, messages = [], []
    suite = iter(codes)
    monkeypatch.setattr(lanceur.subprocess, "Popen", lambda *a, **k: lances.append(1) or FauxProcessus(next(suite)))
    monkeypatch.setattr(lanceur.time, "sleep", lambda s: None)
    monkeypatch.setattr(lanceur, "alerte", messages.append)
    lanceur.main()
    return len(lances), messages


def test_relance_apres_plantage_puis_arret_normal(monkeypatch):
    n, messages = _lancer(monkeypatch, [1, 1, 0])
    assert n == 3 and sum("je le relance" in m for m in messages) == 2


def test_arret_si_un_autre_bot_tourne(monkeypatch):
    n, _ = _lancer(monkeypatch, [lanceur.CODE_VERROU])
    assert n == 1


def test_arret_apres_trop_de_plantages(monkeypatch):
    n, messages = _lancer(monkeypatch, [1] * 20)
    assert n == lanceur.config.PLANTAGES_MAX_H + 1 and "j'arrête de relancer le bot" in messages[-1]

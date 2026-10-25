"""Sauvegardes de nuit, entretien et restauration : sans réseau."""
import gzip
import sqlite3
import time

from armee_or import apprentissage as A, base, config, donnees, sauvegarde as SV, telegram


def _remplir():
    A.enregistrer("veille:acheteurs_pct", [(1_700_000_000 + i, float(i)) for i in range(50)])
    base.ecrire("mt5:permis", {"1h": {"ok": False}})
    base.ecrire("telegram_decalage", 111)
    donnees.inserer("XAUUSDT", "1h", [[1_700_000_000_000 + i * 3_600_000, 1, 1, 1, 1, 1] for i in range(30)])
    with base.connexion() as c:
        c.executemany("INSERT INTO rapports(ts, bot, ok, duree, message) VALUES(?,?,?,?,?)",
                      [(time.time() - 30 * 86400, "vieux", 1, 0.1, "x")] * 5 + [(time.time(), "récent", 1, 0.1, "y")])


def _compter(chemin_gz, table):
    brut = str(chemin_gz)[:-3]
    with gzip.open(chemin_gz) as g, open(brut, "wb") as f:
        f.write(g.read())
    c = sqlite3.connect(brut)
    try:
        if not c.execute("SELECT name FROM sqlite_master WHERE name=?", (table,)).fetchone():
            return None
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


def test_sauvegarde_complete_essentielle_et_entretien():
    _remplir()
    info = SV.sauvegarder(envoyer=False)
    assert info["rapports_purges"] == 5
    assert _compter(info["complete"], "bougies") == 30 and _compter(info["complete"], "rapports") == 1
    assert _compter(info["essentielle"], "bougies") is None and _compter(info["essentielle"], "rapports") is None
    assert _compter(info["essentielle"], "observations") == 50
    assert "Dernière sauvegarde" in SV.texte()


def test_seules_les_3_dernieres_copies_sont_gardees():
    _remplir()
    for j in range(5):
        SV.complete(maintenant=1_800_000_000 + j * 86400)
    assert len(list(SV.dossier().glob("or-complete-*.db.gz"))) == 3


def test_restauration_essentielle_sur_un_serveur_neuf(tmp_path, monkeypatch):
    _remplir()
    ess = SV.essentielle()
    monkeypatch.setattr(config, "BASE", tmp_path / "neuf.db")             # serveur neuf : historique réimporté
    donnees.inserer("XAUUSDT", "1h", [[1_700_000_000_000, 2, 2, 2, 2, 2]])
    base.ecrire("telegram_decalage", 999)
    texte = SV.restaurer(str(ess))
    assert "essentielle restaurée" in texte
    assert len(A.serie("veille:acheteurs_pct")[0]) == 50 and base.lire("mt5:permis") == {"1h": {"ok": False}}
    assert base.lire("telegram_decalage") == 999                         # pas d'anciennes commandes rejouées
    with base.connexion() as c:
        assert c.execute("SELECT COUNT(*) FROM bougies").fetchone()[0] == 1   # bougies du serveur gardées


def test_restauration_complete_depuis_la_copie_locale():
    _remplir()
    SV.complete()
    base.ecrire("mt5:permis", {"1h": {"ok": True}})
    assert "Base entière restaurée" in SV.restaurer()
    assert base.lire("mt5:permis") == {"1h": {"ok": False}}


def test_restauration_par_code_telegram_et_fichier_invalide(tmp_path, monkeypatch):
    _remplir()
    ess = SV.essentielle()
    monkeypatch.setattr(config, "TELEGRAM_JETON", "jeton")

    class Rep:
        def __init__(self, d=None, contenu=b""):
            self.d, self.content = d, contenu

        def json(self):
            return self.d

    class Session:
        def get(self, url, params=None, timeout=None):
            if "getFile" in url:
                ok = params["file_id"] == "BON"
                return Rep({"ok": ok, "result": {"file_path": "documents/f.gz"}, "description": "file not found"})
            return Rep(contenu=ess.read_bytes())
    assert "restaurée" in SV.restaurer("BON", session=Session())
    try:
        SV.restaurer("MAUVAIS", session=Session())
        assert False
    except RuntimeError as ex:
        assert "refuse" in str(ex)
    faux = tmp_path / "faux.db.gz"
    with gzip.open(faux, "wb") as g:
        g.write(b"pas une base")
    try:
        SV.restaurer(str(faux))
        assert False
    except Exception:
        pass


def test_envoi_du_document(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TELEGRAM_JETON", "x")
    monkeypatch.setattr(config, "TELEGRAM_CHAT", "1")
    f = tmp_path / "a.gz"
    f.write_bytes(b"123")

    class S:
        def post(self, url, data=None, files=None, timeout=None):
            assert url.endswith("/sendDocument") and files["document"].read() == b"123"
            return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"ok": True, "result": {"document": {"file_id": "ABC"}}}})()
    assert telegram.envoyer_document(f, "x", session=S()) == "ABC"


def test_bot_de_nuit_une_fois_vers_3_h(monkeypatch):
    import calendar
    _remplir()
    monkeypatch.setattr(SV.telegram, "envoyer_document", lambda *a, **k: "CODE")
    monkeypatch.setattr(SV.telegram, "envoyer", lambda *a, **k: True)
    trois_h = calendar.timegm((2026, 10, 14, 1, 10, 0))                  # 3 h 10 à Paris
    assert "prochaine" in SV.bot_nuit(trois_h - 3 * 3600)
    assert "sauvegarde faite" in SV.bot_nuit(trois_h)
    assert "déjà faite" in SV.bot_nuit(trois_h + 600)
    assert base.lire("sauvegarde:derniere")["file_id"] == "CODE"

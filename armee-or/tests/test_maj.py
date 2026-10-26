"""R5.2 : tout depuis Termius (or maj) et Telegram (/or_maj), jamais de retour à une version plus ancienne,
contrôle de version tenu par root, installation en pause avec les commandes pour reprendre. Aucun réseau."""
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

import deployer

RACINE = Path(__file__).resolve().parent.parent


def test_versions_comparees_dans_l_ordre():
    v = deployer.version
    assert v("2.5-R4") < v("2.5-R5") < v("2.5-R5.1") < v("2.5-R5.2") < v("2.5-R5.10") < v("2.5-R6") < v("2.6-R1")
    assert v("") == v("n'importe quoi") == (0,) < v("2.5-R4")


def _paquet(dossier, version):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "PAQUET.json").write_text(json.dumps({"version": version}))
    return dossier / "PAQUET.json"


def test_comparer_refuse_plus_ancienne_et_deja_a_jour(tmp_path, capsys):
    cible, etat = tmp_path / "armee-or", tmp_path / "root"
    _paquet(cible, "2.5-R5.1")
    publie = _paquet(tmp_path / "publie", "2.5-R5.2")
    assert deployer.comparer(publie, cible, etat) == 0 and "2.5-R5.1 -> 2.5-R5.2" in capsys.readouterr().out
    _paquet(tmp_path / "publie", "2.5-R5.1")
    assert deployer.comparer(publie, cible, etat) == deployer.DEJA_A_JOUR
    _paquet(tmp_path / "publie", "2.5-R4")
    assert deployer.comparer(publie, cible, etat) == deployer.PLUS_ANCIENNE and "ANCIENNE" in capsys.readouterr().out
    (tmp_path / "publie" / "PAQUET.json").write_text("{}")
    with pytest.raises(RuntimeError, match="illisible"):
        deployer.comparer(publie, cible, etat)


def test_le_compte_bots_ne_peut_pas_rouvrir_une_ancienne_version(tmp_path):
    """La version notée par root compte : baisser PAQUET.json dans le dossier de l'armée ne suffit pas."""
    cible, etat = tmp_path / "armee-or", tmp_path / "root"
    source = tmp_path / "source"
    source.mkdir()
    (source / "deployer.py").write_text("# copie\n")
    deployer.noter_version({"version": "2.5-R5.2"}, etat, source)
    assert (etat / "deployer.py").read_text() == "# copie\n" and oct((etat / "deployer.py").stat().st_mode)[-3:] == "644"
    _paquet(cible, "2.5-R4")                                                     # dossier bots falsifié
    assert deployer.version_installee(cible, etat) == "2.5-R5.2"
    assert deployer.comparer(_paquet(tmp_path / "publie", "2.5-R5.1"), cible, etat) == deployer.PLUS_ANCIENNE


def test_installateur_refuse_un_paquet_plus_ancien_avant_toute_modification(monkeypatch):
    monkeypatch.setattr(deployer, "verifier_installation", lambda *a, **k: {"version": "2.5-R5"})
    monkeypatch.setattr(deployer, "controles_systeme", lambda: None)
    monkeypatch.setattr(deployer, "version_installee", lambda *a, **k: "2.5-R5.2")
    monkeypatch.setattr(deployer, "tester", lambda *a, **k: pytest.fail("aucun test ni modification attendus"))
    with pytest.raises(RuntimeError, match="plus ancien"):
        deployer.installer()


def test_reprise_proposee_pour_ce_qui_etait_actif(tmp_path):
    (tmp_path / "runtime").mkdir(exist_ok=True)
    with sqlite3.connect(tmp_path / "runtime/or.db") as c:
        c.execute("CREATE TABLE kv(cle TEXT PRIMARY KEY, valeur TEXT, maj REAL)")
        c.execute("INSERT INTO kv VALUES ('marches:actif','true',0),('video:actif','false',0)")
    assert deployer.equipes_actives(tmp_path) == [("multi-marchés", "or marches on", "/or_marches_on")]
    (tmp_path / "runtime/demo-r4.json").write_text(json.dumps({"actif": True}))
    assert [t for _, t, _ in deployer.equipes_actives(tmp_path)] == ["or marches on", "or demo on"]
    assert deployer.equipes_actives(tmp_path / "absent") == []


def test_services_or_maj_poses_par_root(tmp_path, monkeypatch):
    monkeypatch.setattr(deployer, "UNITE_MAJ", tmp_path / "armee-or-maj.service")
    monkeypatch.setattr(deployer, "CHEMIN_MAJ", tmp_path / "armee-or-maj.path")
    appels = []
    monkeypatch.setattr(deployer, "appeler", lambda args, **k: appels.append(args))
    deployer.poser_maj(Path("/home/bots/armee-or"))
    unite = (tmp_path / "armee-or-maj.service").read_text()
    assert "ExecStart=/usr/local/bin/or maj-auto" in unite and "rm -f /home/bots/armee-or/runtime/demande_maj" in unite
    assert "PathExists=/home/bots/armee-or/runtime/demande_maj" in (tmp_path / "armee-or-maj.path").read_text()
    assert appels == [["systemctl", "daemon-reload"], ["systemctl", "enable", "armee-or-maj.path"],
                      ["systemctl", "start", "armee-or-maj.path"]]


def test_or_maj_controle_par_root_puis_installe(tmp_path):
    texte = (RACINE / "or").read_text(encoding="utf-8")
    maj = texte[texte.index("\n  maj)"):texte.index("\n  maj-auto)")]
    assert "CONTROLE=/var/lib/armee-or/deployer.py" in maj and '"$DOSSIER/deployer.py"' not in maj   # rien du compte bots
    assert maj.index("comparer") < maj.index("installer") and "github.com/antoineplaton20/ai-market-watch-" in maj
    auto = texte[texte.index("\n  maj-auto)"):texte.index("\n  mettre-a-jour)")]
    assert "/var/log/armee-or-maj.log" in auto and "3) RES=" in auto and "4) RES=" in auto
    assert subprocess.run(["bash", "-n", str(RACINE / "or")]).returncode == 0


def test_le_paquet_publie_est_a_jour():
    """Ce qui part sur GitHub est ce que « or maj » installe : manifeste, empreintes et version doivent concorder."""
    m = deployer.verifier_paquet(RACINE)
    from armee_or import __version__
    from armee_or.surveillance import diagnostic
    assert m["version"] == deployer.VERSION == __version__
    assert diagnostic()["version"] == __version__
    suivis = {str(p.relative_to(RACINE)) for d in ("armee_or", "tests", "etudes") for p in (RACINE / d).rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")}
    assert suivis <= set(m["fichiers"]), sorted(suivis - set(m["fichiers"]))
    assert deployer.version("2.5-R5.1") < deployer.version(m["version"])            # chaque publication monte la version


def test_installer_arrete_vraiment_la_demo_r4(tmp_path):
    """Avant R5.3, la démo R4 n'était retenue que par les pauses : /or_marches_on (qui lève la pause MT5) la
    relançait. Toute installation l'arrête maintenant comme /or_demo_off, sans effacer ses compteurs ni ses incidents."""
    (tmp_path / "runtime").mkdir(exist_ok=True)
    with sqlite3.connect(tmp_path / "runtime/or.db") as c:
        c.execute("CREATE TABLE kv(cle TEXT PRIMARY KEY, valeur TEXT, maj REAL)")
    etat = {"version": "R4-demo-ema20-50-v1", "actif": True, "pic": 3012.5, "entrees_jour": 2, "incident": None}
    demo = tmp_path / "runtime/demo-r4.json"
    demo.write_text(json.dumps(etat))
    demo.chmod(0o640)
    avant = demo.stat()
    assert deployer.equipes_actives(tmp_path)[-1][1] == "or demo on"                  # proposé pour reprendre
    deployer.pause(tmp_path)
    apres = json.loads(demo.read_text())
    assert apres == {**etat, "actif": False}                                          # compteurs gardés
    assert (demo.stat().st_uid, demo.stat().st_gid, demo.stat().st_mode) == (avant.st_uid, avant.st_gid, avant.st_mode)
    assert not deployer.arreter_demo(tmp_path) and not (tmp_path / "runtime/demo-r4.json.arret").exists()
    with sqlite3.connect(tmp_path / "runtime/or.db") as c:
        kv = dict(c.execute("SELECT cle, valeur FROM kv").fetchall())
    assert kv["mt5:pause"] == "true" and kv["marches:actif"] == "false"
    assert not deployer.arreter_demo(tmp_path / "absent")


def test_la_telecommande_est_remplacee_d_un_coup(tmp_path):
    """R8.4 : le bash qui exécute encore l'ancien « or maj » garde l'ancien fichier ; une copie par-dessus lui faisait
    lire la suite au mauvais endroit du nouveau (« line 117: syntax error » à l'installation de R8.3)."""
    cible, source = tmp_path / "or", tmp_path / "nouveau"
    cible.write_text("ANCIEN " * 50)
    source.write_text("NOUVEAU " * 80)
    with open(cible) as lu_par_bash:
        lu_par_bash.read(14)
        deployer.poser_telecommande(source, cible)
        assert lu_par_bash.read(7) == "ANCIEN "                                   # la suite reste l'ancien texte
    assert cible.read_text() == source.read_text() and cible.stat().st_mode & 0o777 == 0o755
    assert not list(tmp_path.glob(".*nouveau"))
    lien = tmp_path / "lien"
    lien.symlink_to(cible)
    with pytest.raises(RuntimeError):
        deployer.poser_telecommande(source, lien)


def test_or_mt5_compte_change_seulement_les_identifiants(tmp_path):
    """R8.4 : « or mt5 compte » (fichier de root) : saisie masquée, les trois lignes d'identifiants seules changent,
    copie de l'ancien réglage, pont redémarré, compte DÉMO confirmé, relié seulement sur « OUI »."""
    texte = (RACINE / "or").read_text(encoding="utf-8")
    fonction = texte[texte.index("changer_compte() {"):texte.index("\n}\n", texte.index("changer_compte() {")) + 3]
    assert "read -r -s -p \"Login" in fonction and "read -r -s -p \"Mot de passe" in fonction
    assert '"$DOSSIER/' not in fonction.split("python_or")[0].replace('"$DOSSIER/.env', "").replace(
        '"$DOSSIER/runtime/env-avant', "").replace('"$DOSSIER/.env.XXXXXX', "")              # rien n'est exécuté du dossier bots
    dossier = tmp_path / "armee-or"
    (dossier / "runtime").mkdir(parents=True)
    (dossier / ".env").write_text("OR_MT5_ACTIF=1\nOR_MT5_LOGIN=111022\nOR_MT5_MOT_DE_PASSE=ancien\n"
                                  "OR_MT5_SERVEUR=MetaQuotes-Demo\nOR_MT5_TERMINAL=C:\\\\MT5\\\\terminal64.exe\nOR_MT5_PORT=18777\n")
    journal = tmp_path / "journal.txt"
    harnais = f"""
set -euo pipefail
DOSSIER={dossier}
systemctl() {{ echo "systemctl $*" >> {journal}; }}
sleep() {{ :; }}
chown() {{ :; }}
install() {{ cp "${{@: -2:1}}" "${{@: -1}}"; }}
runuser() {{ echo "telegram" >> {journal}; }}
python_or() {{ echo "python_or $*" >> {journal}; if [ "$*" = "compte" ]; then echo "connecté · compte …777 · serveur Test-Demo · DÉMO · solde 1000 EUR"; else echo "relié"; fi; }}
{fonction}
changer_compte
"""
    r = subprocess.run(["bash", "-c", harnais], input="5550777\nsecret de test\nTest-Demo\nOUI\n", text=True,
                       capture_output=True)
    assert r.returncode == 0, r.stderr
    env = (dossier / ".env").read_text()
    assert "OR_MT5_LOGIN=5550777" in env and "OR_MT5_MOT_DE_PASSE=secret de test" in env and "OR_MT5_SERVEUR=Test-Demo" in env
    assert "111022" not in env and "ancien" not in env and "OR_MT5_TERMINAL=" in env and "OR_MT5_PORT=18777" in env
    assert "111022" in (dossier / "runtime" / "env-avant-changement-de-compte").read_text()
    assert "secret de test" not in r.stdout and "5550777" not in r.stdout                  # jamais affichés en entier
    j = journal.read_text()
    assert "systemctl restart armee-or-mt5" in j and "python_or compte relier" in j
    (dossier / ".env").write_text(env)
    r = subprocess.run(["bash", "-c", harnais], input="5550777\nsecret\nTest-Demo\nnon\n", text=True, capture_output=True)
    assert r.returncode == 1 and "Rien n'est relié" in r.stdout                          # sans « OUI » : rien n'est relié

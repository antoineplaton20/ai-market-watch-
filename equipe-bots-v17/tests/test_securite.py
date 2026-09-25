"""SÉCURITÉ : une seule instance, signe de vie, sauvegardes."""
import os
import zipfile
import securite


def test_deux_bots_ne_peuvent_pas_tourner_ensemble():
    assert securite.prendre_verrou()
    premier = securite._verrou
    assert not securite.prendre_verrou()
    premier.close()                             # le premier s'arrête : la place est libre
    assert securite.prendre_verrou()
    securite._verrou.close()


def test_signe_de_vie():
    securite.battement("test")
    assert securite.age_battement() < 5


def test_sauvegarde_une_fois_par_jour():
    for f in ("champion.json", "journal.db"):
        open(f, "w").write("x")
    etat = {}
    chemin = securite.sauvegarde_quotidienne(etat)
    assert chemin and set(zipfile.ZipFile(chemin).namelist()) >= {"champion.json", "journal.db"}
    assert securite.sauvegarde_quotidienne(etat) is None


def test_seules_les_30_dernieres_sauvegardes_restent():
    os.makedirs("sauvegardes")
    for i in range(35):
        open(f"sauvegardes/sauvegarde_2020-01-{i:02d}.zip", "w").close()
    securite.sauvegarde_quotidienne({})
    assert len(os.listdir("sauvegardes")) == 30

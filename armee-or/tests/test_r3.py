import hashlib
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace as NS
import pytest
from test_mt5 import faux, _chef, _prono
from armee_or import base, commandes, registre, telegram, qualification, pont_mt5, executant, mt5, risque
import deployer


def test_release_bloque_meme_permis_ancien_et_mode_agressif(faux,monkeypatch):
    monkeypatch.setattr(qualification,'OUVERTURES_VALIDEES',False)
    monkeypatch.setattr(pont_mt5,'OUVERTURES_VALIDEES',False)
    base.ecrire('mt5:permis_exige',False);base.ecrire('mt5:agressif',True)
    _prono('1d',1)
    assert 'bloquées' in executant.bot_mt5(_chef())
    with pytest.raises(mt5.ErreurMT5):mt5.appel('ouvrir',sens=1,volume=.01,sl=3900)
    with pytest.raises(mt5.ErreurMT5):executant._ouvrir('1d',1,mt5.appel('etat')['compte'],set())
    assert not faux.envois


def test_fermeture_partielle_et_reprise_sur_date_courtier(faux,monkeypatch):
    _prono('4h',1);executant.bot_mt5(_chef())
    ticket=faux.positions[0].ticket
    original=faux.order_send
    def partiel(d):
        faux.positions[0].volume/=2
        return NS(retcode=10010,comment='partial',order=ticket,deal=ticket,price=4000,volume=faux.positions[0].volume)
    monkeypatch.setattr(faux,'order_send',partiel)
    with pytest.raises(mt5.ErreurMT5,match='non confirmée'):executant.fermer_tout()
    assert str(ticket) in base.lire('mt5:suivi')
    monkeypatch.setattr(faux,'order_send',original)
    faux.positions[0].time=int(time.time())-1000
    base.ecrire('mt5:suivi',{})
    executant.bot_mt5(_chef(pause=True))
    assert base.lire('mt5:suivi')[str(ticket)]['ouverture']==faux.positions[0].time


def test_erreur_positions_ne_vaut_pas_absence(faux,monkeypatch):
    monkeypatch.setattr(faux,'positions_get',lambda **kw:None)
    with pytest.raises(mt5.ErreurMT5):mt5.appel('positions')


@pytest.mark.parametrize('equite',[float('nan'),float('inf'),-1])
def test_equite_invalide_ne_valide_pas_risque(equite):
    with pytest.raises(ValueError):risque.controler({'login':1,'equity':equite})


def test_file_dedoublonne_et_ne_rejoue_pas_apres_panne():
    commandes.ajouter('/or_mt5_fermer','telegram:1')
    commandes.ajouter('/or_mt5_fermer','telegram:1')
    demandes=commandes.prendre()
    assert demandes==['/or_mt5_fermer'] and commandes.prendre()==[]
    assert commandes.reprise_apres_panne()==1
    assert commandes.prendre()==[] and commandes.etat()['incertaine']==1
    assert base.lire('mt5:pause') is True


def test_file_expire_et_ack():
    commandes.ajouter('/or_mt5_fermer',date=time.time()-121)
    commandes.ajouter('/or_pause')
    demandes=commandes.prendre();assert demandes==['/or_pause']
    commandes.terminer(demandes[0]);assert commandes.etat()=={'expiree':1,'terminee':1}


def test_registre_declare_avant_resultat_et_interdit_modification():
    identifiant=registre.declarer('H05','v0','sha256:faux','periode-test','regle fixee','commit-test')
    registre.conclure(identifiant,{'net':-1},'rejete')
    r=registre.resume();assert r['hypotheses']==len(registre.catalogue())==43 and r['essais_declares']==1 and r['permis'] is False
    with base.connexion() as c:
        with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM essais')
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE resultats_essais SET verdict='admis'")
    with pytest.raises(ValueError):registre.conclure(999,{},'rejete')
    with pytest.raises(ValueError):registre.conclure(identifiant,{},'admis')


def test_pagination_ne_perd_pas_le_texte_et_ne_coupe_pas_html(monkeypatch):
    from armee_or import config
    monkeypatch.setattr(config,'TELEGRAM_JETON','faux');monkeypatch.setattr(config,'TELEGRAM_CHAT','1')
    texte=('é 🟡 <&>\n'*2000)
    assert ''.join(telegram.decouper(texte))==texte
    messages=[]
    class Rep:
        def raise_for_status(self):pass
        def json(self):return {'ok':True}
    def post(*a,**kw):messages.append(kw['json']['text']);return Rep()
    assert telegram.envoyer(texte,session=NS(post=post),mono=True)
    assert len(messages)>1 and all(len(x.encode('utf-16-le'))//2<4000 for x in messages)
    assert all(x.endswith('</pre>') for x in messages)


def installation_factice(tmp_path):
    src=tmp_path/'paquet';dst=tmp_path/'installation';src.mkdir();dst.mkdir()
    for r in (src,dst):
        (r/'armee_or').mkdir();(r/'armee_or/a.py').write_text('ancien')
    (src/'armee_or/a.py').write_text('nouveau')
    (dst/'.venv/bin').mkdir(parents=True);(dst/'.venv/bin/python').touch()
    (dst/'.env').write_text('OR_MT5_ACTIF=0\n');(dst/'runtime').mkdir()
    with sqlite3.connect(dst/'runtime/or.db') as c:
        c.execute('CREATE TABLE kv(cle TEXT PRIMARY KEY,valeur TEXT,maj REAL)')
        c.execute("INSERT INTO kv VALUES ('preuve','123',0)")
    m={'base':{'armee_or/a.py':deployer.sha(dst/'armee_or/a.py')},
       'fichiers':{'armee_or/a.py':deployer.sha(src/'armee_or/a.py')}}
    (src/'PAQUET.json').write_text(json.dumps(m))
    return src,dst,m


def test_migration_refuse_version_inconnue_avant_ecriture(tmp_path):
    src,dst,m=installation_factice(tmp_path)
    assert deployer.verifier_installation(dst,src)==m
    (dst/'armee_or/a.py').write_text('version inconnue')
    with pytest.raises(RuntimeError,match='version locale différente'):deployer.verifier_installation(dst,src)
    assert (dst/'armee_or/a.py').read_text()=='version inconnue'


def test_paquet_modifie_et_chemin_exterieur_refuses(tmp_path):
    src,dst,m=installation_factice(tmp_path)
    (src/'armee_or/a.py').write_text('corrompu')
    with pytest.raises(RuntimeError,match='modifié'):deployer.verifier_paquet(src)
    with pytest.raises(RuntimeError):deployer.chemin(dst,'../autre-bot.py')
    (dst/'lien').symlink_to(src)
    with pytest.raises(RuntimeError):deployer.chemin(dst,'lien/armee_or/a.py')


def test_sauvegarde_et_retour_code_conservent_transactions_recentes(tmp_path):
    src,dst,m=installation_factice(tmp_path)
    (dst/'PAQUET.json').write_text('{}')
    sauvegarde=deployer.sauvegarder(m,dst,tmp_path/'sauvegardes')
    with sqlite3.connect(sauvegarde/'or.db') as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    (dst/'armee_or/a.py').write_text('nouveau')
    with sqlite3.connect(dst/'runtime/or.db') as c:c.execute("INSERT INTO kv VALUES ('nouvelle_transaction','456',0)")
    deployer.retablir(sauvegarde,dst)
    assert (dst/'armee_or/a.py').read_text()=='ancien'
    with sqlite3.connect(dst/'runtime/or.db') as c:
        assert c.execute("SELECT valeur FROM kv WHERE cle='nouvelle_transaction'").fetchone()[0]=='456'
        assert c.execute("SELECT valeur FROM kv WHERE cle='mt5:pause'").fetchone()[0]=='true'


def test_deployeur_interdit_autres_services():
    with pytest.raises(RuntimeError):deployer.service('stop','bots-autre.service')


def test_archive_erreur_pas_fin_historique(faux,monkeypatch):
    from armee_or import archive_mt5
    monkeypatch.setattr(faux,'copy_rates_range',lambda *a:None)
    with pytest.raises(mt5.ErreurMT5):archive_mt5.archiver(unites=('1d',))
    assert not base.lire('mt5:archive:utc-r3:1d')
    base.ecrire('mt5:decalage',10800)
    assert archive_mt5.decalage_serveur()==0

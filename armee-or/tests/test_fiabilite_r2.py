import time
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_mt5 import faux, _chef, _prono
from armee_or import base, config, executant, mt5, telegram, surveillance, chef


def test_reponse_ordre_perdue_ne_provoque_pas_un_second_ordre(faux, monkeypatch):
    original=mt5.appel
    def perte(op, **kw):
        r=original(op, **kw)
        if op=='ouvrir': raise mt5.ErreurMT5('réponse perdue après exécution')
        return r
    monkeypatch.setattr(mt5,'appel',perte)
    _prono('4h',1)
    with pytest.raises(mt5.ErreurMT5): executant.bot_mt5(_chef())
    assert len(faux.positions)==1 and base.lire('r2:ordre_incertain')
    assert base.lire('mt5:pause') is True
    monkeypatch.setattr(mt5,'appel',original)
    executant.bot_mt5(_chef())
    assert len(faux.positions)==1
    monkeypatch.setattr(telegram,'commandes',lambda:['/or_mt5_reprendre'])
    chef.bot_commandes(_chef())
    assert base.lire('mt5:pause') is True


def test_refus_explicite_ne_laisse_pas_incident(faux,monkeypatch):
    monkeypatch.setattr(faux,'order_send',lambda d:NS(retcode=10019,comment='insufficient',order=0,deal=0,price=0,volume=0))
    _prono('4h',1)
    executant.bot_mt5(_chef())
    assert not faux.positions and not base.lire('r2:ordre_incertain')


def test_changement_compte_bloque_avant_gestion(faux):
    base.ecrire('r2:compte_lie',{'login':999,'server':'autre'})
    with pytest.raises(mt5.ErreurMT5): executant.fermer_tout()
    assert base.lire('r2:compte_change') and not faux.envois


def test_un_seul_chef_et_liberation():
    with surveillance.verrou_chef():
        with pytest.raises(RuntimeError):
            with surveillance.verrou_chef(): pass
    with surveillance.verrou_chef(): pass


@pytest.mark.parametrize('erreur',['ancien','nan','ordre','ohlc'])
def test_bougies_invalides_refusees(faux,monkeypatch,erreur):
    original=faux.copy_rates_from_pos
    def invalide(*a):
        r=original(*a)
        if erreur=='ancien':r['time']-=86400*10
        elif erreur=='nan':r['close'][5]=np.nan
        elif erreur=='ordre':r['time'][5]=r['time'][4]
        else:r['high'][5]=1
        return r
    monkeypatch.setattr(faux,'copy_rates_from_pos',invalide)
    with pytest.raises(mt5.ErreurMT5):executant._atr('4h')
    assert not faux.envois


class Reponse:
    def __init__(self,data,erreur=False):self.data=data;self.erreur=erreur
    def raise_for_status(self):
        if self.erreur:raise RuntimeError('HTTP')
    def json(self):return self.data


def tg(monkeypatch):
    monkeypatch.setattr(config,'TELEGRAM_JETON','faux')
    monkeypatch.setattr(config,'TELEGRAM_CHAT','123')
    monkeypatch.setattr(config,'TELEGRAM_COMMANDES',True)


@pytest.mark.parametrize('data,erreur', [({'ok':False},False),({'ok':True},True),([],False)])
def test_telegram_ne_confirme_pas_un_echec(monkeypatch,data,erreur):
    tg(monkeypatch)
    s=NS(post=lambda *a,**kw:Reponse(data,erreur))
    assert telegram.envoyer('test',session=s) is False
    assert telegram.installer_menu(session=s) is False


@pytest.mark.parametrize('changement',[{'date':0},{'from':{'id':999}},{'chat':{'id':123,'type':'group'}},{'forward_origin':{'type':'user'}}])
def test_commandes_non_autorisees_ou_perimees(monkeypatch,changement):
    tg(monkeypatch)
    msg={'date':time.time(),'from':{'id':123},'chat':{'id':123,'type':'private'},'text':'/or_mt5_reprendre'}
    msg.update(changement)
    s=NS(get=lambda *a,**kw:Reponse({'ok':True,'result':[{'update_id':1,'message':msg}]}))
    assert telegram.commandes(s)==[]


def test_commande_adressee_conserve_argument(monkeypatch):
    tg(monkeypatch)
    msg={'date':time.time(),'from':{'id':123},'chat':{'id':123,'type':'private'},'text':'/or_mt5_profil@MonBot x3'}
    s=NS(get=lambda *a,**kw:Reponse({'ok':True,'result':[{'update_id':1,'message':msg}]}))
    assert telegram.commandes(s)==[]
    from armee_or import commandes
    assert commandes.prendre()==['/or_mt5_profil x3']
    assert telegram.commandes(s)==[]


def test_alerte_echouee_reessayable(monkeypatch):
    horloge=[10000.]
    monkeypatch.setattr(telegram.time,'time',lambda:horloge[0])
    appels=[]
    def envoyer(*a):appels.append(a);return len(appels)>1
    monkeypatch.setattr(telegram,'envoyer',envoyer)
    assert not telegram.alerte_rare('x','test')
    assert not base.lire('alerte:x')
    assert not telegram.alerte_rare('x','test') and len(appels)==1
    horloge[0]+=61
    assert telegram.alerte_rare('x','test') and base.lire('alerte:x')==10061


def test_diagnostic_absence_et_incident():
    assert surveillance.diagnostic()['etat']=='BLOQUE_OU_NON_VERIFIE'
    base.ecrire('r2:ordre_incertain',{'compte':123,'serveur':'secret','equipe':'4h'})
    d=surveillance.diagnostic()
    assert d['incident_ordre']=={'equipe':'4h'}
    assert 'aucun_ordre_incertain' in d['motifs']


@pytest.mark.parametrize('payload',[b'[]\n',b'{"ok":1,"r":[]}\n',b'{"ok":true}\n',b'invalide\n'])
def test_client_refuse_reponses_invalides(monkeypatch,payload):
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def sendall(self,*a):pass
        def recv(self,*a):return payload
    monkeypatch.setattr(mt5.socket,'create_connection',lambda *a,**kw:Socket())
    with pytest.raises(mt5.ErreurMT5):mt5.appel('etat')


def test_diagnostic_telegram(monkeypatch):
    monkeypatch.setattr(telegram,'commandes',lambda:['/or_diagnostic'])
    messages=[]
    monkeypatch.setattr(telegram,'envoyer',lambda x:messages.append(x))
    chef.bot_commandes(_chef())
    assert 'BLOQUE_OU_NON_VERIFIE' in messages[0]

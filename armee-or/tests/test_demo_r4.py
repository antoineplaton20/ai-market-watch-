import datetime as dt
import time
import json
from types import SimpleNamespace as NS
import pytest
from armee_or import demo_regles as R, demo_auto, pont_mt5, base, chef, config
from test_mt5 import FauxMT5, LOGIN

NOW=dt.datetime(2026,10,26,10,0,30,tzinfo=dt.timezone.utc).timestamp()


def barres(pas,sens=1):
    dernier=NOW-NOW%pas
    return [[dernier-(299-i)*pas,4000+sens*(i-299)*.2,4000+sens*(i-299)*.2+.3,
             4000+sens*(i-299)*.2-.3,4000+sens*(i-299)*.2,100] for i in range(300)]


@pytest.fixture
def pont(tmp_path,monkeypatch):
    f=FauxMT5();p=pont_mt5.Pont(f,{'OR_MT5_LOGIN':str(LOGIN)},dossier=str(tmp_path))
    monkeypatch.setattr(time,'time',lambda:NOW)
    original_tick=f.symbol_info_tick
    def tick(s):
        t=original_tick(s);t.bid=f.prix-.01;t.ask=f.prix+.01;return t
    monkeypatch.setattr(f,'symbol_info_tick',tick)
    monkeypatch.setattr(p,'op_bougies',lambda tf='1h',**kw:barres(900 if tf=='15m' else 3600))
    return p,f


def lancer(p):
    return p.op_demo_cycle(autoriser=True,calendrier={'ts':time.time(),'evenements':[]})


def test_signal_symetrique_et_bougie_courante_ignorée():
    for sens in (-1,1):
        m,h=barres(900,sens),barres(3600,sens)
        a=R.signal(m,h,NOW)
        assert a['sens']==sens and a['atr']>0
        m[-1][1:5]=[9000,10000,8000,9999]
        assert R.signal(m,h,NOW)==a


def test_signal_historique_ne_depend_pas_du_futur():
    m,h=barres(900),barres(3600)
    t=NOW-3600
    a=R.signal(m,h,t)
    assert a==R.signal([x for x in m if x[0]<=t],[x for x in h if x[0]<=t],t)
    m[10][0]=m[9][0]
    with pytest.raises(ValueError):R.signal(m,h,NOW)


@pytest.mark.parametrize('sens',[-1,1])
def test_achat_vente_stop_objectif_et_pas_de_doublon(pont,monkeypatch,sens):
    p,f=pont
    monkeypatch.setattr(p,'op_bougies',lambda tf='1h',**kw:barres(900 if tf=='15m' else 3600,sens))
    p.op_demo_mode(actif=True);r=lancer(p)
    assert 'confirmé' in r['message'] and len(f.positions)==1
    d=f.envois[-1];assert d['type']==(0 if sens>0 else 1) and d['magic']==R.MAGIC
    assert (d['price']-d['sl'])*sens>0 and (d['tp']-d['price'])*sens>0
    assert abs(abs(d['tp']-d['price'])-2*abs(d['price']-d['sl']))<.03
    n=len(f.envois);lancer(p);assert len(f.envois)==n
    p2=pont_mt5.Pont(f,p.r,dossier=p.dossier)
    assert 'déjà présent' in lancer(p2)['message'] and len(f.envois)==n


def test_mode_off_et_pause_ne_creent_pas_ordre(pont):
    p,f=pont
    assert not lancer(p)['actif'] and not f.envois
    p.op_demo_mode(actif=True)
    assert 'Pause' in p.op_demo_cycle()['message'];assert not f.envois
    p.op_demo_mode(actif=False);lancer(p);assert not f.envois


def test_pas_de_changement_compte_ni_reel(pont,monkeypatch):
    p,f=pont;f.trade_mode=2
    with pytest.raises(RuntimeError,match='DÉMO'):p.op_demo_mode(actif=True)
    f.trade_mode=0;p.op_demo_mode(actif=True)
    original=f.account_info
    def change():
        a=original();a.server+='-autre';return a
    monkeypatch.setattr(f,'account_info',change)
    with pytest.raises(RuntimeError,match='différent'):lancer(p)
    assert not f.envois


def test_lot_minimum_trop_risque_est_refuse(pont):
    p,f=pont;f.solde=100
    p.op_demo_mode(actif=True)
    assert 'trop risqué' in lancer(p)['message'] and not f.envois


def test_calendrier_absent_perime_annonce_et_horaires(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True)
    for cal,texte in [(None,'absent'),({'ts':NOW-22000,'evenements':[]},'périmé'),
                      ({'ts':NOW,'evenements':[{'ts':NOW+100}]},'annonce')]:
        assert texte in p.op_demo_cycle(autoriser=True,calendrier=cal)['message']
    monkeypatch.setattr(time,'time',lambda:NOW+8*3600)
    assert '7 h' in lancer(p)['message'] and not f.envois


def test_frein_jour_ferme_et_coupe_persistante(pont):
    p,f=pont;p.op_demo_mode(actif=True);lancer(p)
    f.solde*=.989;r=lancer(p)
    assert 'frein' in r['message'] and not f.positions
    assert 'Frein' in lancer(p)['message']
    f.solde*=.97;lancer(p)
    p.op_demo_mode(actif=False)
    with pytest.raises(RuntimeError,match='coupe-circuit'):p.op_demo_mode(actif=True)


def test_pause_conserve_sortie_horizon(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True);lancer(p);p.op_demo_mode(actif=False)
    monkeypatch.setattr(time,'time',lambda:NOW+R.HORIZON+1)
    assert 'horizon' in p.op_demo_cycle()['message'] and not f.positions


def test_reponse_perdue_avec_ordre_execute_verrouille_entrees(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True);send=f.order_send
    def perdu(d):
        r=send(d)
        if r.retcode==10009:raise TimeoutError('réponse perdue')
        return r
    monkeypatch.setattr(f,'order_send',perdu)
    with pytest.raises(TimeoutError):lancer(p)
    assert len(f.positions)==1 and p._demo_lire()['incident']
    n=len(f.envois);assert 'Incident' in lancer(p)['message'];assert len(f.envois)==n
    with pytest.raises(RuntimeError,match='incident'):p.op_demo_mode(actif=True)


def test_protection_non_confirmee_fermeture_et_verrou(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True);send=f.order_send
    def sans_tp(d):
        r=send(d)
        if f.positions:f.positions[0].tp=0
        return r
    monkeypatch.setattr(f,'order_send',sans_tp)
    r=lancer(p);assert r['incident'] and not r['actif'] and not f.positions


def test_fermeture_partielle_reessayee_sans_oubli(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True);lancer(p)
    monkeypatch.setattr(time,'time',lambda:NOW+R.HORIZON+1)
    send=f.order_send
    def partiel(d):
        f.positions[0].volume/=2
        return NS(retcode=10010,comment='partial',order=f.positions[0].ticket,deal=1,price=4000,volume=.005)
    monkeypatch.setattr(f,'order_send',partiel)
    assert 'réessayer' in lancer(p)['message'] and len(f.positions)==1
    monkeypatch.setattr(f,'order_send',send)
    assert 'fermée' in lancer(p)['message'] and not f.positions


def test_refus_certain_pas_de_rejeu_meme_bougie(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True)
    monkeypatch.setattr(f,'order_send',lambda d:NS(retcode=10019,comment='margin',order=0,deal=0,price=0,volume=0))
    assert lancer(p)['incident'] is None
    assert p._demo_lire()['entrees_jour']==1
    assert 'heure' in lancer(p)['message']


def test_activation_telegram_et_arret(pont,monkeypatch):
    p,f=pont
    def appel(op,**kw):return getattr(p,'op_'+op)(**kw)
    monkeypatch.setattr(demo_auto.mt5,'appel',appel)
    monkeypatch.setattr(chef.telegram,'commandes',lambda:['/or_demo_on'])
    monkeypatch.setattr(chef.telegram,'envoyer',lambda *a,**k:True)
    c=NS(pause=True);chef.bot_commandes(c)
    assert not c.pause and base.lire('r4:configure') and not base.lire('mt5:pause')
    assert p.op_demo_etat()['actif']
    base.ecrire('calendrier',{'ts':NOW,'evenements':[]})
    assert 'confirmé' in demo_auto.cycle(c)
    monkeypatch.setattr(chef.telegram,'commandes',lambda:['/or_demo_off']);chef.bot_commandes(c)
    assert not p.op_demo_etat()['actif'] and f.positions  # arrêt des entrées, pas fermeture forcée


def test_fichier_corrompu_ne_reinitialise_pas(pont):
    p,f=pont;p.op_demo_mode(actif=True);p._demo_fichier().write_text('{invalid')
    with pytest.raises(ValueError):lancer(p)
    assert not f.envois


def test_trois_tentatives_et_reactivation_ne_reset_pas_risque(pont):
    p,f=pont;p.op_demo_mode(actif=True)
    lancer(p);pic=p._demo_lire()['pic'];p.op_fermer(f.positions[0].ticket)
    e=p._demo_lire();e['entrees_jour']=3;e['derniere_entree']=0;p._demo_ecrire(e)
    p.op_demo_mode(actif=False);p.op_demo_mode(actif=True)
    assert 'Maximum' in lancer(p)['message']
    assert p._demo_lire()['pic']>=pic
    lignes=p._demo_fichier().with_name('demo-r4-journal.jsonl').read_text().splitlines()
    assert {'intention','reponse','activation'}<={json.loads(l)['action'] for l in lignes}


def test_position_manuelle_et_cours_perime_interdisent_entree(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True)
    f.positions.append(NS(magic=1,volume=.01,price_open=4000))
    assert 'déjà présent' in lancer(p)['message'] and not f.envois
    f.positions.clear()
    tick=f.symbol_info_tick('XAUUSD');tick.time=NOW-100
    monkeypatch.setattr(f,'symbol_info_tick',lambda s:tick)
    with pytest.raises(pont_mt5.ErreurPont,match='périmé'):lancer(p)
    assert not f.envois


def test_etat_risque_compte_reel_apres_activation_refuse_meme_fermeture(pont):
    p,f=pont;p.op_demo_mode(actif=True);lancer(p)
    n=len(f.envois);f.trade_mode=2
    with pytest.raises(RuntimeError,match='DÉMO'):lancer(p)
    assert len(f.envois)==n


def test_protection_incorrecte_et_fermeture_refusee_reessayee(pont,monkeypatch):
    p,f=pont;p.op_demo_mode(actif=True);send=f.order_send
    def mauvaise_protection(d):
        if d.get('position'):
            return NS(retcode=10018,comment='closed',order=0,deal=0,price=0,volume=0)
        r=send(d)
        if f.positions:f.positions[0].sl-=100
        return r
    monkeypatch.setattr(f,'order_send',mauvaise_protection)
    r=lancer(p)
    assert r['incident'] and not r['actif'] and r['fermeture_requise'] and f.positions
    monkeypatch.setattr(f,'order_send',send)
    assert 'protection à corriger' in lancer(p)['message'] and not f.positions
    assert p._demo_lire()['incident']  # jamais de nouvelle entrée implicite après incident


def test_retour_r3_refuse_mode_incident_position_et_pont_absent(tmp_path,monkeypatch):
    import deployer
    (tmp_path/'runtime').mkdir(exist_ok=True)
    fichier=tmp_path/'runtime/demo-r4.json'
    (tmp_path/'.env').write_text('OR_MT5_PORT=18777\n')
    for e in ({'actif':True},{'incident':{'ts':1}}):
        fichier.write_text(json.dumps(e))
        with pytest.raises(RuntimeError,match='retour refusé'):deployer.verifier_retour(tmp_path)
    fichier.write_text('{"actif":false}')
    class Sock:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def sendall(self,b):assert json.loads(b)=={'op':'positions'}
        def recv(self,n):return json.dumps({'ok':True,'r':self.positions}).encode()+b'\n'
    sock=Sock();sock.positions=[{'magic':R.MAGIC}]
    monkeypatch.setattr(deployer.socket,'create_connection',lambda *a,**k:sock)
    with pytest.raises(RuntimeError,match='position R4'):deployer.verifier_retour(tmp_path)
    sock.positions=[];deployer.verifier_retour(tmp_path)
    def absent(*a,**kw):raise ConnectionRefusedError('absent')
    monkeypatch.setattr(deployer.socket,'create_connection',absent)
    with pytest.raises(ConnectionRefusedError):deployer.verifier_retour(tmp_path)


def test_cycle_chef_execute_demo_et_fermeture_generale(pont,monkeypatch):
    from armee_or import executant
    p,f=pont
    monkeypatch.setattr(config,'MT5_ACTIF',True)
    monkeypatch.setattr(demo_auto.mt5,'appel',lambda op,**kw:getattr(p,'op_'+op)(**kw))
    monkeypatch.setattr(chef.telegram,'envoyer',lambda *a,**k:True)
    demo_auto.mode(True);base.ecrire('calendrier',{'ts':NOW,'evenements':[]})
    c=NS(pause=False)
    assert 'confirmé' in executant.bot_mt5(c) and len(f.positions)==1
    assert len(executant.fermer_tout())==1 and not f.positions
    base.ecrire('mt5:pause',True)
    assert 'Pause' in executant.bot_mt5(c) and not f.positions


def test_bridge_charge_comme_script_autonome():
    import subprocess,sys
    from pathlib import Path
    dossier=Path(pont_mt5.__file__).parent
    r=subprocess.run([sys.executable,'-c','import pont_mt5; assert hasattr(pont_mt5.Pont, "op_demo_cycle")'],
                     cwd=dossier,capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stderr

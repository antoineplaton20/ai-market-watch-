import numpy as np
import pytest
pytest.importorskip('talib')
from armee_or import recherche as R
from test_armee import _barres


def exemple(n=1000):
    rng=np.random.default_rng(123)
    return _barres(2000*np.exp(np.cumsum(rng.normal(0,.002,n))))


def test_catalogue_complet_et_signaux_causaux():
    b=exemple();s,m=R.signaux(b)
    assert len(m)==61
    coupe={k:v[:500] for k,v in b.items()}
    s2,m2=R.signaux(coupe)
    for nom in s:np.testing.assert_array_equal(s[nom][:500],s2[nom])
    for nom in m:np.testing.assert_array_equal(m[nom][:500],m2[nom])


def test_doublons_et_ohlc_refuses():
    b=exemple();b['ts'][1]=b['ts'][0]
    with pytest.raises(ValueError,match='horodatages'):R.verifier(b,3600000)
    b=exemple();b['h'][1]=1
    with pytest.raises(ValueError,match='OHLC'):R.verifier(b,3600000)


def test_import_csv_validation_avant_ecriture(tmp_path):
    from armee_or import import_csv, donnees
    f=tmp_path/'export.csv'
    f.write_text('ts,o,h,l,c,v\n0,100,102,99,101,1\n3600000,101,103,100,102,2\n')
    r=import_csv.importer(f,'EXPORT_TEST','1h',maintenant_ms=7200000)
    assert r['lignes']==2
    f.write_text('ts,o,h,l,c,v\n0,100,105,99,101,1\n')
    with pytest.raises(ValueError,match='conflit'):
        import_csv.importer(f,'EXPORT_TEST','1h',maintenant_ms=7200000)
    assert donnees.charger('EXPORT_TEST','1h')['h'][0]==102


def test_regroupement_refuse_doublons():
    from armee_or import donnees
    lignes=[[0,1,2,.5,1.5,1],[0,1,2,.5,1.5,1],[900000,1,2,.5,1.5,1],[2700000,1,2,.5,1.5,1]]
    with pytest.raises(donnees.DonneesInvalides,match='dupliqués'):
        donnees.regrouper(lignes,60,900000)


def test_entree_bougie_suivante_et_stop_prioritaire():
    b=_barres(np.full(350,100.0));s=np.zeros(350,int);s[100]=1
    b['h'][101]=110;b['l'][101]=90
    r=R.simuler(b,s,100,150,3600000)
    t=r['operations'][0]
    assert t['signal_ts']==b['ts'][100] and t['entree_ts']==b['ts'][101]
    assert t['motif']=='stop' and t['sortie']==98


def test_gap_stop_execution_au_prix_defavorable():
    b=_barres(np.full(350,100.0));s=np.zeros(350,int);s[100]=1
    b['o'][102]=95;b['l'][102]=94
    r=R.simuler(b,s,100,150,3600000)
    assert r['operations'][0]['sortie']==95


def test_rupture_exclut_transaction():
    b=exemple();s=np.zeros(1000,int);s[100]=1
    b['ts'][110:]+=3600000
    r=R.simuler(b,s,100,150,3600000)
    assert r['trades']==0


def test_couts_doubles_reduisent_rendement():
    b=exemple();s=np.ones(1000,int)
    a=R.simuler(b,s,300,900,3600000)
    z=R.simuler(b,s,300,900,3600000,cout_cote=.0014)
    assert a['trades']==z['trades'] and z['rendement_net']<a['rendement_net']


def test_test_final_ne_selectionne_pas_strategie():
    b=exemple();a=R.evaluer(b,3600000)
    for k in ('o','h','l','c'):b[k][800:]*=2
    z=R.evaluer(b,3600000)
    assert a['validation']==z['validation']
    assert a['selection_validation']==z['selection_validation']
    assert a['autorisation_mt5'] is False


def test_indicateurs_reinitialises_apres_rupture():
    b=exemple();b['ts'][500:]+=3600000
    s,m=R.signaux(b,3600000)
    seul={k:v[500:] for k,v in b.items()}
    ss,mm=R.signaux(seul)
    for nom in s:np.testing.assert_array_equal(s[nom][500:],ss[nom])
    assert not s['ema_50_200'][500:699].any()
    avant={k:v[:750] for k,v in b.items()}
    court,_=R.signaux(avant,3600000)
    for nom in s:np.testing.assert_array_equal(s[nom][:750],court[nom])

"""Pilotage Linux du mode démo expérimental explicitement autorisé par le propriétaire."""
import time
from . import base,mt5,risque,telegram


def mode(actif):
    from .executant import _verifier_compte
    if actif:
        e=mt5.appel('etat')
        if not e.get('connecte'):raise mt5.ErreurMT5('connexion démo non confirmée')
        _verifier_compte(e.get('compte'))
        if base.lire('r2:ordre_incertain') or base.lire('r2:compte_change'):
            raise mt5.ErreurMT5('incident existant : activation refusée')
    base.ecrire('r4:configure',True)
    r=mt5.appel('demo_mode',actif=actif)
    if actif:
        base.ecrire('mt5:pause',False)
        base.ecrire('pause',False)
    base.ecrire('r4:demo', {**mt5.appel('demo_etat'),'ts_lecture':time.time()})
    return r['message']


def cycle(chef):
    if not base.lire('r4:configure'):return None
    ok,raison=risque.autorise()
    if chef.pause or base.lire('mt5:pause',True):ok,raison=False,'Pause demandée.'
    if base.lire('r2:ordre_incertain') or base.lire('r2:compte_change'):ok,raison=False,'Incident de l’armée non résolu.'
    r=mt5.appel('demo_cycle',autoriser=bool(ok),motif=raison,calendrier=base.lire('calendrier'))
    base.ecrire('r4:demo',{**r,'ts_lecture':time.time()})
    if r.get('ordre') or r.get('sortie'):
        with base.connexion() as c:
            c.execute('INSERT INTO rapports(ts,bot,ok,duree,message) VALUES(?,?,?,?,?)',
                      (time.time(),'Démo expérimentale R4',int(not r.get('incident')),0,str(r)))
        telegram.envoyer('MT5 DÉMO EXPÉRIMENTALE · '+r['message'])
    return r.get('message','Démo expérimentale en attente.')


# Mesure R5.1 (25/10/2026) : la règle elle-même (demo_regles.signal), rejouée sur PAXGUSDT 15 min 2021-2026,
# entrée à l'ouverture suivante, écart 0,30 $/once, sans le calendrier des annonces (donc plutôt optimiste).
MESURE=('Mesurée sur l’or 2021-2026 (2 783 trades) : 44 % gagnants, −0,04 R par trade, perdante de 2021 à 2024, '
        'légèrement gagnante en 2025-2026 : pas de permis.')


def texte():
    e=base.lire('r4:demo') or {}
    if not base.lire('r4:configure'):
        return 'Démo expérimentale non activée. Activation : /or_demo_on ou or demo on.\n'+MESURE
    age=time.time()-e.get('ts_lecture',0)
    return ('DÉMO EXPÉRIMENTALE — rentabilité non démontrée.\n'
            +('Mode activé' if e.get('actif') else 'Mode arrêté')
            +(' · état périmé, connexion à vérifier' if not 0<=age<=60 else '')+'\n'
            +'Risque visé 0,25 %/ordre ; lot minimum ; 1 position ; 3 entrées/jour maximum.\n'
            +'Stop 3 ATR et objectif 6 ATR chez le courtier ; horizon 4 h.\n'
            +f"Freins : jour −1 %, sommet −3 %. Baisse de l’essai : {100*e.get('baisse',0):+.2f} %.\n"
            +str(e.get('message') or 'Attente du prochain passage.')
            +'\n'+MESURE
            +'\nArrêter les entrées : /or_demo_off ou or demo off.')

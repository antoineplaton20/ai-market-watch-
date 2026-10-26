"""Un seul chef par dossier ; diagnostic explicite à partir de l'état observé."""
import time
from contextlib import contextmanager
from . import base,config


@contextmanager
def verrou_chef():
    import fcntl
    p=config.RACINE/'runtime'/'chef.lock'
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a') as fichier:
        try:
            fcntl.flock(fichier,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("un chef d'orchestre fonctionne déjà dans ce dossier") from exc
        try:
            yield
        finally:
            fcntl.flock(fichier,fcntl.LOCK_UN)


def diagnostic(maintenant=None):
    maintenant=time.time() if maintenant is None else maintenant
    ch=base.lire('chef',{}) or {}
    e=base.lire('mt5:etat',{}) or {}
    compte=e.get('compte') or {}
    r=base.lire('risque:etat',{}) or {}
    incident=base.lire('r2:ordre_incertain')
    from .qualification import OUVERTURES_VALIDEES
    from .commandes import etat as etat_commandes
    file=etat_commandes()
    demo=base.lire('r4:demo') or {}
    experimental=demo.get('actif') is True and 0<=maintenant-demo.get('ts_lecture',0)<=60
    marches_actif=base.lire('marches:actif',False) is True  # R5 : activation explicite du propriétaire
    controles={
        'aucun_incident_demo':not bool(demo.get('incident')),
        'frein_demo_non_declenche':not demo.get('coupe') and not demo.get('arret_jour'),
        'etat_demo_recent':not base.lire('r4:configure') or 0<=maintenant-demo.get('ts_lecture',0)<=60,
        "aucune_commande_incertaine":not file.get("incertaine",0),
        'strategie_qualifiee_ou_demo_explicite':OUVERTURES_VALIDEES or experimental or marches_actif,
        'chef_recent':0<=maintenant-ch.get('ts',0)<=90,
        'etat_mt5_recent':0<=maintenant-e.get('ts',0)<=60,
        'connexion':e.get('connecte') is True,
        'compte_demo':compte.get('demo') is True,
        'compte_hedging':compte.get('margin_mode')==2,
        'trading_terminal':(e.get('terminal') or {}).get('trade_allowed') is True,
        'trading_compte':compte.get('trade_allowed') is True,
        'reference_risque_recente':0<=maintenant-r.get('ts',0)<=60,
        'frein_non_declenche':bool(r) and not r.get('coupe') and not r.get('arret_jour'),
        'aucun_ordre_incertain':not bool(incident),
        'compte_inchange':not bool(base.lire('r2:compte_change')),
        'pause_generale_levee':base.lire('pause',False) is False,
        'pause_mt5_levee':base.lire('mt5:pause',True) is False,
    }
    return {'version':'2.5-R8.4', 'mode_experimental':experimental, 'strategie_qualifiee':OUVERTURES_VALIDEES,'ts':maintenant,'controles':controles,
            'etat':'CONTROLES_OBSERVES_OK' if all(controles.values()) else 'BLOQUE_OU_NON_VERIFIE',
            'motifs':[k for k,v in controles.items() if not v],
            'commandes':file,
            'equipes_r5':{'multi_marches':marches_actif,'video':base.lire('video:actif',False) is True},
            'incident_ordre':None if not incident else {k:v for k,v in incident.items() if k not in ('compte','serveur')},
            'limite':"État local observé, pas une certification de bon fonctionnement ni de rentabilité."}

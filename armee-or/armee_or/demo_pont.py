"""Exécution expérimentale MT5, limitée au compte démo explicitement activé.
État persistant privé au pont ; intention écrite avant l'ordre, jamais rejouée après panne.
"""
import datetime as dt
import json
import math
import os
import time
from pathlib import Path
try:
    from . import demo_regles as R
except ImportError:  # Python Windows, lancement de pont_mt5.py directement
    import demo_regles as R

REFUS_CERTAINS={10004,10006,10013,10014,10015,10016,10017,10018,10019,10021,10030}


class DemoMixin:
    def _demo_fichier(self):
        if not self.dossier:raise RuntimeError('dossier persistant du pont absent')
        return Path(self.dossier)/'runtime'/'demo-r4.json'

    def _demo_lire(self):
        p=self._demo_fichier()
        if not p.exists():return {}
        e=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(e,dict) or e.get('version')!=R.VERSION:
            raise RuntimeError('état démo R4 incompatible : aucune ouverture')
        return e

    def _demo_ecrire(self,e):
        p=self._demo_fichier();p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_suffix('.tmp')
        if p.is_symlink() or tmp.is_symlink():raise RuntimeError('fichier démo symbolique refusé')
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(e,f,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)

    def _demo_trace(self,action,detail):
        p=self._demo_fichier().with_name('demo-r4-journal.jsonl')
        if p.is_symlink():raise RuntimeError('journal symbolique refusé')
        with p.open('a',encoding='utf-8') as f:
            f.write(json.dumps({'ts':time.time(),'action':action,'detail':detail},allow_nan=False)+'\n')
            f.flush();os.fsync(f.fileno())

    def _demo_compte(self,e):
        self.exiger();a=self.mt5.account_info()
        if a is None or a.trade_mode!=0:raise RuntimeError('R4 : compte DÉMO obligatoire')
        if e and (e.get('login'),e.get('server'))!=(a.login,a.server):
            raise RuntimeError('R4 : compte différent, activation refusée')
        if not math.isfinite(a.equity) or a.equity<=0:raise RuntimeError('équité invalide')
        return a

    def op_demo_etat(self,**_):
        e=self._demo_lire()
        return {k:v for k,v in e.items() if k not in ('login','server')}

    def op_demo_mode(self,actif=False,**_):
        if type(actif) is not bool:raise RuntimeError('mode booléen requis')
        e=self._demo_lire()
        if not actif:
            if e:e['actif']=False;self._demo_ecrire(e)
            return {'actif':False,'message':'Démo expérimentale arrêtée ; sorties des positions maintenues.'}
        a=self._demo_compte(e)
        if getattr(a,'margin_mode',None)!=2:raise RuntimeError('compte hedging requis')
        if e.get('incident') or e.get('coupe'):
            raise RuntimeError('incident ou coupe-circuit R4 : diagnostic requis, pas de remise à zéro automatique')
        if not e:
            pos=self.mt5.positions_get();ordres=self.mt5.orders_get()
            if pos is None or ordres is None or pos or ordres:
                raise RuntimeError('première activation : compte sans positions ni ordres requis')
            e={'version':R.VERSION,'login':a.login,'server':a.server,'origine':time.time(),
               'pic':a.equity,'actif':False,'incident':None,'coupe':False}
        e['actif']=True;self._demo_ecrire(e)
        self._demo_trace('activation',{'version':R.VERSION})
        return {'actif':True,'message':'Démo expérimentale activée : aucune rentabilité démontrée ; risque 0,25 %, 1 position, 3 entrées/jour maximum.'}

    def _demo_risque(self,e,a,now):
        jour=dt.datetime.fromtimestamp(now,dt.timezone.utc).date().isoformat()
        if e.get('jour') and jour<e['jour']:raise RuntimeError('horloge revenue en arrière')
        if e.get('jour')!=jour:
            e.update(jour=jour,equite_jour=a.equity,entrees_jour=0,arret_jour=False)
        e['pic']=max(e['pic'],a.equity)
        e['perte_jour']=a.equity/e['equite_jour']-1
        e['baisse']=a.equity/e['pic']-1
        if e['perte_jour']<=-R.PERTE_JOUR:e['arret_jour']=True
        if e['baisse']<=-R.BAISSE_MAX:e['coupe']=True;e['actif']=False
        e['ts']=now;self._demo_ecrire(e)

    def op_demo_cycle(self,autoriser=False,motif='',calendrier=None,**_):
        e=self._demo_lire()
        if not e:return {'actif':False,'message':'Démo expérimentale non activée.'}
        now=time.time();a=self._demo_compte(e);self._demo_risque(e,a,now)
        def fin(message,**extra):
            e['message']=message;self._demo_ecrire(e)
            return {**{k:v for k,v in e.items() if k not in ('login','server')},**extra}
        positions=self.mt5.positions_get();ordres=self.mt5.orders_get()
        if positions is None or ordres is None:raise RuntimeError('positions/ordres indisponibles')
        propres=[p for p in positions if p.magic==R.MAGIC]
        for p in propres:
            if not math.isfinite(p.time) or not 0<p.time<=now+5:raise RuntimeError('date position invalide')
            vendredi=dt.datetime.fromtimestamp(now,dt.timezone.utc)
            raison=('protection à corriger' if e.get('fermeture_requise')==p.ticket else
                    'frein expérimental' if e.get('coupe') or e.get('arret_jour') else
                    'horizon 4 h' if now>=p.time+R.HORIZON else
                    'fin de semaine' if vendredi.weekday()==4 and vendredi.hour>=20 else
                    'protection absente' if not all(math.isfinite(v) and v>0 for v in (p.sl,p.tp)) else '')
            if raison:
                r=self.op_fermer(ticket=p.ticket,commentaire='armee-or demo sortie')
                return fin(raison+(' : position fermée' if r['ok'] else ' : fermeture à réessayer'),sortie=r)
        if e.get('incident'):return fin('Incident d’ordre : nouvelles entrées verrouillées ; vérifier le courtier.')
        if e.get('coupe') or e.get('arret_jour'):return fin('Frein expérimental atteint : entrées bloquées.')
        if not e.get('actif'):return fin('Démo expérimentale arrêtée.')
        if autoriser is not True:return fin(motif or 'Pause : aucune nouvelle entrée.')
        if positions or ordres:return fin('Position ou ordre déjà présent : aucune nouvelle entrée.')
        if getattr(a,'margin_mode',None)!=2 or not a.trade_allowed or not self.mt5.terminal_info().trade_allowed:
            return fin('Compte hedging et trading autorisé requis.')
        if not R.horaires(now):return fin('Entrées du lundi au vendredi, de 7 h à 16 h UTC.')
        ok,raison=R.calendrier_ok(calendrier,now)
        if not ok:return fin(raison)
        if e.get('entrees_jour',0)>=R.MAX_ORDRES_JOUR:return fin('Maximum 3 tentatives d’entrée par jour UTC.')
        if now-e.get('derniere_entree',0)<R.ATTENTE:return fin('Délai minimal d’une heure entre entrées.')
        if e.get('evaluation') and now-e['evaluation']<10:return fin(e.get('message','Attente du signal.'))
        e['evaluation']=now
        s=R.signal(self.op_bougies(tf='15m',n=300),self.op_bougies(tf='1h',n=300),now)
        if now-s['connue_a']>120:return fin('Attente de la prochaine clôture 15 min (fenêtre 120 s).')
        if e.get('fait',0)>=s['bougie']:return fin('Cette bougie a déjà été traitée.')
        if not s['sens']:return fin(s['raison'])
        tick=self._cours_valide(self.symbole);info=self.mt5.symbol_info(self.symbole)
        if info is None or info.currency_profit!='USD' or not self.symbole.upper().startswith(('XAUUSD','GOLD')):
            return fin('Seul l’or coté en USD est autorisé.')
        if tick.ask-tick.bid>min(2.0,.1*s['atr']):return fin('Écart achat/vente trop large.')
        prix=tick.ask if s['sens']>0 else tick.bid
        sl,tp=R.niveaux(prix,s['sens'],s['atr'],info.digits)
        if min(sl,tp)<=0:return fin('Niveaux invalides.')
        ecart=max(0,info.trade_stops_level)*info.point
        if (s['sens']>0 and tp<=tick.ask+ecart) or (s['sens']<0 and tp>=tick.bid-ecart):
            return fin('Objectif trop proche.')
        vol=info.volume_min
        controle=self.op_dimensionner(sens=s['sens'],sl=sl,volume=vol)
        perte=self._perte(s['sens'],self.symbole,vol,prix,sl)
        if controle['volume']<vol or perte>a.equity*R.RISQUE:return fin('Lot minimum trop risqué : plafond 0,25 % avec réserve de coûts.')
        # Revérification du cours et du budget juste avant de persister l'intention.
        tick=self._cours_valide(self.symbole);prix=tick.ask if s['sens']>0 else tick.bid
        sl,tp=R.niveaux(prix,s['sens'],s['atr'],info.digits)
        if tick.ask-tick.bid>min(2.0,.1*s['atr']):return fin('Écart achat/vente trop large avant envoi.')
        controle=self.op_dimensionner(sens=s['sens'],sl=sl,volume=vol)
        if controle['volume']<vol or self._perte(s['sens'],self.symbole,vol,prix,sl)>a.equity*R.RISQUE:
            return fin('Cours modifié : risque refusé.')
        e['fait']=s['bougie'];e['derniere_entree']=now;e['entrees_jour']+=1
        e['incident']={'ts':now,'sens':s['sens'],'volume':vol,'sl':sl,'tp':tp,'signal':s}
        self._demo_ecrire(e)  # avant order_send ; une panne conserve cette intention.
        demande={'action':self.mt5.TRADE_ACTION_DEAL,'symbol':self.symbole,'volume':vol,
                 'type':self.mt5.ORDER_TYPE_BUY if s['sens']>0 else self.mt5.ORDER_TYPE_SELL,
                 'price':prix,'sl':sl,'tp':tp,'deviation':20,'magic':R.MAGIC,
                 'comment':'armee-or demo R4','type_time':self.mt5.ORDER_TIME_GTC}
        self._demo_trace('intention',e['incident'])
        r=self._envoyer(demande,info)
        self._demo_trace('reponse',r)
        if not r['ok'] and r['retcode'] in REFUS_CERTAINS:
            e['incident']=None;return fin('Ordre refusé par MT5 : '+str(r['retcode']),ordre=r)
        confirmation=self.mt5.positions_get()
        ps=[] if confirmation is None else [p for p in confirmation if p.magic==R.MAGIC]
        if r['ok'] and r['retcode'] in (10009,10010) and len(ps)==1:
            p=ps[0]
            conforme=(p.symbol==self.symbole and p.type==(0 if s['sens']>0 else 1) and 0<p.volume<=vol+1e-8
                      and abs(p.sl-sl)<=info.point and abs(p.tp-tp)<=info.point
                      and self._perte(s['sens'],self.symbole,p.volume,p.price_open,p.sl)<=a.equity*R.RISQUE)
            if conforme:
                e['incident']=None;e['dernier_ordre']={'ticket':p.ticket,'ts':now,**s,'sl':sl,'tp':tp,'volume':p.volume}
                return fin(('Achat' if s['sens']>0 else 'Vente')+' démo expérimental confirmé.',ordre=r)
            e['actif']=False;e['fermeture_requise']=p.ticket;self._demo_ecrire(e)
            self.op_fermer(ticket=p.ticket,commentaire='armee-or protection')
        e['actif']=False
        return fin('Ordre non confirmé ou protection incohérente : mode arrêté, incident conservé.',ordre=r)

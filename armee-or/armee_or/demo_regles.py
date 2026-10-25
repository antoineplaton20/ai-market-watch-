"""R4 démo expérimentale : règles fixes, bibliothèque standard, aucun ordre ici.
Aucune rentabilité démontrée. Les paramètres ne sont pas optimisés sur l'historique.
"""
import datetime as dt
import math

MAGIC = 770090
RISQUE = .0025
PERTE_JOUR = .01
BAISSE_MAX = .03
HORIZON = 4 * 3600
MAX_ORDRES_JOUR = 3
ATTENTE = 3600
VERSION = 'R4-demo-ema20-50-v1'


def horaires(ts):
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    return d.weekday() < 5 and 7 <= d.hour < 16


def closes(lignes, pas, maintenant):
    precedent = None
    resultat = []
    for ligne in lignes:
        if len(ligne) != 6 or not all(math.isfinite(float(v)) for v in ligne):
            raise ValueError('bougies invalides')
        t,o,h,l,c,v = ligne
        if t != int(t) or t % pas or (precedent is not None and t <= precedent):
            raise ValueError('horodatages invalides')
        if min(o,h,l,c) <= 0 or v < 0 or l > min(o,c) or h < max(o,c):
            raise ValueError('OHLC invalide')
        precedent=t
        if t+pas <= maintenant:resultat.append(ligne)
    if len(resultat) < 100:
        raise ValueError('au moins 100 bougies closes requises')
    if not 0 <= maintenant-(resultat[-1][0]+pas) < pas:
        raise ValueError('bougies périmées')
    return resultat


def ema(x,n):
    valeur=float(x[0]);a=2/(n+1)
    for v in x[1:]:valeur=a*v+(1-a)*valeur
    return valeur


def signal(m15,h1,maintenant):
    a=closes(m15,900,maintenant);b=closes(h1,3600,maintenant)
    def direction(lignes):
        c=[x[4] for x in lignes];rapide,lente=ema(c,20),ema(c,50)
        return 1 if c[-1]>rapide>lente else -1 if c[-1]<rapide<lente else 0
    d=direction(a);d=d if d==direction(b) else 0
    tr=[max(a[i][2]-a[i][3],abs(a[i][2]-a[i-1][4]),abs(a[i][3]-a[i-1][4])) for i in range(1,len(a))]
    atr=sum(tr[:14])/14
    for v in tr[14:]:atr=(13*atr+v)/14
    if not math.isfinite(atr) or atr<=0:raise ValueError('ATR invalide')
    return {'sens':d,'atr':atr,'bougie':int(a[-1][0]),'connue_a':int(a[-1][0]+900),
            'raison':'EMA20/50 et clôture concordantes en 15 min et 1 h' if d else 'pas de tendance concordante'}


def niveaux(entree,sens,atr,digits):
    return round(entree-sens*3*atr,digits),round(entree+sens*6*atr,digits)


def calendrier_ok(cal,maintenant):
    if not isinstance(cal,dict) or not isinstance(cal.get('evenements'),list):
        return False,'calendrier absent'
    ts=cal.get('ts')
    if not isinstance(ts,(int,float)) or not math.isfinite(ts) or not 0<=maintenant-ts<=6*3600:
        return False,'calendrier périmé'
    for e in cal['evenements']:
        if not isinstance(e,dict) or not isinstance(e.get('ts'),(int,float)) or not math.isfinite(e['ts']):
            return False,'calendrier invalide'
        if abs(e['ts']-maintenant)<=900:return False,'annonce à fort impact : pause ±15 min'
    return True,''

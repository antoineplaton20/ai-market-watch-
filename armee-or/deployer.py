"""Migration locale R5.1 d'une installation connue (R4, R5, ou la base acceptée par R4). Pas d'installation Wine ni de
changement des autres bots. R5 = R4 + équipe multi-marchés + équipe vidéo (2e compte démo), toutes deux désactivées."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import socket
import time

SOURCE = Path(__file__).resolve().parent
CIBLE = Path('/home/bots/armee-or')
SAUVEGARDES = Path('/var/backups/armee-or-r5')
TELECOMMANDE = Path('/usr/local/bin/or')
SERVICES = ('armee-or-mt5.service','armee-or-flux.service','armee-or-chef.service')
VIDEO = 'armee-or-mt5-video.service'  # pont du 2e compte : relancé s'il tournait, jamais exigé pour valider
VERSION = '2.5-R5.1'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def chemin(root,rel):
    p=Path(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise RuntimeError('chemin interdit dans le paquet')
    cible=root/p
    if any(x.is_symlink() for x in (cible,*cible.parents)):
        raise RuntimeError('lien symbolique refusé : '+rel)
    return cible


def manifestes(source=SOURCE):
    return json.loads((source/'PAQUET.json').read_text())


def verifier_paquet(source=SOURCE):
    m=manifestes(source)
    for rel,h in m['fichiers'].items():
        p=chemin(source,rel)
        if not p.is_file() or sha(p)!=h:
            raise RuntimeError('paquet incomplet ou modifié : '+rel)
    return m


def verifier_installation(cible=CIBLE,source=SOURCE):
    m=verifier_paquet(source)
    if cible.is_symlink() or not (cible/'.venv/bin/python').is_file():
        raise RuntimeError('installation existante avec Python dédié requise')
    env=chemin(cible,'.env')
    if not env.is_file():
        raise RuntimeError('réglages locaux absents ; aucun mot de passe demandé ici')
    for line in env.read_text().splitlines():
        if '=' not in line:continue
        k,v=line.split('=',1);v=v.strip().strip('"\'')
        if k.strip()=='OR_DOSSIER' and v!=str(cible):
            raise RuntimeError('OR_DOSSIER personnalisé : revue requise')
        if k.strip()=='OR_BASE' and v!=str(cible/'runtime/or.db'):
            raise RuntimeError('OR_BASE personnalisé : revue requise')
    erreurs=[]
    for rel,h in m['base'].items():
        p=chemin(cible,rel)
        acceptes={*(h if isinstance(h,list) else [h]),m['fichiers'].get(rel)}
        if not p.is_file() or sha(p) not in acceptes:
            erreurs.append(rel)
    for p in (cible/'armee_or').glob('*.py'):
        rel=str(p.relative_to(cible))
        if rel not in m['base'] and rel not in m['fichiers']:
            erreurs.append(rel)
    if erreurs:
        raise RuntimeError('version locale différente : migration refusée avant modification. Fichiers : '+', '.join(erreurs))
    if not chemin(cible,'runtime/or.db').is_file():
        raise RuntimeError('base existante absente')
    return m


def appeler(args,**kw):
    return subprocess.run(list(map(str,args)),check=True,timeout=kw.pop('timeout',120),**kw)


def service(action,*noms):
    autorises=set(SERVICES)|{VIDEO,'armee-or-maj.path','armee-or-maj.service'}
    if not set(noms)<=autorises:raise RuntimeError('service hors périmètre')
    return appeler(['systemctl',action,*noms])


def actifs(noms=SERVICES):
    return [n for n in noms if subprocess.run(['systemctl','is-active','--quiet',n],timeout=10).returncode==0]


def pont_multi_instance(cible=CIBLE):
    """Le code en place sait-il lancer le pont du 2e compte ? (sinon il ouvrirait le compte de l'armée)"""
    try:return 'def reglages_instance(' in (cible/'armee_or/pont_mt5.py').read_text(encoding='utf-8')
    except OSError:return False


def video_apres_retablissement(etait_actif):
    if not Path('/etc/systemd/system/'+VIDEO).exists():return
    if pont_multi_instance():
        if etait_actif:service('start',VIDEO)
    else:
        service('stop',VIDEO);service('disable',VIDEO)


def controles_systeme():
    for n in ('armee-or-chef.service','armee-or-flux.service'):
        d=appeler(['systemctl','show',n,'-p','WorkingDirectory','--value'],capture_output=True,text=True).stdout.strip()
        if d!=str(CIBLE):raise RuntimeError('service atypique : '+n)


def copie_base(cible,destination):
    src=sqlite3.connect(f'file:{cible}?mode=ro',uri=True)
    dst=sqlite3.connect(destination)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('sauvegarde SQLite invalide')
    finally:dst.close();src.close()
    destination.chmod(0o600)


def pause(cible):
    with sqlite3.connect(cible/'runtime/or.db',timeout=30) as c:
        for k,v in {'pause':True,'mt5:pause':True,'mt5:permis_exige':True,'mt5:permis':{},
                    'mt5:entrainement':False,'marches:actif':False,'video:actif':False}.items():
            c.execute('INSERT OR REPLACE INTO kv(cle,valeur,maj) VALUES (?,?,?)',(k,json.dumps(v),time.time()))


def sauvegarder(m,cible=CIBLE,racine=SAUVEGARDES):
    racine.mkdir(parents=True,exist_ok=True,mode=0o700)
    dossier=racine/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    dossier.mkdir(mode=0o700)
    anciens={}
    for rel in (*m['fichiers'],'PAQUET.json'):
        p=chemin(cible,rel)
        if p.exists():
            b=dossier/'code'/rel;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
            anciens[rel]=True
        else:anciens[rel]=False
    copie_base(cible/'runtime/or.db',dossier/'or.db')
    shutil.copy2(cible/'.env',dossier/'reglages.env');(dossier/'reglages.env').chmod(0o600)
    (dossier/'anciens.json').write_text(json.dumps(anciens))
    return dossier


def poser(source,cible,m,uid,gid):
    for rel in (*m['fichiers'],'PAQUET.json'):
        p=chemin(cible,rel);p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_name(p.name+'.r3-nouveau')
        if tmp.is_symlink():raise RuntimeError('lien temporaire refusé')
        shutil.copyfile(chemin(source,rel),tmp);tmp.chmod(0o755 if rel=='or' else 0o644)
        os.chown(tmp,uid,gid);os.replace(tmp,p)
    for cache in (cible/'armee_or').glob('__pycache__/*.pyc'):
        cache.unlink()


def retablir(dossier,cible=CIBLE):
    anciens=json.loads((dossier/'anciens.json').read_text())
    for rel,existe in anciens.items():
        p=chemin(cible,rel)
        if existe:
            shutil.copy2(dossier/'code'/rel,p)
        else:p.unlink(missing_ok=True)
    pause(cible)  # Pas de restauration du passé des transactions : on conserve la base courante.


def tester(source,cible,uid,gid):
    # Aucun .env ni base du compte dans le dossier des tests.
    with tempfile.TemporaryDirectory(prefix='armee-or-r5-') as nom:
        stage=Path(nom);stage.chmod(0o755)
        m=manifestes(source)
        for rel in (*m['fichiers'],'PAQUET.json'):
            p=stage/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,p)
        tmp=stage/'tmp';tmp.mkdir();os.chown(tmp,uid,gid)
        env={k:v for k,v in os.environ.items() if not k.startswith('OR_') and k not in ('PYTHONPATH','PYTHONHOME')}
        env.update(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(tmp))
        log=source/'validation/installation-tests.txt';log.parent.mkdir(exist_ok=True)
        with log.open('w') as f:
            r=subprocess.run(['runuser','-u','bots','--',str(cible/'.venv/bin/python'),'-m','pytest',
                'tests','-q','-p','no:cacheprovider','--basetemp',str(tmp/'pytest')],cwd=stage,env=env,
                stdout=f,stderr=subprocess.STDOUT,timeout=600)
        if r.returncode:raise RuntimeError('tests du serveur en échec (code '+str(r.returncode)+') : '+str(log))
        print('Tests du serveur : code 0.')


def sain(noms,debut):
    fin=time.monotonic()+45
    while time.monotonic()<fin:
        if set(noms)<=set(actifs()):
            with sqlite3.connect(CIBLE/'runtime/or.db') as c:
                row=c.execute("SELECT valeur FROM kv WHERE cle='chef'").fetchone()
            if 'armee-or-chef.service' not in noms or row and json.loads(row[0]).get('ts',0)>=debut:
                return
        time.sleep(2)
    raise RuntimeError('services ou battement du chef non confirmés')


def installer():
    m=verifier_installation();controles_systeme()
    compte=pwd.getpwnam('bots')
    tester(SOURCE,CIBLE,compte.pw_uid,compte.pw_gid)
    # Vérifier de nouveau après les tests, avant la première mutation de production.
    verifier_installation()
    en_marche=actifs()
    video=actifs((VIDEO,))
    if 'armee-or-chef.service' not in en_marche:
        raise RuntimeError('chef arrêté : diagnostiquer avant migration, aucun démarrage implicite')
    # Évite qu'une ancienne mise à jour puisse écraser le paquet local non publié.
    if Path('/etc/systemd/system/armee-or-maj.path').exists():
        service('stop','armee-or-maj.path')
    dossier=None
    try:
        service('stop',*en_marche,*video)
        dossier=sauvegarder(m)
        (dossier/'services.json').write_text(json.dumps(en_marche))
        pause(CIBLE)
        ancien_fichier=chemin(CIBLE,'runtime/commandes.txt')
        if ancien_fichier.exists():
            shutil.copy2(ancien_fichier,dossier/'commandes-anciennes.txt')
            ancien_fichier.unlink()
        poser(SOURCE,CIBLE,m,compte.pw_uid,compte.pw_gid)
        wrapper=TELECOMMANDE
        if wrapper.is_symlink():raise RuntimeError('télécommande symbolique refusée')
        if wrapper.exists():shutil.copy2(wrapper,dossier/'telecommande')
        shutil.copyfile(CIBLE/'or',wrapper);wrapper.chmod(0o755)
        debut=time.time();service('start',*en_marche);sain(en_marche,debut)
        if video:service('start',*video)
        (CIBLE/'runtime/version-r5.json').write_text(json.dumps({'version':VERSION,'sauvegarde':str(dossier),'ts':time.time()}))
        print('R5.1 installée en pause. Multi-marchés et équipe vidéo DÉSACTIVÉS : or marches on / or video on '
              '(ou /or_marches_on, /or_video_on) quand tu le décides. Démo R4 : or demo on. Sauvegarde : '+str(dossier))
        print('Vérifier : or diagnostic, or mt5, or marches. 2e compte (équipe vidéo) : or video installer. '
              'Retour du code : bash '+str(CIBLE/'installer_or.sh')+' retour '+dossier.name)
    except BaseException:
        service('stop',*en_marche,*video)
        if dossier and (dossier/'anciens.json').exists():
            retablir(dossier)
            if (dossier/'telecommande').exists():shutil.copy2(dossier/'telecommande',TELECOMMANDE)
        service('start',*en_marche)
        video_apres_retablissement(bool(video))
        print('Échec : retour du code précédent tenté ; vérifier les services et la pause avec or mt5.',file=sys.stderr)
        raise


def positions_pont(port):
    with socket.create_connection(('127.0.0.1',int(port)),timeout=10) as sock:
        sock.sendall(b'{"op":"positions"}\n');brut=b''
        while not brut.endswith(b'\n'):
            morceau=sock.recv(65536)
            if not morceau or len(brut)>1024*1024:raise RuntimeError('réponse MT5 incomplète')
            brut+=morceau
    r=json.loads(brut)
    if r.get('ok') is not True or not isinstance(r.get('r'),list):
        raise RuntimeError('positions MT5 non vérifiées : retour refusé')
    return r['r']


def verifier_retour(cible=CIBLE):
    env={}
    for ligne in (cible/'.env').read_text().splitlines():
        if '=' in ligne:
            k,v=ligne.split('=',1);env[k.strip()]=v.strip().strip(chr(34)+chr(39))
    fichier=cible/'runtime/demo-r4.json'
    if fichier.exists():
        e=json.loads(fichier.read_text())
        if e.get('actif') or e.get('incident'):
            raise RuntimeError('retour refusé : arrêter le mode avec or demo off et résoudre tout incident')
    try:positions=positions_pont(env.get('OR_MT5_PORT',18777))
    except OSError:
        if fichier.exists():raise  # démo R4 déjà utilisée : sa position doit être vérifiée, comme en R4
        print('Pont MT5 injoignable : positions non vérifiées (elles gardent leurs stops chez le courtier).')
        positions=[]
    if any(p.get('magic')==770090 for p in positions):
        raise RuntimeError('position R4 encore ouverte : attendre sa sortie ou or mt5 fermer avant retour')
    if any(p.get('magic')==770050 for p in positions):
        raise RuntimeError('position multi-marchés encore ouverte : or marches fermer avant retour')
    if env.get('OR_VIDEO_LOGIN'):
        try:video=positions_pont(env.get('OR_VIDEO_PORT',18778))
        except OSError:video=[]  # pont vidéo arrêté : compte démo séparé, rien à protéger côté armée
        if any(p.get('magic')==770077 for p in video):
            raise RuntimeError('panier vidéo encore ouvert sur le 2e compte : or video fermer avant retour')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('verifier','installer','retour'),nargs='?',default='installer')
    p.add_argument('sauvegarde',nargs='?');args=p.parse_args()
    if os.geteuid()!=0:raise RuntimeError('commande à exécuter en root dans Termius')
    with open('/run/lock/armee-or-r3.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action=='verifier':
            verifier_installation();controles_systeme();print('Version locale compatible. Aucune modification de production.')
        elif args.action=='installer':installer()
        else:
            if not args.sauvegarde or Path(args.sauvegarde).name!=args.sauvegarde:
                raise RuntimeError('identifiant de sauvegarde requis')
            d=SAUVEGARDES/args.sauvegarde
            if d.is_symlink() or not (d/'anciens.json').is_file():raise RuntimeError('sauvegarde inconnue')
            verifier_retour()
            noms=json.loads((d/'services.json').read_text())
            video=actifs((VIDEO,))
            service('stop',*noms,*video);retablir(d)
            if (d/'telecommande').exists():shutil.copy2(d/'telecommande',TELECOMMANDE)
            service('start',*noms)
            video_apres_retablissement(bool(video))
            print('Code précédent restauré, base courante conservée, ouvertures en pause. Vérifier or etat.'
                  +('' if pont_multi_instance() else ' Pont du 2e compte arrêté : ce code ne le connaît pas.'))


if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.SubprocessError,OSError) as ex:
        print('STOP : '+str(ex),file=sys.stderr);sys.exit(1)

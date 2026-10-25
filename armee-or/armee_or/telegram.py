"""Messages Telegram de l'armée de l'or.

- Bot Telegram DÉDIÉ (recommandé : @BotFather > /newbot) : l'armée envoie ses rapports ET reçoit ses commandes
  (/or, /or_levier, /or_bilan, /or_pause, /or_reprise, /or_mt5, /or_mt5_fermer), sans jamais gêner le bot existant.
- Sans bot dédié : réutilisation du bot existant en ENVOI SEUL (deux lecteurs sur un même bot se voleraient
  les commandes) ; les commandes passent alors par Termius (« or etat », « or pause »...).
Telegram en panne ne fait jamais tomber l'armée : le message est journalisé et l'armée continue.
"""
from __future__ import annotations

import logging
import time
import re

from . import base, config

_log = logging.getLogger("or.telegram")
PREFIXE = "🟡 [or] "
LIMITE = 4000


def _confirme(reponse):
    reponse.raise_for_status()
    resultat = reponse.json()
    return isinstance(resultat, dict) and resultat.get("ok") is True



def decouper(texte, limite=3500):
    """Découpage conservant tout le texte ; budget UTF-16 et HTML < 4000."""
    import html
    pages, morceau = [], ""
    for caractere in str(texte):
        candidat = morceau + caractere
        if len(html.escape(candidat).encode("utf-16-le")) // 2 > limite:
            pages.append(morceau)
            morceau = caractere
        else:
            morceau = candidat
    if morceau:
        pages.append(morceau)
    return pages or [""]


def envoyer(texte, important=False, session=None, mono=False):
    if not (config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return False
    import html
    import requests
    for page in decouper(texte):
        corps = PREFIXE + ("<pre>" + html.escape(page) + "</pre>" if mono else page)
        extra = {"parse_mode": "HTML"} if mono else {}
        try:
            rep = (session or requests).post(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/sendMessage",
                json={"chat_id": config.TELEGRAM_CHAT, "text": corps,
                      "disable_notification": not important, **extra}, timeout=15)
            if not _confirme(rep):
                return False
        except Exception as ex:
            _log.warning("Telegram indisponible : %s", type(ex).__name__)
            return False
    return True


def envoyer_photo(chemin, legende="", session=None):
    """Photo (ex. capture de l'écran virtuel de MT5 pendant l'installation) : diagnostic depuis le téléphone."""
    if not (config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return False
    try:
        import requests
        with open(chemin, "rb") as f:
            reponse = (session or requests).post(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/sendPhoto",
                                       data={"chat_id": config.TELEGRAM_CHAT, "caption": (PREFIXE + legende)[:1000]},
                                       files={"photo": f}, timeout=60)
        return _confirme(reponse)
    except Exception as ex:
        _log.warning("Photo Telegram non envoyée : %s", type(ex).__name__)
        return False



def envoyer_document(chemin, legende="", session=None):
    """Fichier (sauvegarde) envoyé dans la conversation. -> code du fichier chez Telegram (pour le retélécharger)."""
    if not (config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return None
    try:
        import requests
        with open(chemin, "rb") as f:
            rep = (session or requests).post(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/sendDocument",
                                           data={"chat_id": config.TELEGRAM_CHAT,
                                                 "caption": (PREFIXE + legende)[:1000]},
                                           files={"document": f}, timeout=60)
            if not _confirme(rep):
                return None
            r = rep.json()
        return ((r.get("result") or {}).get("document") or {}).get("file_id")
    except Exception as ex:
        _log.warning("Document Telegram non envoyé : %s", type(ex).__name__)
        return None


def alerte_rare(cle, texte, fenetre_s=3600, important=False):
    """Au plus un message par `cle` et par fenêtre (mémoire en base : survit aux redémarrages)."""
    deja = base.lire(f"alerte:{cle}", 0) or 0
    if time.time() - deja < fenetre_s:
        _log.info("(alerte déjà envoyée) %s", texte[:200])
        return False
    tentative = base.lire(f"alerte_tentative:{cle}", 0) or 0
    if time.time() - tentative < 60:
        return False
    base.ecrire(f"alerte_tentative:{cle}", time.time())
    ok = envoyer(texte, important)
    if ok:
        base.ecrire(f"alerte:{cle}", time.time())
    return ok



MENU = [("or_demo", "État du mode démo expérimental"), ("or_demo_on", "Activer les ordres de test en DÉMO"), ("or_demo_off", "Arrêter les nouvelles entrées expérimentales"), ("or_marches", "Multi-marchés : forex, métaux, énergie, indices, crypto"), ("or_marches_on", "Activer le multi-marchés (sous permis)"), ("or_marches_off", "Arrêter les achats multi-marchés"), ("or_video", "Équipe vidéo : 2e compte démo, méthode des vidéos"), ("or_video_on", "Activer l'équipe vidéo (2e compte)"), ("or_video_off", "Arrêter les paniers de l'équipe vidéo"), ("or_grands", "Bibliothèque : /or_grands 1, 2…"), ("or_go", "Terminal : écran de lancement"), ("or_gp", "Terminal : graphique 1 h (or_gp_4h, _1d…)"),
        ("or_rv", "Terminal : or / argent"), ("or_corr", "Terminal : corrélations"), ("or_wei", "Terminal : marchés liés"),
        ("or_brief", "Brief du matin (envoyé seul à 8 h)"),
        ("or_risque", "Risque : perte du jour, coupe-circuit"), ("or_sauvegarde", "Dernière sauvegarde"),
        ("or_alerte", "Alerte de prix : /or_alerte 4200 ou +1%"), ("or_alertes", "Mes alertes de prix"),
        ("or", "Rapport complet"), ("or_veille", "Veille : tendances, niveaux, flux, COT, annonces, actus"),
        ("or_apprentissage", "Ce que l'armée a appris (journal)"),
        ("or_verif", "Vérifier : croissance de la mémoire et diagnostic des trades"),
        ("or_calendrier", "Annonces économiques à fort impact"), ("or_niveaux", "Niveaux clés (supports, résistances)"),
        ("or_actus", "Derniers titres sur l'or"), ("or_mt5", "Compte MT5 démo et équipes"),
        ("or_mt5_fermer", "Fermer les positions de l'armée et suspendre"), ("or_mt5_reprendre", "Reprendre les ordres MT5"),
        ("or_mt5_profil", "Choisir le levier des décisions"), ("or_mt5_ecran", "Photo de l'écran du terminal MT5"), ("or_entrainement", "Équipe d'entraînement on/off"), ("or_gain", "Prise de gain : fermer dès +X €"), ("or_tendance", "Filtre : jamais contre la tendance on/off"), ("or_permis", "Preuve obligatoire ; ouvertures bloquées R3"), ("or_registre", "Hypothèses et essais enregistrés"), ("or_diagnostic", "Contrôles observés et blocages"),
        ("or_maj", "Mettre à jour l'armée (sans terminal)"), ("or_journal", "Dernières lignes du journal"),
        ("or_prompt", "Prompt maître : à donner à une IA"),
        ("or_levier", "Fiches de levier x1 à x50"), ("or_bougies", "Les 40 chandeliers mesurés sur l'or"), ("or_bilan", "Bilan historique"), ("or_pause", "Pause des nouvelles positions"),
        ("or_reprise", "Reprise des positions"), ("or_bibliotheque", "Connaissances utilisées"), ("or_aide", "Toutes les commandes")]


def installer_menu(session=None):
    """Menu « / » du bot dédié : tout se pilote d'un doigt depuis le téléphone."""
    if not (config.TELEGRAM_COMMANDES and config.TELEGRAM_JETON):
        return False
    try:
        import requests
        reponse = (session or requests).post(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/setMyCommands",
                                   json={"commands": [{"command": c, "description": d} for c, d in MENU]}, timeout=15)
        return _confirme(reponse)
    except Exception as ex:
        _log.warning("menu Telegram non installé : %s", type(ex).__name__)
        return False



def commandes(session=None):
    """Commandes reçues sur le bot DÉDIÉ uniquement (jamais sur le bot partagé)."""
    if not (config.TELEGRAM_COMMANDES and config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return []
    import requests
    s = session or requests
    decalage = base.lire("telegram_decalage", 0) or 0
    try:
        rep = s.get(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/getUpdates",
                  params={"offset": decalage, "timeout": 0}, timeout=15)
        rep.raise_for_status()
        r = rep.json()
        if not isinstance(r,dict) or r.get("ok") is not True or not isinstance(r.get("result"),list):
            return []
    except Exception:
        return []
    out = []
    dates = []
    identifiants = []
    for u in r.get("result", []):
        if not isinstance(u,dict) or not isinstance(u.get("update_id"),int):
            continue
        if u["update_id"] < decalage:
            continue
        decalage = max(decalage, u["update_id"] + 1)
        msg = u.get("message") or {}
        if not isinstance(msg,dict) or msg.get('forward_origin'):
            continue
        chat = msg.get("chat") or {}
        auteur = msg.get("from") or {}
        if not isinstance(chat,dict) or not isinstance(auteur,dict):
            continue
        # Pilotage privé uniquement : un membre d'un groupe ne peut pas envoyer un ordre.
        if (chat.get("type") != "private" or str(chat.get("id")) != str(config.TELEGRAM_CHAT)
                or str(auteur.get("id")) != str(config.TELEGRAM_CHAT) or auteur.get("is_bot")):
            continue
        date = msg.get("date")
        if not isinstance(date,(int,float)) or not -5 <= time.time()-date <= 120:
            continue
        texte = msg.get("text") or ""
        if not isinstance(texte,str) or len(texte)>256:
            continue
        morceaux=texte.strip().split(maxsplit=1)
        if not morceaux:
            continue
        commande=morceaux[0].split('@',1)[0].lower()
        if re.fullmatch(r'/[a-z0-9_]+',commande):
            out.append(commande+(' '+morceaux[1].strip().lower() if len(morceaux)>1 else ''))
            dates.append(date)
            identifiants.append('telegram:'+str(u['update_id']))
    from . import commandes as file_commandes
    import json
    with base.connexion() as c:
        for texte,identifiant,date in zip(out,identifiants,dates):
            file_commandes.ajouter(texte,identifiant,date,c)
        c.execute("INSERT INTO kv(cle,valeur,maj) VALUES ('telegram_decalage',?,?) "
                  "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur,maj=excluded.maj",
                  (json.dumps(decalage),time.time()))
    return []  # le chef consomme ensuite la file persistante, y compris après une coupure

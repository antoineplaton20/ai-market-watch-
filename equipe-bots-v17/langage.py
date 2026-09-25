"""Textes en langage simple pour Telegram (ce que tu lis sur ton téléphone).
Les codes techniques (METEO, MTF_3/4...) restent dans les journaux du serveur ; ici on les traduit."""
import re

# Chaque « risque pris » ou veto, en une phrase simple
RISQUES = {
    "VOTE_FAIBLE": "l'équipe n'était pas assez d'accord",
    "HORS_ESPECE": "la stratégie habituelle ne voyait pas de signal",
    "COUTS": "le gain espéré couvre mal les frais",
    "GARANTIE": "achat forcé pour continuer à apprendre (aucun achat depuis un moment)",
    "PUMP": "la crypto avait déjà beaucoup monté en 24 h",
    "METEO": "le marché crypto général est en baisse",
    "PEUR_AVIDITE": "les investisseurs sont trop euphoriques ou trop paniqués",
    "CALENDRIER": "une annonce économique importante est proche",
    "ANTI_HYPE": "emballement soudain (volume anormal)",
    "DERIVES_VETO": "les paris à effet de levier sont déséquilibrés",
    "LIQUIDITE_VETO": "peu d'argent frais entre dans les cryptos",
    "MACRO_VETO": "contexte économique défavorable",
    "POSITIONNEMENT_VETO": "trop de parieurs misent déjà sur la hausse",
    "MARCHES_MONDIAUX_VETO": "les bourses mondiales sont nerveuses",
    "ATTENTION_VETO": "engouement inhabituel du grand public",
    "BALEINES_VETO": "les gros portefeuilles vendent",
    "CORRELATION": "ressemble trop à une crypto déjà achetée",
    "RECHERCHE_VETO": "fondamentaux douteux (nouveaux jetons qui vont arriver sur le marché...)",
    "CONTRADICTEUR": "l'IA relectrice a dit non",
    "IA_INDISPONIBLE": "l'IA relectrice n'a pas répondu",
    "VEILLE": "mauvaise nouvelle dans la presse",
    "OPPORTUNITE_VETO": "gain espéré trop faible une fois les frais payés, ou horizons de temps pas d'accord",
    "RISK_ATR": "la crypto bouge trop, ou trop peu",
}

# Les membres de l'équipe, en clair
BOTS = {
    "TENDANCE": "Tendance de fond", "MOMENTUM": "Élan du prix", "MULTI_UNITES": "Accord des horizons de temps",
    "CARNET": "Acheteurs contre vendeurs", "DERIVES": "Marchés à effet de levier", "LIQUIDITE": "Argent frais",
    "MACRO": "Économie", "POSITIONNEMENT": "Position des parieurs", "MARCHES_MONDIAUX": "Bourses mondiales",
    "DEVELOPPEURS": "Activité des développeurs", "BALEINES": "Gros portefeuilles", "CONTRADICTEUR": "IA relectrice",
}

RAISONS_VENTE = {
    "stop-loss": "le prix a touché le seuil de protection",
    "objectif atteint": "objectif atteint",
    "filet de secours": "sécurité : le prix est passé sous le seuil de protection",
    "trop long sans résultat": "rien ne s'est passé dans le temps prévu",
    "vente manuelle": "tu as demandé de tout vendre",
    "sortie anticipée : mauvaise nouvelle": "mauvaise nouvelle dans la presse",
}

NIVEAUX_RISQUE = {"SÛR": "normal", "PRUDENCE": "prudence (achats réduits d'un quart)",
                  "RÉDUCTION": "réduction (achats réduits de moitié)", "ARRÊT": "arrêt (aucun achat)"}

UNITES = {"5m": "5 min", "15m": "15 min", "1h": "1 heure", "4h": "4 heures", "1d": "1 jour", "1w": "1 semaine"}


def risque(code: str) -> str:
    m = re.fullmatch(r"MTF_(\d)/4", code or "")
    if m:
        n = int(m.group(1))
        return ("aucun des 4 horizons de temps n'est à la hausse" if n == 0 else
                f"seulement {n} horizon{'s' if n > 1 else ''} de temps sur 4 à la hausse")
    return RISQUES.get(code, code.replace("_VETO", "").replace("_", " ").lower())


def puces(codes) -> str:
    return "\n".join(f"• {risque(c)}" for c in codes) if codes else "• aucun"


def bot(code: str) -> str:
    return BOTS.get(code, risque(code) if code in RISQUES else code.title())


def raison_vente(raison: str) -> str:
    return RAISONS_VENTE.get(raison, raison)


def nombre(x: float, decimales: int = 2) -> str:
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def prix(x: float) -> str:
    """Prix lisible : 117,26 · 1 581,39 · 0,0001234"""
    if x >= 1:
        return nombre(x, 2)
    return f"{x:.4g}".replace(".", ",")


def dollars(x: float, signe: bool = False) -> str:
    s = nombre(abs(x), 2)
    return (("+" if x >= 0 else "−") if signe else ("−" if x < 0 else "")) + s + " $"


def pct(x: float, decimales: int = 1) -> str:
    return ("+" if x >= 0 else "−") + nombre(abs(x), decimales) + " %"


def fois_risque(r: float) -> str:
    """Un résultat en R : 1 = gagné autant que ce qu'on risquait, −1 = perdu ce qu'on risquait."""
    return ("+" if r >= 0 else "−") + nombre(abs(r), 2) + " × le risque"


def pourcent(fraction: float) -> str:
    """0.82 -> « 82 % »"""
    return f"{fraction * 100:.0f}\u202f%"


def pluriel(n: int, mot: str, pluriel_mot: str = None) -> str:
    return f"{n} {mot if n <= 1 else (pluriel_mot or mot + 's')}"


def toutes_les_heures(h: float) -> str:
    return "chaque heure" if h == 1 else f"toutes les {h:g} h"


EXPLICATION_R = "(1 = gagné autant que ce qu'on risquait · −1 = perdu ce qu'on risquait)"

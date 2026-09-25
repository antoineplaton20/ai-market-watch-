"""Univers OFFICIEL Trade Republic : lecture de la liste publiée par Trade Republic (PDF public).

Sources (dans l'ordre, première réussite retenue) : config.TR_URLS_UNIVERS, ou un PDF déposé sur le
serveur par l'utilisateur. Aucune API privée, aucun identifiant Trade Republic.
Sortie : univers_trade_republic.csv, lu par le registre d'instruments (moteurs/instrument_registry.py).
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import config

_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
_NAVIGATEUR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/126.0 Safari/537.36", "Accept": "application/pdf,*/*"}
ENTETE = ["symbol", "nom", "kind", "currency", "active", "min_order", "fixed_fee", "source"]

# Titres de sections (lignes courtes sans ISIN) -> type d'instrument
_SECTIONS = [
    (re.compile(r"\b(ETF|ETFS|ETC|ETCS|ETN|ETP|FONDS|FUNDS|TRACKERS?)\b", re.I), "etf"),
    (re.compile(r"\b(ACTIONS?|STOCKS?|AKTIEN|EQUITIES|SHARES)\b", re.I), "stock"),
    (re.compile(r"\b(OBLIGATIONS?|BONDS?|ANLEIHEN)\b", re.I), "bond"),
    (re.compile(r"\b(CRYPTOS?|CRYPTO-?MONNAIES|KRYPTO)\b", re.I), "crypto"),
    (re.compile(r"\b(DÉRIVÉS|DERIVES|DERIVATIVES|DERIVATE|WARRANTS|TURBOS?)\b", re.I), "derivative"),
]
# Noms typiques d'émetteurs d'ETF : sert quand le PDF n'a pas de titre de section
_EMETTEURS_ETF = re.compile(r"\b(UCITS|ETF|ETC|ETN|ISHARES|XTRACKERS|AMUNDI|LYXOR|VANGUARD|SPDR|WISDOMTREE|"
                            r"VANECK|INVESCO|HSBC MSCI|FRANKLIN|GLOBAL X|L&G|DEKA|COMSTAGE|BNP PARIBAS EASY|"
                            r"UBS ETF|JPM|FIDELITY|21SHARES|WISDOM TREE)\b", re.I)


def isin_valide(isin: str) -> bool:
    """Clé de contrôle ISIN (norme ISO 6166, algorithme de Luhn)."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin or ""):
        return False
    chiffres = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(chiffres)):
        x = int(ch) * (2 if i % 2 == 0 else 1)
        total += x // 10 + x % 10
    return (10 - total % 10) % 10 == int(isin[-1])


def _section(ligne: str) -> Optional[str]:
    if len(ligne) > 70 or _ISIN.search(ligne):
        return None
    for motif, genre in _SECTIONS:
        if motif.search(ligne):
            return genre
    return None


def analyser_texte(texte: str) -> List[Dict[str, str]]:
    """Extrait (ISIN, nom, type) de chaque ligne. Robuste à l'ordre des colonnes (« ISIN Nom » ou « Nom ISIN »)."""
    lignes, vus, genre = [], set(), None
    for brute in texte.splitlines():
        ligne = " ".join(brute.split())
        if not ligne:
            continue
        s = _section(ligne)
        if s:
            genre = s
            continue
        m = _ISIN.search(ligne)
        if not m or not isin_valide(m.group(1)):
            continue
        isin = m.group(1)
        if isin in vus:
            continue
        nom = (ligne[:m.start()] + " " + ligne[m.end():]).strip(" -|;,\t")
        nom = re.sub(r"\s{2,}", " ", nom)
        g = genre or ("etf" if _EMETTEURS_ETF.search(nom) else "stock")
        vus.add(isin)
        lignes.append({"isin": isin, "nom": nom or isin, "kind": g})
    return lignes


def texte_pdf(contenu: bytes) -> str:
    from pypdf import PdfReader
    lecteur = PdfReader(io.BytesIO(contenu))
    return "\n".join((page.extract_text() or "") for page in lecteur.pages)


def telecharger(urls: Optional[List[str]] = None, timeout: int = 60) -> Tuple[Optional[bytes], str, List[str]]:
    """Essaie chaque source officielle. Renvoie (contenu PDF, url retenue, erreurs rencontrées)."""
    import requests
    erreurs = []
    for url in urls or config.TR_URLS_UNIVERS:
        try:
            r = requests.get(url, headers=_NAVIGATEUR, timeout=timeout)
            if r.status_code == 200 and r.content[:5] == b"%PDF-":
                return r.content, url, erreurs
            erreurs.append(f"{url.rsplit('/', 1)[-1]} : HTTP {r.status_code}")
        except Exception as e:
            erreurs.append(f"{url.rsplit('/', 1)[-1]} : {str(e)[:80]}")
    return None, "", erreurs


def ecrire_csv(instruments: List[Dict[str, str]], fichier: str, source: str) -> None:
    """Écriture atomique. Une liste manuelle existante (sans colonne source) est sauvegardée une fois."""
    if os.path.exists(fichier):
        with open(fichier, encoding="utf-8-sig") as f:
            entete = f.readline()
        manuel = fichier.replace(".csv", "_manuel.csv")
        if "source" not in entete and not os.path.exists(manuel):
            os.replace(fichier, manuel)
    tmp = fichier + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(ENTETE)
        for i in instruments:
            w.writerow([i["isin"], i["nom"], i["kind"], "EUR", "true", 1,
                        config.TRADE_REPUBLIC_SETTLEMENT_FEE_EUR, source])
    os.replace(tmp, fichier)


def mettre_a_jour(fichier: Optional[str] = None, pdf_local: Optional[str] = None) -> Dict:
    """Télécharge (ou lit un PDF local), analyse et écrit l'univers. Ne remplace JAMAIS un univers valide
    par une lecture ratée. Renvoie un résumé pour l'état et Telegram."""
    fichier = fichier or config.UNIVERS_TR_FICHIER
    if pdf_local:
        with open(pdf_local, "rb") as f:
            sources = [(f.read(), os.path.basename(pdf_local), None)]
    else:
        sources = [None] * len(config.TR_URLS_UNIVERS)
    erreurs = []
    for k, src in enumerate(sources):                # chaque source officielle, jusqu'à une lecture valide
        if src is None:
            contenu, url, errs = telecharger([config.TR_URLS_UNIVERS[k]])
            erreurs += errs
            if not contenu:
                continue
            src = (contenu, url, None)
        contenu, source = src[0], src[1].rsplit("/", 1)[-1]
        try:
            instruments = analyser_texte(texte_pdf(contenu))
        except Exception as e:
            erreurs.append(f"{source} : PDF illisible ({str(e)[:80]})")
            continue
        if len(instruments) < config.TR_UNIVERS_MIN:
            erreurs.append(f"{source} : seulement {len(instruments)} titres lus (format du PDF changé ?)")
            continue
        ecrire_csv(instruments, fichier, source)
        par_type = {}
        for i in instruments:
            par_type[i["kind"]] = par_type.get(i["kind"], 0) + 1
        return {"ok": True, "ts": time.time(), "n": len(instruments), "source": source,
                "par_type": par_type, "erreurs_sources": erreurs}
    return {"ok": False, "ts": time.time(),
            "erreur": ("; ".join(erreurs) or "aucune source") + " — ancien univers conservé"}


def lire(fichier: Optional[str] = None) -> List[Dict[str, str]]:
    """Univers actuel : [{"isin", "nom", "kind"}], quelle que soit son origine (officiel ou manuel)."""
    fichier = fichier or config.UNIVERS_TR_FICHIER
    if not os.path.exists(fichier):
        return []
    with open(fichier, encoding="utf-8-sig", newline="") as f:
        return [{"isin": (r.get("symbol") or r.get("isin") or "").strip(), "nom": (r.get("nom") or r.get("name") or "").strip(),
                 "kind": (r.get("kind") or "stock").strip().lower()}
                for r in csv.DictReader(f)
                if (r.get("symbol") or r.get("isin")) and str(r.get("active", "true")).lower() not in {"false", "0", "no"}]

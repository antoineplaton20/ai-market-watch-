"""Sources de la veille marchés : flux RSS publics de presse, banques centrales et institutions.

Uniquement des flux publiés pour être lus par des lecteurs RSS (titres + liens), jamais de contenu payant.
Chaque source est indépendante : une source en panne est signalée et ignorée, les autres continuent.
Les titres sont classés par thème avec des mots-clés (français + anglais), car la plupart des flux sont généralistes.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, Tuple

AGENT = "Mozilla/5.0 (compatible; EquipeBots/17.3; lecteur RSS personnel)"

# (thème principal, nom, adresse). Les thèmes réels de chaque titre sont recalculés par mots-clés.
FLUX: List[Tuple[str, str, str]] = [
    ("banques_centrales", "BCE", "https://www.ecb.europa.eu/rss/press.html"),
    ("banques_centrales", "Réserve fédérale (Fed)", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("economie", "FMI", "https://www.imf.org/en/News/RSS?Language=ENG"),
    ("economie", "Euronews Business", "https://www.euronews.com/rss?level=vertical&name=business"),
    ("economie", "BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("economie", "Le Monde Économie", "https://www.lemonde.fr/economie/rss_full.xml"),
    ("economie", "Investing.com FR Économie", "https://fr.investing.com/rss/news_14.rss"),
    ("geopolitique", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("geopolitique", "BBC Monde", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("geopolitique", "Le Monde International", "https://www.lemonde.fr/international/rss_full.xml"),
    ("defense", "Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("wall_street", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("wall_street", "Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("wall_street", "CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("wall_street", "Investing.com Actions", "https://www.investing.com/rss/news_25.rss"),
    ("europe", "Investing.com FR", "https://fr.investing.com/rss/news.rss"),
    ("europe", "Les Echos Marchés", "https://www.lesechos.fr/rss/rss_finance-marches.xml"),
    ("europe", "BFM Économie", "https://www.bfmtv.com/rss/economie/"),
    ("devises", "Investing.com Forex", "https://www.investing.com/rss/news_1.rss"),
    ("matieres", "Investing.com Matières premières", "https://www.investing.com/rss/news_11.rss"),
    ("energie", "OilPrice", "https://oilprice.com/rss/main"),
    ("crypto", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("crypto", "Cointelegraph", "https://cointelegraph.com/rss"),
]

THEMES = {
    "geopolitique": "🌍 Géopolitique",
    "economie": "📊 Économie mondiale",
    "banques_centrales": "🏦 Banques centrales / taux",
    "wall_street": "🇺🇸 Wall Street",
    "europe": "🇪🇺 Europe / CAC 40",
    "industrie": "🏭 Industrie",
    "energie": "🛢 Énergie",
    "alimentaire": "🌾 Alimentation / agriculture",
    "matieres": "🥇 Métaux / matières premières",
    "devises": "💱 Devises",
    "defense": "🛡 Défense",
    "tech": "💻 Tech / IA",
    "crypto": "₿ Crypto",
    "experts": "🎓 Avis des banques et analystes",
    "social": "✊ Social (grèves, manifestations)",
    "sante": "🦠 Santé / épidémies",
    "climat": "🌪 Climat / catastrophes",
}

MOTS = {
    "geopolitique": ["war", "guerre", "sanction", "tariff", "droits de douane", "missile", "invasion", "ceasefire",
                     "cessez-le-feu", "nato", "otan", "ukraine", "russia", "russie", "iran", "israel", "gaza", "taiwan",
                     "china", "chine", "election", "élection", "coup d'état", "embargo", "g7", "g20", "united nations",
                     "onu", "diplomat", "trade war", "guerre commerciale"],
    "economie": ["inflation", "gdp", "pib", "recession", "récession", "growth", "croissance", "unemployment", "chômage",
                 "jobs report", "emploi", "consumer", "consommation", "retail sales", "deficit", "déficit", "debt",
                 "dette", "imf", "fmi", "world bank", "banque mondiale", "cpi", "economy", "économie"],
    "banques_centrales": ["fed", "federal reserve", "réserve fédérale", "ecb", "bce", "lagarde", "powell",
                          "interest rate", "taux directeur", "rate cut", "rate hike", "baisse des taux",
                          "hausse des taux", "bank of england", "bank of japan", "boj", "treasury yield",
                          "rendement", "obligataire", "bond"],
    "wall_street": ["wall street", "s&p 500", "s&p500", "nasdaq", "dow jones", "nyse", "earnings", "résultats",
                    "stocks", "shares"],
    "europe": ["cac 40", "cac40", "euronext", "bourse de paris", "stoxx", "dax", "ftse", "europe", "européen",
               "zone euro", "eurozone"],
    "industrie": ["pmi", "industrial", "industriel", "manufactur", "usine", "factory", "supply chain",
                  "chaîne d'approvisionnement", "semiconductor", "semi-conducteur", "steel", "acier", "automaker",
                  "automobile", "aerospace", "aéronautique", "chip"],
    "energie": ["oil", "pétrole", "crude", "brut", "opec", "opep", "natural gas", "gaz", "lng", "gnl", "diesel",
                "refin", "raffin", "electricity", "électricité", "nuclear", "nucléaire", "energy", "énergie"],
    "alimentaire": ["food", "alimentaire", "wheat", "blé", "corn", "maïs", "soy", "soja", "crop", "récolte",
                    "harvest", "fertilizer", "engrais", "cocoa", "cacao", "coffee", "café", "sugar", "sucre", "fao",
                    "agricult", "famine", "drought", "sécheresse", "rice", "riz"],
    "matieres": ["gold", "cours de l'or", "prix de l'or", "silver", "argent métal", "copper", "cuivre", "lithium", "nickel",
                 "iron ore", "minerai", "commodit", "matières premières", "aluminium", "platinum", "platine"],
    "devises": ["dollar", "euro", "eur/usd", "yen", "yuan", "sterling", "livre sterling", "forex", "currency",
                "devise", "franc suisse", "swiss franc", "dxy"],
    "defense": ["defense", "défense", "military", "militaire", "armement", "weapons", "army", "armée", "navy",
                "marine nationale", "drone", "fighter jet", "rheinmetall", "thales", "dassault", "safran",
                "lockheed", "raytheon"],
    "tech": ["artificial intelligence", "intelligence artificielle", "generative ai", "ai chip", "nvidia", "microsoft", "apple",
             "alphabet", "google", "amazon", "meta", "openai", "cloud", "data center", "tesla", "software"],
    "crypto": ["bitcoin", "crypto", "ethereum", "ether", "blockchain", "stablecoin", "binance", "solana"],
    "experts": ["goldman", "jpmorgan", "morgan stanley", "bank of america", "citi", "ubs", "barclays", "hsbc",
                "blackrock", "bnp paribas", "société générale", "deutsche bank", "analyst", "analyste",
                "upgrade", "downgrade", "relève", "abaisse", "price target", "objectif de cours", "strategist",
                "stratégiste", "outlook", "prévision", "forecast", "recommandation"],
    "social": ["strike", "grève", "greve", "protest", "manifestation", "riot", "émeute", "unrest", "syndicat",
               "labor union", "walkout", "blocage", "boycott", "mouvement social"],
    "sante": ["pandemic", "pandémie", "outbreak", "épidémie", "epidemic", "virus", "bird flu", "grippe aviaire",
              "who", "oms", "vaccine", "vaccin", "quarantine", "quarantaine"],
    "climat": ["earthquake", "séisme", "hurricane", "ouragan", "typhoon", "typhon", "cyclone", "flood", "inondation",
               "wildfire", "incendie", "heatwave", "canicule", "tsunami", "volcan", "eruption", "storm", "tempête",
               "el nino", "el niño", "climate", "climat"],
}


def _norm(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def _motif(mot: str):
    """Mot court (<= 4 lettres) : mot entier. Mot long : début de mot (« manufactur » trouve « manufacturing »)."""
    m = re.escape(_norm(mot))
    return re.compile(rf"(?<![a-z0-9]){m}(?![a-z0-9])" if len(mot.strip()) <= 4 else rf"(?<![a-z0-9]){m}")


_MOTIFS = {theme: [_motif(m) for m in mots] for theme, mots in MOTS.items()}


def themes_du_titre(titre: str, defaut: Optional[str] = None) -> List[str]:
    t = _norm(titre)
    trouves = [theme for theme, motifs in _MOTIFS.items() if any(m.search(t) for m in motifs)]
    if not trouves and defaut:
        trouves = [defaut]
    return trouves


def _texte(el) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", (el.text or "") if el is not None else "")).strip()


def _date(texte: str) -> Optional[float]:
    texte = (texte or "").strip()
    if not texte:
        return None
    try:
        return parsedate_to_datetime(texte).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = dt.datetime.fromisoformat(texte.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except ValueError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def analyser_flux(contenu: bytes, source: str, theme: str, maintenant: Optional[float] = None) -> List[Dict]:
    """RSS 2.0, RSS 1.0 (RDF) ou Atom -> [{titre, lien, source, ts, themes}]."""
    maintenant = maintenant or time.time()
    racine = ET.fromstring(contenu)
    articles = []
    for el in racine.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        champs = {_local(c.tag): c for c in el}
        titre = _texte(champs.get("title"))
        if not titre:                                   # réseaux sociaux (Mastodon) : pas de titre, juste le texte
            corps = next((champs[k] for k in ("description", "summary", "content") if k in champs), None)
            titre = _texte(corps)[:220]
        if not titre:
            continue
        lien_el = champs.get("link")
        lien = ""
        if lien_el is not None:
            lien = (lien_el.text or lien_el.get("href") or "").strip()
        ts = None
        for nom in ("pubDate", "published", "updated", "date"):
            if nom in champs:
                ts = _date(champs[nom].text or "")
                if ts:
                    break
        ts = min(ts or maintenant, maintenant)
        articles.append({"titre": titre[:300], "lien": lien, "source": source, "ts": ts,
                         "themes": themes_du_titre(titre, theme)})
    return articles


def _get(url: str, timeout: int = 15):
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": AGENT, "Accept": "application/rss+xml, "
                                                                                   "application/xml, text/xml, */*"})
    r.raise_for_status()
    return r.content


def collecter(flux: Optional[List[Tuple[str, str, str]]] = None, lire: Optional[Callable] = None,
              age_max_h: float = 48, pause_s: float = 0.3) -> Tuple[List[Dict], Dict[str, str]]:
    """Lit toutes les sources. Renvoie (articles récents sans doublon, état par source)."""
    flux = FLUX if flux is None else flux
    lire = lire or _get
    maintenant = time.time()
    limite = maintenant - age_max_h * 3600
    tous, etat, vus = [], {}, set()
    for theme, nom, url in flux:
        try:
            articles = analyser_flux(lire(url), nom, theme, maintenant)
            recents = [a for a in articles if a["ts"] >= limite]
            etat[nom] = f"ok ({len(recents)})"
            for a in recents:
                cle = _norm(a["titre"])[:120]
                if cle not in vus:
                    vus.add(cle)
                    tous.append(a)
        except Exception as e:                       # une source en panne n'arrête pas la veille
            etat[nom] = f"ko : {type(e).__name__} {str(e)[:80]}"
        if pause_s:
            time.sleep(pause_s)
    tous.sort(key=lambda a: -a["ts"])
    return tous, etat


def par_theme(articles: List[Dict], n: int = 12) -> Dict[str, List[Dict]]:
    res = {t: [] for t in THEMES}
    for a in articles:
        for t in a["themes"]:
            if t in res and len(res[t]) < n:
                res[t].append(a)
    return res


# ------------------------------------------------------------------ actualité d'un titre (Yahoo Finance)
def actus_yahoo(brut: List[Dict], maintenant: Optional[float] = None, age_max_j: float = 7) -> List[Dict]:
    """Normalise Ticker.news de yfinance (ancien et nouveau format) -> [{titre, source, ts}]."""
    maintenant = maintenant or time.time()
    res = []
    for n in brut or []:
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        titre = (c.get("title") or "").strip()
        if not titre:
            continue
        ts = c.get("providerPublishTime") or _date(c.get("pubDate") or c.get("displayTime") or "")
        fournisseur = c.get("provider") or {}
        source = fournisseur.get("displayName") if isinstance(fournisseur, dict) else None
        source = source or c.get("publisher") or "Yahoo Finance"
        ts = float(ts) if ts else maintenant
        if ts >= maintenant - age_max_j * 86400:
            res.append({"titre": titre[:300], "source": source, "ts": ts})
    return res


def mentionnant(articles: List[Dict], nom: str, ticker: str = "") -> List[Dict]:
    """Titres de la presse générale qui citent ce nom (ex. « LVMH », « Airbus »)."""
    mots = [m for m in {_norm(nom).split(" ")[0] if nom else "", ticker.split(".")[0].split("-")[0].lower()}
            if len(m) >= 4]
    return [a for a in articles if any(re.search(rf"\b{re.escape(m)}\b", _norm(a["titre"])) for m in mots)]

"""L'ARMÉE DE RENSEIGNEMENT : chaque bot a UNE mission (une famille de sources) et un rythme.

Familles :
- presse     : flux RSS publics (banques centrales, FMI, ONU, presse éco FR / monde, Wall Street, énergie, défense, crypto)
- monde      : GDELT (projet qui surveille la presse de tous les pays, dans plus de 100 langues, mise à jour toutes les
               15 min) — un bot par thème : géopolitique, économie, taux, alimentation, énergie, social, industrie,
               tech, défense, santé, climat, crypto, marchés français
- ton        : GDELT, ton moyen de la presse mondiale par thème (ce qui change sur 6 h par rapport à 3 jours)
- terrain    : séismes (USGS) et catastrophes (GDACS : inondations, cyclones, sécheresses...)
- foule      : marchés de prédiction (Polymarket : probabilités d'événements économiques et géopolitiques)
- social     : Mastodon (hashtags économie, bourse, bitcoin, inflation...)
- de près    : un bot qui cherche dans la presse mondiale chaque actif suivi par nos bots de trading

Un bot renvoie des « faits » : {titre, lien, source, ts, themes, actifs, ton?, importance?}.
Tout est public, gratuit et lu avec des pauses : l'armée ne se fait pas bannir et ne surcharge personne.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from moteurs import sources_marches as S

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
PAUSE_GDELT_S = 6                    # GDELT demande de ne pas l'interroger plus d'une fois toutes les 5 s
LANGUES = "(sourcelang:english OR sourcelang:french)"

FLUX_EN_PLUS: List[Tuple[str, str, str]] = [
    ("banques_centrales", "Banque d'Angleterre", "https://www.bankofengland.co.uk/rss/news"),
    ("geopolitique", "ONU Info", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    ("crypto", "Decrypt", "https://decrypt.co/feed"),
]
MASTODON = ["economy", "stocks", "bitcoin", "inflation", "geopolitics", "finance", "economie", "bourse"]

REQUETES_GDELT = {
    "geopolitique": '(war OR sanctions OR invasion OR ceasefire OR "military strike" OR tariffs)',
    "economie": '(recession OR inflation OR "economic growth" OR unemployment OR "consumer confidence")',
    "banques_centrales": '("central bank" OR "interest rates" OR "Federal Reserve" OR "European Central Bank")',
    "alimentaire": '("food prices" OR wheat OR famine OR "crop failure" OR fertilizer OR "food security")',
    "energie": '("oil price" OR OPEC OR "natural gas" OR "power outage" OR refinery)',
    "social": '(strike OR protest OR riots OR "general strike" OR unrest)',
    "industrie": '("supply chain" OR semiconductor OR "factory output" OR PMI OR shipping)',
    "tech": '("artificial intelligence" OR Nvidia OR "chip export" OR cyberattack)',
    "defense": '(NATO OR "defense spending" OR "arms deal" OR missile)',
    "sante": '(pandemic OR outbreak OR epidemic OR "bird flu")',
    "climat": '(earthquake OR hurricane OR flood OR wildfire OR typhoon OR heatwave)',
    "crypto": '(bitcoin OR ethereum OR "crypto regulation" OR stablecoin)',
    "europe": '("CAC 40" OR "Bourse de Paris" OR Euronext OR "Stoxx 600")',
}

CRYPTOS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
           "DOGE": "dogecoin", "LINK": "chainlink", "DOT": "polkadot", "LTC": "litecoin", "AVAX": "avalanche",
           "BNB": "binance coin", "TRX": "tron"}
GRANDS_NOMS = {"MC.PA": "LVMH", "TTE.PA": "TotalEnergies", "AIR.PA": "Airbus", "SU.PA": "Schneider Electric",
               "OR.PA": "L'Oréal", "SAN.PA": "Sanofi", "AI.PA": "Air Liquide", "BNP.PA": "BNP Paribas",
               "SAF.PA": "Safran", "HO.PA": "Thales", "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia",
               "AMZN": "Amazon", "GOOGL": "Alphabet", "META": "Meta Platforms", "TSLA": "Tesla"}
SPORTS = re.compile(r"\b(vs\.?|spread|o/u|win on|nba|nfl|nhl|mlb|premier league|champions league|match|game \d|"
                    r"grand prix|tennis|ufc|world series|super bowl|masters)\b", re.I)
DANGER = ["declares war", "déclare la guerre", "invasion", "invades", "nuclear strike", "coup d'état", "coup attempt",
          "default", "défaut de paiement", "bankruptcy", "faillite", "hacked", "hack", "exploit", "crash", "krach",
          "emergency rate", "sanctions", "embargo", "collapse", "effondrement", "pandemic", "pandémie",
          "martial law", "loi martiale", "terror", "attentat", "blackout", "delist", "halts withdrawals",
          "suspends withdrawals", "bank run", "tsunami"]


@dataclass
class Bot:
    nom: str
    famille: str
    periode_min: float
    collecte: Callable[["Contexte"], Tuple[List[Dict], Dict[str, float]]]


class Contexte:
    """Outils partagés par les bots : lecture HTTP polie (ETag / If-Modified-Since), GDELT sérialisé, actifs suivis."""

    def __init__(self, lire: Optional[Callable] = None, gdelt_json: Optional[Callable] = None,
                 actifs: Optional[Callable] = None, pause_gdelt_s: float = PAUSE_GDELT_S):
        self._lire = lire
        self._gdelt = gdelt_json
        self._actifs = actifs or (lambda: [])
        self._verrou_gdelt = threading.Lock()
        self._dernier_gdelt = 0.0
        self.pause_gdelt_s = pause_gdelt_s
        self._cache_http: Dict[str, Tuple[str, str]] = {}

    def lire(self, url: str) -> Optional[bytes]:
        """Contenu, ou None si rien de neuf depuis la dernière lecture (réponse 304)."""
        if self._lire:
            return self._lire(url)
        import requests
        entetes = {"User-Agent": S.AGENT}
        etag, modif = self._cache_http.get(url, ("", ""))
        if etag:
            entetes["If-None-Match"] = etag
        if modif:
            entetes["If-Modified-Since"] = modif
        r = requests.get(url, timeout=20, headers=entetes)
        if r.status_code == 304:
            return None
        r.raise_for_status()
        self._cache_http[url] = (r.headers.get("ETag", ""), r.headers.get("Last-Modified", ""))
        return r.content

    def gdelt(self, params: Dict) -> Dict:
        with self._verrou_gdelt:                              # une requête GDELT à la fois, espacées
            attente = self._dernier_gdelt + self.pause_gdelt_s - time.time()
            if attente > 0:
                time.sleep(attente)
            try:
                if self._gdelt:
                    return self._gdelt(params)
                import requests
                r = requests.get(GDELT, params={**params, "format": "json"}, timeout=30,
                                 headers={"User-Agent": S.AGENT})
                r.raise_for_status()
                texte = r.text.strip()
                if not texte.startswith("{"):                 # GDELT répond en texte quand la requête est refusée
                    raise ValueError(texte[:120])
                return json.loads(texte)
            finally:
                self._dernier_gdelt = time.time()

    def actifs_suivis(self) -> List[Tuple[str, str]]:
        return self._actifs()


# ================================ BOTS « PRESSE » ================================
def _bot_presse(nom: str, flux: List[Tuple[str, str, str]]):
    def collecte(ctx: Contexte):
        faits, erreurs = [], []
        for theme, source, url in flux:
            try:
                contenu = ctx.lire(url)
                if contenu:
                    faits += S.analyser_flux(contenu, source, theme)
            except Exception as e:
                erreurs.append(f"{source}: {type(e).__name__}")
        if erreurs and not faits:
            raise RuntimeError("; ".join(erreurs)[:200])
        return faits, {}
    return Bot(nom, "presse", 15, collecte)


def bots_presse() -> List[Bot]:
    groupes: Dict[str, List] = {}
    for f in S.FLUX + FLUX_EN_PLUS:
        groupes.setdefault(f[0], []).append(f)
    bots = [_bot_presse(f"Presse · {S.THEMES.get(t, t)}", g) for t, g in groupes.items()]
    social = [("social", f"Mastodon #{h}", f"https://mastodon.social/tags/{h}.rss") for h in MASTODON]
    b = _bot_presse("Réseaux sociaux · Mastodon", social)
    b.famille = "social"
    return bots + [b]


# ================================ BOTS « MONDE » (GDELT) ================================
def _date_gdelt(s: str) -> Optional[float]:
    try:
        return dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def articles_gdelt(data: Dict, theme: Optional[str] = None, actifs: Optional[List[str]] = None) -> List[Dict]:
    faits = []
    for a in (data or {}).get("articles") or []:
        titre = (a.get("title") or "").strip()
        if not titre:
            continue
        themes = S.themes_du_titre(titre, theme)
        faits.append({"titre": titre[:300], "lien": a.get("url", ""), "source": a.get("domain") or "GDELT",
                      "ts": _date_gdelt(a.get("seendate")) or time.time(), "themes": themes,
                      "actifs": list(actifs or [])})
    return faits


def _bot_gdelt(theme: str, requete: str):
    def collecte(ctx: Contexte):
        data = ctx.gdelt({"query": f"{requete} {LANGUES}", "mode": "artlist", "maxrecords": 75,
                          "timespan": "30min", "sort": "datedesc"})
        return articles_gdelt(data, theme), {}
    return Bot(f"Monde · {S.THEMES.get(theme, theme)}", "monde", 15, collecte)


def ton_gdelt(data: Dict) -> Optional[float]:
    """Ton des 6 dernières heures comparé aux 3 derniers jours, ramené de -2 à +2."""
    try:
        points = [(p["date"], float(p["value"])) for p in data["timeline"][0]["data"]]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if len(points) < 12:
        return None
    points.sort()
    valeurs = [v for _, v in points]
    recent = sum(valeurs[-6:]) / 6 if len(valeurs) >= 6 else valeurs[-1]
    moyenne = sum(valeurs) / len(valeurs)
    return max(-2.0, min(2.0, (recent - moyenne) / 0.75))


def bot_ton():
    etat = {"i": 0}

    def collecte(ctx: Contexte):
        themes = list(REQUETES_GDELT)
        signaux = {}
        for _ in range(3):                                   # 3 thèmes par passage, chacun revu toutes les ~1 h 15
            t = themes[etat["i"] % len(themes)]
            etat["i"] += 1
            v = ton_gdelt(ctx.gdelt({"query": f"{REQUETES_GDELT[t]} {LANGUES}", "mode": "timelinetone",
                                     "timespan": "3d"}))
            if v is not None:
                signaux[f"gdelt:{t}"] = v
        return [], signaux
    return Bot("Monde · ton de la presse mondiale", "ton", 15, collecte)


# ================================ TERRAIN ================================
def seismes(data: Dict) -> List[Dict]:
    faits = []
    for f in (data or {}).get("features") or []:
        p = f.get("properties") or {}
        mag, alerte = p.get("mag") or 0, (p.get("alert") or "").lower()
        if mag < 6 and alerte not in ("orange", "red"):
            continue
        imp = 3 if (mag >= 7.5 or alerte == "red") else (2 if (mag >= 6.5 or alerte == "orange") else 1)
        faits.append({"titre": f"Séisme de magnitude {mag:.1f} : {p.get('place', '?')}"
                               + (" (alerte tsunami)" if p.get("tsunami") else ""),
                      "lien": p.get("url", ""), "source": "USGS", "ts": (p.get("time") or 0) / 1000 or time.time(),
                      "themes": ["climat"], "actifs": [], "ton": -2 if imp == 3 else -1, "importance": imp})
    return faits


def bot_seismes():
    def collecte(ctx: Contexte):
        c = ctx.lire("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
        return (seismes(json.loads(c)) if c else []), {}
    return Bot("Terrain · séismes (USGS)", "terrain", 15, collecte)


def catastrophes(contenu: bytes) -> List[Dict]:
    import xml.etree.ElementTree as ET
    faits = []
    for item in ET.fromstring(contenu).iter("item"):
        champs = {c.tag.rsplit("}", 1)[-1].lower(): (c.text or "").strip() for c in item}
        niveau = champs.get("alertlevel", "").lower()
        if niveau not in ("orange", "red"):
            continue
        imp = 3 if niveau == "red" else 2
        faits.append({"titre": f"Alerte {'ROUGE' if imp == 3 else 'orange'} GDACS : {champs.get('title', '?')}",
                      "lien": champs.get("link", ""), "source": "GDACS", "ts": S._date(champs.get("pubdate", ""))
                      or time.time(), "themes": ["climat"], "actifs": [], "ton": -2 if imp == 3 else -1,
                      "importance": imp})
    return faits


def bot_catastrophes():
    def collecte(ctx: Contexte):
        c = ctx.lire("https://www.gdacs.org/xml/rss.xml")
        return (catastrophes(c) if c else []), {}
    return Bot("Terrain · catastrophes (GDACS)", "terrain", 15, collecte)


# ================================ FOULE (prédictions) ================================
def predictions(marches: List[Dict]) -> List[Dict]:
    faits = []
    for m in marches or []:
        q = (m.get("question") or "").strip()
        if not q or SPORTS.search(q):
            continue
        themes = S.themes_du_titre(q)
        if not themes:
            continue
        try:
            issues = json.loads(m.get("outcomes") or "[]")
            prix = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        except (ValueError, TypeError):
            continue
        if not issues or len(issues) != len(prix):
            continue
        variation = float(m.get("oneDayPriceChange") or 0)
        faits.append({"titre": f"Marché de prédiction : « {q} » → {issues[0]} {prix[0] * 100:.0f} % "
                               f"({variation * 100:+.0f} pts sur 24 h)",
                      "lien": f"https://polymarket.com/market/{m.get('slug', '')}", "source": "Polymarket",
                      "ts": time.time(), "themes": themes, "actifs": [],
                      "importance": 2 if abs(variation) >= 0.10 else 1})
    return faits


def bot_predictions():
    def collecte(ctx: Contexte):
        c = ctx.lire("https://gamma-api.polymarket.com/markets?limit=200&active=true&closed=false"
                     "&order=volume24hr&ascending=false")
        return (predictions(json.loads(c)) if c else []), {}
    return Bot("Foule · marchés de prédiction", "foule", 30, collecte)


# ================================ DE PRÈS (actifs suivis) ================================
def requete_actif(nom: str) -> str:
    nom = re.sub(r"\b(SA|SE|NV|AG|PLC|INC|CORP|CORPORATION|LTD|GROUP|HOLDING|CLASS [A-Z]|ORDINARY SHARES)\b\.?", "",
                 nom or "", flags=re.I)
    mots = [m for m in re.split(r"\s+", nom.strip()) if m][:3]
    return f'"{" ".join(mots)}"' if mots else ""


def bot_de_pres():
    etat = {"i": 0}

    def collecte(ctx: Contexte):
        actifs = ctx.actifs_suivis()
        faits = []
        for _ in range(min(2, len(actifs))):                # 2 actifs par passage (10 min) : chacun revu régulièrement
            cle, nom = actifs[etat["i"] % len(actifs)]
            etat["i"] += 1
            q = requete_actif(nom)
            if not q:
                continue
            data = ctx.gdelt({"query": f"{q} {LANGUES}", "mode": "artlist", "maxrecords": 25, "timespan": "24h",
                              "sort": "datedesc"})
            faits += articles_gdelt(data, None, [cle])
        return faits, {}
    return Bot("De près · actifs suivis par nos bots", "de_pres", 10, collecte)


def armee() -> List[Bot]:
    return (bots_presse() + [_bot_gdelt(t, q) for t, q in REQUETES_GDELT.items()]
            + [bot_ton(), bot_seismes(), bot_catastrophes(), bot_predictions(), bot_de_pres()])


# ================================ ANALYSE D'UN FAIT ================================
def importance_lexicale(titre: str, themes: List[str]) -> int:
    t = S._norm(titre)
    if any(S._norm(m) in t for m in DANGER):
        return 2
    return 1 if themes else 0


def reperer_actifs(titre: str, repertoire: Dict[str, List[str]]) -> List[str]:
    """repertoire : actif -> noms (« BTC » -> ["bitcoin", "btc"]) ; renvoie les actifs cités dans le titre."""
    t = S._norm(titre)
    trouves = []
    for actif, noms in repertoire.items():
        for n in noms:
            n = S._norm(n)
            if len(n) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", t):
                trouves.append(actif)
                break
    return trouves

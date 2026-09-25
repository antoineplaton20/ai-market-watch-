"""RECHERCHE FONDAMENTALE HEBDOMADAIRE (lente). Lancement : python recherche.py (automatique le dimanche).
Elle sert UNIQUEMENT de veto : elle peut empêcher un achat, jamais en provoquer un.

Sources (gratuites, datées dans chaque fiche) :
- CoinGecko : capitalisation, valorisation totale diluée, offre en circulation / totale / maximale
- DefiLlama : TVL et son évolution sur 7 jours, frais et revenus des protocoles sur 30 jours
- deblocages.csv (tenu à la main) : dates de déblocage de jetons. Les calendriers fiables de
  déblocages sont payants : aucune source gratuite vérifiable n'a été trouvée, d'où ce fichier.

Chaque chiffre porte sa source et sa date. Les thèses rédigées par l'IA sont étiquetées ESTIMATION."""
import csv
import datetime as dt
import json
import os
import requests
import config
import donnees
import registre

FICHIER = "recherche_hebdo.json"
FICHIER_DEBLOCAGES = "deblocages.csv"
LLAMA = "https://api.llama.fi"


# ================================ COLLECTE ================================
def marches_coingecko():
    pages = []
    for page in (1, 2):
        pages += donnees._cg("/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc",
                                                 "per_page": 250, "page": page})
    return pages


def protocoles_defillama():
    return requests.get(f"{LLAMA}/protocols", timeout=30).json()


def frais_defillama(type_donnee):
    j = requests.get(f"{LLAMA}/overview/fees", params={"excludeTotalDataChart": "true",
                                                         "excludeTotalDataChartBreakdown": "true",
                                                         "dataType": type_donnee}, timeout=30).json()
    return {str(p.get("name", "")).lower(): p for p in j.get("protocols", [])}


def deblocages():
    """deblocages.csv : symbole;date (AAAA-MM-JJ);pourcentage de l'offre totale débloqué."""
    res = {}
    if not os.path.exists(FICHIER_DEBLOCAGES):
        return res
    with open(FICHIER_DEBLOCAGES, encoding="utf-8") as f:
        for ligne in csv.reader(f, delimiter=";"):
            if len(ligne) < 3 or ligne[0].startswith("#") or ligne[0].lower() == "symbole":
                continue
            try:
                res.setdefault(ligne[0].strip().upper(), []).append(
                    (dt.date.fromisoformat(ligne[1].strip()), float(ligne[2].replace(",", "."))))
            except ValueError:
                continue
    return res


# ================================ ANALYSE ================================
def fiche(c, proto, frais, revenus, debl, aujourdhui):
    """Fiche déterministe d'une crypto : chiffres, sources, verdict (EXCLU / OBSERVATION / RAS)."""
    circ, total, maxi = c.get("circulating_supply"), c.get("total_supply"), c.get("max_supply")
    denom = maxi or total
    ratio = (circ / denom) if circ and denom else None
    f = {"symbole": c["symbol"].upper(), "nom": c.get("name"), "capitalisation": c.get("market_cap"),
         "valorisation_diluee": c.get("fully_diluted_valuation"), "offre_en_circulation_pct": ratio,
         "sources": {"marché": f"CoinGecko, {aujourdhui}"}, "raisons": [], "alertes": []}
    if ratio is not None and ratio < config.RECHERCHE_DILUTION_MIN:
        f["raisons"].append(f"seulement {ratio:.0%} de l'offre en circulation : forte dilution à venir")
    if proto:
        f["tvl"], f["tvl_7j_pct"] = proto.get("tvl"), proto.get("change_7d")
        f["sources"]["tvl"] = f"DefiLlama, {aujourdhui}"
        if f["tvl_7j_pct"] is not None and f["tvl_7j_pct"] <= config.RECHERCHE_TVL_CHUTE_7J:
            f["raisons"].append(f"TVL {f['tvl_7j_pct']:+.0f} % en 7 jours : les utilisateurs partent")
        nom = str(proto.get("name", "")).lower()
        f["frais_30j"] = (frais.get(nom) or {}).get("total30d")
        f["revenus_30j"] = (revenus.get(nom) or {}).get("total30d")
        if f["frais_30j"] is not None:
            f["sources"]["frais"] = f"DefiLlama (période : 30 jours glissants), {aujourdhui}"
        if not f["revenus_30j"]:
            f["alertes"].append("aucun revenu mesuré : la valeur ne revient pas forcément au jeton")
        elif f.get("capitalisation"):
            f["capitalisation_sur_revenus_annuels"] = f["capitalisation"] / (f["revenus_30j"] * 12)
    for jour, pct in debl.get(f["symbole"], []):
        if 0 <= (jour - aujourdhui).days <= 14 and pct >= config.RECHERCHE_DEBLOCAGE_PCT:
            f["raisons"].append(f"déblocage de {pct:.1f} % de l'offre le {jour} (deblocages.csv)")
    f["verdict"] = "EXCLU" if f["raisons"] else ("OBSERVATION" if f["alertes"] else "RAS")
    return f


PROMPT_THESE = """Tu es l'analyste fondamental d'une équipe de trading prudente. Rédige une fiche courte sur {nom} ({symbole})
en t'appuyant UNIQUEMENT sur les chiffres ci-dessous. N'invente aucun chiffre, aucun événement, aucune date.
Tout ce qui n'est pas dans les données est une ESTIMATION et doit être étiqueté comme tel.

Données (avec leurs sources) :
{donnees}

Réponds UNIQUEMENT en JSON valide :
{{"these": "...", "mecanisme": "...", "cas_haussier": "...", "cas_central": "...", "cas_baissier": "...",
"invalidation": "ce qui prouverait que la thèse est fausse", "inconnues": "...", "etiquette": "ESTIMATION"}}"""


def these_ia(f):
    from equipe import ia_json
    return ia_json(config.MODELE_IA_VEILLE, PROMPT_THESE.format(
        nom=f["nom"], symbole=f["symbole"], donnees=json.dumps(f, ensure_ascii=False, default=str)), max_tokens=700)


def analyser(marches, protocoles, frais, revenus, debl, aujourdhui):
    par_gecko = {p.get("gecko_id"): p for p in protocoles if p.get("gecko_id")}
    fiches = {}
    for c in marches:
        f = fiche(c, par_gecko.get(c.get("id")), frais, revenus, debl, aujourdhui)
        fiches.setdefault(f["symbole"], f)             # en cas de doublon de symbole : la plus grosse capitalisation
    return fiches


def main():
    aujourdhui = dt.date.today()
    fiches = analyser(marches_coingecko(), protocoles_defillama(), frais_defillama("dailyFees"),
                      frais_defillama("dailyRevenue"), deblocages(), aujourdhui)
    if config.ANTHROPIC_API_KEY:                      # thèses rédigées pour les 5 plus grosses non exclues
        for f in [x for x in fiches.values() if x["verdict"] != "EXCLU"][:5]:
            f["these_ia"] = these_ia(f)
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"date": aujourdhui.isoformat(), "fiches": fiches}, fh, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, FICHIER)
    exclus = {s: f["raisons"] for s, f in fiches.items() if f["verdict"] == "EXCLU"}
    registre.ajouter("recherche", {"date": aujourdhui.isoformat(), "fiches": len(fiches), "exclus": exclus})
    resume = "\n".join(f"• {s} : {r[0]}" for s, r in list(exclus.items())[:15])
    message = (f"🔬 Recherche fondamentale du {aujourdhui} : {len(fiches)} cryptos analysées, "
               f"{len(exclus)} exclues des achats.\n{resume}")
    print(message)
    try:
        from alertes import alerte
        alerte(message, important=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()

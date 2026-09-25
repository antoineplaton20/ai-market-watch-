"""RÉCONCILIATION : ce que le bot croit détenir correspond-il à ce qu'il y a vraiment sur Binance ?
Au démarrage puis toutes les heures. Corrige ce qui peut l'être sans risque, signale le reste."""
import config
import gardien as G
from alertes import alerte, log

PREFIXE = "eqb"          # tous les stops posés par le bot ont un identifiant qui commence ainsi


def _ordre(ex, oid, sym):
    try:
        return ex.fetch_order(oid, sym)
    except Exception:
        return None


def reconcilier(ex, etat, au_demarrage=False):
    rapport = []
    solde = ex.fetch_balance()
    total = solde.get("total") or {}
    for sym in list(etat["positions"]):
        p = etat["positions"][sym]
        base = ex.markets[sym]["base"]
        detenu = float(total.get(base, 0) or 0)
        prix = float(ex.fetch_ticker(sym)["bid"])
        o = _ordre(ex, p["id_stop"], sym) if p["id_stop"] != "aucun" else None

        # 0. Testnet remis à zéro (tous les mois chez Binance) : l'ordre n'existe plus du tout
        if config.MODE == "testnet" and o is None and p["id_stop"] != "aucun":
            del etat["positions"][sym]
            rapport.append(f"{sym} : testnet réinitialisé par Binance, position retirée (hors statistiques)")
            continue

        # 1. Stop exécuté pendant une coupure, ou plus rien sur Binance (vente manuelle)
        if (o and o["status"] == "closed") or detenu * prix < 5:
            sortie = float(o.get("average") or o.get("price") or prix) if o and o["status"] == "closed" else prix
            G.cloturer(etat, sym, sortie, "clôturée pendant une coupure")
            rapport.append(f"{sym} : n'est plus détenue sur Binance, position clôturée dans le journal")
            continue

        # 2. Quantité inférieure à ce que le bot croit (vente manuelle partielle, frais)
        corrige = False
        if detenu < p["quantite"] * 0.98:
            rapport.append(f"{sym} : quantité corrigée {p['quantite']:.6g} → {detenu:.6g}")
            p["quantite"] = detenu
            corrige = True

        # 3. Stop absent, annulé ou à la mauvaise quantité
        if not o or o["status"] in ("canceled", "expired", "rejected") or corrige:
            if prix <= p["stop"]:
                G.vendre(ex, sym, etat, "stop dépassé pendant une coupure")
                rapport.append(f"{sym} : prix sous le stop, position vendue par sécurité")
                continue
            if o and o["status"] == "open":
                try:
                    ex.cancel_order(p["id_stop"], sym)
                except Exception:
                    pass
            try:
                p["id_stop"] = G.poser_stop(ex, sym, p["quantite"], p["stop"])
                rapport.append(f"{sym} : stop reposé à {p['stop']:.6g}")
            except Exception as e:
                G.vendre(ex, sym, etat, f"stop impossible à reposer ({e})")
                rapport.append(f"{sym} : stop impossible à reposer, position vendue par sécurité")

    # 4. Ordres orphelins créés par le bot (position disparue mais stop resté ouvert)
    try:
        ex.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
        connus = {p["id_stop"] for p in etat["positions"].values()}
        for o in ex.fetch_open_orders():
            if str(o.get("clientOrderId") or "").startswith(PREFIXE) and o["id"] not in connus:
                ex.cancel_order(o["id"], o["symbol"])
                rapport.append(f"{o['symbol']} : ordre orphelin du bot annulé")
    except Exception as e:
        log(f"Réconciliation : lecture des ordres ouverts impossible ({e})")

    # 5. En réel : avoirs inconnus du bot, signalés mais JAMAIS vendus d'office (ils peuvent être à toi)
    if au_demarrage and config.REEL:
        suivis = {ex.markets[s]["base"] for s in etat["positions"]} | {config.DEVISE, "BNB"}
        for actif, qte in total.items():
            if actif in suivis or not qte:
                continue
            sym = f"{actif}/{config.DEVISE}"
            if sym in ex.markets:
                try:
                    valeur = float(qte) * float(ex.fetch_ticker(sym)["bid"])
                except Exception:
                    continue
                if valeur >= config.AVOIR_HORS_BOT_USDT:
                    rapport.append(f"{actif} : {valeur:.0f} USDT détenus hors du bot (non touchés)")

    if rapport:
        alerte("🧾 Réconciliation avec Binance :\n" + "\n".join(rapport))
    elif au_demarrage:
        log("🧾 Réconciliation : tout est cohérent avec Binance")
    return rapport

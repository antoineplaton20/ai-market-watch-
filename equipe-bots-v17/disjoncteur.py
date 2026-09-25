"""DISJONCTEUR DE PERFORMANCE : le système reconnaît qu'il ne fonctionne plus au lieu de s'obstiner.
- Pire baisse réelle > 1,5 x la pire baisse prévue par le coffre-fort  → arrêt des achats.
- Espérance réelle nettement sous la prévision (test statistique, 30 trades min) → arrêt des achats.
- 7 pertes d'affilée → pause de 24 h.
Les positions ouvertes restent protégées par leur stop. Réarmement manuel : /rearmer sur Telegram."""
import datetime as dt
import math
import time
import config
import auditeur
import paliers
import strategie as S
from alertes import alerte


def reference(etat):
    """Ce que le champion actuel avait promis sur le coffre-fort, et depuis quand on le juge."""
    c = S.charger(S.FICHIER_CHAMPION) or {}
    coffre = c.get("coffre") or {}
    dd_ref = coffre.get("mc_dd95") or config.EVO_DD_MAX
    date = c.get("promu") or c.get("date")
    depuis = dt.datetime.fromisoformat(date).timestamp() if date else 0.0
    depuis = max(depuis, etat.get("disjoncteur_rearme", 0.0))
    return dd_ref, coffre.get("E"), coffre.get("std"), depuis


def pire_baisse(pnls, latent=0.0, base=None):
    capital = pic = base or config.CAPITAL_MAX_USDT
    pire = 0.0
    for u in list(pnls) + [latent]:
        capital += u
        pic = max(pic, capital)
        pire = max(pire, 1 - capital / pic)
    return pire


def baisse_actuelle(pnls, latent=0.0, base=None):
    """Baisse actuelle depuis le plus haut (et non la pire baisse passée)."""
    capital = pic = base or config.CAPITAL_MAX_USDT
    for u in pnls:
        capital += u
        pic = max(pic, capital)
    return max(0.0, 1 - (capital + latent) / pic)


def declencher(etat, raison):
    etat["disjoncteur"] = {"raison": raison, "date": dt.datetime.now().isoformat(timespec="minutes")}
    alerte(f"🚨 SÉCURITÉ GÉNÉRALE DÉCLENCHÉE : {raison}\nLe bot prudent n'achète plus. Les achats en cours restent "
           "protégés.\nQuand tu as regardé ce qui se passe, envoie /rearmer pour relancer.")
    paliers.descendre(etat, "disjoncteur déclenché")


def verifier(etat, latent=0.0):
    if etat.get("disjoncteur"):
        return
    base = paliers.capital_autorise(etat)
    # Coupe-circuit ABSOLU : -15 % depuis le plus haut, quelle que soit la prévision du champion
    depuis_rearmement = auditeur.trades_depuis(etat.get("disjoncteur_rearme", 0.0), "strict")
    dd_abs = pire_baisse([u for _, u in depuis_rearmement], latent, base)
    if dd_abs >= config.COUPE_CIRCUIT_DD:
        return declencher(etat, f"COUPE-CIRCUIT ABSOLU : baisse de {dd_abs:.1%} (limite {config.COUPE_CIRCUIT_DD:.0%})")
    dd_ref, e_ref, std_ref, depuis = reference(etat)
    trades = auditeur.trades_depuis(depuis, "strict")
    dd = pire_baisse([u for _, u in trades], latent, base)
    if dd > config.DISJONCTEUR_DD_MULT * dd_ref:
        return declencher(etat, f"pire baisse réelle {dd:.1%} contre {dd_ref:.1%} prévue")
    rs = [r for r, _ in trades]
    if len(rs) >= config.DISJONCTEUR_TRADES_MIN and e_ref is not None:
        e = sum(rs) / len(rs)
        ecart = math.sqrt(sum((x - e) ** 2 for x in rs) / (len(rs) - 1))
        if e < 0 and e < e_ref - 2 * ecart / math.sqrt(len(rs)):
            return declencher(etat, f"espérance réelle {e:+.2f} R contre {e_ref:+.2f} R prévue ({len(rs)} trades)")
    # Série de pertes : pause de 24 h (une seule fois par série)
    serie = 0
    for r in reversed(rs):
        if r >= 0:
            break
        serie += 1
    if serie >= config.PERTES_SUITE_MAX and etat.get("serie_traitee") != len(trades):
        etat["serie_traitee"] = len(trades)
        etat["pause_jusqua"] = time.time() + config.PAUSE_PERTES_H * 3600
        alerte(f"⏸ {serie} pertes d'affilée : le bot prudent fait une pause de {config.PAUSE_PERTES_H} h pour laisser passer la mauvaise période.")


def rearmer(etat):
    etat["disjoncteur"] = None
    etat["disjoncteur_rearme"] = time.time()      # on repart de zéro pour ne pas redéclencher sur le passé
    etat["pause_jusqua"] = 0
    alerte("🔌 Sécurité générale relancée : les achats peuvent reprendre.")

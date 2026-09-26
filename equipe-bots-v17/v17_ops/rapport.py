"""État de la V17 lu dans sa base (sans démarrer de moteur) : API /state et commande Telegram /v17."""
from __future__ import annotations

import datetime as dt
import time

from .core.config import settings as SETTINGS
from .core.portfolio import PaperPortfolio
from .core.store import OpsStore
from .format import MODES as NOMS_MODES, dollars, pct, prix


def _store(store, s):
    return store or OpsStore(s.ops_db)


def etat(store=None, settings=None):
    s = settings or SETTINGS
    store = _store(store, s)
    hb = store.get('heartbeat') or {}
    mode = hb.get('mode', s.mode)
    depart = s.paper_cash_usdt if mode == 'paper' else s.capital_max_usdt
    book = PaperPortfolio.from_dict(store.get(f'portfolio:{mode}'), default_cash=depart)
    prices = hb.get('prices') or {}
    minuit = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    ordres = store.orders_since(minuit, statuses=('filled',))
    ventes = [o for o in ordres if o['side'] == 'sell']
    positions = []
    for sym, q in book.open_positions().items():
        pru = book.avg_cost.get(sym, 0)
        px = float(prices.get(sym, pru) or pru)
        positions.append({'symbol': sym, 'qty': q, 'entry': pru, 'price': px, 'value': q * px,
                          'pnl_pct': (px / pru - 1) * 100 if pru else 0.0})
    age = time.time() - hb['ts'] if hb.get('ts') else None
    return {
        'mode': mode, 'symbols': hb.get('symbols', list(s.symbols)), 'timeframe': hb.get('timeframe', s.timeframe),
        'alive': age is not None and age < 3 * s.interval + 120, 'heartbeat_age_s': age,
        'network_failures': int(hb.get('network_failures', 0) or 0),
        'paused': bool(store.get('pause', False)) or time.time() < float(store.get('pause_until', 0) or 0),
        'kill_switch': s.kill_switch,
        'entries_blocked': s.entries_blocked,
        'governor': store.get(f'governor:{mode}') or {},
        'pending': store.get(f'pending:{mode}'),
        'cash': book.cash, 'equity': book.equity(prices), 'start_equity': depart,
        'realized_pnl': book.realized_pnl, 'positions': positions,
        'today': {'buys': len(ordres) - len(ventes), 'sells': len(ventes),
                  'realized_pnl': sum(float(o['payload'].get('pnl', 0) or 0) for o in ventes)},
    }


def s_auto(settings=None):
    return bool(getattr(settings or SETTINGS, 'auto_reconcile', False))


def texte_statut(store=None, settings=None):
    e = etat(store, settings)
    if e['heartbeat_age_s'] is None:
        return ("🧪 v17 : pas encore démarrée sur ce serveur.\n"
                "Dans Termius : bots v17-demarrer")
    lignes = [f"🧪 v17 — {NOMS_MODES.get(e['mode'], e['mode'])}",
              f"Suit : {', '.join(x.split('/')[0] for x in e['symbols'])} · décision à chaque bougie de {e['timeframe']}"]
    if not e['alive']:
        lignes.append(f"⚠️ Ne donne plus signe de vie depuis {e['heartbeat_age_s'] / 60:.0f} min "
                      "(Termius : bots v17-etat)")
    if e['network_failures']:
        lignes.append(f"⚠️ Binance ne répond pas depuis {e['network_failures']} tour(s) : la v17 attend")
    if e['pending']:
        p = e['pending']
        auto = e['mode'] in ('demo', 'testnet') and s_auto(settings)
        lignes.append(f"⛔ BLOQUÉE : rapprochement requis ({p.get('symbol', '?')} · {p.get('reason') or p.get('side', '?')}). "
                      + ("Rapprochement automatique avec Binance en cours (essai chaque minute)."
                         if auto else "Aucun ordre, ventes et protection comprises. Termius : bots v17-rapprochement"))
    if e['kill_switch']:
        lignes.append("⛔ KILL_SWITCH actif : aucun ordre")
    elif e['paused']:
        lignes.append("⏸ Achats en pause (/v17 reprise pour relancer) · ventes et protections actives")
    if e['entries_blocked']:
        lignes.append('⛔ Achats bloqués : corriger les réglages invalides dans .env, puis redémarrer la v17.')
    if e['governor'].get('halted'):
        lignes.append('⛔ Limite de perte cumulée atteinte : achats bloqués, ventes actives. /v17 reprise ne réarme pas cette protection.')
    total = e['equity'] - e['start_equity']
    lignes.append(f"Portefeuille : {dollars(e['equity'])} ({dollars(total, True)} depuis le départ) · "
                  f"disponible {dollars(e['cash'])}")
    j = e['today']
    lignes.append(f"Aujourd'hui : {j['buys']} achat(s), {j['sells']} vente(s), résultat {dollars(j['realized_pnl'], True)}")
    if e['positions']:
        lignes.append("En cours :")
        for p in e['positions']:
            lignes.append(f"• {p['symbol'].split('/')[0]} : acheté {prix(p['entry'])} $, maintenant {prix(p['price'])} $ "
                          f"({pct(p['pnl_pct'])}) · {dollars(p['value'])}")
    else:
        lignes.append("Aucune position en cours.")
    lignes.append("Commandes : /v17 · /v17 stop (pause des achats) · /v17 reprise")
    return "\n".join(lignes)


def regler_pause(active, store=None, settings=None):
    s = settings or SETTINGS
    store = _store(store, s)
    store.set('pause', bool(active))
    if not active:
        store.set('pause_until', 0)                    # /v17 reprise lève aussi une pause automatique
    store.event('pause', {'active': bool(active)})
    return ("⏸ v17 : achats en pause. Les ventes et la protection continuent. Pour reprendre : /v17 reprise"
            if active else "▶️ v17 : pause levée. Les autres contrôles de risque restent actifs.")


def commande_telegram(arg=None, store=None, settings=None):
    """Appelé par le bot principal (main.py) pour /v17, /v17 stop, /v17 reprise."""
    arg = (arg or "").lower()
    if arg in ("stop", "pause"):
        return regler_pause(True, store, settings)
    if arg in ("reprise", "reprendre", "start"):
        return regler_pause(False, store, settings)
    return texte_statut(store, settings)


def avertir_positions(mode, store=None, settings=None):
    """Avant de quitter un mode exchange : positions de la v17 encore détenues sur le compte (plus surveillées)."""
    s = settings or SETTINGS
    store = _store(store, s)
    book = PaperPortfolio.from_dict(store.get(f'portfolio:{mode}'), default_cash=s.capital_max_usdt)
    ouvertes = book.open_positions()
    if ouvertes:
        compte = {'demo': 'démo', 'testnet': 'testnet', 'live': 'réel'}.get(mode, mode)
        print(f"⚠️ La v17 détient encore sur le compte {compte} : "
              + ", ".join(f"{q:.6g} {sym.split('/')[0]}" for sym, q in ouvertes.items())
              + ". Elles ne seront plus surveillées (ni signal de vente, ni protection). "
              "Reviens en démo (bots v17-demo) jusqu'à leur vente, ou vends-les dans l'application Binance.")
    return ouvertes


def rapprochement(store=None, settings=None):
    """Détail du blocage « rapprochement requis » (lecture seule) pour bots v17-rapprochement."""
    import json
    s = settings or SETTINGS
    store = _store(store, s)
    hb = store.get('heartbeat') or {}
    mode = hb.get('mode', s.mode)
    p = store.get(f'pending:{mode}')
    if not p:
        return f"✅ Aucun blocage (mode {mode})."
    lignes = [f"⛔ v17 bloquée (mode {mode}) : un ordre ou un solde n'a pas pu être confirmé.",
              json.dumps(p, ensure_ascii=False, indent=1, default=str),
              "À vérifier dans l'application Binance (compte démo : demo.binance.com > Ordres) :",
              f"  • l'ordre {p.get('symbol', '?')} {p.get('side', '')} a-t-il été exécuté ? quantité, prix ;",
              "  • le solde de la crypto (libre ET bloqué).",
              "Ensuite : bots v17-debloquer (les achats resteront en pause jusqu'à /v17 reprise)."]
    return "\n".join(lignes)


def debloquer(store=None, settings=None):
    """Retire le blocage après vérification humaine ; remet les achats en pause (jamais en argent réel)."""
    s = settings or SETTINGS
    store = _store(store, s)
    hb = store.get('heartbeat') or {}
    mode = hb.get('mode', s.mode)
    if mode == 'live':
        return "✖ Argent réel : déblocage manuel dans la base uniquement, après rapprochement comptable complet."
    p = store.get(f'pending:{mode}')
    if not p:
        return f"✅ Aucun blocage (mode {mode})."
    store.set('pause', True)
    store.event('reconciliation_cleared', {'mode': mode, 'pending': p})
    with store.lock, store._conn() as c:
        c.execute('DELETE FROM kv WHERE key=?', (f'pending:{mode}',))
    return ("🔓 Blocage retiré. Achats en PAUSE ; ventes et protection reprennent. "
            "Vérifie /v17 puis /v17 reprise pour relancer les achats.")

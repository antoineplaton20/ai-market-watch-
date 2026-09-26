"""Sélection chronologique hors ligne. Ne modifie aucun moteur ni réglage réel.
python -m research.walk_forward_ops
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from .validate import decode, simulate, STEP

CANDIDATES = ('v177', 'trend200', 'cooldown8', 'cash')


def trend(closes, signal):
    if signal != 'buy':
        return signal
    if len(closes) < 220:
        return None
    mean = sum(closes[-200:]) / 200
    previous = sum(closes[-220:-20]) / 200
    return 'buy' if closes[-1] > mean > previous else None


def run(rows, name, stress=False):
    return simulate(rows, policy=(lambda *_: None) if name == 'cash' else trend if name == 'trend200' else None,
                    cooldown_bars=8 if name == 'cooldown8' else 0,
                    fee=.002 if stress else .001, slip=.001 if stress else .0005)


def choose(training, min_trades=10):
    """La sélection ne reçoit jamais les données de la fenêtre de test."""
    results = {name: {'base': run(training, name), 'stress': run(training, name, True)} for name in CANDIDATES}
    best, score = 'cash', 0.0
    for name, result in results.items():
        b, s = result['base'], result['stress']
        candidate_score = s['return_pct'] - s['max_close_drawdown_pct']
        if (b['round_trips'] >= min_trades and s['return_pct'] > 0 and candidate_score > score):
            best, score = name, candidate_score
    return best, results


def evaluate(monthly):
    months = sorted(monthly)
    if len(months) < 9:
        raise ValueError('Au moins neuf mois complets sont requis')
    windows = []
    # Rolling six-month fit, three-month forward test; disjoint test windows.
    for start in range(6, len(months) - 2, 3):
        training = [r for m in months[start-6:start] for r in monthly[m]]
        chosen, scores = choose(training)
        testing = [r for m in months[start:start+3] for r in monthly[m]]
        assert training[-1][0] < testing[0][0]
        windows.append({'train_months': months[start-6:start], 'test_months': months[start:start+3],
                        'chosen': chosen, 'training_results': scores,
                        'selected_base': run(testing, chosen), 'selected_stress': run(testing, chosen, True),
                        'baseline_base': run(testing, 'v177')})
    return {'windows': windows, 'unused_final_months': months[6+3*len(windows):],
            'sum_window_pnl_usdt': sum(w['selected_base']['pnl_usdt'] for w in windows),
            'baseline_sum_window_pnl_usdt': sum(w['baseline_base']['pnl_usdt'] for w in windows),
            'cash_windows': sum(w['chosen'] == 'cash' for w in windows),
            'note': 'Chaque fenêtre repart à 1000 USDT ; somme de PnL de comptes réinitialisés, pas un rendement composé.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('research/results'))
    parser.add_argument('--output', type=Path, default=Path('research/walk_forward_v178.json'))
    a = parser.parse_args(argv)
    manifest = json.loads((a.input / 'provenance.json').read_text())
    if manifest.get('errors'):
        raise ValueError('Collecte incomplète : corriger les erreurs avant validation')
    datasets = {}
    for meta in manifest['files']:
        symbol, month = meta['symbol'], meta['month']
        name = f'{symbol}-15m-{month}.zip'
        raw = (a.input / 'archives' / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta['sha256']:
            raise ValueError(f'Empreinte invalide : {name}')
        datasets.setdefault(symbol, {})[month] = decode(raw, month)
    out = {'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
           'candidates': CANDIDATES, 'live_authorized': False,
           'method': 'six-month train / three-month test, fixed candidate set, cash allowed, doubled cost gate',
           'limitations': ['surviving asset selection', 'OHLC execution approximation',
                           'existing observed history, not a pristine holdout', 'no leverage/funding/liquidation model',
                           'does not replay all live-engine risk logic', 'per-window cash reset and warmup'], 'symbols': {}}
    for symbol, monthly in datasets.items():
        rows = [r for m in sorted(monthly) for r in monthly[m]]
        if any(b[0]-a[0] != STEP for a,b in zip(rows, rows[1:])):
            raise ValueError('Historique non contigu')
        out['symbols'][symbol] = evaluate(monthly)
        print(symbol, 'terminé', flush=True)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    temp = a.output.with_suffix('.tmp')
    temp.write_text(json.dumps(out, indent=2, allow_nan=False))
    temp.replace(a.output)
    print('Rapport enregistré. Aucun paramètre de trading ni compte modifié.')

if __name__ == '__main__':
    main()

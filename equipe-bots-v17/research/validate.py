"""Download checksum-verified public candles and compare fixed policies, offline.
python -m research.validate --start 2024-01 --end 2026-08
No strategy search, no live orders. Results are historical diagnostics only.
"""
import argparse
import calendar
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from v17_ops.strategies.ensemble import Ensemble
from v17_ops.core.portfolio import PaperPortfolio

BASE = 'https://data.binance.vision/data/spot/monthly/klines'
STEP = 900000


def months(start, end):
    a = dt.datetime.strptime(start, '%Y-%m').date()
    b = dt.datetime.strptime(end, '%Y-%m').date()
    if a > b or b >= dt.datetime.now(dt.timezone.utc).date().replace(day=1):
        raise ValueError('Only completed months in chronological order are supported')
    out = []
    while a <= b:
        out.append(a.strftime('%Y-%m'))
        a = a.replace(year=a.year + (a.month == 12), month=a.month % 12 + 1)
    return out


def get_bytes(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                raw = response.read(20_000_001)
            if len(raw) > 20_000_000:
                raise ValueError('archive too large')
            return raw
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def decode(raw, month):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].file_size > 50_000_000:
            raise ValueError('invalid archive layout')
        lines = csv.reader(io.StringIO(archive.read(entries[0]).decode()))
        rows = []
        for row in lines:
            ts = int(row[0])
            if ts >= 100_000_000_000_000:
                ts //= 1000
            prices = list(map(float, row[1:6]))
            if not all(math.isfinite(x) for x in prices):
                raise ValueError('nonfinite candle')
            op, high, low, close, volume = prices
            if min(op, high, low, close) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close):
                raise ValueError('invalid OHLCV')
            rows.append([ts, *prices])
    year, mon = map(int, month.split('-'))
    first = int(dt.datetime(year, mon, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    expected = calendar.monthrange(year, mon)[1] * 96
    if len(rows) != expected or any(r[0] != first + i * STEP for i, r in enumerate(rows)):
        raise ValueError('missing, duplicate or unordered candles')
    return rows


def collect(symbol, month, root):
    if not re.fullmatch(r'[A-Z0-9]{3,20}USDT', symbol):
        raise ValueError('invalid USDT symbol')
    name = f'{symbol}-15m-{month}.zip'
    url = f'{BASE}/{symbol}/15m/{name}'
    path = root / name
    # Refresh the publisher checksum even for cached archives.
    checksum = get_bytes(url + '.CHECKSUM').decode().split()[0].lower()
    if not re.fullmatch('[0-9a-f]{64}', checksum):
        raise ValueError('invalid checksum')
    raw = path.read_bytes() if path.exists() else get_bytes(url)
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError(f'checksum mismatch: {name}')
    rows = decode(raw, month)
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(raw)
    tmp.replace(path)
    return rows, {'symbol': symbol, 'month': month, 'url': url,
                  'sha256': checksum, 'bytes': len(raw), 'rows': len(rows),
                  'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat()}


def simulate(rows, strength=True, fee=0.001, slip=0.0005):
    """Fixed-size spot proxy, not a full OpsEngine replay or profitability proof.
    Decision at closed bar t; fill at next open; pessimistic stop at open/low.
    Initial and deployable cash 1000 USDT; order 100; stop 3%; daily loss 50.
    """
    book = PaperPortfolio(1000)
    ensemble = Ensemble()
    closes = []
    equity = peak = 1000.0
    dd = 0.0
    pnls = []
    orders = 0
    day = None
    day_equity = equity
    pending = None
    for ts, op, high, low, close, volume in rows:
        date = ts // 86400000
        if date != day:
            day, day_equity = date, book.equity({'X': op})
        qty = book.positions.get('X', 0)
        if qty and pending == 'sell':
            result = book.execute('X', 'sell', qty, op * (1 - slip), fee_rate=fee)
            pnls.append(result['pnl'])
            orders += 1
        elif not qty and pending == 'buy' and book.equity({'X': op}) - day_equity > -50:
            notional = min(100, book.cash / ((1 + fee) * (1 + slip)))
            if notional >= 10:
                book.execute('X', 'buy', notional / op, op * (1 + slip), fee_rate=fee)
                orders += 1
        qty = book.positions.get('X', 0)
        stop = book.avg_cost.get('X', 0) * 0.97
        # Includes gap-through-stop and stops hit within the entry bar.
        if qty and low <= stop:
            result = book.execute('X', 'sell', qty, min(op, stop) * (1 - slip), fee_rate=fee)
            pnls.append(result['pnl'])
            orders += 1
        equity = book.equity({'X': close})
        peak = max(peak, equity)
        dd = max(dd, 1 - equity / peak)
        closes.append(close)
        closes = closes[-300:]
        votes = ensemble.votes(closes)
        if strength:
            agg = ensemble.aggregate(votes)
        else:
            buy = sum(v.score for v in votes if v.side == 'buy')
            sell = sum(v.score for v in votes if v.side == 'sell')
            agg = None if buy == sell else ('buy' if buy > sell else 'sell', max(buy, sell) / (buy + sell))
        pending = agg[0] if agg and agg[1] >= 0.65 else None
    qty = book.positions.get('X', 0)
    if qty:
        result = book.execute('X', 'sell', qty, rows[-1][4] * (1 - slip), fee_rate=fee)
        pnls.append(result['pnl'])
        orders += 1
    dd = max(dd, 1 - book.cash / peak)
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return {'pnl_usdt': round(book.cash - 1000, 4), 'return_pct': round((book.cash / 1000 - 1) * 100, 4),
            'max_close_drawdown_pct': round(dd * 100, 4), 'round_trips': len(pnls), 'orders': orders,
            'win_rate': sum(p > 0 for p in pnls) / len(pnls) if pnls else None,
            'profit_factor': gains / losses if losses else None,
            'ending_equity': book.cash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2024-01')
    parser.add_argument('--end', default='2026-08')
    parser.add_argument('--symbols', nargs='+', default=['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
    parser.add_argument('--output', type=Path, default=Path('research/results'))
    args = parser.parse_args()
    periods = months(args.start, args.end)
    if len(periods) * len(args.symbols) > 180:
        parser.error('Maximum 180 archives per run; partition larger collections')
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / 'archives'
    cache.mkdir(exist_ok=True)
    manifest, datasets, errors = [], {}, []
    jobs = [(s, m) for s in args.symbols for m in periods]
    def job(pair):
        try:
            return pair, collect(*pair, cache), None
        except Exception as exc:
            return pair, None, str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for pair, result, error in pool.map(job, jobs):
            if error:
                errors.append({'symbol': pair[0], 'month': pair[1], 'error': error})
            else:
                rows, meta = result
                manifest.append(meta)
                datasets.setdefault(pair[0], []).extend(rows)
            print(f'{pair[0]} {pair[1]}: {error or "verified"}', flush=True)
    (args.output / 'provenance.json').write_text(json.dumps({'files': manifest, 'errors': errors}, indent=2))
    report = {'method': 'fixed policy comparison; next-open fills; independent symbol accounts; no parameter search',
              'limitations': ['not an exact live-engine replay', 'three surviving assets: selection bias',
                              'fixed fees, synthetic slippage, no order book', 'drawdown measured at closes',
                              'observed historical test, not a guarantee or untouched prospective holdout'],
              'complete': not errors, 'live_authorized': False, 'results': []}
    for symbol, rows in datasets.items():
        if any(e['symbol'] == symbol for e in errors):
            continue  # never backtest a partial collection as though complete
        rows.sort(key=lambda r: r[0])
        if any(b[0] - a[0] != STEP for a, b in zip(rows, rows[1:])):
            raise ValueError(f'non-contiguous dataset: {symbol}')
        split = int(len(rows) * .7)
        for period, segment in [('first_70pct', rows[:split]), ('last_30pct', rows[split:])]:
            for policy in ('original_vote', 'strength_vote'):
                for costs, fee, slip in [('base', .001, .0005), ('stress', .002, .001)]:
                    report['results'].append({'symbol': symbol, 'period': period,
                                              'start_ms': segment[0][0], 'end_ms': segment[-1][0],
                                              'policy': policy, 'costs': costs,
                                              **simulate(segment, policy == 'strength_vote', fee, slip)})
    (args.output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(f'Completed: {len(manifest)} verified archives, {len(errors)} errors; no live trading enabled')
    return 0 if not errors else 1

if __name__ == '__main__':
    raise SystemExit(main())

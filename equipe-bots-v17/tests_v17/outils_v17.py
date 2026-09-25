"""Outils communs des tests V17 (marché simulé, séries de prix)."""
import time

TF_MS = 900_000
clock_ms = int(time.time() * 1000)


class FakeMarket:
    """Bougies de 15 min fermées (dans le passé) + éventuellement une bougie en cours (prix actuel)."""

    def __init__(self, closes=()):
        global clock_ms
        maintenant = clock_ms = int(time.time() * 1000)
        self.base = maintenant - maintenant % TF_MS
        self.ts0 = self.base - len(closes) * TF_MS
        self.closes = list(closes)
        self.forming = None
        self.appels = 0

    def ajouter(self, *prix):
        global clock_ms
        self.base += len(prix) * TF_MS
        clock_ms += len(prix) * TF_MS
        self.closes.extend(prix)
        self.forming = None

    def fetch_ohlcv(self, symbol, timeframe='15m', limit=120):
        self.appels += 1
        rows = [[self.ts0 + i * TF_MS, c, c, c, c, 1.0] for i, c in enumerate(self.closes)]
        if self.forming is not None:
            rows.append([self.base, self.forming, self.forming, self.forming, self.forming, 1.0])
        return rows[-limit:]


def hausse(n=60, debut=100.0, pas=0.5):
    return [debut + i * pas for i in range(n)]


def baisse(n=60, debut=130.0, pas=0.5):
    return [debut - i * pas for i in range(n)]

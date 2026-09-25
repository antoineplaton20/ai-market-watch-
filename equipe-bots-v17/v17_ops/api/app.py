"""API de supervision V17. Écoute sur 127.0.0.1 : jamais exposée sur Internet.
Les routes historiques (/state, /orders...) sont en lecture seule. L'application iPhone (/app, voir mobile.py)
exige le code V17_APP_TOKEN ; depuis le téléphone : Tailscale (HTTPS privé) ou redirection de port Termius."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .. import rapport
from . import mobile
from ..core.config import settings
from ..core.store import OpsStore

app = FastAPI(title='Trading Army V17 OPS', version='17.1.0')
store = OpsStore(settings.ops_db)
app.include_router(mobile.router)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'v17-ops', 'mode': settings.mode,
            'live_enabled': settings.live_trading_enabled}


@app.get('/ready')
def ready():
    try:
        store.recent('events', 1)
        return {'ready': True, 'db': True, 'mode': settings.mode}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get('/state')
def state():
    try:
        return rapport.etat(store)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def _borne(limit):
    return min(max(int(limit), 1), 500)


@app.get('/events')
def events(limit: int = 50):
    return store.recent('events', _borne(limit))


@app.get('/signals')
def signals(limit: int = 50):
    return store.recent('signals', _borne(limit))


@app.get('/orders')
def orders(limit: int = 50):
    return store.recent('orders', _borne(limit))


@app.get('/snapshots')
def snapshots(limit: int = 50):
    return store.recent('snapshots', _borne(limit))

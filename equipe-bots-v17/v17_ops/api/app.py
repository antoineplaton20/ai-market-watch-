"""API de supervision V17 (lecture seule). Écoute sur 127.0.0.1 : jamais exposée sur Internet.
Depuis le téléphone : redirection de port dans Termius (port 8080 du serveur), puis http://127.0.0.1:8080/state"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .. import rapport
from ..core.config import settings
from ..core.store import OpsStore

app = FastAPI(title='Trading Army V17 OPS', version='17.1.0')
store = OpsStore(settings.ops_db)


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

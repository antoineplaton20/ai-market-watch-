from v17_ops.workers.engine import OpsEngine

def test_engine_warmup_with_injected_price(tmp_path):
    from v17_ops.core.store import OpsStore
    e=OpsEngine('paper',['BTC/USDT'],OpsStore(tmp_path/'db.sqlite'))
    r=e.tick('BTC/USDT',50000)
    assert r['status']=='warming'

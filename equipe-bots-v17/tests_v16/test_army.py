from trading_army.bot_catalog import build_trading_army_catalog

def test_large_catalog_unique():
    c=build_trading_army_catalog(); assert len(c)>=1000; assert len({x['id'] for x in c})==len(c)

def test_no_withdraw_permission():
    assert all('withdraw' not in b['permissions'] for b in build_trading_army_catalog())

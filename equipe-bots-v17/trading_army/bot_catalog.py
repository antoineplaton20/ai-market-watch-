import itertools
DEPARTMENTS={
"market_intelligence":["price","volume","momentum","trend","volatility","liquidity","spread","orderbook","trade_flow","microstructure"],
"derivatives":["funding","open_interest","basis","liquidations","options","leverage","term_structure","long_short"],
"onchain":["whale","exchange_flow","holder","wallet","network","stablecoin","miner","bridge","defi","token_unlock"],
"research":["web","news","macro","regulation","company","technology","competitor","academic","fact_check","source_validation"],
"sentiment":["news_sentiment","social_sentiment","community","narrative","event","fear_greed","topic","rumor_detection"],
"strategy":["trend","mean_reversion","breakout","momentum","arbitrage","market_neutral","statistical","event_driven","pairs","portfolio"],
"risk":["position","portfolio","drawdown","correlation","liquidity","slippage","tail_risk","stress","limit","kill_switch"],
"execution":["order_router","smart_order","limit","market","twap","vwap","slippage","reconciliation","fill_monitor","cancel_replace"],
"data":["collector","normalizer","validator","deduplicator","timestamp","quality","anomaly","schema","provenance","feature_store"],
"testing":["backtest","walk_forward","monte_carlo","stress_test","regime_test","overfit","data_leakage","latency","cost_model","paper_trade"],
"evaluation":["accuracy","precision","recall","robustness","calibration","drift","cost","latency","ablation","benchmark"],
"governance":["policy","permission","audit","compliance","secret_guard","access_control","incident","approval","change_control","release"],
"memory":["market_memory","bot_memory","team_memory","strategy_memory","source_memory","event_memory","postmortem","lesson","retrieval","provenance"],
"orchestration":["router","planner","dispatcher","manager","team_lead","debate","contradiction","consensus","champion","challenger"],
"infrastructure":["api","websocket","queue","cache","database","observability","metrics","logging","scheduler","healthcheck"],
"portfolio":["allocation","rebalance","exposure","sector","asset_class","cash","hedge","diversification","concentration","scenario"],
}
PREFIXES=["scout","analyst","validator","challenger","specialist","monitor","researcher","auditor","planner","guardian"]
def build_trading_army_catalog():
    bots=[]
    for dept, skills in DEPARTMENTS.items():
        for skill, prefix, variant in itertools.product(skills, PREFIXES, range(1,3)):
            bid=f"{dept}.{prefix}.{skill}.{variant:02d}"
            bots.append({"id":bid,"department":dept,"skill":skill,"role":prefix,"variant":variant,"status":"scaffold","permissions":["read"],"live_trade":False})
    return bots

# v11 — architecture multi-timeframe + coûts + opportunité + data lake

Cette version conserve le cœur de sécurité du v10 et ajoute quatre moteurs :

1. `moteurs/multi_timeframe.py` : 4h régime → 1h tendance → 15m signal → 5m entrée. Toutes les décisions utilisent la dernière bougie clôturée (`iloc[-2]`).
2. `moteurs/cost_engine.py` : coût aller-retour, maker/taker, frais fixes, spread et slippage. Les valeurs peuvent être surchargées par variables d'environnement.
3. `moteurs/opportunity_engine.py` : porte stricte. Toutes les conditions obligatoires doivent être positives et le potentiel brut doit dépasser les coûts + marge de sécurité + seuil de gain net.
4. `data_lake/` : SQLite append-only pour OHLCV, trades, carnets et événements, avec source et timestamp.

## Règle d'entrée v11

`4h OK AND 1h OK AND 15m OK AND 5m OK AND risque OK AND données OK AND liquidité OK AND spread OK AND potentiel net OK`.

Une seule condition obligatoire négative bloque l'entrée.

## Frais par défaut

- Binance Spot : 0,10 % maker / 0,10 % taker pour l'utilisateur standard ; VIP/BNB peuvent modifier ces taux. Voir le barème officiel avant un passage en réel.
- Trade Republic : 1 € de frais de règlement par transaction individuelle ; 2 € si Direct Price est sélectionné, plus spread et autres coûts éventuels.

Le moteur Trade Republic est volontairement un moteur de **coût**, pas un faux connecteur d'exécution : aucun ordre Trade Republic n'est envoyé par ce v11 tant qu'un connecteur/API autorisé n'a pas été ajouté et testé.

## Compatibilité v10

- `UNITE_BOUGIE` reste un alias de `TIMEFRAME_SIGNAL`.
- Le génome reste entraîné sur 15m.
- Le moteur de risque et le gardien restent les derniers remparts.
- Le backtest historique v10 continue d'exister ; la reconstruction 1m → 5m/15m/1h/4h est la prochaine étape pour un backtest v11 complet et sans look-ahead.

## Variables d'environnement utiles

```env
TIMEFRAME_ENTRY=5m
TIMEFRAME_SIGNAL=15m
TIMEFRAME_TREND=1h
TIMEFRAME_REGIME=4h
PLATEFORME_EXECUTION=binance
BINANCE_MAKER_FEE_PCT=0.10
BINANCE_TAKER_FEE_PCT=0.10
TRADE_REPUBLIC_SETTLEMENT_FEE_EUR=1.0
TRADE_REPUBLIC_DIRECT_PRICE_FEE_EUR=2.0
OPPORTUNITE_MIN_NET_PCT=0.15
OPPORTUNITE_MARGE_SECURITE_PCT=0.05
```

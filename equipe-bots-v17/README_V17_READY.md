> Mise à jour V17.8 : lire d’abord **V17_8_TERMIUS.md**. Les anciens déblocages par simple délai sont supprimés. Les résultats positifs ne sont pas garantis.

> Révision du 25/09/2026 : lire `LIRE_AVANT_UTILISATION.md` et `RESULTATS_HISTORIQUES.md` avant utilisation. Version de recherche ; rentabilité non démontrée.

# V17 OPS — prête pour la plateforme

Mode d'emploi sur le serveur : **`V17_PLATEFORME.md`** (installation en 3 commandes, Telegram, réglages).

## Garanties

- Portefeuille **fictif** par défaut (`V17_MODE=paper`) sur les vrais prix publics de Binance : aucun ordre.
- La v17 ne lit pas `MODE` pour son propre mode. Compte démo : `bots v17-demo` (verrouillé en démo).
- Argent réel verrouillé : `V17_MODE=live` + `LIVE_TRADING_ENABLED=1` + clés d'un sous-compte dédié.
- Retraits toujours refusés par la policy. `KILL_SWITCH=1` bloque tout ordre.
- API en lecture seule, écoute sur 127.0.0.1 uniquement.
- Aucune promesse de rentabilité : la stratégie livrée n'a pas été validée par backtest.

## Vérification (sans réseau)

```bash
.venv/bin/python verifier.py                          # tests plateforme + v15 + v16 + v17
.venv/bin/python -m v17_ops --once --price 50000      # un passage avec prix injecté
```

> Révision du 25/09/2026 : lire `LIRE_AVANT_UTILISATION.md` et `RESULTATS_HISTORIQUES.md` avant utilisation. Version de recherche ; rentabilité non démontrée.

# V17 OPS — Trading Army opérationnelle

V17 transforme V16 en runtime exploitable : collecte de prix, stratégie d'ensemble, garde-fous risque/policy, paper trading, adaptateur CCXT Binance sandbox, persistance SQLite et API de supervision.

## Modes

Le mode se règle avec `V17_MODE` (jamais avec `MODE`, qui appartient au bot principal) :

- `paper` : défaut, portefeuille fictif sur les vrais prix publics de Binance, aucun appel privé.
- `demo` / `testnet` : Binance démo / sandbox, avec des clés **propres à la v17** (`V17_API_KEY`, `V17_API_SECRET`).
- `live` : **désactivé par défaut**. `LIVE_TRADING_ENABLED=1` + clés propres à la v17. Les retraits restent interdits.

Sur le serveur, voir `V17_PLATEFORME.md`.

CCXT recommande d'activer le sandbox immédiatement après création de l'instance, et précise que les clés sandbox ne sont pas interchangeables avec les clés de production. citeturn0search0

## Démarrage local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m v17_ops --mode paper --symbol BTC/USDT
```

Pour l'API :

```bash
./run_api_v17.sh      # 127.0.0.1:8080 uniquement
```

Endpoints : `/health`, `/ready`, `/state`, `/signals`, `/orders`, `/snapshots`, `/events`.

## Testnet

Configurer uniquement des identifiants sandbox propres à la v17 (`V17_API_KEY`, `V17_API_SECRET`), puis :

```bash
python -m v17_ops --mode testnet --symbol BTC/USDT
```

Le moteur utilise CCXT et son mode sandbox. Il ne doit pas être considéré comme une garantie d'exécution identique à la production : types d'ordres, paramètres et fonctionnalités peuvent varier selon l'exchange. citeturn0search0

## Live

Le live n'est pas activé par défaut. Avant toute activation, il faut compléter la validation : réconciliation, surveillance, limites de perte, alertes, reprise après incident, validation des permissions de clé et revue humaine. Le code fourni ne promet aucune rentabilité et ne constitue pas une stratégie d'investissement.

## Architecture

`Market data → signals → risk → policy → execution → store → monitoring`.

Les bots d'analyse ne reçoivent pas directement les secrets d'exchange. Les retraits sont explicitement refusés par la policy.

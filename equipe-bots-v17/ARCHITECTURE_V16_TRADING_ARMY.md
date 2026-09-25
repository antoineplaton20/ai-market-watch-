# V16 — Trading Intelligence + Bot Army

## Mission
Construire une population massive d'agents spécialisés pour collecter, vérifier, analyser, simuler et surveiller les marchés, tout en séparant strictement intelligence, risque, autorisation et exécution.

## Pipeline
DATA SOURCES -> DATA LAKE -> SOURCE FUSION -> MARKET REGIME -> BOT ARMIES -> CONTRADICTION -> STRATEGY LAB -> RISK ENGINE -> POLICY -> PAPER/TESTNET -> EXECUTION -> POSTMORTEM -> MEMORY/EVALUATION -> BOT FACTORY.

## Sources prévues
- Binance / autres exchanges via adaptateurs CCXT et APIs natives lorsque nécessaire.
- Yahoo Finance via yfinance pour recherche/études, avec respect des conditions et licences applicables.
- News/web/on-chain/macro à connecter via connecteurs séparés.

## Séparation critique
Les agents d'analyse ne possèdent pas les credentials d'exécution. L'ExecutionEngine est le seul chemin vers un exchange privé. Les retraits sont interdits dans cette architecture. Live est désactivé par défaut.

## Modes
- paper/demo: aucune requête privée d'ordre réel.
- testnet: sandbox si supporté.
- live: nécessite explicitement LIVE_TRADING_ENABLED=1, MODE=live, clés valides, et les garde-fous.

## Armée
Le catalogue initial V16 génère plus de 1000 rôles spécialisés. Les entrées sont des scaffolds: elles ne deviennent des agents actifs qu'après branchement d'un runtime, outils, mémoire et évaluations.

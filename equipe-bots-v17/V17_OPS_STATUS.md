# V17 OPS — état (V17.2)

## Validé

- `verifier.py` lance tests (plateforme), tests_v15, tests_v16 et tests_v17 : c'est la barrière de
  `bots mettre-a-jour` (retour arrière automatique en cas d'échec).
- Moteur paper : bougies fermées, une décision par bougie, pas de rejeu au redémarrage, pas d'achat en
  boucle, vente seulement d'une position détenue, protection, plafond de capital, perte du jour,
  kill switch, pause Telegram.
- Mode démo contre un faux Binance (clés de repli du bot principal, position disparue, vente partielle) ;
  vraie bibliothèque ccxt avec réponses Binance simulées ; V17_DEMO_ONLY ; verrou une seule instance ;
  live verrouillé (clés du bot principal refusées).
- `/v17` dans le bot principal, API en lecture seule, CLI.
- Scripts `bots`, `installer.sh`, `configurer.sh` (conserve les réglages V17_ du .env).

## Non validé ici (pas d'accès réseau pendant la préparation)

- Appels réels aux prix publics Binance (même bibliothèque ccxt que le bot principal).
- Mode démo avec les vraies clés (à faire sur le serveur : bots v17-demo-test).
- Rentabilité de la stratégie d'ensemble (aucun backtest).

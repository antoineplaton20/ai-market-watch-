# V17.10 — Labo de stratégies (onglet « Labo » de l'application iPhone)

La méthode de la vidéo « AI Trading Bot » (DaviddTech), rendue utilisable depuis le téléphone, avec les données
et les garde-fous de la plateforme.

```
Idée en français ──► IA Claude ──► stratégie en blocs ──► backtest 2024-2026 (BTC, ETH, SOL)
                                                            │
                                         7 portes ◄─────────┘
                                           │
             rejetée (le cas normal) ◄─────┼─────► candidate ──► test en direct PAPIER + signaux Telegram
                                           │
                          Pine Script v6 pour TradingView (dans les deux cas)
```

## Utilisation (iPhone)

1. Onglet **Labo**.
2. **Nouvelle idée** : décris une stratégie avec tes mots, puis « Tester avec l'IA ». Ou touche un **exemple**.
3. 10 à 60 secondes plus tard : le verdict, les 7 portes, la courbe, le détail par crypto.
4. **Copier le Pine Script** : colle-le dans l'éditeur Pine de TradingView (site web ; sur iPhone, Safari en
   « version pour ordinateur ») puis « Ajouter au graphique » pour une seconde opinion dans le testeur de TradingView.
5. **Suivre en direct** (candidates) : la stratégie tourne sur les vrais prix Binance, en PAPIER. Chaque achat et
   chaque sortie fictifs arrivent sur Telegram, préfixés `[labo]`. Aucun ordre n'est passé.

## Le modèle de stratégie (celui de la vidéo)

- 1 **tendance** : prix au-dessus d'une EMA, croisement de deux EMA, Supertrend, cassure de Donchian ;
- 2 **confirmations** de types différents : RSI (élan ou repli), MACD, ADX, momentum, Bollinger ;
- 1 **filtre** : volume, volatilité (ATR %), ou aucun ;
- **stop** = multiple d'ATR sous le prix, **objectif** = multiple du risque (R), sortie optionnelle si la tendance casse ;
- achat seulement (spot), une position à la fois, frais 0,1 % + glissement 0,05 % par côté, 1 % du capital risqué.

L'IA ne fait que choisir des blocs et des réglages dans ce catalogue : elle n'écrit aucun code exécuté par le
serveur, et chaque réglage est borné.

## Les 7 portes (« 99 % des backtests échouent »)

| Porte | Exigence |
|---|---|
| Assez de trades | au moins 30 |
| Rentable après frais | facteur de profit ≥ 1,2 |
| Résiste à des coûts doublés | encore gagnante avec frais et glissement × 2 |
| Gagnante sur plusieurs cryptos | au moins 2 sur 3 |
| Stable dans le temps | au moins 3 périodes gagnantes sur 5 |
| Baisse maximale supportable | ≤ 20 % |
| Pas un coup de chance (Monte-Carlo, 2 000 tirages) | ≥ 90 % de chances de finir gagnant, pire baisse probable ≤ 30 % |

Premiers résultats sur l'historique fourni : les 3 exemples sont **rejetés**. Les deux stratégies « de manuel »
perdent nettement après frais ; la cassure 4 h passe 5 portes sur 7 mais sa baisse maximale (30 %) est trop forte.
C'est le fonctionnement attendu : le labo sert d'abord à éviter de perdre de l'argent sur de mauvaises idées.

## Ce que le labo ne fait pas

- Il ne passe **aucun ordre** et ne modifie **aucun bot** qui trade (bot principal, v17). Brancher une candidate
  sur un vrai compte reste une décision humaine, après plusieurs semaines de test en direct.
- Il ne prouve pas qu'une stratégie gagnera : l'historique couvre BTC, ETH et SOL depuis janvier 2024, déjà
  observés. Plus on teste d'idées, plus une réussite peut venir du hasard : chaque essai est gardé et compté.
- Il n'optimise pas les réglages (ce serait le plus sûr moyen de sur-apprendre le passé).

## Réglages et coûts

- Clé de l'IA : `bots cle-anthropic` (saisie masquée). Sans clé, les exemples fonctionnent.
- Modèle : `LABO_MODELE_IA` (défaut `claude-opus-5`, avec repli automatique si Claude refuse). Quelques centimes
  par idée. Au plus `LABO_IA_PAR_JOUR` idées par 24 h (défaut 30).
- Au plus 5 stratégies en test en direct. Données : `runtime/labo.db`. Journal : `bots labo-journal`.
- Le labo tourne dans l'API de l'application : après la mise à jour, lancer `bots app` (mémoire de l'API portée à
  700 Mo pour les calculs).

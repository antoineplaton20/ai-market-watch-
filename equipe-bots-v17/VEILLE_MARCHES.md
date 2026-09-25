# Veille marchés mondiaux (v17.3)

Service séparé : `equipe-bots-marches`. **Aucun ordre n'est passé** : c'est toi qui décides et qui agis dans
Trade Republic.

## Ce qu'elle lit

- **Toutes les 4 h, la presse mondiale** : 23 flux publics. Banques centrales (BCE, Fed), FMI, BBC, Le Monde,
  Euronews, Al Jazeera, MarketWatch, Yahoo Finance, CNBC, Investing.com (actions, forex, matières premières,
  économie), Les Echos, BFM, OilPrice, Defense News, CoinDesk et Cointelegraph.
- **14 thèmes** : géopolitique, économie mondiale, banques centrales et taux, Wall Street, Europe et CAC 40,
  industrie, énergie, alimentation et agriculture, métaux, devises, défense, tech et IA, crypto, avis des
  banques et des analystes.
- **Repères** : CAC 40, Euro Stoxx 50, S&P 500, Nasdaq, or, pétrole Brent, EUR/USD, EUR/GBP, EUR/CHF, EUR/JPY.
- **Pour chaque titre** : cours sur 1 an, consensus des analystes des banques (Goldman, JPMorgan, BNP…,
  agrégé par Yahoo), objectif de cours, comptes (croissance, marges, PER, dette) et presse des 7 derniers jours.

Avec une clé Anthropic dans `.env` (`ANTHROPIC_API_KEY`), l'IA fait la synthèse mondiale et lit le ton de la
presse. Sans clé, la lecture se fait par mots-clés : c'est moins fin.

## La note de 0 à 5

| Avis | Poids |
|---|---|
| Graphique : tendance, élan sur 3 et 6 mois, RSI, distance au plus haut | 30 % |
| Analystes : consensus et objectif de cours | 20 % |
| Presse des 7 derniers jours | 20 % |
| Comptes de l'entreprise | 15 % |
| Contexte mondial de son secteur | 15 % |

Un avis indisponible est retiré du calcul (une crypto n'a ni analystes ni comptes). 5 = meilleure option
selon ces critères, 0 = à éviter.

**Que faire maintenant**, avec les niveaux de prix (entrée, protection, objectif) :

- **ACHETER** : note ≥ 4, cours au-dessus de sa moyenne 50 jours, pas en surchauffe.
- **ATTENDRE UN REPLI** : bon dossier mais déjà trop monté (RSI ≥ 70).
- **ATTENDRE** : note de 3 à 3,5.
- **ÉVITER** : note inférieure à 3.
- **Pour les titres que tu détiens** : GARDER, ou **VENDRE / ALLÉGER** si la note tombe à 2 ou moins, ou si le
  cours casse sa tendance. Tu reçois alors une alerte immédiate avec le son.

Une note résume des informations publiques que le marché connaît déjà. Ce n'est ni une promesse de gain, ni un
conseil en investissement.

## Quels titres sont notés

1. Tes titres (`bots marches-portefeuille`).
2. Ta liste (`bots marches-suivre`).
3. Les principales cryptos disponibles chez TR (`MARCHES_CRYPTOS`).
4. Jusqu'à 60 actions et ETF Trade Republic retenus chaque jour par la veille TR (liquides, en tendance
   haussière). Tant que la veille TR n'a pas fini son premier tri, ce sont de grandes valeurs du CAC 40, de
   Wall Street et des ETF Monde.

N'importe quel titre peut être noté à la demande : `/note LVMH`, `/note MC.PA`, `/note FR0000121014`,
`/note bitcoin`.

## Commandes

Telegram : `/marches` (résumé) · `/briefing` (les 14 thèmes) · `/note NOM`

Termius :

```bash
bots marches-test                           # test : sources, Yahoo, 3 notes d'essai
bots marches-demarrer                       # démarrage (ensuite automatique, même après un redémarrage)
bots marches-portefeuille MC.PA,AAPL,BTC    # ce que tu détiens (alertes de vente)
bots marches-suivre AIR.PA,NVDA             # ta liste de surveillance
bots marches-note LVMH                      # une note tout de suite dans le terminal
bots marches-journal                        # journal en direct
```

Réglages facultatifs dans `.env` : `MARCHES_BRIEFING_H` (4), `MARCHES_RAPPORT_HEURE` (8), `MARCHES_NOTES_MAX`
(60), `MARCHES_CRYPTOS`, `MARCHES_DEVISES`, `MARCHES_INDICES`.

## Limites

- Les analyses payantes des banques et les terminaux professionnels (Bloomberg…) ne sont pas accessibles. Leurs
  recommandations arrivent par le consensus des analystes et par les titres de presse.
- Yahoo est gratuit mais non officiel : il limite les requêtes. La veille fait alors une pause de 30 minutes.
- Une source de presse en panne est signalée par `bots marches-test` et simplement ignorée.

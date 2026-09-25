# Veille Trade Republic (v13)

Processus **séparé** du bot Binance (service `equipe-bots-tr`, priorité plus basse, mémoire plafonnée à 1,2 Go) :
s'il plante ou si Yahoo bloque, le bot Binance n'est jamais touché.

**Aucun ordre n'est passé chez Trade Republic.** La veille t'envoie des signaux sur Telegram ; c'est toi qui
décides et qui passes l'ordre dans l'application.

## Chaîne complète

| Étape | Fréquence | Ce qui se passe |
|---|---|---|
| 1. Univers officiel | 1 fois / jour | Téléchargement de la liste publiée par Trade Republic (PDF « liste d'actions et ETF disponibles », version FR ; version DE en secours). Chaque ISIN est contrôlé (clé ISO 6166). Écrit `univers_trade_republic.csv`, lu par le registre v12 (`/univers`). Une lecture ratée ne remplace jamais un univers valide. |
| 2. Correspondance Yahoo | en continu jusqu'à la fin | Chaque ISIN (actions, ETF) est cherché une fois sur Yahoo Finance ; cotation retenue : place principale pour une action (hors OTC et places régionales), cotation européenne liquide pour un ETF. Cache : `tr_yahoo.json`. Plusieurs milliers d'ISIN : la première fois prend quelques heures, ensuite seuls les nouveaux titres sont cherchés. |
| 3. Tri quotidien | 1 fois / jour (+ nouveaux titres) | Bougies journalières fermées : échanges médians sur 20 jours convertis en euros ≥ `TR_VOLUME_MIN_EUR`, tendance journalière haussière. Les `TR_PRESELECTION` plus liquides forment la présélection. |
| 4. Signal d'ACHAT | toutes les 15 min | Bougies 1 h et 5 min Yahoo ; 4h reconstruit depuis le 1h, 15m depuis le 5m (aucune bougie inventée). Uniquement des bougies fermées. 4h + 1h + 15m + 5m haussiers, données fraîches, puis porte d'opportunité v11 avec les coûts TR (1 € par ordre ramené à `TR_MONTANT_ORDRE_EUR`, écart estimé, glissement). Max `TR_SIGNAUX_MAX_JOUR` par jour, les meilleurs potentiels nets d'abord. |
| 5. Signaux de VENTE | toutes les 15 min | Chaque signal est suivi comme une position du GARDIEN : stop (1,5 ATR), « monte ton stop au prix d'achat » à +1 R, stop suiveur (2 ATR, par pas de 1 ATR), objectif (6 ATR), retournement de la tendance 1 h, fin de suivi après `TR_SUIVI_JOURS` jours. |

## Commandes

- Telegram : **/tr** (état, suivis en cours, bilan des signaux clos après frais), **/univers**.
- Serveur : `bots tr-test`, `bots tr-univers [fichier.pdf]`, `bots tr-montant 500`, `bots tr-journal`,
  `bots tr-demarrer`, `bots tr-arreter`, `bots etat`.

## Limites à connaître

- Signaux d'alignement de tendance **non validés par backtest** : le bilan de `/tr` sert précisément à juger,
  après quelques semaines, s'ils valent quelque chose.
- Yahoo est gratuit et non officiel : certaines bourses sont différées de 15-20 min, et Yahoo peut limiter les
  requêtes (la veille se met en pause 30 min puis reprend seule).
- Les cours Yahoo sont dans la devise de la cotation (USD, GBp...) alors que TR affiche des euros :
  stop et objectif sont donnés en % pour cette raison.
- Obligations, dérivés et cryptos de la liste TR ne sont pas suivis (pas sur Yahoo ; la crypto est déjà
  couverte par le bot Binance).
- Si le PDF officiel change d'adresse : télécharge-le depuis le site Trade Republic, envoie-le par SFTP,
  puis `bots tr-univers /root/NOM.pdf`.

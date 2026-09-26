# V17.9 — TradingView, Polymarket et Jev

Ce qui peut être relié aux bots, ce qui ne peut pas l'être, et pourquoi. Aucun de ces liens ne passe
d'ordre, ne parie et ne reçoit tes clés Binance.

## TradingView (compte gratuit « Basic ») — relié à l'application iPhone

| Fonction | Où | Compte gratuit |
|---|---|---|
| Graphique en direct de chaque crypto suivie ou détenue par les bots (Binance, bougies de 15 min) | App > **Positions** (en haut) ; toucher une position affiche son graphique | ✅ |
| Bouton **Ouvrir dans TradingView** : le même graphique dans ton app TradingView (ou le site), avec ton compte, tes dessins et tes indicateurs | App > Positions | ✅ |
| Bouton **Liste pour TradingView** : la liste des marchés des bots (`BINANCE:BTCUSDT,…`) à importer dans une liste de suivi | App > Positions | ✅ (import sur le site web : liste de suivi > « Importer la liste ») |
| Alertes TradingView → bots (webhooks) | — | ❌ Réservé aux offres payantes (à partir de « Essential »). Il faudrait aussi ouvrir le serveur à Internet. Non installé. |

Le graphique est le widget public officiel de TradingView : il ne voit pas ton compte et ton compte ne voit pas
les bots. La liaison se fait par le bouton « Ouvrir dans TradingView » et par la liste importée.

## Polymarket — déjà relié, en lecture seule

L'armée de renseignement lit déjà toutes les 30 minutes les probabilités **publiques** des marchés de
prédiction (économie, banques centrales, géopolitique, crypto ; le sport est ignoré). Nouveau : les plus
marquantes des dernières 24 h sont affichées dans l'app, onglet **Veille**.

**Aucun pari n'est et ne sera passé** : l'ANJ a ordonné le blocage de Polymarket en France le 16 juillet 2026
(offre de jeux d'argent non autorisée). Ces probabilités ne sont pas utilisées pour décider des achats :
une question comme « Bitcoin au-dessus de 120 000 $ ? » n'indique pas une direction fiable, et les
contrôles de la v17.8 exigent qu'un nouveau signal soit d'abord validé sur l'historique.

## Jev (jevai.org) — non relié

Jev n'est pas une plateforme de marché : c'est un modèle d'IA (TypeSafe AI) spécialisé dans le tri et la
classification de textes. Il n'apporte ni prix, ni données de marché, ni ordres. Le projet utilise déjà
Claude (clé `ANTHROPIC_API_KEY`) pour lire la presse. Remplacer ou doubler ce lecteur par Jev demanderait une
clé API payante (l'essai gratuit s'est terminé le 25 septembre 2026) sans gain démontré. À reconsidérer
seulement si une comparaison mesurée montre qu'il classe mieux les nouvelles.

## Application iPhone : correctif `bots app`

La première fois, Tailscale affiche un lien d'activation du partage HTTPS et **attend** qu'on l'ouvre.
L'ancienne commande masquait ce lien : elle semblait figée. Désormais le lien s'affiche, avec la marche à
suivre, et l'attente est limitée à 5 minutes. Si le partage n'est toujours pas actif, `bots app` le dit et
indique quoi activer dans la console Tailscale (DNS > MagicDNS et HTTPS Certificates).

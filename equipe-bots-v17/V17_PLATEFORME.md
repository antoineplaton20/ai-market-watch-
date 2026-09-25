# V17 sur la plateforme (serveur Hetzner + Telegram)

## Ce qui tourne après la mise à jour

| Service | Rôle | Commande |
|---|---|---|
| `equipe-bots` | bot principal (v14.1 inchangé) : compte **démo** Binance, exploration, évolution | `bots etat` |
| `equipe-bots-tr` | veille Trade Republic (signaux manuels) | `bots tr-demarrer` |
| `equipe-bots-v17` | **moteur v17** : portefeuille **fictif** (défaut) ou **compte démo** Binance | `bots v17-demarrer` / `bots v17-demo` |
| `equipe-bots-v17-api` | API de lecture v17 (facultative, 127.0.0.1 uniquement) | `bots v17-api-demarrer` |

Deux modes pour la v17 :

- **fictif** (par défaut) : aucun ordre. Caisse fictive de 10 000 $ sur les prix publics de Binance, frais
  Binance (0,1 %) et glissement simulés.
- **démo** (`bots v17-demo`) : **vrais ordres sur le compte démo Binance** (argent fictif), le même compte que
  le bot principal, avec les clés démo déjà configurées. La v17 tient son propre carnet : elle ne vend **que ce
  qu'elle a elle-même acheté** (le bot principal fait pareil) et ne dépasse jamais son budget
  (`V17_CAPITAL_MAX_USDT`, 1 000 USDT par défaut). Le seul partage est donc celui des USDT libres du compte.

## Installer (depuis le téléphone, 5 minutes)

1. Termius > SFTP > envoie `equipe-bots-v17.zip` dans `/root`.
2. Terminal : `bots mettre-a-jour /root/equipe-bots-v17.zip`
   (sauvegarde de l'ancienne version, installation, **tous les tests** (plus de 220), puis retour arrière
   automatique si un seul échoue. Clés, historique, champion et réglages conservés.)
3. Terminal : `bots v17-demarrer` (une seule fois ; ensuite la v17 redémarre toute seule, y compris
   après les prochaines mises à jour).
4. Telegram : `/v17`.

## Passer la v17 sur le compte démo Binance

1. Termius : `bots v17-demo`
   - teste d'abord la connexion au compte démo (aucun ordre) ; en cas d'échec, rien ne change ;
   - clés utilisées : `V17_API_KEY` / `V17_API_SECRET` si tu les as mises, sinon celles du bot principal
     (uniquement s'il est lui-même en `MODE=demo`) ;
   - verrouille la v17 en démo (`V17_DEMO_ONLY=1`) : ni testnet, ni argent réel possibles.
2. Retour au portefeuille fictif : `bots v17-fictif` (prévient si la v17 détient encore des cryptos sur le
   compte démo : elles ne seraient plus surveillées).
3. Test seul : `bots v17-demo-test`.

Les scripts `termius_demo_*.sh` font la même chose : sur ce serveur, ils passent la main à `bots`.
Une seule v17 peut tourner à la fois (verrou) : impossible d'avoir le service et un script en double.

Si une crypto de la v17 disparaît du compte (vendue à la main, compte démo remis à zéro), la v17 la retire
de son carnet sans passer d'ordre et te prévient.

## Au quotidien

- Telegram : `/v17` (état et portefeuille), `/v17 stop` (pause des achats — ventes et protection
  continuent), `/v17 reprise`.
- Chaque achat 🟢 et chaque vente 🔴 de la v17 arrivent **tout de suite** sur Telegram, avec le son,
  préfixés `[v17]`. Les signaux refusés (budget, perte du jour...) arrivent en silencieux, au plus une
  fois toutes les 6 h.
- Termius : `bots v17-etat`, `bots v17-journal`, `bots v17-symboles BTC/USDT,ETH/USDT`.

## Fonctionnement du moteur

1. Toutes les 60 s : bougies de 15 min de chaque symbole (prix publics, aucune clé).
2. **Une décision par bougie fermée** (jamais sur une bougie en cours, jamais deux fois la même, même
   après un redémarrage).
3. Stratégie d'ensemble (inchangée) : moyenne 8 contre moyenne 30 + élan sur 10 bougies. Il faut au moins
   65 % d'accord (`V17_SCORE_MIN`).
4. Achat seulement si la crypto n'est pas déjà détenue. Montant = le plus petit de : 100 $
   (`MAX_ORDER_USDT`), place sous 250 $ par position, place sous le plafond de capital, caisse.
5. Vente de toute la position sur signal de vente, ou si la protection est touchée (-3 %,
   `V17_STOP_LOSS_PCT`). Un signal de vente sans position ne fait rien (spot : pas de vente à découvert).
6. Refus d'achat si la perte du jour dépasse 50 $ (`MAX_DAILY_LOSS_USDT`). `KILL_SWITCH=1` bloque tout.
7. Portefeuille, décisions et ordres enregistrés dans `runtime/v17_ops.db` (sauvegardé chaque jour avec le
   reste, conservé par les mises à jour). Journal : `v17.log`.

Tous les réglages sont facultatifs : voir la section V17 de `.env.example`. `bots config` les conserve.

## Ce qu'il faut savoir

- **La stratégie v17 n'est pas validée par un backtest.** Ce sont deux votes simples. Le portefeuille
  fictif sert justement à la juger sur de vrais prix avant toute autre décision.
- **Les catalogues v15/v16 (3 120 « bots ») sont des fiches de description** (`status: scaffold`,
  permission lecture seule). Aucun n'analyse ni ne trade. Ils sont testés mais ne tournent pas sur le serveur.
- Mode démo : testé contre un faux Binance et contre la vraie bibliothèque ccxt avec des réponses Binance
  simulées (aucun accès réseau pendant la préparation). `bots v17-demo-test` fait le vrai test sur le serveur.
- `testnet` exige des clés sandbox propres à la v17. `live` (argent réel) exige des clés d'un sous-compte
  dédié, différentes de celles du bot principal, et `LIVE_TRADING_ENABLED=1` : non recommandé.
- Docker (`docker-compose.v17.yml`) sert à un essai hors plateforme. Sur le serveur : systemd uniquement.
  Docker contourne le pare-feu ufw, c'est pourquoi l'API n'y est publiée que sur 127.0.0.1.

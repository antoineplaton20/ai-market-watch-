# V17.6 — Bots increvables

Objectif : **rien n'arrête les bots, sauf toi.** Plantage, Binance injoignable, Telegram en panne, fichier
d'état abîmé, réglage invalide, ordre au résultat incertain, bot figé, redémarrage du serveur : tout se
relance ou se répare tout seul.

## Installer (serveur de la plateforme)

1. Termius > SFTP > envoie `equipe-bots-v17.zip` dans `/root`.
2. `bots mettre-a-jour /root/equipe-bots-v17.zip` (tests + retour arrière automatique).
3. **Une seule fois** : `bots increvable` (réécrit toutes les unités systemd avec la relance sans fin et
   redémarre ce qui était en service). À faire une fois, car c'est l'ancienne télécommande qui exécute la
   mise à jour.
4. `bots etat` pour vérifier.

Sur une autre machine Linux (sans « bots ») : `./termius_demo_start.sh` lance maintenant un **superviseur**
qui relance la v17 sans fin, et ajoute deux lignes cron (contrôle toutes les 5 min + relance au démarrage de
la machine). Arrêt : `./termius_demo_stop.sh` (arrête le superviseur ET retire les lignes cron).

## Ce qui a changé

| Point de panne (avant) | Maintenant |
|---|---|
| systemd abandonnait après 6 plantages en 1 h (`StartLimitBurst=6`) | `StartLimitIntervalSec=0` : jamais d'abandon ; relance 15 s puis attente croissante jusqu'à 5 min |
| `Restart=on-failure` : une sortie « propre » inattendue n'était pas relancée | `Restart=always` sur tous les services |
| Chien de garde `lanceur.py` : arrêt définitif après 5 plantages en 1 h | Relance sans fin ; en cas de tempête, une alerte Telegram par heure |
| `lanceur.py` s'arrêtait si un autre bot tenait le verrou | Attend 60 s et réessaie |
| Bot principal : Binance injoignable au démarrage = plantage | Réessaie sans fin (15 s → 5 min), message au retour |
| Une erreur Telegram / évolution / rapport sautait toute la boucle (dont les achats) et, répétée, faisait tuer le bot | Chaque tâche annexe est isolée ; état et signe de vie toujours enregistrés ; redémarrage à neuf seulement après ~1 h d'erreurs continues |
| v17 : réglage invalide dans `.env` = arrêt définitif (`RestartPreventExitStatus=2`) | Valeur invalide remplacée par la valeur par défaut (+ alerte) ; erreur bloquante = nouvel essai toutes les 30 min, alerte au plus toutes les 6 h |
| v17 : tous les symboles invalides = arrêt | Repli sur BTC/USDT + alerte |
| v17 : moteur figé non détecté | Watchdog systemd (`WatchdogSec=900`) : un moteur figé est tué et relancé |
| v17 : « rapprochement requis » bloquait tout jusqu'à une intervention manuelle | **Démo/testnet** : la v17 interroge Binance (identifiant client de l'ordre) chaque minute et lève le blocage seule (voir ci-dessous) |
| v17 : glissement excessif = achats en pause jusqu'à `/v17 reprise` | Pause de 60 min puis reprise automatique (`V17_SLIPPAGE_PAUSE_MIN`) |
| Veilles marchés / TR : fichier d'état abîmé ou disque plein = plantage | État neuf / sauvegarde sautée, la veille continue |
| Armée de renseignement : une erreur de cycle arrêtait tout | Le cycle est protégé, l'armée continue |
| Scripts Termius hors plateforme : `nohup` sans relance | Superviseur + cron (relance après plantage et après redémarrage de la machine) |

## Rapprochement automatique (démo et testnet uniquement)

- **Ordre au résultat incertain** (coupure pendant l'envoi) : la v17 demande à Binance l'ordre portant son
  identifiant client. Exécuté → carnet mis à jour avec la quantité et le prix réels ; clos sans exécution → rien ;
  encore ouvert → annulé puis relu ; inconnu de Binance depuis plus de 2 min → il n'est jamais parti.
  Jamais de second envoi à l'aveugle.
- **Solde incohérent** (crypto vendue à la main, compte démo remis à zéro) : si cela dure 10 min, le carnet de
  la v17 est aligné sur le compte Binance, sans inventer de recette de vente.
- Désactivable : `V17_AUTO_RECONCILE=0`. En **argent réel**, rien n'est automatique (procédure manuelle
  inchangée, `bots v17-rapprochement`).

## Ce qui reste volontairement

Ce sont des **règles de trading**, pas des pannes : elles ne tuent aucun processus et se lèvent seules ou sur
ta commande.

- Perte maximale du jour (`MAX_DAILY_LOSS_USDT`) : plus d'achats jusqu'au lendemain (UTC), ventes et
  protections continuent.
- Disjoncteur de performance et coupe-circuit des essais du bot principal.
- `/stop`, `/v17 stop`, `KILL_SWITCH=1` : tes interrupteurs. Ils restent prioritaires.
- Arrêt volontaire : `bots arreter`, `bots v17-arreter`, `bots tr-arreter`, `bots marches-arreter`,
  `bots renseignement-arreter` (systemd respecte toujours un arrêt demandé).

Rappel : ces changements rendent les bots plus **robustes**, pas plus **rentables**. La stratégie v17 n'est
pas validée (voir `LIRE_AVANT_UTILISATION.md`) ; le compte reste en démo.

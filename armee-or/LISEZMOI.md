# Armée de l'or — v2 (avec MetaTrader 5 démo)

Des bots dédiés **uniquement à l'or**. Ils tournent **à côté** de l'équipe V17.9, sans jamais la toucher :

| | Équipe V17.9 | Armée de l'or |
|---|---|---|
| Dossier | `/home/bots/equipe-bots` | `/home/bots/armee-or` |
| Python | son `.venv` | son propre `.venv` |
| Base de données | la sienne | `runtime/or.db` (SQLite) |
| Services | `bots-*` | `armee-or-flux`, `armee-or-chef`, `armee-or-mt5` |
| Télécommande | `bots` | `or` |
| Clé Claude | – | **aucune** |

Les comptes de levier x1 → x50 restent **simulés sur papier**. Si tu branches MetaTrader 5, l'armée passe aussi de **vrais ordres sur ton compte DÉMO** (argent fictif). Elle refuse tout ordre sur un compte réel : le contrôle est fait deux fois, dans le chef et dans le pont MT5. Aucune clé Binance n'est demandée.

## Installation (Termius, en root)

1. Envoie `armee-or-v2.zip` dans `/root` (SFTP de Termius).
2. Lance :
   ```
   unzip -o /root/armee-or-v2.zip -d /root/
   bash /root/armee-or/installer_or.sh
   ```
3. Choisis le Telegram :
   - **Recommandé** : crée un nouveau bot avec @BotFather (`/newbot`), colle le jeton, puis envoie « bonjour » à ce nouveau bot. Tu pourras ensuite lui envoyer `/or`, `/or_levier`, `/or_bilan`, `/or_pause`, `/or_reprise`, `/or_bibliotheque`, `/or_mt5`, `/or_mt5_fermer`, `/or_mt5_reprendre`.
   - **Sinon**, appuie sur Entrée : ton bot actuel est réutilisé en **envoi seul**, avec des messages préfixés 🟡 [or]. Il ne lit jamais les messages, pour ne pas voler les commandes de l'équipe V17.9.
4. À la question « Brancher ton compte DÉMO MetaTrader 5 ? », réponds **O**. Donne ensuite :
   - le login ;
   - le mot de passe **principal**, qui reste invisible pendant la frappe (le mot de passe investisseur ne permet que la lecture) ;
   - le serveur (`MetaQuotes-Demo` par défaut).
5. L'installateur :
   - lance les tests et s'arrête si un seul échoue ;
   - importe l'historique livré (environ 5 s) ;
   - installe Wine, un écran virtuel, le terminal MT5 et Python pour Windows avec la bibliothèque officielle MetaTrader5 (10 à 20 minutes la première fois) ;
   - démarre les services.

## Commandes Termius

```
or etat          cours en direct, rythme, marchés liés, pronostics, comptes papier, santé des bots
or levier        fiches x1 → x50 : marge, prix de liquidation, perte au stop, risque historique
or bilan         bilan sur tout l'historique (sans regarder le futur, frais compris)
or bibliotheque  études et manuels utilisés
or pause|reprise positions papier suspendues / reprises (l'analyse continue)
or journal       journal en direct
or demarrer|arreter|redemarrer
or test          contrôle complet
or mt5           compte MT5 démo : solde, positions de chaque équipe, résultats
or mt5 fermer    ferme toutes les positions de l'armée et suspend ses ordres (or mt5 reprendre)
or mt5 profil x20            levier des décisions : x1 x3 x5 x10 x20 x50 ou pro (défaut : pro 1 % risqué)
or mt5 entrainement on|off   équipe d'entraînement au lot minimum
or mt5 journal | compte      journal du pont MT5 / changer de compte démo
or mettre-a-jour /root/armee-or-vX.zip
or config        refaire le réglage Telegram
```

## L'armée

Le **chef d'orchestre** (`armee-or-chef`) fait passer chaque bot à son tour, toutes les quelques secondes. Chaque passage est inscrit dans la table `rapports` : réussite, durée, message. Si un bot échoue :

- ses tentatives sont espacées, jusqu'à 1 h maximum ;
- après 5 échecs, une alerte part sur Telegram ;
- **les autres bots continuent**.

systemd relance les services quoi qu'il arrive : `Restart=always`, sans limite de relances, et un watchdog de 10 min.

| Bot | Rythme | Rôle |
|---|---|---|
| Vigies du cours (`armee-or-flux`) | continu | WebSocket Binance XAUUSDT (perpétuel or) et PAXGUSDT, bougies 1 min. Retard affiché en ms, reconnexion automatique, rattrapage REST des minutes perdues. |
| Vigie du cours | 30 s | Fraîcheur du prix. Écart PAXG/XAU > 1 %. Secours COMEX (GC=F) si Binance est muet. |
| Archiviste | 60 s | Bougies 1 min → 15 min → 1 h → 4 h → 1 j. Mise à jour COMEX quotidienne. |
| Vigie des marchés liés | 15 min | Dollar (DXY), taux US 10 ans, argent, cuivre, pétrole, S&P 500, VIX, EUR/USD, mines d'or (GDX), Bitcoin. Corrélations sur 60 jours et « contexte » pour l'or. |
| Analyste du rythme | 5 min | Séance (Asie / Londres / New York), rang de volatilité, expansion, séries de bougies, régime. |
| Analyste des chandeliers | 60 s | 16 motifs (marteau, avalements, étoiles, trois soldats…) avec leur **taux de réussite réel mesuré sur l'or**. |
| Pronostiqueurs + décision | 60 s | 7 pronostiqueurs (tendance, momentum, retour à la moyenne, chandeliers, canal, saisonnalité, volatilité) en 1 h, 4 h et 1 j. Chacun est noté en continu (Brier) contre le naïf. Consensus pondéré par la compétence. Décision seulement si l'avantage dépasse 1,5 × les coûts. |
| Stratège de fond | 1 h | « Garder l'or » comparé à « tendance 10 mois » (Faber) sur les clôtures COMEX. |
| Bilan historique | 7 j | Rejoue tout l'historique sans regarder le futur. |
| Commandes / Rapporteur | 10 s / 6 h | Commandes Telegram ou Termius. Rapport complet toutes les 6 h. |

Les comptes papier sont suivis **par profil de levier** : x1, x3, x5, x10, x20 (max. UE), x50 (max. Binance) et « pro 1 % risqué ». Ils comptent :

- les frais et le glissement ;
- le financement horaire ;
- les trous d'ouverture ;
- la liquidation, testée en premier.

## MetaTrader 5 : l'armée s'entraîne sur ton compte démo

Ubuntu ne peut pas lancer MT5 directement. Le service `armee-or-mt5` fait tourner le terminal officiel sous Wine, la méthode de MetaQuotes pour Linux, avec un écran virtuel. Un **pont** (`armee_or/pont_mt5.py`) y utilise la bibliothèque officielle MetaTrader5. Le reste de l'armée lui parle uniquement par `127.0.0.1`.

| Équipe | Numéro magique | Quand | Taille | Sortie |
|---|---|---|---|---|
| Décisions 4 h | 770004 | décision du chef (avantage > 1,5 × coûts) | profil choisi (défaut : 1 % du capital risqué) | stop 3 ATR ou 24 h |
| Décisions 1 j | 770024 | décision du chef | profil choisi | stop 3 ATR ou 5 jours |
| Entraînement 1 h | 770001 | chaque bougie d'1 h, sens du consensus | lot minimum (0,01) | stop 3 ATR ou 4 h |

- Chaque équipe a au plus une position à la fois. Une décision donne un seul ordre au plus.
- L'équipe d'entraînement trade **même quand l'avantage est inférieur aux coûts**. Elle mesure en vrai l'écart achat/vente, l'exécution et la justesse des pronostics. Elle perdra probablement un peu : c'est le prix de la mesure.
- **Tes ordres manuels ne sont jamais touchés** : le pont ne ferme que les positions qui portent un numéro magique de l'armée.
- Tu peux suivre les positions en direct dans l'app **MetaTrader 5 sur iPhone**, connectée au même compte démo.
- `or pause` ou `or mt5 fermer` arrêtent les nouveaux ordres. `or arreter` laisse les positions ouvertes avec leur stop.
- Si le pont perd la connexion au serveur MT5 pendant 10 minutes, il se relance avec le terminal. Le chef signale le problème sur Telegram.

Ce qui a été vérifié avant livraison :
- les 45 tests passent, dont 18 sur MT5 avec un faux terminal ;
- Wine 11 s'installe sur Ubuntu 24.04 ;
- la vraie bibliothèque MetaTrader5 (5.0.6180) tourne sous Wine et expose exactement les fonctions et constantes utilisées ;
- le vrai pont sous Wine répond au client Linux.

Ce qui n'a **pas** pu être testé depuis ma machine : l'installation du terminal, la connexion à ton compte et le premier ordre réel de démo. `or mt5` et `or mt5 journal` te montrent où ça en est.

## Les données livrées (`donnees_initiales/`, voir `PROVENANCE.md`)

- **Or mensuel depuis 1833** et annuel : jeu de données public `datasets/gold-prices`.
- **COMEX GC=F quotidien** depuis 2000 : 6 102 bougies.
- **Binance PAXGUSDT** en 15 min depuis 10/2020 (207 363 bougies) et **XAUUSDT** en 15 min depuis 01/2026. Il s'agit des archives officielles `data.binance.vision`, dont chaque fichier est vérifié par SHA-256.

## Ce que l'historique a montré (honnêtement)

Mesures sans regarder le futur, frais compris, capital de départ 1 000 $ :

| Unité | Décisions | x1 | x3 | x10 | x20 | x50 | pro 1 % |
|---|---|---|---|---|---|---|---|
| 1 h | 0 | 1000 | 1000 | 1000 | 1000 | 1000 | 1000 |
| 4 h | 6 | 938 | 822 | 481 | 154 | **0 ruiné** | 982 |
| 1 j | 166 | 955 | 755 | **44 ruiné** | **0 ruiné** | **0 ruiné** | 1011 |

Sur la même période, **garder l'or a fait ×2,35**. Depuis 2000, le facteur est ×15,8.

- En 1 h, les pronostiqueurs font à peine mieux que le hasard (quelques dixièmes de %). C'est **moins que les frais** : le chef refuse donc de trader, et c'est voulu.
- Sur PAXG 1 h, la plupart des motifs de bougies sont suivis du mouvement **inverse**. Par exemple, après un avalement haussier, la hausse ne vient que 43 % du temps, contre 48 % en moyenne.
- En x50, la liquidation est à 1,5 % du prix d'entrée : ce seuil a été franchi dans 13,7 % des fenêtres de 24 h passées. En x20, la liquidation est à 4,5 %.
- La règle des 10 mois réduit la pire baisse (35 % au lieu de 62 % sur 1971-2026). En revanche, sur les vraies clôtures COMEX 2000-2026, elle rapporte **moins** que garder l'or (7,3 %/an contre 11,1 %/an).

## Limites

- **Influencer le rythme des bougies**, c'est de la manipulation de marché, interdite par le règlement européen MAR. L'armée observe et calcule, elle n'influence rien.
- **Aucune architecture ne garantit un profit.** Environ 89 % des particuliers sur CFD/Forex perdent de l'argent (AMF, 2014). Le levier maximal pour un particulier dans l'UE est de 20 sur l'or (ESMA).
- **MT5 démo** : les résultats de démo ne garantissent rien en réel, car l'exécution et les écarts diffèrent selon le courtier. Le compte « MetaQuotes-Demo » sert à s'entraîner, pas à trader de l'argent.
- **Binance** a cessé de servir les résidents de l'UE au 1er juillet 2026 (MiCA), et XAUUSDT n'y est pas ouvert aux Européens. Les flux publics restent lisibles depuis le serveur, ce qui suffit à l'armée, qui ne passe aucun ordre.
- « Aucune erreur possible » n'existe pas. Ce qui existe : chaque erreur est isolée, relancée, comptée et signalée au chef, puis sur Telegram.

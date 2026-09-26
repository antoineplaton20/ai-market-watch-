# Application iPhone « Bots »

Tableau de bord de **toute** l'équipe (bot principal, moteur v17, veilles, renseignement) et commandes
essentielles, dans une application plein écran avec son icône sur l'iPhone.

C'est une **application web installable** : elle s'installe depuis Safari, sans App Store, sans Mac et sans
compte développeur Apple. Le serveur la fournit ; ton téléphone ne garde que le code d'accès.

## Installation (10 minutes, une seule fois)

Sur le serveur (Termius), après `bots mettre-a-jour /root/equipe-bots-v17.zip` :

```bash
bots app-tailscale     # installe Tailscale et affiche un lien de connexion à ouvrir
```

1. Ouvre le lien affiché et crée ton compte Tailscale (gratuit), par exemple avec ton compte Apple ou Google.
2. Si le message parle de « HTTPS Certificates » : console Tailscale > **DNS** > active **MagicDNS** et
   **HTTPS Certificates**, puis `bots app`.
3. Sur l'iPhone : installe **Tailscale** (App Store) et connecte-toi avec **le même compte**.
4. Ouvre dans **Safari** l'adresse affichée par `bots app` (du type `https://serveur.xxxx.ts.net/app/`).
5. Entre le **code d'accès** affiché par `bots app`.
6. Safari > bouton **Partager** > **Sur l'écran d'accueil** > Ajouter. L'icône **Bots** apparaît.

Dépannage sans Tailscale : Termius > Port Forwarding > Local, port 8080 vers `127.0.0.1:8080`, puis Safari
`http://127.0.0.1:8080/app/`. Cela ne fonctionne que tant que Termius reste ouvert.

## Ce que montre l'application

| Onglet | Contenu |
|---|---|
| Accueil | Alertes, moteur v17 (valeur, courbe, résultat du jour), bot principal (gain latent, risque, signe de vie), état de chaque service |
| Positions | Graphique TradingView en direct (toucher une position l'affiche), boutons « Ouvrir dans TradingView » et « Liste pour TradingView » ; achats en cours du bot principal (stop, objectif, 🔒 sans perte, 🧪 essai) et de la v17, derniers ordres v17 |
| Labo | Idée de stratégie en français → IA Claude → backtest sur l'historique Binance → 7 portes → Pine Script TradingView → test en direct papier (voir LABO.md) |
| Journal | Dernières lignes des journaux : principal, v17, marchés, renseignement, TR (secrets masqués) |
| Veille | Armée de renseignement (climat mondial, alertes), marchés de prédiction Polymarket (lecture seule) et veille marchés |
| Commandes | Bot principal : arrêter / reprendre les achats, réarmer la sécurité, tout vendre (il faut écrire VENDRE). v17 : pause / reprise des achats. Réglages : actualisation, apparence, déconnexion |

Actualisation automatique toutes les 20 s. Sans réseau, l'application affiche les dernières données reçues.
`https://…/app/?demo=1` : démonstration avec des données fictives.

## Sécurité

- L'API écoute uniquement sur `127.0.0.1` : aucun port n'est ouvert sur Internet. Tailscale crée un réseau
  privé chiffré entre **tes** appareils seulement.
- Toutes les données et commandes exigent le code d'accès (`V17_APP_TOKEN` dans `.env`). 10 codes faux en
  10 minutes verrouillent l'application pendant 10 minutes. Nouveau code : `bots app-nouveau-code`.
- Les commandes du bot principal passent par une liste blanche (`/stop`, `/reprise`, `/rearmer`,
  `/vendre_tout`) et sont appliquées par le bot lui-même, avec confirmation sur Telegram, comme depuis Telegram.
- Les jetons Telegram, signatures Binance et clés Anthropic sont masqués dans les journaux affichés.
- Aucune clé Binance n'est jamais envoyée au téléphone.

## Limites

- Les notifications restent sur Telegram. Les notifications web d'iOS demanderaient un service d'envoi en plus.
- Une vraie application App Store (Swift) demanderait un Mac, Xcode et un compte développeur Apple (99 $/an).
  L'application web fait la même chose ici, sans ces contraintes.

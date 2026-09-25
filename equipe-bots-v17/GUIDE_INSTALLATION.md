# Guide d'installation pas à pas (100 % depuis ton téléphone)

**Ce que tu vas obtenir** : l'équipe de bots tourne 24 h/24 sur un serveur en Allemagne ou en Finlande,
en **mode démo** (vrais prix, argent fictif). Tu suis et tu pilotes tout depuis Telegram.

**Durée** : environ 1 h 30 la première fois (dont 30 à 90 min où tu n'as rien à faire).
**Coût** : environ 4 à 6 € par mois pour le serveur. L'IA (clé Anthropic) est facultative et payée à l'usage.

**Il te faut** : ton téléphone, une adresse e-mail, une carte bancaire (pour le serveur),
ton compte Binance, et l'application Telegram.

> Règle d'or : tes clés (Binance, Telegram, Anthropic) ne se partagent JAMAIS, avec personne,
> même pas avec Claude. Tu les colleras uniquement dans l'assistant d'installation, sur TON serveur.

---

## Étape 1 — Créer ton bot Telegram (5 min)

**Pourquoi** : c'est par lui que tu recevras toutes les alertes et que tu piloteras le bot.

1. Ouvre Telegram, cherche **@BotFather** (avec la coche bleue officielle).
2. Appuie sur **Démarrer**, puis envoie : `/newbot`
3. Donne-lui un **nom** (exemple : `Mes Bots Crypto`), puis un **identifiant** qui finit par `bot`
   (exemple : `antoine_equipe_bot`).
4. BotFather te répond avec un **token**, une longue suite du type `7123456789:AAH...`.
   **Copie-le dans tes notes** : tu en auras besoin à l'étape 7.
5. Ouvre ton nouveau bot (lien donné par BotFather) et appuie sur **Démarrer**.

---

## Étape 2 — Créer tes clés Binance Démo (10 min)

**Pourquoi** : le mode démo utilise les vrais prix du marché avec de l'argent fictif. C'est là que le bot
fait ses preuves pendant au moins 4 semaines, sans aucun risque.

1. Dans ton navigateur, va sur **demo.binance.com** et connecte-toi avec ton compte Binance.
2. Ouvre **Gestion des API** (en anglais *API Management* ; le libellé peut varier).
3. Crée une clé (type *généré par le système* / HMAC si on te demande), donne-lui un nom (`bots`).
4. Binance affiche une **API Key** et une **Secret Key**.
   **Copie les deux dans tes notes tout de suite** : la clé secrète ne s'affiche qu'une seule fois.
5. Autorisations : le trading au comptant (*Spot*) doit être actif. **Jamais les retraits.**
6. La restriction d'adresse IP se fera à l'étape 8, une fois le serveur créé.

> Les clés démo ne marchent qu'en démo. Pour le réel, il faudra plus tard de NOUVELLES clés sur binance.com.

---

## Étape 3 — Clés facultatives (5 min, tu peux passer)

- **Anthropic** (l'IA du CONTRADICTEUR, de la VEILLE et des thèses) : **console.anthropic.com** > API Keys >
  Create Key. Payant à l'usage. Sans elle, le bot fonctionne, mais sans relecture par l'IA.
- **CoinGecko « Demo »** (gratuite, sert à la recherche fondamentale) : **coingecko.com** > Developers >
  API > plan Demo gratuit > copie la clé.

---

## Étape 4 — Louer le serveur (15 min)

**Pourquoi** : un serveur tourne jour et nuit sans jamais se mettre en veille, avec une adresse IP fixe
(ce qui permet de verrouiller ta clé Binance sur ce seul serveur).

1. Va sur **hetzner.com** > **Cloud** > crée ton compte. Hetzner peut demander une vérification d'identité
   avant le premier serveur : c'est normal.
2. Dans la **Cloud Console** : **Nouveau projet** (nom : `bots`) > ouvre-le > **Ajouter un serveur**.
3. Choisis exactement :
   - **Emplacement** : Allemagne (**Nuremberg** ou **Falkenstein**) ou Finlande (**Helsinki**).
     **Pas les États-Unis** : Binance y est interdit.
   - **Image** : **Ubuntu 24.04**.
   - **Type** : processeur partagé **x86**, la plus petite offre avec **au moins 4 Go de mémoire**
     (en 2026 : **CX23**).
   - **Réseau** : laisse **IPv4 public** coché (indispensable pour Binance).
   - **Clé SSH** : ne mets rien. Hetzner t'enverra le mot de passe par e-mail.
   - **Nom** : `bots`.
4. Appuie sur **Créer et acheter**.
5. Tu reçois un **e-mail** avec l'**adresse IP** du serveur et le **mot de passe root**. Garde-le ouvert.

---

## Étape 5 — Se connecter au serveur avec Termius (5 min)

**Pourquoi** : Termius est une application gratuite qui te donne un terminal sur ton serveur depuis le téléphone.

1. Installe **Termius** (App Store / Play Store), ouvre-la. Le compte Termius est facultatif.
2. **Hosts** > **+** > **New Host** :
   - **Address** : l'adresse IP de l'e-mail
   - **Username** : `root`
   - **Password** : le mot de passe de l'e-mail
3. Enregistre, puis appuie sur le serveur pour te connecter.
4. Première connexion : Termius demande de faire confiance à l'empreinte du serveur > **Continue**.
   Si le serveur te demande de changer le mot de passe, choisis-en un solide et **note-le**.
5. Tu vois une ligne qui finit par `root@bots:~#` : tu es sur ton serveur.

> Coller dans Termius : appui long sur l'écran > **Paste**. La touche **Ctrl** est dans la barre au-dessus du clavier.

---

## Étape 6 — Mettre le code en ligne pour le serveur (5 min)

**Pourquoi** : le serveur doit pouvoir télécharger le fichier `equipe-bots-v17.zip` que Claude t'a donné.

1. Télécharge **equipe-bots-v17.zip** depuis la conversation avec Claude (il va dans tes Fichiers / Téléchargements).
2. Ouvre **Google Drive** > **+** > **Importer** > choisis le zip.
3. Sur le fichier : **⋮** > **Partager** > **Accès général** : « Tous les utilisateurs disposant du lien » >
   **Copier le lien**.
   (Avec **Dropbox** : Partager > Copier le lien, ça marche aussi.)

> Le zip ne contient aucune clé ni aucun mot de passe. Tu supprimeras quand même ce partage à l'étape 11.

---

## Étape 7 — Lancer l'installation (15 à 20 min)

**Pourquoi** : un seul script installe tout (sécurité, Python, bot, tests, démarrage automatique) et te pose
les questions de configuration une par une.

**7.1** Dans Termius, colle cette ligne en remplaçant `COLLE_ICI_TON_LIEN` par le lien copié à l'étape 6
(garde les apostrophes), puis **Entrée** :

```bash
LIEN='COLLE_ICI_TON_LIEN'
```

**7.2** Puis colle ce bloc entier et appuie sur **Entrée** :

```bash
apt-get update -qq; apt-get install -y -qq unzip curl
ID=$(echo "$LIEN" | grep -oE '/d/[^/]+' | cut -d/ -f3); [ -n "$ID" ] && LIEN="https://drive.google.com/uc?export=download&id=$ID"
curl -sL "${LIEN/dl=0/dl=1}" -o /root/bots.zip && unzip -oq /root/bots.zip -d /root && bash /root/equipe-bots-v17/installer.sh
```

Ce que fait chaque ligne :
- **ligne 1** : installe les deux outils pour télécharger et décompresser ;
- **ligne 2** : transforme ton lien Google Drive en lien de téléchargement direct ;
- **ligne 3** : télécharge le zip, le décompresse, puis lance l'installateur.

**7.3** L'installateur déroule 9 étapes. Tu verras défiler :
1. mise à jour du serveur (2 à 5 min) ;
2. heure de Paris et synchronisation automatique de l'horloge (Binance refuse les ordres mal datés) ;
3. pare-feu (seul l'accès SSH reste ouvert), protection anti-intrusion, mises à jour de sécurité automatiques ;
4. mémoire de secours de 2 Go (évite les plantages pendant l'évolution) ;
5. compte dédié `bots` : le bot ne tourne jamais en administrateur ;
6. Python et bibliothèques (3 à 8 min, **c'est normal que ce soit long**) ;
7. **tous les tests automatiques** : si l'un échoue, l'installation s'arrête et affiche pourquoi ;
8. **les questions de configuration** (ci-dessous) ;
9. démarrage automatique du bot, qui redémarrera seul si le serveur redémarre.

**7.4** Les questions (étape 8/9) — colle chaque réponse puis **Entrée** :

| Question | Ta réponse |
|---|---|
| Mode | **Entrée** (= `demo`) |
| Clé API | l'API Key de l'étape 2 |
| Clé secrète | la Secret Key de l'étape 2 |
| Plafond en USDT | **Entrée** (= 1 000 en démo) |
| Token du bot Telegram | le token de l'étape 1 |
| « Envoie bonjour à ton bot, puis Entrée » | dans Telegram, envoie `bonjour` à ton bot, reviens, **Entrée** |
| Clé Anthropic | colle-la, ou **Entrée** pour passer |
| Clé CoinGecko | colle-la, ou **Entrée** pour passer |

À la fin de la configuration :
- **Telegram** reçoit « ✅ Le bot est bien relié à ton Telegram » ;
- le terminal affiche « ✔ Connexion Binance réussie ». En cas d'erreur, il explique quoi corriger,
  puis tu relances la configuration avec `bots config`.

**7.5** L'installation se termine par **✔ INSTALLATION TERMINÉE**. Sur Telegram arrive
« 🤖 Bots v17 démarrés » avec la liste des commandes.

---

## Étape 8 — Verrouiller la clé Binance sur ton serveur (2 min)

**Pourquoi** : même si quelqu'un volait ta clé, elle ne marcherait que depuis ton serveur.

1. Dans Termius, tape : `bots ip` → note l'adresse affichée.
2. Sur demo.binance.com > Gestion des API > ta clé > **Modifier les restrictions** >
   **Restreindre l'accès aux IP de confiance** > colle l'adresse > enregistre.
3. Vérifie que tout marche encore : `bots redemarrer`, puis `/sante` dans Telegram.

---

## Étape 9 — Vérifier que tout fonctionne (2 min)

Dans **Telegram**, envoie à ton bot :
- `/sante` → risque SÛR, disjoncteur armé, données fraîches, réseau ok ;
- `/statut` → mode DEMO, palier 1, aucune position pour l'instant.

Dans **Termius** : `bots etat` → « ● Bot en marche » et les dernières lignes du journal.

Tu peux maintenant **fermer Termius** : le bot continue sans toi.

---

## Étape 10 — La préparation automatique (30 à 90 min, rien à faire)

**Pourquoi** : avant de faire confiance au bot, le système se teste lui-même sur 2 ans d'historique.

Sur Telegram, tu recevras dans l'ordre :
1. 🧪 **Préparation lancée** ;
2. 📊 **Backtest terminé**, avec la comparaison 15 min / 1 h / 4 h. Trois cas possibles :
   - « l'unité actuelle est la bonne » → la première évolution démarre toute seule ;
   - « le backtest recommande des bougies de 1 h » → dans Termius, tape `bots unite 1h` puis `bots evolution` ;
   - « aucune unité n'a d'avantage prouvé » → le bot reste en démo, et l'évolution quotidienne continue à chercher ;
3. 🧬 **Évolution terminée** : nouveau challenger ou non, avec la mesure du sur-apprentissage (PBO).

---

## Étape 11 — Ménage de sécurité (1 min)

1. Dans Google Drive : sur le zip > **Partager** > **Accès restreint** (ou supprime le fichier).
2. Dans Termius, efface le zip du serveur : `rm -f /root/bots.zip`

---

## Au quotidien : tout se passe sur Telegram

**Les alertes qui sonnent** (à lire tout de suite) :
- 🔔 🟢 **ACHAT** : le bot vient d'acheter (prix, quantité, stop, score) ;
- 🔔 ✅ / 🔻 **VENTE** : le bot vient de vendre (raison, gain ou perte) ;
- 🔔 **Signal d'achat → ⛔ bloqué** : un achat était prévu mais un veto l'a bloqué (le message dit lequel) ;
- 🔔 🚨 **VENTE ANTICIPÉE** : vraie mauvaise nouvelle (piratage, délisting) sur une position, vendue aussitôt ;
- 🟠 / 🔴 **État de risque** : le bot réduit la taille de ses positions ou s'arrête ;
- 🙋 **APPROBATION DEMANDÉE** : deux boutons ✅ / ❌. Rien ne change tant que tu n'as pas répondu.

**Les messages silencieux** : stop suiveur remonté, signe de vie toutes les 6 h, bilan de 21 h,
recherche et évolution du dimanche.

**Tes commandes** :

| Commande | Effet |
|---|---|
| `/statut` | positions, risque, palier, résultats |
| `/rapport` | bilan de la journée |
| `/journal` | les 10 dernières décisions et leur issue |
| `/sante` | disjoncteur, données, réseau, sauvegarde |
| `/notes` | bulletin des bots sur 10 |
| `/calibration` | fiabilité mesurée de l'IA |
| `/evolution` | champion, challenger, état du duel |
| `/attente` | approbations en attente |
| `/stop` · `/reprise` | suspendre / reprendre les achats (les stops restent) |
| `/rearmer` | relancer après un disjoncteur (après avoir compris pourquoi) |
| `/vendre_tout` | tout vendre et suspendre les achats (urgence) |

**Chaque dimanche** : l'évolution et la recherche fondamentale tournent seules. Si un challenger a gagné
son duel, tu reçois la demande d'approbation avec ses chiffres.

**Facultatif** : `deblocages.csv` (déblocages de jetons à venir) se remplit à la main.
Dans Termius : `nano /home/bots/equipe-bots/deblocages.csv`, une ligne par déblocage
(`ARB;2026-10-16;2.3`), puis **Ctrl+O**, **Entrée**, **Ctrl+X** pour enregistrer et quitter.

---

## Si quelque chose ne va pas

| Ce que tu vois | Ce que ça veut dire | Quoi faire |
|---|---|---|
| Plus aucun message 💓 depuis plus de 7 h | le bot ou le serveur est arrêté | Termius : `bots etat`, puis `bots demarrer` |
| « ⚠️ Données douteuses » | Binance répond mal ou l'horloge dérive | rien : le bot reprend seul quand c'est rétabli |
| « 🔴 Connexion à Binance instable » | coupure réseau | rien : les stops restent chez Binance |
| « 🚨 DISJONCTEUR » | pertes nettement pires que prévu | analyse avec `/rapport` et `/journal`, puis `/rearmer` si tu le décides |
| « ✖ Connexion Binance impossible » | clé fausse, mauvais environnement ou IP | vérifie les clés, puis `bots config` |
| « 🛑 plantages en 1 h » | bug répété : le chien de garde s'est arrêté | `bots etat`, envoie les lignes à Claude |
| Erreur pendant l'installation | le message dit l'étape | relance `bash /root/equipe-bots-v17/installer.sh` : c'est sans danger |

---

## Exploration (v14, démo uniquement)

En démo, l'équipe prend volontairement des risques mesurés pour apprendre (niveau 2 par défaut).
Sur Telegram : `/exploration` pour le bilan des risques pris, `/exploration 0|1|2|3` pour régler.
Jamais en argent réel. Détails : `EXPLORATION.md`.

---

## Veille Trade Republic (v13)

Elle démarre toute seule avec le bot. Vérifie-la une fois avec `bots tr-test` (liste officielle + Yahoo).
Sur Telegram : `/tr` pour l'état, les suivis et le bilan. Règle le montant de tes ordres TR avec
`bots tr-montant 500`. Détails et limites : `VEILLE_TRADE_REPUBLIC.md`.

---

## Armée de renseignement (v17.4)

29 bots qui cherchent en continu (presse mondiale, GDELT, banques centrales, catastrophes, marchés de prédiction,
réseaux sociaux, actifs suivis) et informent tous les autres bots sans les ralentir. Aucun ordre.
Déploiement : `bots renseignement-demarrer` · test : `bots renseignement-test` · Telegram : `/renseignement`.
Détails : `RENSEIGNEMENT.md`.

---

## Veille marchés mondiaux (v17.3)

Presse mondiale toutes les 4 h (géopolitique, économie, taux, Wall Street, CAC 40, énergie, alimentation,
industrie, devises, défense…), consensus des analystes, **note de 0 à 5** et moment d'acheter ou de vendre pour
les titres Trade Republic. Aucun ordre. Démarrage : `bots marches-demarrer` · test : `bots marches-test`.
Telegram : `/marches`, `/briefing`, `/note LVMH`. Détails : `VEILLE_MARCHES.md`.

---

## Moteur v17 (portefeuille fictif)

Service séparé du bot principal : il suit quelques cryptos (BTC par défaut) sur les **vrais prix publics
de Binance** et gère **son propre portefeuille fictif** (10 000 $). Il ne passe **aucun ordre** sur ton
compte Binance. Chaque achat et chaque vente arrivent sur Telegram, préfixés `[v17]`.
Démarrage (une fois) : `bots v17-demarrer`. État : `/v17` sur Telegram ou `bots v17-etat`.
Vrais ordres sur le compte démo Binance (argent fictif) : `bots v17-demo` · retour : `bots v17-fictif`.
Pause des achats : `/v17 stop` · reprise : `/v17 reprise`. Détails : `V17_PLATEFORME.md`.

---

## Mettre à jour le bot (nouvelle version)

**Méthode simple (sans Google Drive)**
1. Enregistre le nouveau zip dans Fichiers sur ton téléphone.
2. Termius > appui long sur le serveur > **Connect via SFTP** > envoie le zip dans `/root`.
3. Dans le terminal : `bots mettre-a-jour /root/NOM_DU_ZIP.zip`

**Autre méthode** : zip sur Google Drive, lien de partage, puis `bots mettre-a-jour 'COLLE_ICI_LE_LIEN'`

Le script sauvegarde l'ancienne version, installe la nouvelle, lance **tous les tests**, et **remet
automatiquement l'ancienne version** si un test échoue. Tes clés, ton historique, ton champion et tes
réglages (unité de signal) sont conservés.

---

## Passer en argent réel (plus tard, jamais avant d'avoir coché toute la liste)

- [ ] Au moins **4 semaines** de démo sans intervention d'urgence.
- [ ] Backtest : espérance **hors échantillon** positive (étape 10).
- [ ] Espérance réelle positive dans `/statut` sur au moins **50 trades** démo.
- [ ] `/calibration` : CALIBRÉ ou en rodage, jamais NON FIABLE.
- [ ] Aucun disjoncteur déclenché dans les 2 dernières semaines.
- [ ] Tu as lu `/journal` et tu comprends pourquoi le bot achète et vend.

Ensuite :
1. Sur **binance.com** (le vrai site) : Gestion des API > nouvelle clé > coche **UNIQUEMENT** le trading Spot >
   **jamais les retraits** > restriction à l'IP de ton serveur (`bots ip`).
2. Dans Termius : `bots config` > mode `reel` > tape `JE CONFIRME` > les nouvelles clés > plafond **100** USDT.
3. Le bot démarre au palier 1 (100 USDT). Chaque palier supérieur te sera proposé par Telegram,
   et seulement si les résultats le justifient.

> Fiscalité (France) : échanger une crypto contre une autre (y compris un stablecoin comme l'USDT) n'est pas
> imposable ; la conversion en euros l'est (formulaire 2086). Un compte sur une plateforme étrangère se
> déclare (formulaire 3916-bis). Garde le fichier `journal.db` comme historique.

---

## Récapitulatif de la sécurité en place

- Le bot tourne sous un compte dédié, jamais en administrateur.
- Pare-feu : seul l'accès SSH est ouvert ; fail2ban bloque les tentatives d'intrusion.
- Mises à jour de sécurité automatiques ; horloge synchronisée en continu.
- Clés dans un fichier lisible uniquement par le compte du bot.
- Clé Binance sans droit de retrait, verrouillée sur l'IP du serveur.
- Un seul bot peut tourner à la fois (verrou), avec un chien de garde et une réconciliation avec Binance.
- Sauvegarde quotidienne (30 jours gardés) ; mises à jour testées, avec retour arrière automatique.

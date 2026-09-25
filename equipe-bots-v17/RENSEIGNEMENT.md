# Armée de renseignement (v17.4)

Service séparé : `equipe-bots-renseignement`. Il **cherche sans arrêt, jour et nuit**, ne passe **aucun ordre**
et ne touche à aucun compte. Son seul travail : informer les autres bots.

## Les 29 bots et leurs missions

| Famille | Bots | Rythme |
|---|---|---|
| Presse | 10 bots par thème : banques centrales (BCE, Fed, Banque d'Angleterre), FMI, ONU, BBC, Le Monde, Euronews, Al Jazeera, MarketWatch, CNBC, Yahoo Finance, Investing.com, Les Echos, BFM, OilPrice, Defense News, CoinDesk, Cointelegraph, Decrypt | 15 min |
| Monde (GDELT) | 13 bots : géopolitique, économie, taux, alimentation, énergie, social (grèves, manifestations), industrie, tech/IA, défense, santé/épidémies, climat/catastrophes, crypto, marchés européens. GDELT lit la presse de tous les pays, dans plus de 100 langues ; les bots gardent les articles en anglais et en français | 15 min |
| Ton mondial | 1 bot : le ton de la presse mondiale par thème, sur 6 h, comparé aux 3 derniers jours | 15 min |
| Terrain | 2 bots : séismes (USGS, magnitude 6 et plus) et catastrophes (GDACS, alertes orange et rouges) | 15 min |
| Foule | 1 bot : marchés de prédiction (Polymarket), probabilités d'événements économiques et géopolitiques ; le sport est ignoré | 30 min |
| Réseaux sociaux | 1 bot : Mastodon, hashtags economy, stocks, bitcoin, inflation, geopolitics, finance, economie, bourse | 15 min |
| De près | 1 bot : cherche dans la presse mondiale chaque actif que nos bots détiennent ou regardent (positions Binance, cryptos v17, portefeuille et liste TR, meilleures notes du jour) | 10 min |

Un bot en panne réessaie seul, de plus en plus espacé (30 min, 1 h… jusqu'à 6 h), sans gêner les autres.

## Ce qu'elle produit (base `runtime/renseignement.db`)

- **Faits** : chaque info, avec ses thèmes, les actifs cités, son ton (-2 à +2) et son importance (0 à 3). Une
  même info reprise par plusieurs sources est renforcée, jamais comptée deux fois.
- **Analyste IA** : avec une clé Anthropic, lit les titres importants par lots de 40 (4 lots par heure au
  maximum, environ 0,5 € par jour) pour noter leur ton, leur importance et les actifs touchés. Sans clé, la
  lecture se fait par mots-clés.
- **Synthèse toutes les 5 min** :
  - le climat mondial, chaque thème et chaque secteur, **par rapport à la normale des 3 derniers jours** (la
    presse est toujours un peu négative : seul ce qui change compte) ;
  - chaque actif, pris tel quel.
- **Alertes** :
  - choc majeur (importance 3) ;
  - mauvaise nouvelle sur un actif reprise par au moins 2 sources en 6 h ;
  - pic d'attention, quand un thème fait soudain 3 fois plus parler que d'habitude.

  Envoyées sur Telegram, 8 par jour au maximum.

## Qui s'en sert, et comment

| Bot | Utilisation |
|---|---|
| Bot principal (Binance) | Nouvelle grave sur une crypto : veto VEILLE, donc pas d'achat. Si elle est déjà détenue, avertissement (la protection reste en place) |
| Moteur v17 | Pas de nouvel achat sur une nouvelle grave concernant l'actif, ni quand le climat mondial se dégrade nettement. Désactivable : `V17_RENSEIGNEMENT=0` |
| Veille marchés | Utilise toute la presse de l'armée pour son briefing ; le ton de chaque actif et de chaque secteur entre dans les notes de 0 à 5 |

**Sans jamais les ralentir :**
- les bots lisent la base en lecture seule, avec 0,3 s d'attente au maximum ;
- toute panne veut dire « pas d'information », jamais un blocage ;
- l'armée tourne en priorité basse : 50 % d'un processeur au maximum, disque en dernier.

## Commandes

Telegram : `/renseignement`

Termius :

```bash
bots renseignement-test        # tester chaque bot une fois
bots renseignement-demarrer    # déployer (ensuite automatique, même après un redémarrage)
bots renseignement-etat        # bilan : bots, infos, climat, alertes, bots en difficulté
bots renseignement-journal     # journal en direct
bots renseignement-arreter
```

## Limites

- « Tout internet » n'est pas lisible : les sites payants, les réseaux fermés et les sites qui interdisent les
  robots sont exclus. GDELT est ce qui s'en approche le plus : il couvre la presse de tous les pays.
- Plus d'informations ne veut pas dire de meilleurs trades. L'armée sert surtout à **éviter** d'acheter au
  mauvais moment (nouvelle grave, climat qui se dégrade) et à nourrir les notes. Elle ne crée pas d'avantage à
  elle seule.

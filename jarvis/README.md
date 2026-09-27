# JARVIS : votre assistant personnel

Un assistant inspiré du J.A.R.V.I.S. d'Iron Man, propulsé par **Claude** (Anthropic), que vous utilisez
sur **Telegram** (texte, vocal, photo, PDF) et dans le **terminal** de votre serveur (Termius).

## Ce qu'il sait faire

| Pouvoir | Comment |
|---|---|
| Répondre sur n'importe quel sujet, raisonner, analyser | Claude Opus 5, réflexion adaptative |
| Chercher sur le web et lire des pages (actualité, faits récents), avec les sources | Recherche et lecture web côté Anthropic |
| Cours, tendances, RSI, ATR, moyennes mobiles de n'importe quel actif | `cours_marche` (Yahoo Finance) |
| Connaître l'état de vos bots (moteur V17, bot Trade Republic, bilan de la semaine) | `etat_bots` |
| Lire et expliquer le code et la doc du projet | `lister_projet`, `lire_fichier_projet`, `chercher_projet` |
| Démarrer ou arrêter le moteur V17 démo, **avec votre confirmation** | `piloter_bots` (/oui, /non) |
| Se souvenir de vous d'une conversation à l'autre | Mémoire long terme (`jarvis/data/memoires/`) |
| Comprendre vos vocaux et répondre à voix haute | Whisper (Groq) + voix neuronale edge-tts |
| Analyser photos, captures d'écran de graphiques et PDF | Vision de Claude |

**Ses limites :** Jarvis est très capable, mais il n'est pas omniscient. Il peut se tromper, et
certaines questions n'ont pas de réponse connue. Il est conçu pour vérifier avant d'affirmer, citer ses
sources et dire franchement quand il ne sait pas. Aucune analyse de marché n'est une garantie.

## Installation sur le serveur (Termius)

```bash
cd ~/ai-market-watch-            # le dossier du dépôt sur votre serveur
git pull
./jarvis/jarvis.sh installer
nano jarvis/.env                 # remplir les clés (voir ci-dessous)
./jarvis/jarvis.sh demarrer
```

Dans `jarvis/.env` :

1. **`ANTHROPIC_API_KEY`** : créez-la sur https://console.anthropic.com (API Keys) et ajoutez du crédit.
2. **`JARVIS_TELEGRAM_TOKEN`** : sur Telegram, écrivez à **@BotFather** → `/newbot` → nom « Jarvis ».
   Utilisez un **nouveau** bot : si vous reprenez le token des bots de trading, les deux se volent les messages.
3. **`JARVIS_TELEGRAM_CHAT_IDS`** : laissez vide, démarrez, écrivez à votre bot. Il vous répond
   « Votre chat_id est 123456… » : collez-le ici, puis `./jarvis/jarvis.sh arreter && ./jarvis/jarvis.sh demarrer`.
4. **`GROQ_API_KEY`** : la même clé Groq que `LLM_API_KEY` de vos bots, pour transcrire les vocaux.

Pour de vraies notes vocales en réponse : `sudo apt install ffmpeg` (sinon Jarvis envoie un fichier MP3).

## Utilisation

```bash
./jarvis/jarvis.sh parler     # discuter dans le terminal
./jarvis/jarvis.sh etat       # en ligne ? + journal
./jarvis/jarvis.sh arreter
```

Jarvis tourne en arrière-plan, redémarre tout seul s'il plante et après un redémarrage du serveur (cron).

Sur Telegram : `/etat`, `/voix auto|on|off`, `/memoire`, `/oubli`, `/oui`, `/non`, `/aide`.
Dans le terminal : `/fichier chemin question`, `/memoire`, `/oubli`, `/quitter`.

## Coût

Vous payez Claude à l'usage (Opus 5 : 5 $ par million de jetons en entrée, 25 $ en sortie ; le cache
réduit fortement le prix des messages suivants). Une question simple coûte quelques centimes, une grosse
recherche web quelques dizaines. Pour réduire la facture : `JARVIS_EFFORT=medium`, ou
`JARVIS_MODEL=claude-sonnet-5` (environ 2,5 fois moins cher).

## Sécurité

- Seuls les `chat_id` autorisés peuvent lui parler.
- Il lit le projet en lecture seule ; les fichiers `.env`, clés et secrets lui sont masqués.
- La seule action réelle possible (démarrer ou arrêter le moteur V17 démo) demande votre confirmation.
- Vos conversations et sa mémoire restent sur votre serveur, dans `jarvis/data/` (non versionné).

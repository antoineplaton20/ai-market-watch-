# V17 — Binance Démo depuis Termius

## Sur le serveur de la plateforme (Hetzner) — le cas normal

La v17 y tourne en **service systemd** (redémarrage automatique, Telegram, `/v17`). Tout se fait avec `bots` :

```bash
bots mettre-a-jour /root/equipe-bots-v17.zip   # installe cette version (tests + retour arrière auto)
bots v17-demo                                 # test du compte démo, puis v17 en démo (V17_DEMO_ONLY=1)
bots v17-etat                                 # état, portefeuille v17, journal
bots v17-fictif                               # retour au portefeuille fictif
bots increvable                               # une fois après la mise à jour : relance sans fin de tout
```

V17.6 « increvable » : voir `INCREVABLE.md`.
Application iPhone : `bots app` puis voir `APPLI_IPHONE.md`.

Les clés : celles du bot principal (même compte démo), sauf si tu mets `V17_API_KEY` / `V17_API_SECRET`.
Les scripts `termius_demo_*.sh` détectent ce serveur et passent la main à `bots` : pas de `nohup` en root,
pas de deuxième v17 en parallèle (un verrou l'interdit de toute façon).

Détails, budget et sécurité : `V17_PLATEFORME.md`.

## Sur une autre machine Linux (sans la plateforme)

```bash
./termius_demo_install.sh      # crée .venv et .env (copie de .env.termux.demo.example)
nano .env                      # V17_API_KEY / V17_API_SECRET = clés créées sur demo.binance.com
./termius_demo_check.sh        # test de connexion (aucun ordre, clés jamais affichées)
./termius_demo_start.sh        # démarrage sous superviseur : relance sans fin + cron (redémarrage machine)
./termius_demo_status.sh       # état + 20 dernières lignes
./termius_demo_stop.sh
```

## Sécurité

- `V17_DEMO_ONLY=1` : le moteur refuse tout autre mode que la démo (ni testnet, ni argent réel).
- Argent réel impossible avec les clés du bot principal ; retraits refusés par la policy.
- La v17 ne vend que ce qu'elle a acheté et respecte son budget (`V17_CAPITAL_MAX_USDT`).
- Les ordres sont de vrais ordres sur le compte **démo** : argent fictif, mais pas un backtest.
- La stratégie v17 (2 votes simples) n'est pas validée : les résultats observés ne prouvent aucune rentabilité.

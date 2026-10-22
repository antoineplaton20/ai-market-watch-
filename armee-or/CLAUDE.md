# Armée de l'or — consignes pour l'IA

Avant toute action, lis `PROMPT_MAITRE.md` (même dossier). C'est la consigne complète :

- la mission et les lois d'airain ;
- les faits déjà mesurés ;
- le savoir sur l'or et sur les grands traders ;
- la méthode de preuve ;
- les chantiers.

En cas de conflit, l'ordre de priorité est le suivant :

1. les lois d'airain ;
2. une décision écrite du propriétaire ;
3. le reste du prompt.

## L'essentiel, si tu ne lis que ceci

**Le permis de trader.** Le trading se fait en démo seulement, et aucun ordre ne part sans permis. Pour l'obtenir, une règle doit, sur chaque moitié de l'historique :

- gagner, frais réels compris ;
- faire mieux que le naïf ;
- compter au moins 30 décisions.

**L'honnêteté des tests.**

- Aucune donnée du futur.
- Chaque essai est compté.
- Jamais de chiffre, de source ou de citation inventés.

**La sécurité.**

- Ne jamais toucher aux bots V17.9 du serveur.
- Aucun secret dans le dépôt, qui est public.
- Ne jamais demander de mot de passe.

**Git.**

- La branche de travail est `claude/termius-binance-bot-optimization-g98ihl`.
- Pas de demande de fusion (PR) sans demande explicite.

**Les tests.** Prépare l'environnement avec `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, puis lance :

```
.venv/bin/python -m pytest -q > /tmp/res-or.txt 2>&1; echo $?
```

La commande doit afficher `0`. Vérifie toujours ce code de sortie, jamais une fin de sortie filtrée par un tube.

**Après chaque changement.**

- Ajoute une section datée dans `LISEZMOI.md`.
- Le propriétaire installe la nouvelle version depuis son iPhone avec `/or_maj`.

# Vigie

Détection et suivi de drones dans un flux vidéo, pour l'alerte précoce du guetteur et de l'équipage.

Vigie détecte les drones image par image, les suit avec un identifiant stable, ne donne l'alerte que
pour une piste confirmée et estime le temps restant avant contact quand un drone se rapproche. Il
produit une vidéo annotée et un journal horodaté.

**Vigie n'a aucune interface avec une arme.** C'est un démonstrateur logiciel d'alerte, construit
uniquement à partir de sources et de données ouvertes.

Le dossier technique complet (architecture, données, résultats mesurés, limites, feuille de route)
accompagne ce code.

## Installation

```bash
cd vigie
pip install -r requirements.txt
python -m pytest
```

Python 3.11 ou plus récent. Aucune carte graphique n'est nécessaire.

## Utilisation

```bash
# Démonstration sur vidéo synthétique, sans données ni modèle
python -m vigie demo --dossier demo

# Traiter une vidéo avec un modèle entraîné
python -m vigie detecter video.mp4 --modele meilleur.pt --sortie annotee.mp4 --journal journal.jsonl

# Vidéo haute définition : analyse complémentaire par tuiles pour les drones lointains
python -m vigie detecter video.mp4 --modele meilleur.pt --tuiles 2

# Mesurer les performances sur un jeu d'images au format YOLO
python -m vigie evaluer donnees/test --modele meilleur.pt --rapport rapport.json

# Entraîner
python -m vigie entrainer --entrainement donnees/entrainement --validation donnees/validation --sortie runs/v1
```

## Reproduire les mesures du dossier technique

```bash
# 1. Jeu Seraphim (CC BY 4.0) : lot de test et premier lot d'entraînement
#    https://huggingface.co/datasets/lgrzybowski/seraphim-drone-detection-dataset
#    Extraire test/images, test/labels, train/images (batch_001) et train/labels dans data/seraphim/

# 2. Découpage disjoint entraînement / validation
python scripts/preparer_decoupage.py --source data/seraphim/train --destination data/decoupe \
    --entrainement 7000 --validation 500 --graine 0

# 3. Entraînement (environ 3 heures sur un processeur à 4 cœurs)
python -m vigie entrainer --entrainement data/decoupe/entrainement --validation data/decoupe/validation \
    --sortie runs/v1 --epoques 2 --lot 4

# 4. Mesure sur le jeu de test, jamais utilisé avant
python -m vigie evaluer data/seraphim/test --modele runs/v1/meilleur.pt --rapport resultats/test.json

# 5. Séquences vidéo réelles Anti-UAV, puis mesure de la chaîne complète
python scripts/telecharger_sequences_antiuav.py --destination data/antiuav --sequences 10 --images 300
python scripts/evaluer_sequences.py --modele runs/v1/meilleur.pt --donnees data/antiuav --rapport resultats/sequences.json
```

## Organisation

| Fichier | Rôle |
| --- | --- |
| `vigie/detecteur.py` | Réseau Faster R-CNN MobileNetV3-FPN, chargement, inférence, mode tuiles |
| `vigie/suivi.py` | Filtre de Kalman, association hongroise, confirmation, temps avant contact |
| `vigie/pipeline.py` | Traitement vidéo, alerte, vidéo annotée, journal |
| `vigie/donnees.py` | Lecture des jeux au format YOLO |
| `vigie/entrainement.py` | Entraînement, validation, sauvegarde |
| `vigie/evaluation.py` | Précision moyenne, rappel par taille, fausses alarmes |
| `vigie/evaluation_video.py` | Indicateurs de la chaîne complète sur vidéo |
| `vigie/synthetique.py` | Vidéos de synthèse pour les tests |
| `scripts/` | Préparation des données et évaluation sur séquences |
| `tests/` | Tests automatiques |

## Licences

Composants sous licences BSD et Apache 2.0, sans licence à réciprocité forte. Détail des composants
et des jeux de données dans [NOTICE.md](NOTICE.md). Les données et les modèles ne sont pas inclus
dans le dépôt.

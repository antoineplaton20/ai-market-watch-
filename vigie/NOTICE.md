# Composants et données de tiers

## Logiciels

| Composant | Licence | Usage |
| --- | --- | --- |
| PyTorch | BSD-3-Clause | Calcul des réseaux de neurones |
| torchvision | BSD-3-Clause | Architecture Faster R-CNN MobileNetV3-FPN et poids COCO de départ |
| NumPy | BSD-3-Clause | Calcul numérique |
| SciPy | BSD-3-Clause | Association optimale (algorithme hongrois) |
| OpenCV | Apache-2.0 | Lecture et écriture des images et vidéos |
| pytest | MIT | Tests automatiques |

Aucun composant sous licence à réciprocité forte (GPL, AGPL) n'est utilisé.

## Poids de départ

Les poids COCO de `fasterrcnn_mobilenet_v3_large_fpn` sont publiés par le projet torchvision. Le
jeu COCO a ses propres conditions d'utilisation, à vérifier pour tout usage opérationnel.

## Données d'entraînement et d'évaluation

| Jeu | Licence annoncée | Usage | Attribution |
| --- | --- | --- | --- |
| Seraphim Drone Detection Dataset | CC BY 4.0, agrégat de 23 jeux sous MIT, CC BY 4.0 ou CC0 | Entraînement, validation, test | Łukasz Grzybowski, Seraphim Defence Systems, 2025, https://huggingface.co/datasets/lgrzybowski/seraphim-drone-detection-dataset |
| Anti-UAV (version Hugging Face DestinyLove/AntiUAV300) | MIT annoncée par la page de mise à disposition | Évaluation sur vidéo réelle uniquement, non redistribué | Jeu d'origine : https://github.com/ZhaoJ9014/Anti-UAV ; conditions du jeu d'origine à vérifier |

Les données ne sont pas incluses dans ce dépôt ; les scripts du dossier `scripts/` les téléchargent.

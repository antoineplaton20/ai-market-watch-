"""Envoie un message Telegram depuis le terminal : python notifier.py "texte" """
import sys
from alertes import alerte

if __name__ == "__main__":
    alerte(" ".join(sys.argv[1:]) or "(message vide)", important=False)

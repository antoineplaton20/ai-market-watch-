"""Vérifie le logiciel localement, sans conclure à sa rentabilité."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    print("Vérification logicielle, sans ordre Binance ni message Telegram.", flush=True)
    env = dict(os.environ, PYTHON_DOTENV_DISABLED="1")
    total = 0
    with tempfile.TemporaryDirectory(prefix="verification-bots-") as tmp:
        for folder in ("tests", "tests_v15", "tests_v16", "tests_v17"):
            if not Path(folder).is_dir():
                print(f"Suite obligatoire absente : {folder}", flush=True)
                sys.exit(1)
            print(f"Tests : {folder}", flush=True)
            report = Path(tmp) / (folder + ".xml")
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--import-mode=importlib",
                                     "-p", "no:cacheprovider", f"--junitxml={report}", folder], env=env)
            if result.returncode:
                print("Échec : corriger avant tout redémarrage.", flush=True)
                sys.exit(result.returncode)
            try:
                suites = ET.parse(report).getroot().iter('testsuite')
                counts = [(int(s.get('tests', 0)), int(s.get('failures', 0)),
                           int(s.get('errors', 0)), int(s.get('skipped', 0))) for s in suites]
                if not counts or sum(n for n, _, _, _ in counts) == 0 or any(f or e or k for _, f, e, k in counts):
                    raise ValueError('tests absents, ignorés ou en échec')
                total += sum(n for n, _, _, _ in counts)
            except (OSError, ValueError, ET.ParseError) as ex:
                print(f"Vérification incomplète : {ex}", flush=True)
                sys.exit(1)
    print(f"{total} tests logiciels réussis. Aucune garantie de résultat financier.", flush=True)

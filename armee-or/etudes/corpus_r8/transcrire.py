"""Transcription locale (Whisper « base », sur le processeur) des épisodes choisis : 30 premières minutes."""
import hashlib, json, os, subprocess, sys, time
import numpy as np
from faster_whisper import WhisperModel
sel = json.load(open(sys.argv[1], encoding="utf-8"))
dossier, minutes = sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30
sel.sort(key=lambda e: -e.get("score", 0))
modeles = {}
for k, e in enumerate(sel):
    cle = hashlib.sha1((e.get("audio") or e.get("url")).encode()).hexdigest()[:16]
    chemin = os.path.join(dossier, cle + ".json")
    if os.path.exists(chemin):
        continue
    t0 = time.time()
    cmd = ["ffmpeg", "-loglevel", "error", "-user_agent", "Mozilla/5.0", "-i", e.get("audio") or e.get("url"),
           "-t", str(minutes * 60), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    try:
        brut = subprocess.run(cmd, capture_output=True, timeout=900).stdout
    except subprocess.TimeoutExpired:
        print("trop long", e["titre"][:60], flush=True); continue
    if len(brut) < 16000 * 2 * 30:
        print("audio illisible", e["titre"][:60], flush=True); continue
    a = np.frombuffer(brut, np.int16).astype(np.float32) / 32768.0
    langue = e.get("langue", "en")
    nom = "base.en" if langue == "en" else "base"
    if nom not in modeles:
        modeles[nom] = WhisperModel(nom, device="cpu", compute_type="int8", cpu_threads=4)
    segs, info = modeles[nom].transcribe(a, beam_size=1, vad_filter=True, language=langue)
    texte = " ".join(s.text.strip() for s in segs)
    json.dump({**{x: e.get(x) for x in ("podcast", "channel", "titre", "date", "audio", "url", "langue")},
               "secondes": round(len(a) / 16000), "texte": texte}, open(chemin, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{k + 1}/{len(sel)} {round(len(a) / 16000 / 60)} min en {time.time() - t0:.0f} s : {e['titre'][:70]}", flush=True)

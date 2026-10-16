#!/usr/bin/env python3
"""
Livres audio Yannis Gautier — process validé le 02/10/2026 (voix Nicolas Petit).

- Un chapitre = UNE seule requête ElevenLabs (previous_text / next_text = chapitres voisins).
  Jamais de collage paragraphe par paragraphe ni de coupe des silences.
- 3 prises par chapitre ; la meilleure est choisie par transcription Whisper locale
  (mlx_whisper) comparée au texte. Sans Whisper, la prise 1 est retenue et les autres gardées.
- Master : voix seule, mono 44,1 kHz, 192 kb/s, −23 LUFS (ffmpeg). Sans ffmpeg, les prises
  ElevenLabs (déjà en 44,1 kHz / 192 kb/s) sont livrées telles quelles, non normalisées.

Chaque livre a son dossier : livre.json (titre, chapitres) + texte/NN_*.txt (un fichier par chapitre).

Usage :
    python3 generer_livre_audio.py <dossier-du-livre>            # clé dans ELEVENLABS_API_KEY
    python3 generer_livre_audio.py <dossier-du-livre> --estimation
    python3 generer_livre_audio.py <dossier-du-livre> --montage-seul
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
AUTEUR = "Yannis Gautier"
VOIX = "aQROLel5sQbj1vuIVi6B"            # « Voix Nicolas Petit IA AUDIO Narration »
MODELE = "eleven_multilingual_v2"
REGLAGES = {"stability": 0.86, "similarity_boost": 0.78, "style": 0.28,
            "use_speaker_boost": True, "speed": 0.90}
FORMAT = "mp3_44100_192"
DEBIT = 192000                            # bits/s, pour estimer les durées
WHISPER = "mlx-community/whisper-large-v3-turbo"


# ---------------------------------------------------------------- livre

def charger_livre(dossier):
    dossier = Path(dossier)
    if not dossier.is_absolute() and not dossier.exists():
        dossier = Path(__file__).resolve().parent / dossier
    dossier = dossier.resolve()
    fiche = dossier / "livre.json"
    if not fiche.exists():
        sys.exit(f"{fiche} introuvable")
    infos = json.loads(fiche.read_text(encoding="utf-8"))
    chapitres = []
    for f in sorted((dossier / "texte").glob("*.txt")):
        blocs = [b.strip() for b in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if b.strip()]
        paragraphes = [" ".join(l.strip() for l in (b[3:] if b.startswith("## ") else b).splitlines() if l.strip())
                       for b in blocs]
        num = f.name[:2]
        chapitres.append({"num": num, "fichier": f.stem, "titre": infos["chapitres"].get(num, f.stem),
                          "texte": "\n\n".join(paragraphes)})
    if not chapitres:
        sys.exit(f"Aucun chapitre dans {dossier / 'texte'}")
    return dossier, infos, chapitres


# ---------------------------------------------------------------- ElevenLabs

def requete(chemin, cle, corps, essais=5):
    donnees = json.dumps(corps).encode("utf-8")
    entetes = {"Content-Type": "application/json", "Accept": "audio/mpeg"}
    if cle:
        entetes["xi-api-key"] = cle
    for essai in range(essais):
        req = urllib.request.Request(f"{API}{chemin}?output_format={FORMAT}", data=donnees,
                                     method="POST", headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and essai < essais - 1:
                time.sleep(2 ** (essai + 1))
                continue
            sys.exit(f"Erreur ElevenLabs {e.code} : {msg}")
        except urllib.error.URLError as e:
            if essai < essais - 1:
                time.sleep(2 ** (essai + 1))
                continue
            sys.exit(f"Impossible de joindre ElevenLabs : {e.reason}")


def generer(dossier, chapitres, nb_prises, cle):
    for k, c in enumerate(chapitres):
        corps = {"text": c["texte"], "model_id": MODELE, "voice_settings": REGLAGES}
        if k > 0:
            corps["previous_text"] = chapitres[k - 1]["texte"][-1500:]
        if k + 1 < len(chapitres):
            corps["next_text"] = chapitres[k + 1]["texte"][:1500]
        empreinte = hashlib.sha1(json.dumps([corps, VOIX], ensure_ascii=False).encode()).hexdigest()[:10]
        rep = dossier / "segments" / c["fichier"]
        rep.mkdir(parents=True, exist_ok=True)
        c["prises"] = []
        for n in range(1, nb_prises + 1):
            f = rep / f"prise{n}_{empreinte}.mp3"
            if f.exists():
                print(f"  chapitre {c['num']} prise {n} : déjà générée")
            else:
                print(f"  chapitre {c['num']} prise {n} : génération ({len(c['texte'])} caractères)")
                f.write_bytes(requete(f"/text-to-speech/{VOIX}", cle, dict(corps, seed=1000 + n)))
            c["prises"].append(f)
        for vieux in rep.glob("*.mp3"):
            if vieux not in c["prises"]:
                vieux.unlink()


def retrouver_prises(dossier, chapitres):
    for c in chapitres:
        c["prises"] = sorted((dossier / "segments" / c["fichier"]).glob("prise*.mp3"))
        if not c["prises"]:
            sys.exit(f"Aucune prise pour le chapitre {c['num']}")


# ---------------------------------------------------------------- contrôle Whisper

def mots(t):
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", t)


def choisir_prises(chapitres):
    try:
        import mlx_whisper
    except Exception:
        mlx_whisper = None
        print("  Whisper (mlx_whisper) absent : prise 1 retenue, les autres sont gardées pour écoute.")
    rapport = []
    for c in chapitres:
        c["choix"], scores = c["prises"][0], []
        if mlx_whisper and len(c["prises"]) > 1:
            ref = mots(c["texte"])
            for f in c["prises"]:
                try:
                    txt = mlx_whisper.transcribe(str(f), path_or_hf_repo=WHISPER, language="fr")["text"]
                except Exception as e:
                    print(f"  Whisper a échoué sur {f.name} : {e}")
                    scores = []
                    break
                scores.append(difflib.SequenceMatcher(None, ref, mots(txt)).ratio())
            if scores:
                c["choix"] = c["prises"][scores.index(max(scores))]
        detail = ", ".join(f"prise {i + 1} : {s:.1%}" for i, s in enumerate(scores)) or "sans contrôle Whisper"
        rapport.append(f"Chapitre {c['num']} — {c['choix'].name.split('_')[0]} retenue ({detail})")
    return rapport


# ---------------------------------------------------------------- master

def ffmpeg(*a):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *a], capture_output=True, text=True, check=True)


def master(src, dest):
    """Voix seule, mono 44,1 kHz, 192 kb/s, −23 LUFS (loudnorm en deux passes)."""
    r = ffmpeg("-i", str(src), "-af", "loudnorm=I=-23:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-")
    m = json.loads(r.stderr[r.stderr.rindex("{"):])
    ffmpeg("-i", str(src), "-af",
           "loudnorm=I=-23:TP=-1.5:LRA=11:linear=true:"
           f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
           f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}",
           "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "192k", str(dest))


def sans_id3(octets):
    if octets[:3] == b"ID3":
        taille = (octets[6] << 21) | (octets[7] << 14) | (octets[8] << 7) | octets[9]
        return octets[10 + taille:]
    return octets


def livrer(dossier, infos, chapitres, rapport):
    sortie = dossier / "sortie"
    if sortie.exists():
        shutil.rmtree(sortie)
    sortie.mkdir()
    avec_ffmpeg = bool(shutil.which("ffmpeg"))
    lignes, debut, complet = [], 0.0, bytearray()
    for i, c in enumerate(chapitres, 1):
        dest = sortie / f"ch_{i:03d}.mp3"
        if avec_ffmpeg:
            master(c["choix"], dest)
        else:
            shutil.copyfile(c["choix"], dest)
        duree = dest.stat().st_size * 8 / DEBIT
        lignes.append(f"{int(debut // 60):02d}:{int(debut % 60):02d}  ch_{i:03d}  {c['titre']}  ({int(duree // 60)} min {int(duree % 60):02d} s)")
        debut += duree
        complet += sans_id3(dest.read_bytes())
    (sortie / "ecoute-complete.mp3").write_bytes(bytes(complet))
    entete = [f"{infos['titre']} — {AUTEUR} — lu par Nicolas Petit",
              f"Durée totale : {int(debut // 60)} min {int(debut % 60):02d} s",
              "Master : mono 44,1 kHz, 192 kb/s, " + ("−23 LUFS" if avec_ffmpeg else "NON normalisé (ffmpeg absent)"), ""]
    texte = "\n".join(entete + lignes + [""] + rapport) + "\n"
    (sortie / "chapitres.txt").write_text(texte, encoding="utf-8")
    print("\n" + texte)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("livre", help="dossier du livre (livre.json + texte/)")
    ap.add_argument("--prises", type=int, default=3)
    ap.add_argument("--estimation", action="store_true", help="compte les caractères, aucun appel")
    ap.add_argument("--montage-seul", action="store_true", help="refait le master avec les prises existantes")
    args = ap.parse_args()

    dossier, infos, chapitres = charger_livre(args.livre)
    nb = sum(len(c["texte"]) for c in chapitres)
    print(f"{infos['titre']} : {len(chapitres)} chapitres, {nb} caractères, {args.prises} prises "
          f"→ ≈ {nb * args.prises} crédits ElevenLabs")
    if args.estimation:
        return

    if args.montage_seul:
        retrouver_prises(dossier, chapitres)
    else:
        cle = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not cle:
            sys.exit("Clé ElevenLabs absente ou vide (ELEVENLABS_API_KEY).")
        generer(dossier, chapitres, args.prises, cle)
    rapport = choisir_prises(chapitres)
    livrer(dossier, infos, chapitres, rapport)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Livres audio Yannis Gautier — génération ElevenLabs + montage ffmpeg.

Chaque livre a son dossier : livre.json (titre, chapitres) + texte/*.txt.

Usage :
    export ELEVENLABS_API_KEY=...                          # clé API ElevenLabs
    python3 generer_livre_audio.py dieu-n-a-pas-fini-avec-toi   # voix Nicolas Petit par défaut
    python3 generer_livre_audio.py dieu-n-a-pas-fini-avec-toi --pochette couverture.jpg

    python3 generer_livre_audio.py <livre> --estimation    # compte les caractères, aucun appel API
    python3 generer_livre_audio.py <livre> --voix          # liste les voix du compte

Chaque paragraphe est généré séparément (avec le texte qui précède et qui suit
pour garder une intonation continue), mis en cache dans segments/, puis les
silences sont posés au montage. Relancer le script ne refacture que les
paragraphes modifiés.

Dépendances : Python 3.8+ (bibliothèque standard uniquement) et ffmpeg.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
AUTEUR = "Yannis Gautier"
EDITEUR = "Gospel Action Productions (GAP)"

# Renseignés par charger_livre() à partir du dossier du livre
DOSSIER_TEXTE = DOSSIER_SEGMENTS = DOSSIER_SORTIE = None
TITRE = SOUS_TITRE = NOM_FICHIER = ""
CHAPITRES = {}


def charger_livre(dossier):
    global DOSSIER_TEXTE, DOSSIER_SEGMENTS, DOSSIER_SORTIE, TITRE, SOUS_TITRE, NOM_FICHIER, CHAPITRES
    dossier = Path(dossier)
    if not dossier.is_absolute() and not dossier.exists():
        dossier = Path(__file__).resolve().parent / dossier
    dossier = dossier.resolve()
    fiche = dossier / "livre.json"
    if not fiche.exists():
        sys.exit(f"{fiche} introuvable")
    infos = json.loads(fiche.read_text(encoding="utf-8"))
    DOSSIER_TEXTE, DOSSIER_SEGMENTS, DOSSIER_SORTIE = dossier / "texte", dossier / "segments", dossier / "sortie"
    TITRE, SOUS_TITRE, NOM_FICHIER = infos["titre"], infos["sous_titre"], infos["nom_fichier"]
    CHAPITRES = infos["chapitres"]

# Silences (secondes)
DEBUT_CHAPITRE = 0.6
ENTRE_PARAGRAPHES = 0.85
AVANT_TITRE = 1.2
APRES_TITRE = 1.4
FIN_CHAPITRE = 2.5

TAUX = 44100


# ---------------------------------------------------------------- texte

def lire_chapitres():
    chapitres = []
    for f in sorted(DOSSIER_TEXTE.glob("*.txt")):
        num = f.name[:2]
        blocs = [b.strip() for b in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if b.strip()]
        paragraphes = []
        for b in blocs:
            titre = b.startswith("## ")
            texte = " ".join(l.strip() for l in (b[3:] if titre else b).splitlines() if l.strip())
            paragraphes.append({"texte": texte, "titre": titre})
        chapitres.append({"num": num, "fichier": f.stem, "titre": CHAPITRES.get(num, f.stem), "paragraphes": paragraphes})
    if not chapitres:
        sys.exit(f"Aucun fichier texte dans {DOSSIER_TEXTE}")
    return chapitres


# ---------------------------------------------------------------- ElevenLabs

def requete(methode, chemin, cle, corps=None, query="", essais=5):
    url = f"{API}{chemin}{query}"
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    for essai in range(essais):
        entetes = {"Content-Type": "application/json",
                   "Accept": "audio/mpeg" if corps is not None else "application/json"}
        if cle:
            # Sans clé locale, la requête part telle quelle (clé injectée par le proxy de l'environnement)
            entetes["xi-api-key"] = cle
        req = urllib.request.Request(url, data=donnees, method=methode, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and essai < essais - 1:
                attente = 2 ** (essai + 1)
                print(f"    ElevenLabs {e.code}, nouvel essai dans {attente}s…")
                time.sleep(attente)
                continue
            sys.exit(f"Erreur ElevenLabs {e.code} : {msg}")
        except urllib.error.URLError as e:
            if essai < essais - 1:
                time.sleep(2 ** (essai + 1))
                continue
            sys.exit(f"Impossible de joindre ElevenLabs : {e.reason}")


def lister_voix(cle):
    brut, _ = requete("GET", "/voices", cle)
    for v in json.loads(brut).get("voices", []):
        print(f"{v['voice_id']}  {v['name']}  ({v.get('category', '')})")


def generer_segments(chapitres, args, cle):
    reglages = {
        "stability": args.stability,
        "similarity_boost": args.similarity,
        "style": args.style,
        "use_speaker_boost": True,
        "speed": args.speed,
    }
    v3 = args.model.startswith("eleven_v3")
    total = sum(len(c["paragraphes"]) for c in chapitres)
    n = 0
    for c in chapitres:
        dossier = DOSSIER_SEGMENTS / c["fichier"]
        dossier.mkdir(parents=True, exist_ok=True)
        paras = c["paragraphes"]
        ids_precedents = []
        for i, p in enumerate(paras):
            n += 1
            empreinte = hashlib.sha1(json.dumps(
                [p["texte"], args.voice_id, args.model, reglages], ensure_ascii=False).encode()).hexdigest()[:10]
            p["mp3"] = dossier / f"{i:02d}_{empreinte}.mp3"
            if p["mp3"].exists():
                print(f"  [{n}/{total}] déjà généré — {p['texte'][:60]}")
                continue
            corps = {"text": p["texte"], "model_id": args.model, "voice_settings": reglages}
            if not v3:
                # Continuité d'intonation entre paragraphes (non supportée par eleven_v3)
                if i > 0:
                    corps["previous_text"] = " ".join(x["texte"] for x in paras[max(0, i - 2):i])
                if i + 1 < len(paras):
                    corps["next_text"] = paras[i + 1]["texte"]
                if ids_precedents:
                    corps["previous_request_ids"] = ids_precedents[-3:]
            if args.langue:
                corps["language_code"] = args.langue
            print(f"  [{n}/{total}] génération — {p['texte'][:60]}")
            audio, entetes = requete("POST", f"/text-to-speech/{args.voice_id}", cle, corps,
                                     query=f"?output_format={args.format}")
            p["mp3"].write_bytes(audio)
            rid = {k.lower(): v for k, v in entetes.items()}.get("request-id")
            if rid:
                ids_precedents.append(rid)
        # ménage : segments obsolètes (texte modifié)
        garder = {p["mp3"].name for p in paras}
        for f in dossier.glob("*.mp3"):
            if f.name not in garder:
                f.unlink()


# ---------------------------------------------------------------- montage

def ffmpeg(*a):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)


def duree(fichier):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(fichier)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def silence(s, dest):
    ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={TAUX}:cl=mono", "-t", f"{s:.3f}", "-c:a", "pcm_s16le", str(dest))


def monter(chapitres, args):
    travail = DOSSIER_SORTIE / "_travail"
    if travail.exists():
        shutil.rmtree(travail)
    travail.mkdir(parents=True)
    (DOSSIER_SORTIE / "chapitres").mkdir(parents=True, exist_ok=True)

    pauses = {}
    def pause(s):
        if s not in pauses:
            pauses[s] = travail / f"silence_{int(s * 1000)}.wav"
            silence(s, pauses[s])
        return pauses[s]

    liste, reperes, t = [], [], 0.0
    for c in chapitres:
        debut = t
        morceaux = [pause(DEBUT_CHAPITRE)]
        for i, p in enumerate(c["paragraphes"]):
            wav = travail / f"{c['num']}_{i:02d}.wav"
            # Rogne les blancs en tête et en fin de segment pour des silences maîtrisés
            ffmpeg("-i", str(p["mp3"]), "-ac", "1", "-ar", str(TAUX),
                   "-af", "silenceremove=start_periods=1:start_threshold=-50dB,"
                          "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                          "afade=t=in:d=0.01",
                   "-c:a", "pcm_s16le", str(wav))
            if p["titre"] and i > 0:
                morceaux.append(pause(AVANT_TITRE))
            morceaux.append(wav)
            if i + 1 < len(c["paragraphes"]):
                morceaux.append(pause(APRES_TITRE if p["titre"] else ENTRE_PARAGRAPHES))
        morceaux.append(pause(FIN_CHAPITRE))
        for m in morceaux:
            t += duree(m)
        liste += morceaux
        reperes.append((c, debut, t))

    concat = travail / "liste.txt"
    concat.write_text("".join(f"file '{m}'\n" for m in liste), encoding="utf-8")
    brut = travail / "livre_brut.wav"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", str(brut))

    # Normalisation du volume en deux passes (cible -16 LUFS, crête -1.5 dBTP)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(brut), "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    mesure = json.loads(r.stderr[r.stderr.rindex("{"):])
    norm = travail / "livre_norm.wav"
    ffmpeg("-i", str(brut), "-af",
           "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:"
           f"measured_I={mesure['input_i']}:measured_TP={mesure['input_tp']}:"
           f"measured_LRA={mesure['input_lra']}:measured_thresh={mesure['input_thresh']}:"
           f"offset={mesure['target_offset']}",
           "-ar", str(TAUX), "-c:a", "pcm_s16le", str(norm))

    # Métadonnées + chapitres
    meta = travail / "meta.txt"
    lignes = [";FFMETADATA1", f"title={TITRE}", f"artist={AUTEUR}", f"album_artist={AUTEUR}",
              f"album={TITRE}", f"publisher={EDITEUR}", "genre=Audiobook", "language=fra",
              f"comment={SOUS_TITRE}. Narration : voix de synthèse ElevenLabs.", ""]
    for c, debut, fin in reperes:
        lignes += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(debut * 1000)}",
                   f"END={int(fin * 1000)}", f"title={c['num']} — {c['titre']}", ""]
    meta.write_text("\n".join(lignes), encoding="utf-8")

    pochette = ["-i", str(args.pochette)] if args.pochette else []
    carte_poch = ["-map", "2:v", "-disposition:v", "attached_pic"] if args.pochette else []

    mp3 = DOSSIER_SORTIE / f"{NOM_FICHIER}.mp3"
    ffmpeg("-i", str(norm), "-i", str(meta), *pochette, "-map", "0:a", *carte_poch,
           "-map_metadata", "1", "-map_chapters", "1", "-c:a", "libmp3lame", "-b:a", "128k",
           *(["-c:v", "copy"] if args.pochette else []), "-id3v2_version", "3", str(mp3))

    m4b = DOSSIER_SORTIE / f"{NOM_FICHIER}.m4b"
    ffmpeg("-i", str(norm), "-i", str(meta), *pochette, "-map", "0:a", *carte_poch,
           "-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", "96k",
           *(["-c:v", "copy"] if args.pochette else []), "-f", "ipod", str(m4b))

    for c, debut, fin in reperes:
        dest = DOSSIER_SORTIE / "chapitres" / f"{c['fichier']}.mp3"
        ffmpeg("-ss", f"{debut:.3f}", "-to", f"{fin:.3f}", "-i", str(norm), "-c:a", "libmp3lame",
               "-b:a", "128k", "-metadata", f"title={c['num']} — {c['titre']}", "-metadata",
               f"artist={AUTEUR}", "-metadata", f"album={TITRE}", "-metadata", f"track={int(c['num']) + 1}",
               str(dest))

    shutil.rmtree(travail)
    print(f"\nDurée totale : {int(t // 60)} min {int(t % 60):02d} s")
    for c, debut, fin in reperes:
        print(f"  {int(debut // 60):02d}:{int(debut % 60):02d}  {c['num']} — {c['titre']}")
    print(f"\n→ {mp3}\n→ {m4b}\n→ {DOSSIER_SORTIE / 'chapitres'}/")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("livre", help="dossier du livre (contient livre.json et texte/)")
    # Préréglage « audiobook.nicolas-petit » (voix Nicolas Petit)
    ap.add_argument("--voice-id", default=os.environ.get("ELEVENLABS_VOICE_NICOLAS_PETIT", "aQROLel5sQbj1vuIVi6B"))
    ap.add_argument("--model", default=os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"))
    ap.add_argument("--stability", type=float, default=0.48)
    ap.add_argument("--similarity", type=float, default=0.88)
    ap.add_argument("--style", type=float, default=0.14)
    ap.add_argument("--speed", type=float, default=0.86)
    ap.add_argument("--langue", default=None, help="ex. fr (seulement si le modèle l'accepte)")
    ap.add_argument("--format", default="mp3_44100_128")
    ap.add_argument("--pochette", type=Path, help="image JPG/PNG carrée pour la pochette")
    ap.add_argument("--estimation", action="store_true", help="compte les caractères sans appeler l'API")
    ap.add_argument("--voix", action="store_true", help="liste les voix du compte")
    ap.add_argument("--montage-seul", action="store_true", help="remonte à partir des segments déjà générés")
    args = ap.parse_args()

    charger_livre(args.livre)
    chapitres = lire_chapitres()
    nb = sum(len(p["texte"]) for c in chapitres for p in c["paragraphes"])
    print(f"{len(chapitres)} chapitres, {sum(len(c['paragraphes']) for c in chapitres)} paragraphes, "
          f"{nb} caractères (≈ {nb} crédits en Multilingual v2, ≈ {round(nb / 900)} min de voix)")
    if args.estimation:
        return

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg est introuvable (macOS : brew install ffmpeg)")
    cle = os.environ.get("ELEVENLABS_API_KEY")
    if not cle and not args.montage_seul:
        print("ELEVENLABS_API_KEY absente : on compte sur la clé injectée par le réseau de l'environnement.")
    if args.voix:
        return lister_voix(cle)

    if args.montage_seul:
        for c in chapitres:
            dossier = DOSSIER_SEGMENTS / c["fichier"]
            for i, p in enumerate(c["paragraphes"]):
                trouves = sorted(dossier.glob(f"{i:02d}_*.mp3"))
                if not trouves:
                    sys.exit(f"Segment manquant : {c['fichier']} paragraphe {i}")
                p["mp3"] = trouves[-1]
    else:
        if not args.voice_id:
            sys.exit("Indique la voix : --voice-id <ID> (python3 generer_livre_audio.py --voix pour la liste)")
        generer_segments(chapitres, args, cle)

    monter(chapitres, args)


if __name__ == "__main__":
    main()

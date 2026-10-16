#!/bin/bash
# Fabrique automatique des livres audio sur l'iMac.
# Lancé toutes les 10 minutes par launchd (voir installer.sh).
# Pour chaque livres-audio/<livre>/livre.json contenant "generer": true,
# génère l'audio avec ElevenLabs, le monte, le copie dans ~/Movies/Claude/audiobooks/<livre>/
# et l'envoie sur Drive. Un livre déjà fabriqué n'est refait que si son texte change.
main() {
set -u
BASE="$HOME/Movies/Claude/livres-audio-auto"
DEPOT="$BASE/depot"
BRANCHE="claude/livre-audio-dieu-t-a-pris-pour-cible"
CLE="$HOME/Movies/Claude/.secrets/elevenlabs.env"
DRIVE_AUDIOBOOKS="1zMgiZvC4P40Eix77D58RwO7QNL9jnjnv"
export PATH="$BASE/bin:$HOME/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:/usr/bin:/bin:$PATH"

mkdir -p "$BASE"
exec >>"$BASE/journal.log" 2>&1
VERROU="$BASE/.en-cours"
mkdir "$VERROU" 2>/dev/null || exit 0          # une seule fabrication à la fois
trap 'rmdir "$VERROU"' EXIT

note() { echo "$(date '+%d/%m %H:%M') $*"; }
alerte() { osascript -e "display notification \"$1\" with title \"Livres audio\"" >/dev/null 2>&1 || true; }

# ffmpeg sert au master (−23 LUFS) ; s'il n'est pas dans le PATH, on cherche celui déjà présent sur le Mac
if ! command -v ffmpeg >/dev/null; then
  trouve=$(find "$HOME/Movies/Claude" "$HOME/Library/Python" "$HOME/.local" "$HOME/miniconda3" "$HOME/anaconda3" \
           -maxdepth 7 -type f -name 'ffmpeg*' -perm -u+x 2>/dev/null | grep -v '\.py$' | head -1)
  if [ -n "$trouve" ]; then mkdir -p "$BASE/bin"; ln -sf "$trouve" "$BASE/bin/ffmpeg"; note "ffmpeg trouvé : $trouve"; fi
fi

cd "$DEPOT" || { note "dépôt introuvable : $DEPOT"; exit 1; }
git fetch -q origin "$BRANCHE" && git reset -q --hard "origin/$BRANCHE" || { note "impossible de récupérer la branche"; exit 1; }
cd livres-audio || exit 1

for fiche in */livre.json; do
  livre="${fiche%/livre.json}"
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("generer") else 1)' "$fiche" || continue

  empreinte=$(cat "$fiche" "$livre"/texte/*.txt generer_livre_audio.py "$livre"/couverture.jpg 2>/dev/null | shasum | cut -c1-16)
  [ "$(cat "$livre/sortie/.fait" 2>/dev/null)" = "$empreinte" ] && continue

  titre=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["titre"])' "$fiche")
  note "début : $titre"
  [ -f "$CLE" ] || { note "clé ElevenLabs absente : $CLE"; alerte "Clé ElevenLabs introuvable"; exit 1; }
  set -a; source "$CLE"; set +a

  if ! python3 generer_livre_audio.py "$livre" > "$livre/journal.txt" 2>&1; then
    note "ÉCHEC : $titre (voir $DEPOT/livres-audio/$livre/journal.txt)"
    if [ "$(cat "$BASE/.echec-$livre" 2>/dev/null)" != "$empreinte" ]; then
      alerte "Échec : $titre"; echo "$empreinte" > "$BASE/.echec-$livre"
    fi
    continue
  fi
  cp "$livre/journal.txt" "$livre/sortie/journal.txt"

  mkdir -p "$HOME/Movies/Claude/audiobooks/$livre"
  cp -R "$livre/sortie/." "$HOME/Movies/Claude/audiobooks/$livre/"

  if command -v rclone >/dev/null && rclone listremotes | grep -q '^gdrive:'; then
    rclone copy "$livre/sortie" "gdrive:À ÉCOUTER — $titre" --drive-root-folder-id "$DRIVE_AUDIOBOOKS" --exclude ".fait" \
      && note "envoyé sur Drive : À ÉCOUTER — $titre" || note "envoi Drive raté pour $titre"
  else
    note "rclone/gdrive absent : fichiers seulement dans ~/Movies/Claude/audiobooks/$livre"
  fi

  echo "$empreinte" > "$livre/sortie/.fait"
  note "terminé : $titre"
  alerte "Prêt : $titre"
done
}
main "$@"; exit

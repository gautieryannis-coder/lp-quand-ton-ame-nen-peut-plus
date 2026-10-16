#!/bin/bash
# Fabrique automatique des livres audio sur l'iMac.
# Lancé toutes les 10 minutes par launchd (voir installer.sh).
# Pour chaque livres-audio/<livre>/livre.json contenant "generer": true,
# génère l'audio avec ElevenLabs, le monte, le copie dans ~/Movies/Claude/audiobooks/<livre>/
# et l'envoie sur Drive. Un livre déjà fabriqué n'est refait que si son texte change.
set -u
BASE="$HOME/Movies/Claude/livres-audio-auto"
DEPOT="$BASE/depot"
BRANCHE="claude/livre-audio-dieu-t-a-pris-pour-cible"
CLE="$HOME/Movies/Claude/.secrets/elevenlabs.env"
DRIVE_AUDIOBOOKS="1zMgiZvC4P40Eix77D58RwO7QNL9jnjnv"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

mkdir -p "$BASE"
exec >>"$BASE/journal.log" 2>&1
VERROU="$BASE/.en-cours"
mkdir "$VERROU" 2>/dev/null || exit 0          # une seule fabrication à la fois
trap 'rmdir "$VERROU"' EXIT

note() { echo "$(date '+%d/%m %H:%M') $*"; }
alerte() { osascript -e "display notification \"$1\" with title \"Livres audio\"" >/dev/null 2>&1 || true; }

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

  pochette=(); [ -f "$livre/couverture.jpg" ] && pochette=(--pochette "$livre/couverture.jpg")
  if ! python3 generer_livre_audio.py "$livre" ${pochette[@]+"${pochette[@]}"} > "$livre/journal.txt" 2>&1; then
    note "ÉCHEC : $titre (voir $DEPOT/livres-audio/$livre/journal.txt)"
    alerte "Échec : $titre"
    continue
  fi
  cp "$livre/journal.txt" "$livre/sortie/rapport.txt"

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

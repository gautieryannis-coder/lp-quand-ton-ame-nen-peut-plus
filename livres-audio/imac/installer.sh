#!/bin/bash
# À lancer UNE fois sur l'iMac. Installe la fabrique automatique des livres audio.
set -u
BASE="$HOME/Movies/Claude/livres-audio-auto"
DEPOT="$BASE/depot"
PLIST="$HOME/Library/LaunchAgents/com.yannisgautier.livres-audio.plist"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
ok() { echo "  ✓ $*"; }; ko() { echo "  ✗ $*"; MANQUE=1; }
MANQUE=0

echo "Vérifications :"
[ -d "$DEPOT/.git" ] && ok "dépôt récupéré" || ko "dépôt absent dans $DEPOT"
command -v python3 >/dev/null && ok "python3" || ko "python3 manquant (xcode-select --install)"
command -v ffmpeg >/dev/null && ok "ffmpeg" || ko "ffmpeg manquant (brew install ffmpeg)"
[ -f "$HOME/Movies/Claude/.secrets/elevenlabs.env" ] && ok "clé ElevenLabs trouvée" || ko "clé ElevenLabs absente de ~/Movies/Claude/.secrets/elevenlabs.env"
if command -v rclone >/dev/null && rclone listremotes | grep -q '^gdrive:'; then ok "envoi Drive (rclone gdrive)"; else echo "  ! rclone gdrive absent : les livres resteront dans ~/Movies/Claude/audiobooks"; fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.yannisgautier.livres-audio</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DEPOT/livres-audio/imac/fabriquer.sh</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" && ok "fabrique activée : vérifie toutes les 10 minutes" || ko "activation launchd ratée"

echo
[ "$MANQUE" = 0 ] && echo "Tout est prêt. Journal : $BASE/journal.log" || echo "Corrige les ✗ ci-dessus puis relance : bash $DEPOT/livres-audio/imac/installer.sh"

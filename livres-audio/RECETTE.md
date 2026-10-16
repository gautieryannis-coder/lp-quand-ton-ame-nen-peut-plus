# Recette des livres audio — Yannis Gautier

À suivre pour chaque nouveau livre audio. Un livre = un dossier `livres-audio/<livre>/`
avec `livre.json` (titre, sous-titre, chapitres) et `texte/*.txt` (une partie par fichier,
lignes `## ` = titres, suivis d'une pause plus longue).

## Texte (process validé le 02/10, prompts/LIVRE-AUDIO-NICOLAS.md sur l'iMac)

- Garder les mots de Yannis. Ne retoucher que ce qui passe mal à l'oral.
- Commencer par le mot des éditions : « Avant de commencer, un mot pour toi. Les éditions
  Gospel Action Productions, Gap, … Bonne écoute. » Écrire « Gap », jamais « GAP » (sinon la voix épelle).
- Références bibliques et nombres en toutes lettres, jamais de chiffres.
- Citations et paroles entre guillemets « … ».
- Reformuler ce que la voix avale : « il s'est tu » → « il est resté silencieux », « ceux-là »…
- Chapitres de 150 à 380 mots, aux vrais changements de mouvement.

## Voix

« Voix Nicolas Petit IA AUDIO Narration » :

| Réglage | Valeur |
|---|---|
| voice_id | `aQROLel5sQbj1vuIVi6B` |
| modèle | `eleven_multilingual_v2` |
| stabilité | 0.86 |
| similarité | 0.78 |
| style | 0.28 |
| speaker boost | oui |
| vitesse | 0.90 |

- **Un chapitre = une seule requête** (previous_text / next_text = chapitres voisins). Jamais de
  collage paragraphe par paragraphe ni de coupe des silences (voix « hachée, qui bute »).
- 3 prises par chapitre, la meilleure choisie par transcription Whisper comparée au texte.
- Master : voix seule, mono 44,1 kHz, 192 kb/s, −23 LUFS. Fichiers `ch_001.mp3`… + `ecoute-complete.mp3`.

Commande : `python3 generer_livre_audio.py <livre>` (clé dans `ELEVENLABS_API_KEY`).

## Couverture

Esprit validé le 9/10 (« M2, la blanche » de « Dieu t'a pris pour cible ») : moderne, graphique,
comme un best-seller actuel. **Pas de style évangélique** (rayons de lumière, portes, nuages,
livres qui brillent, plumes, croix) et **pas d'encart gris** : l'app l'ajoute elle-même.

1. Décor généré (portrait 1024×1536, qualité haute) : rendu 3D studio, un seul objet design,
   tiers supérieur vide pour le titre, aucun texte, palette blanc cassé / bleu nuit / or uniquement.
2. Typographie posée par-dessus (`gen-cover-modern.mjs` sur le MacBook), couverture 1600×2400 :
   - « YANNIS GAUTIER » en haut, Manrope 600, 38 px, espacement .36em ;
   - titre Manrope 800, 196 px, bleu nuit `#0E1A33`, dernière ligne en or `#C9A043` ;
   - sous-titre Inter 400, 46 px ;
   - en bas « LIVRE AUDIO » en or (32 px, .42em) puis « ÉDITIONS GAP » (24 px).
3. Livrer la couverture plate 1600×2400 et un carré 1200. Montrer 3 ou 4 pistes à Yannis avant de choisir.

## Livraison

Drive, dossier Audiobooks (`1zMgiZvC4P40Eix77D58RwO7QNL9jnjnv`), sous-dossier
« AUDIOBOOKS — À ÉCOUTER ET VALIDER », un sous-dossier par livre. Ne rien pousser sur `main` de ce dépôt (site public).

## Fabrication automatique (iMac)

L'iMac fabrique seul les livres audio. Installation, une seule fois, dans le Terminal de l'iMac :

    cd ~/Movies/Claude && git clone -b claude/livre-audio-dieu-t-a-pris-pour-cible https://github.com/gautieryannis-coder/lp-quand-ton-ame-nen-peut-plus.git livres-audio-auto/depot && bash livres-audio-auto/depot/livres-audio/imac/installer.sh

Ensuite, pour chaque nouveau livre :
1. Yannis envoie le texte à Claude (session cloud) ;
2. Claude prépare `livres-audio/<livre>/` (texte découpé, `livre.json` avec `"generer": true`,
   éventuellement `couverture.jpg`) et pousse sur la branche ;
3. dans les 10 minutes, l'iMac récupère la branche, génère avec ElevenLabs, monte le livre,
   le copie dans `~/Movies/Claude/audiobooks/<livre>/`, l'envoie sur Drive (« À ÉCOUTER — <titre> »
   dans le dossier Audiobooks) et affiche une notification « Prêt ».

Un livre déjà fabriqué n'est refait que si son texte, sa fiche ou sa couverture change.
Journal : `~/Movies/Claude/livres-audio-auto/journal.log`. L'iMac doit être allumé et la session ouverte.

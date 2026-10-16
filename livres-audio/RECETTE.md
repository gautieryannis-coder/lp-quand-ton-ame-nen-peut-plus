# Recette des livres audio — Yannis Gautier

À suivre pour chaque nouveau livre audio. Un livre = un dossier `livres-audio/<livre>/`
avec `livre.json` (titre, sous-titre, chapitres) et `texte/*.txt` (une partie par fichier,
lignes `## ` = titres, suivis d'une pause plus longue).

## Texte

- Garder le texte de Yannis mot pour mot. Seules retouches : ce qui aide la voix.
- Références bibliques et nombres toujours **en toutes lettres**
  (« Jérémie, chapitre dix-huit, verset quatre », jamais « Jr 18:4 » ni « 18 »).
  Leçon du 10/10 : des chiffres oubliés ont obligé à régénérer « Dieu t'a pris pour cible ».
- Ouverture fournie par Yannis, à garder telle quelle en partie 00 :
  « Avant de commencer, un mot pour toi. Les éditions Gospel Action Productions, GAP… Bonne écoute. »
  Vérifier à l'écoute que « GAP » est dit comme le mot « Gap ».

## Voix

Nicolas Petit (préréglage `audiobook.nicolas-petit`) :

| Réglage | Valeur |
|---|---|
| voice_id | `aQROLel5sQbj1vuIVi6B` |
| modèle | `eleven_multilingual_v2` |
| speed | 0.86 |
| stability | 0.48 |
| similarity_boost | 0.88 |
| style | 0.14 |
| speaker_boost | oui |

Génération : `cd livres-audio && python3 generer_livre_audio.py <livre> --pochette <couverture.jpg>`
(clé dans `ELEVENLABS_API_KEY`). Sortie : MP3 intégral, M4B avec chapitres, un MP3 par chapitre.
Garder le même niveau sonore que les livres déjà en ligne dans l'app.

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

## Pour que la session cloud génère elle-même

Dans les réglages de l'environnement cloud (menu de l'environnement → Modifier) :
- Accès réseau : ajouter `api.elevenlabs.io` aux domaines autorisés ;
- Variables : `ELEVENLABS_API_KEY` = la clé ElevenLabs.

Les réglages ne valent que pour les **nouvelles** sessions : en démarrer une après la modification.

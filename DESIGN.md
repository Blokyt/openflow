# OpenFlow — DESIGN.md

## Theme
Sombre unique (pas de mode clair). Fond app `#0a0a0a`, sidebar `#080808`.

## Couleurs
- Surfaces : cartes `#111`, éléments imbriqués `#0a0a0a`/`#0c0c0c`, hover `#1a1a1a`.
- Bordures : `#222` (défaut), `#1a1a1a` (séparateurs internes), `#333` (contrôles).
- Texte : blanc (titres/valeurs), `#B0B0B0` (corps), `#666` (labels/meta), `#555`/`#444` (désactivé).
- Accent : doré `#F2C48D` (marque, sélection, CTA principal — fond doré + texte noir).
- Sémantique : recette `#00C853` (vert), dépense `#FF5252` (rouge), virement interne gris `#B0B0B0`.
- Budget : hérité `#777` (gris), modifié ce mandat `#F2C48D` (doré).
- Seuils budget (budgetColor) : <70 % vert, 70-95 % doré, ≥95 % rouge.

## Typographie
- Système sans-serif. Titres de page : text-3xl bold, letter-spacing -0.02em.
- Labels de sections/tableaux : text-xs uppercase tracking-wider text-[#666].
- Montants : font-semibold, toujours via formatEuros (centimes -> €, fr-FR).

## Composants récurrents
- Carte : bg-[#111] border border-[#222] rounded-2xl (p-6).
- Contrôles (inputs/selects) : bg-[#111] ou #0a0a0a, border #222, rounded-xl,
  focus:border-[#F2C48D], [color-scheme:dark] sur les dates.
- Boutons : primaire = pill doré (rounded-full bg-[#F2C48D] text-black font-semibold) ;
  secondaire = pill bordé #333 texte blanc ; tertiaire = texte gris hover blanc.
- Chips/badges : rounded-full, fond couleur+"20", texte de la couleur (entités, catégories).
- Spinner : rond doré animate-spin (h-8/h-10, border-b-2 #F2C48D).
- Tableaux : thead text-xs uppercase #666, lignes séparées border-[#1a1a1a],
  hover:bg-[#1a1a1a], montants alignés à droite.
- Panneau latéral : overlay bg-black/60, panneau max-w-md bg-[#0a0a0a] border-l #222.

## Règles
- Le sens d'un flux vient de txTone (types d'entités), jamais du signe du montant.
- Un montant nul ou non pertinent s'affiche « — » en #444.
- Pas de texte explicatif permanent : l'aide contextuelle n'apparaît que si l'état
  la justifie (état vide, anomalie, première utilisation).
- Focus entité/exercice : rappel discret en une ligne text-xs, nom en doré.

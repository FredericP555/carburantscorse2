# Politique préparée — seuil 45 jours et bouclier

> **PRÉPARÉE, NON ACTIVÉE.** `publication.py` continue d'utiliser la méthode actuelle tant qu'une bascule explicite n'est pas décidée après la mise à jour du lundi.

## Règle cible
- 45 jours par station × carburant, Corse et BdR.
- J0 à J+44 inclus ; J+45 exclu sans nouvelle déclaration.
- Une redéclaration au même prix remet le compteur à zéro.

## Bouclier TotalEnergies
- Exception uniquement après détection du bouclier avec des données normalement fraîches.
- Prix ancien obligatoirement au plafond et admissible à l'entrée de la phase de plafond.
- Corse : vivacité par l'autre carburant principal.
- Continent/BdR : vivacité par toute autre déclaration de carburant disponible dans le snapshot partagé.
- Double plafond Gazole + SP95 : maintien possible au-delà de 45 jours si Rotterdam Gazole confirme que le plafond Gazole reste économiquement contraignant.
- Rotterdam ne constitue pas un indice SP95 ; il justifie seulement l'hypothèse de silence explicable lorsque les deux carburants sont plafonnés.
- Rupture ou preuve indépendante d'inactivité : exclusion prioritaire.

## Identité des stations pour les calculs par enseigne — préparée, inactive
Les calculs sensibles à l'enseigne ne doivent jamais déduire « non-Total » de la seule absence d'un ID dans une liste Total.

Trois états sont utilisés :
- `TOTAL` : enseigne TotalEnergies confirmée ;
- `NON_TOTAL_CONFIRMED` : autre enseigne confirmée ;
- `UNKNOWN` : ID absent du registre, enseigne manquante ou résolution incomplète.

Un ID `UNKNOWN` est exclu des calculs par enseigne jusqu'à résolution. Il ne peut donc polluer ni le groupe Total ni le groupe hors Total.

### Corse
C2 ne maintient pas de second référentiel Corse. `scripts/fetch_c1_corse_station_brands.py` lit en lecture seule le registre de référence de C1 (`config/corse_station_brands.json`) et écrit seulement une copie de travail dans `outputs/c1/corse_station_brands.json`. Le module `carburantscorse2/corse_station_identity_v2.py` utilise cette copie pour classer les IDs. Le fichier de sortie est un artefact d'audit et n'est pas ajouté au commit de publication.

### Bouches-du-Rhône
Le résolveur incrémental existant conserve déjà les nouveaux IDs non résolus en `inconnu`. Ils restent exclus des comparaisons réseau/par enseigne jusqu'à résolution et ne sont jamais classés silencieusement comme réseau traditionnel.

## Rotterdam — source unique C1 → C2, préparée et inactive
La chaîne préparée est désormais **UFIP → C1 → C2**.

- C1 effectue l'unique téléchargement UFIP.
- C1 publie `rotterdam_gazole_observed.csv` et `rotterdam_gazole_daily.csv` dans la même release que le snapshot officiel partagé.
- Les SHA-256 et le calibrage Corse candidat sont inscrits dans `official_13_20.meta.json`.
- C2 exécute `scripts/fetch_shared_ufip_from_c1.py` : il télécharge ces assets depuis la release C1 et **ne contacte jamais UFIP** dans l'automatisation préparée.
- `outputs/ufip/c1_shared_meta.json` conserve la copie des métadonnées C1 utilisée pour l'audit.

### Corse
Le calibrage Corse n'est plus recalculé par C2. `carburantscorse2/rotterdam_calibration_v2.py` lit directement `rotterdam.corsica_calibration` dans les métadonnées C1.

Pour l'épisode entrant le 8 avril 2026 : R1 provient des observations du 3 avril (1,037), 6 avril (1,048) et 7 avril (1,061), soit `R1 ≈ 1,048667 EUR/L`. Les sorties de référence sont les 29 mai, 1er juin et 2 juin ; `k_corse ≈ 0,733` et `R2 = k × R1`.

### Bouches-du-Rhône
C2 conserve uniquement le calcul qui lui est propre : `TOTAL_CLASSIQUE`, avec sorties de référence 20, 21 et 22 mai 2026 et `k_bdr ≈ 0,824`. Ce calcul utilise le **même CSV observé téléchargé une seule fois par C1**, pas une seconde récupération UFIP.

En cas de release C1 sans assets Rotterdam, de SHA-256 incohérent, de métadonnées Corse absentes ou de dates BdR manquantes, la préparation échoue fermée.

## Procédure après lundi
1. Contrôler la publication habituelle C1 puis C2.
2. Figer le snapshot publié comme référence.
3. Brancher le moteur préparé uniquement dans un calcul candidat.
4. Comparer actuel / 45-45 prospectif / 45-45 rétroactif.
5. Mesurer jours modifiés, stations gagnées/perdues, moyennes, écarts Corse-BdR et épisodes de bouclier.
6. Décider explicitement de la migration ; pas de réécriture silencieuse de l'historique.

# Politique préparée — seuil 45 jours et bouclier

> **PRÉPARÉE, NON ACTIVÉE.** `publication.py` continue d'utiliser la méthode actuelle. Rien de cette politique n'est actif dans `main` avant décision explicite après la mise à jour du lundi.

## 1. Règle normale

- 45 jours par station × carburant.
- J0 à J+44 inclus ; J+45 sort de la règle normale sans nouvelle déclaration.
- Une redéclaration au même prix remet le compteur à zéro.
- Prix non fini, date future, rupture/fermeture ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Bouclier TotalEnergies

- Exception uniquement après détection du bouclier avec des données normalement fraîches.
- Prix ancien obligatoirement au plafond et admissible à l'entrée de la phase de plafond.
- Les exceptions de vieillissement concernent uniquement **Gazole et SP95** ; E10 ne peut pas en bénéficier.
- Corse : vivacité par l'autre carburant principal.
- BdR : vivacité par toute autre déclaration de carburant admise par la règle C2.
- Double plafond Gazole + SP95 : Rotterdam Gazole peut intervenir dans le cas particulier prévu ; Rotterdam n'est pas un indice SP95.
- Rupture ou preuve indépendante d'inactivité : exclusion prioritaire.

**Aucun seuil absolu J+90 n'est ajouté à C2 par cette préparation.** Le garde-fou J+90 décidé pour le continent dans C1 est une règle distincte et ne doit pas être transposé automatiquement aux BdR.

## 3. Identité des stations pour les calculs par enseigne

Trois états sont utilisés :

- `TOTAL` : enseigne TotalEnergies confirmée ;
- `NON_TOTAL_CONFIRMED` : autre enseigne confirmée ;
- `UNKNOWN` : ID absent du registre, enseigne manquante ou résolution incomplète.

Un ID `UNKNOWN` est exclu des calculs sensibles à l'enseigne jusqu'à résolution. L'absence d'un ID dans une liste Total n'est jamais une preuve de non-Total.

### Corse

C2 ne maintient pas de second référentiel Corse. Le registre canonique C1 est désormais publié dans **la même release validée** que le snapshot et Rotterdam. C2 le télécharge depuis cette release, vérifie son SHA-256 et l'écrit seulement dans `outputs/c1/corse_station_brands.json` pour le calcul/audit local.

### Bouches-du-Rhône

Le résolveur incrémental conserve les nouveaux IDs non résolus en `inconnu`. Ils restent exclus des comparaisons réseau/par enseigne jusqu'à résolution et ne sont jamais transformés silencieusement en réseau traditionnel.

## 4. Source unique C1 → C2

La chaîne préparée est **UFIP → C1 → C2**.

C1 publie dans une seule release validée :

- `official_13_20.csv.gz` ;
- `official_13_20.meta.json` ;
- `rotterdam_gazole_observed.csv` ;
- `rotterdam_gazole_daily.csv` ;
- `corse_station_brands.json`.

C2 choisit **une seule release C1 au début du cycle** et écrit son tag dans `outputs/c1/shared_release_tag.txt`. Toutes les lectures C1 du cycle sont ensuite épinglées sur ce tag. Les SHA-256 du snapshot, des deux fichiers Rotterdam et du registre Corse sont vérifiés avant utilisation.

Le chemin hebdomadaire C2 **ne contacte plus UFIP** : le générateur de marges lit les CSV locaux déjà fournis par C1. Le téléchargement direct UFIP peut rester un outil diagnostique séparé, mais il n'est plus utilisé par le workflow préparé.

## 5. Calibration Rotterdam

### Corse

Le calibrage Corse n'est pas recalculé par C2. C2 lit directement `rotterdam.corsica_calibration` dans les métadonnées de la release C1 épinglée.

Pour l'épisode entrant le 8 avril 2026 : R1 provient des observations du 3 avril (1,037), 6 avril (1,048) et 7 avril (1,061), soit `R1 ≈ 1,048667 EUR/L`. Les sorties de référence sont les 29 mai, 1er juin et 2 juin ; `k_corse ≈ 0,733` et `R2 = k × R1`.

### Bouches-du-Rhône

C2 conserve son calcul propre `TOTAL_CLASSIQUE`, avec sorties 20, 21 et 22 mai 2026 et `k_bdr ≈ 0,824`, à partir du **même CSV observé produit une seule fois par C1**.

### Franchissement de R2

**La règle exacte de franchissement de R2 n'est pas définie ici.** Le moteur préparé reçoit seulement un booléen `rotterdam_gazole_constraining`. Aucun mécanisme supplémentaire de seuil, confirmation ou verrouillage n'est inventé avant décision méthodologique explicite.

## 6. Échec fermé

La préparation bloque notamment si :

- release C1 ou asset requis absent ;
- SHA-256 incohérent ;
- tag épinglé et tag du snapshot différents ;
- registre Corse invalide ;
- série Rotterdam quotidienne incomplète sur la fenêtre nécessaire ;
- métadonnées Corse de calibration absentes ;
- dates BdR nécessaires au calibrage absentes.

## Procédure après lundi

1. Contrôler la publication habituelle C1 puis C2.
2. Figer le résultat comme référence.
3. Tester le moteur préparé uniquement en calcul candidat.
4. Comparer actuel / prospectif / rétroactif.
5. Mesurer les écarts et les stations affectées.
6. Définir séparément la règle exacte de franchissement R2, puis seulement la coder et la tester.
7. Décider explicitement de toute migration ; aucune réécriture silencieuse de l'historique.

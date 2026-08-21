# Politique préparée — seuil 45 jours et bouclier

> **PRÉPARÉE, NON ACTIVÉE.** `publication.py` continue d'utiliser la méthode actuelle. Rien de cette politique n'est actif dans `main` avant décision explicite après la mise à jour du lundi.

## 1. Règle normale

- 45 jours par station × carburant.
- J0 à J+44 inclus ; J+45 sort de la règle normale sans nouvelle déclaration.
- Une redéclaration au même prix remet le compteur à zéro.
- Prix non fini, date future, rupture/fermeture ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Bouclier effectif et fiabilité d'un vieux prix

Le statut **bouclier effectif** est produit par C1 selon la règle A4C et consommé par C2. R2 n'intervient jamais dans cette détection et ne définit jamais la fin du bouclier effectif.

R2 intervient seulement ensuite pour décider si de vieux prix Gazole/SP95 d'une station peuvent encore être retenus dans la moyenne dans le cas du double plafond.

## 3. Un seul carburant principal au plafond

### Corse

Si le prix cible Gazole/SP95 a dépassé 45 jours mais reste au plafond pendant un bouclier effectif, une nouvelle déclaration de **l'autre carburant principal** datant de moins de 45 jours prouve la vivacité de la station.

Cette déclaration crée une **nouvelle fenêtre glissante de 45 jours** pour le vieux prix cible. Sans nouvelle déclaration admissible pendant 45 jours, le vieux prix sort de la moyenne.

### Bouches-du-Rhône

Même logique, mais la vivacité peut être prouvée par **n'importe quel autre carburant déclaré** par la station.

Chaque nouvelle déclaration admissible d'un autre carburant crée une nouvelle fenêtre glissante de 45 jours. Il n'existe **aucun arrêt arbitraire à J+90 dans C2/BdR**.

## 4. Gazole et SP95 simultanément au plafond

### Corse

La vivacité croisée Gazole ↔ SP95 ne suffit plus puisque les deux peuvent rester figés au plafond.

- Rotterdam Gazole **>= R2 Corse** : les vieux prix Gazole/SP95 peuvent rester admissibles sous réserve des autres garde-fous ;
- Rotterdam Gazole **< R2 Corse** : les vieux prix Gazole/SP95 sont exclus de la moyenne.

### Bouches-du-Rhône

Deux conditions sont requises ensemble :

1. une déclaration datant de moins de 45 jours sur un **autre carburant que Gazole/SP95** prouve que la station est toujours vivante ;
2. le vieux prix ne doit pas avoir été verrouillé par R2.

Le verrou R2 fonctionne de la même façon en Corse et dans les BdR : après l'expiration normale des 45 jours du carburant cible, si Rotterdam passe une seule fois **sous R2** du territoire, ce vieux prix reste exclu même si Rotterdam remonte ensuite. Il ne peut revenir qu'après une **nouvelle déclaration du carburant cible**, qui crée un nouveau J0.

Dans les BdR, la vivacité sur un autre carburant reste en plus obligatoire pendant le double plafond. Dans aucun cas R2 ne met fin au bouclier effectif.

Calibration candidate 2026 : `k_corse ≈ 0,733` et `k_bdr ≈ 0,824`, à partir de la même série Rotterdam observée produite une seule fois par C1.

## 5. Phases de plafond et garde-fou de non-résurrection

C1 publie des **phases de plafond explicites** dans les métadonnées partagées. Une phase est une portion continue de bouclier effectif avec un même montant de plafond.

Un changement de plafond crée automatiquement une nouvelle phase. C2 lit directement la date de début et le plafond de cette phase depuis la release C1.

Le moteur ne fait plus confiance à un booléen manuel `eligible_at_cap_entry`. Il calcule lui-même :

- déclaration encore âgée de moins de 45 jours au début de la phase → admissible aux exceptions prévues ;
- déclaration déjà périmée au début de la phase → aucune résurrection ;
- nouvelle déclaration du carburant cible pendant la phase → nouveau J0, donc preuve fraîche normale.

## 6. Identité des stations pour les calculs par enseigne

Trois états sont utilisés : `TOTAL`, `NON_TOTAL_CONFIRMED`, `UNKNOWN`. Un ID `UNKNOWN` est exclu des calculs sensibles à l'enseigne jusqu'à résolution. L'absence d'un ID dans une liste Total n'est jamais une preuve de non-Total.

Le registre Corse canonique est publié par C1 dans la même release que le snapshot et Rotterdam ; C2 le télécharge depuis cette release et vérifie son SHA-256. Les nouveaux IDs BdR non résolus restent `inconnu` et exclus des comparaisons réseau/par enseigne.

## 7. Source unique C1 → C2

La chaîne préparée est **UFIP → C1 → C2**.

C1 publie dans une seule release validée :

- `official_13_20.csv.gz` ;
- `official_13_20.meta.json` avec bouclier et phases de plafond ;
- `rotterdam_gazole_observed.csv` ;
- `rotterdam_gazole_daily.csv` ;
- `corse_station_brands.json`.

C2 choisit une seule release C1 et épingle toutes les lectures sur son tag. Le chemin hebdomadaire C2 ne contacte plus UFIP directement.

## 8. Garde-fous prioritaires

Dans tous les cas :

- rupture active → exclusion ;
- fermeture / preuve indépendante d'inactivité → exclusion ;
- prix absent, non fini ou invalide → exclusion ;
- date future → exclusion ;
- prix déjà périmé lors de l'entrée dans la phase de plafond → aucune résurrection ;
- changement de plafond → nouvelle phase et nouvelle vérification automatique.

## 9. Échec fermé

La préparation bloque notamment si : release C1/asset requis absent, SHA-256 incohérent, registre invalide, série Rotterdam quotidienne incomplète, calibration Corse absente, dates BdR de calibration absentes, ou phase de plafond requise absente/invalide.

## Procédure après lundi

1. Contrôler la publication habituelle C1 puis C2.
2. Figer le résultat comme référence.
3. Tester le moteur préparé uniquement en calcul candidat.
4. Comparer actuel / prospectif / rétroactif.
5. Mesurer les écarts et les stations affectées.
6. Décider explicitement de toute migration ; aucune réécriture silencieuse de l'historique.

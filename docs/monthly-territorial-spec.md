# Bilan mensuel territorial A4C — spécification de prototype

Ce document décrit une chaîne **indépendante** du workflow hebdomadaire C2. Elle ne modifie ni `data.json`, ni le site public, ni WordPress, ni les règles de publication existantes.

## 1. Périmètre

- Carburants : `Gazole`, `SP95`.
- Territoire principal : Corse.
- Regroupement territorial : `station_id -> localite -> commune -> epci_siren / epci_nom` depuis le registre géographique de la branche de travail.
- Référence externe : Bouches-du-Rhône avec deux périmètres explicites : `network` (stations de réseau) et `all` (ensemble hors autoroutes).
- Un mois n'est calculé comme bilan que s'il est **complet** dans la release C1 effectivement épinglée par C2.

## 2. Population statistique et moteur de fiabilité

La géographie territoriale est nouvelle, mais **la décision de fiabilité d'un station-jour n'est pas réimplémentée dans le générateur mensuel**.

`build_monthly_territorial.py` reprend la même release C1 V2 que celle déjà consommée par C2 et réutilise la chaîne du moteur de production C2 : état de publication, résolution du périmètre Bouches-du-Rhône, métadonnées de bouclier, marques corses, gardes événementiels et évaluation V2 via `scripts.build_v2_production_candidate._evaluate_v2`.

La transition V2 conserve les mêmes sémantiques que C2 : V2 remplace l'éligibilité à partir du 23 juillet 2026 ; les jours antérieurs conservent l'état de publication historique.

Les agrégats mensuels ne sont calculés que sur les station-jours marqués `eligible_publication` par cette chaîne. Une donnée retenue par le moteur est utilisée normalement ; une donnée rejetée n'entre pas dans les calculs.

## 3. Registre géographique et garde-fou sur les nouveaux identifiants

Chaque identifiant de station corse éligible doit disposer d'un rattachement territorial explicite. Le rattachement EPCI se fait par la **commune**, jamais par la seule localité commerciale ou postale.

Le générateur ne doit ni inventer un EPCI, ni fusionner automatiquement deux identifiants de station. Si une station corse éligible apparaît dans C2 sans rattachement dans le registre géographique, la génération mensuelle doit échouer explicitement afin que l'identifiant soit vérifié et rattaché avant production du bilan.

## 4. Indicateurs par EPCI et par carburant

Pour chaque mois complet :

- `mean_eur_l` : moyenne TTC des station-jours éligibles du territoire ;
- `median_station_eur_l` : médiane des moyennes mensuelles calculées station par station ;
- `station_mean_min_eur_l` / `station_mean_max_eur_l` : plus petite et plus grande **moyenne mensuelle de station** dans le territoire ;
- `station_mean_spread_cpl` : écart entre ces deux moyennes de station, en centimes/litre ;
- `change_vs_previous_month_cpl` : différence avec la moyenne du mois précédent, en centimes/litre ;
- `vs_corse_cpl` : différence avec la moyenne Corse du même mois, en centimes/litre ;
- `n_stations` : nombre de stations ayant au moins un station-jour effectivement retenu ;
- `n_station_days` : nombre de station-jours retenus ;
- `n_days_covered` : nombre de jours du mois pour lesquels le territoire dispose d'au moins une valeur éligible ;
- `coverage_ratio` : `n_station_days / (n_stations * nombre_de_jours_du_mois)` ; cet indicateur est nommé publiquement **couverture temporelle de l'échantillon** ;
- `n_communes` et liste des localités représentées.

Le module n'utilise pas le minimum ou le maximum ponctuel observé pendant le mois comme indicateur principal de dispersion. Il affiche la plage des **moyennes mensuelles de station**, moins sensible à une valeur isolée d'un seul jour.

## 5. Affichage, comparaison et classement

Les **19 EPCI restent accessibles** dans le module dès lors qu'une donnée mensuelle peut être calculée. Un territoire n'est exclu de l'interface simplement parce qu'il ne franchit pas un seuil de classement.

Un EPCI est classable entre territoires si :

1. `n_stations >= 3` ;
2. `n_days_covered >= 80 %` des jours du mois ;
3. `coverage_ratio >= 0.80`.

Sous ces seuils, ses valeurs restent affichées, avec une mention explicite indiquant qu'il est hors classement inter-EPCI pour ce carburant et ce mois. Une comparaison directe avec un autre territoire reste possible mais est présentée comme descriptive.

Le diagnostic interne peut calculer un indicateur plus sévère de représentativité rapportant les station-jours retenus à toutes les stations du registre historiquement connues pour vendre le carburant. Cet indicateur **ne remplace pas** la couverture temporelle de l'échantillon et ne modifie pas automatiquement les seuils de classement : il sert au contrôle interne.

## 6. Comparaison Corse / Bouches-du-Rhône

Pour chaque carburant et pour chacun des périmètres `network` et `all`, le fichier mensuel contient :

- moyenne TTC Corse et Bouches-du-Rhône ;
- écart TTC en centimes/litre ;
- moyenne HT Corse et Bouches-du-Rhône suivant la convention C2 ;
- écart HT en centimes/litre ;
- évolution mensuelle des écarts TTC et HT ;
- nombre de jours ayant franchi les gardes d'effectif C2 ;
- effectifs de stations et de station-jours utilisés.

Les libellés distinguent explicitement TTC et HT. L'écart TTC est celui utilisé pour l'estimation budgétaire destinée à l'automobiliste ; l'écart HT reste analytique.

## 7. Séparation « aujourd'hui » / « bilan du mois »

Le bilan mensuel porte exclusivement sur le mois complet sélectionné. Si une donnée courante est ajoutée ultérieurement dans un article, elle doit être visuellement séparée et datée (« dernière donnée disponible au ... »). Un bilan figé ne doit pas être silencieusement réécrit par une donnée plus récente.

## 8. Calculateur personnel

Le module permet :

- soit de saisir directement un volume de carburant en litres ;
- soit de saisir `kilomètres + consommation L/100 km` pour obtenir un volume estimé ;
- de choisir la référence Bouches-du-Rhône (`network` ou `all`) ;
- d'afficher l'effet budgétaire à partir de l'écart TTC, avec l'écart HT présenté séparément comme indicateur analytique.

Aucune hypothèse fixe de réservoir de 50 L n'est imposée.

## 9. Contrôles avant toute intégration

Le prototype possède deux niveaux de contrôle indépendants :

- un contrôle de contrat JSON/HTML vérifiant le schéma, les 19 EPCI, les champs consommés, les deux périmètres Bouches-du-Rhône et la syntaxe JavaScript ;
- un test dans un vrai navigateur Chrome, en vue ordinateur et mobile, qui exerce les deux carburants, les 38 couples EPCI/carburant, les cas hors classement, la comparaison entre territoires, le calculateur et l'absence de débordement horizontal de page.

Les tableaux peuvent défiler horizontalement dans leur propre conteneur sur mobile ; la page elle-même ne doit pas déborder. Les contrôles tactiles principaux visent au moins 44 px de hauteur.

## 10. Sécurité de publication

Le prototype est développé uniquement sur `add-corse-station-geography-2026`. Aucun workflow hebdomadaire de production n'est modifié. Aucun fichier produit par ce prototype n'est consommé par le site C2 public ni par WordPress tant qu'une validation séparée et explicite n'a pas été décidée.

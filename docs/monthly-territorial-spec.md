# Bilan mensuel territorial A4C — spécification de prototype

Ce document décrit une chaîne **indépendante** du workflow hebdomadaire C2. Elle ne modifie ni `data.json`, ni le site public, ni les règles de publication existantes.

## 1. Périmètre

- Carburants : `Gazole`, `SP95`.
- Territoire principal : Corse.
- Regroupement territorial : `station_id -> localite -> commune -> epci_siren / epci_nom` depuis `config/corse_station_geography_2026.csv`.
- Référence externe : Bouches-du-Rhône, calculée avec le même état de publication C2 lorsque le fichier mensuel est généré.
- Un mois n'est publiable que s'il est **complet** dans la source officielle. Aucune moyenne d'un mois en cours n'est présentée comme un bilan mensuel.

## 2. Population statistique et nettoyage

Le prototype réutilise `carburantscorse2.publication.build_publication_state` et donc les règles de fiabilité déjà utilisées par C2 : dernière déclaration du jour, valeurs aberrantes exclues sans correction arbitraire, gestion des longues périodes sans déclaration et des stations devenues inactives.

Les agrégats mensuels ne sont calculés que sur les `station-day` marqués `eligible_publication`.

## 3. Indicateurs par EPCI et par carburant

Pour chaque mois complet :

- `mean_eur_l` : moyenne des prix TTC sur les station-days éligibles du mois ;
- `median_station_eur_l` : médiane des moyennes mensuelles calculées station par station ;
- `observed_min_eur_l` / `observed_max_eur_l` : minimum et maximum réellement observés parmi les station-days éligibles ;
- `change_vs_previous_month_cpl` : différence avec la moyenne du mois précédent, en centimes/litre ;
- `vs_corse_cpl` : différence avec la moyenne Corse du même mois, en centimes/litre ;
- `n_stations` : nombre de stations distinctes effectivement retenues ;
- `n_station_days` : nombre de station-days retenus ;
- `n_days_covered` : nombre de jours du mois pour lesquels le territoire dispose d'au moins une valeur éligible ;
- `coverage_ratio` : `n_station_days / (n_stations * nombre_de_jours_du_mois)` ;
- `n_communes` et liste des localités représentées.

## 4. Règles d'affichage et de classement

Un territoire peut être **affiché** dès qu'il possède au moins une station éligible dans le mois. Il n'est **classable/comparable** entre EPCI que si :

1. `n_stations >= 3` ;
2. `n_days_covered >= 80 %` des jours du mois ;
3. `coverage_ratio >= 0.80`.

Sous ces seuils, les valeurs peuvent être montrées avec la mention « échantillon limité », mais ne doivent pas servir à désigner les territoires « les moins chers » ou « les plus chers ».

Les localités sont affichées comme informations de proximité. Elles ne sont pas classées comme territoires robustes si elles ne satisfont pas elles-mêmes un effectif suffisant.

## 5. Comparaison Corse / Bouches-du-Rhône

Le fichier mensuel contient, pour chaque carburant :

- moyenne TTC Corse ;
- moyenne TTC Bouches-du-Rhône ;
- écart TTC en centimes/litre ;
- moyenne HT Corse et Bouches-du-Rhône suivant la convention C2 ;
- écart HT en centimes/litre ;
- évolution de ces écarts par rapport au mois précédent.

Les libellés doivent distinguer explicitement TTC et HT. Le module ne doit jamais présenter l'écart HT comme le prix réellement payé à la pompe.

## 6. Séparation « aujourd'hui » / « bilan du mois »

Le bilan mensuel porte exclusivement sur le mois complet sélectionné. Si une donnée courante est ajoutée ultérieurement dans WordPress, elle doit être visuellement séparée et datée (« dernière donnée disponible au ... »).

## 7. Calculateur personnel

Le premier prototype HTML peut convertir un volume déclaré par l'utilisateur en impact théorique de l'écart de prix. Il doit :

- laisser l'utilisateur saisir ses litres ;
- proposer en option `kilomètres + consommation L/100 km` pour calculer un volume ;
- afficher séparément l'effet de l'écart TTC et l'écart HT ;
- préciser qu'il s'agit d'une estimation à partir de moyennes territoriales et non de la facture réelle de l'utilisateur.

Aucune hypothèse fixe de réservoir de 50 L n'est imposée.

## 8. Sécurité de publication

Le prototype est développé uniquement sur `add-corse-station-geography-2026`. Aucun workflow hebdomadaire n'est modifié. Aucun fichier produit par ce prototype n'est consommé par le site C2 public tant qu'une validation séparée n'a pas été faite.

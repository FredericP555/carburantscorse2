# Bilan mensuel territorial A4C — spécification de prototype

Ce document décrit une chaîne **indépendante** du workflow hebdomadaire C2. Tant qu'elle reste sur la branche de travail, elle ne modifie ni `data.json`, ni le site public, ni WordPress, ni les règles de publication existantes.

## 1. Périmètre

- Carburants : `Gazole`, `SP95`.
- Territoire principal : Corse.
- Regroupement territorial : `station_id -> localite -> commune -> epci_siren / epci_nom` depuis le registre géographique de la branche de travail.
- Référence externe : Bouches-du-Rhône avec deux périmètres explicites : `network` (stations de réseau) et `all` (ensemble hors autoroutes).
- Un mois n'est calculé comme bilan que s'il est **complet** dans la release C1 effectivement épinglée par C2.

## 2. Population statistique et moteur de fiabilité

La géographie territoriale est nouvelle, mais **la décision de fiabilité d'un station-jour n'est pas réimplémentée comme une politique concurrente de C2**.

`build_monthly_territorial.py` reprend la même release C1 V2 que celle déjà consommée par C2 et réutilise la chaîne du moteur de production C2 : état de publication, résolution du périmètre Bouches-du-Rhône, métadonnées de bouclier, marques corses, gardes événementiels et évaluation V2 via `scripts.build_v2_production_candidate._evaluate_v2`.

La transition V2 conserve les mêmes sémantiques que C2 : V2 remplace l'éligibilité à partir du 23 juillet 2026 ; les jours antérieurs conservent l'état de publication historique.

Les agrégats mensuels ne sont calculés que sur les station-jours marqués `eligible_publication` par cette chaîne. Une donnée retenue par le moteur est utilisée normalement ; une donnée rejetée n'entre pas dans les calculs.

Les points d'entrée de test durci sont `build_monthly_territorial_hardened.py` et `validate_monthly_source_guards_hardened.py`. Ils ne remplacent aucune règle de prix ou d'éligibilité C2 : ils ajoutent uniquement la règle mensuelle de classification BdR décrite ci-dessous et inscrivent son usage dans l'audit interne.

## 3. Registre géographique et périmètre Bouches-du-Rhône

Le rattachement EPCI se fait par la **commune**, jamais par la seule localité commerciale ou postale. La chaîne de production mensuelle doit vérifier les identifiants de stations corses présents dans le mois **avant le filtrage d'éligibilité**. Ainsi, un nouvel identifiant entièrement rejeté par la politique de fiabilité ne peut pas échapper au contrôle géographique.

Aucun EPCI n'est inventé et aucun historique n'est transféré entre deux `station_id`. Tout identifiant corse présent dans le mois mais absent du registre provoque un échec explicite.

La chaîne réutilise également le garde-fou C2 `validate_recent_bdr_perimeter`. Une station BdR éligible restant classée `unknown` sur le mois est un arrêt bloquant avant promotion d'un résultat mensuel.

### Règle mensuelle de rétro-propagation de catégorie BdR

C2 reste temporel et append-only : sa classification historique n'est pas réécrite. Pour une **reconstruction mensuelle seulement**, lorsqu'un station-jour BdR éligible n'a encore aucune catégorie C2, une catégorie vérifiée quelques jours plus tard peut être rétro-propagée sous les conditions cumulatives suivantes :

1. il s'agit exactement du **même `station_id`** ;
2. la catégorie future est résolue (`gms` ou `network`) et porte une date de vérification ;
3. la classification devient valable au plus **7 jours** après le station-jour à compléter ;
4. aucune information enregistrée dans l'intervalle ne montre une enseigne ou une catégorie contradictoire ;
5. la classification C2 normale reste toujours prioritaire si elle existe déjà.

Cette règle ne modifie **ni le prix, ni la date de déclaration, ni l'éligibilité du station-jour**. Elle complète seulement le champ de catégorie nécessaire au périmètre `network`. Chaque station-jour ainsi classé est consigné dans `internal_audit.bdr_category_backfill`, avec l'identifiant, la période rétro-propagée, l'enseigne, la catégorie, la date de prise d'effet de la classification vérifiée et sa date de vérification. Un conflit empêche la rétro-propagation et laisse le garde BdR bloquant.

Cas de référence d'août 2026 : le `station_id` `13120012` de Gardanne est vérifié `Carrefour Market`, donc `gms`, à compter du 31 août. Les station-jours éligibles du 25 au 30 août peuvent recevoir cette même catégorie dans la reconstruction mensuelle, en l'absence de preuve contradictoire. Comme la catégorie obtenue est `gms`, ce cas ne doit pas modifier le périmètre `network` par rapport au prototype antérieur où ces jours `unknown` en étaient déjà absents ; un contrôle avant/après le vérifie explicitement.

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

Les **19 EPCI restent accessibles** dans le module dès lors qu'une donnée mensuelle peut être calculée. Un territoire n'est pas retiré de l'interface simplement parce qu'il ne franchit pas un seuil de classement.

Un EPCI est classable entre territoires si :

1. `n_stations >= 3` ;
2. `n_days_covered >= 80 %` des jours du mois ;
3. `coverage_ratio >= 0.80`.

Sous ces seuils, ses valeurs restent affichées, avec une mention explicite indiquant qu'il est hors classement inter-EPCI pour ce carburant et ce mois. Une comparaison directe avec un autre territoire reste possible mais est présentée comme descriptive.

Le diagnostic interne peut calculer un indicateur plus sévère de représentativité rapportant les station-jours retenus à toutes les stations du registre historiquement connues pour vendre le carburant. Cet indicateur **ne remplace pas** la couverture temporelle de l'échantillon et ne modifie pas automatiquement les seuils de classement.

## 6. Comparaison Corse / Bouches-du-Rhône

Pour chaque carburant et pour chacun des périmètres `network` et `all`, le fichier mensuel contient les moyennes TTC et HT, les écarts en centimes/litre, leur évolution mensuelle, les jours franchissant les gardes d'effectif C2 et les effectifs utilisés.

Les libellés distinguent explicitement TTC et HT. L'écart TTC est celui utilisé pour l'estimation budgétaire destinée à l'automobiliste ; l'écart HT reste analytique.

## 7. Preuve de succès C2 avant génération

Le simple passage au mois suivant n'autorise pas une génération. `check_monthly_readiness.py` exige un **reçu `business-success` réel de C2**, issu de la vérification de publication bout-en-bout, et vérifie notamment :

- que le mois demandé est terminé ;
- que `data.json` couvre un jour postérieur à la fin du mois ;
- que `data.json` et `homepage-summary.json` portent la même provenance C1 ;
- que les SHA-256 du dépôt correspondent à ceux certifiés par le reçu C2 et aux contenus observés sur Pages ;
- que le tag et l'empreinte de la release C1 correspondent ;
- que le registre géographique est complet et unique ;
- qu'aucun reçu mensuel final valide n'existe déjà.

Le champ `commit` du reçu C2 est conservé comme provenance du vérificateur, mais l'identité du contenu repose sur les empreintes SHA-256 certifiées. Le SHA de `main` utilisé au moment du calcul mensuel est enregistré séparément.

## 8. Isolation d'exécution et idempotence

Les tests d'intégration sont exécutés dans un **worktree jetable construit à partir du `main` courant**, auquel seuls les fichiers mensuels sont superposés. Cela évite de tester contre l'ancien arbre de la branche et empêche les écritures auxiliaires du résolveur BdR ou des téléchargements C1 de contaminer le checkout de production.

Avant chaque reconstruction sensible, le registre BdR de départ est restauré. Seules les sorties mensuelles explicitement autorisées sont recopiées vers la branche de travail.

La future automatisation doit être sérialisée par une `concurrency` GitHub Actions et écrire, après réussite complète, un reçu mensuel structuré. `write_monthly_receipt.py` utilise une création exclusive (`O_EXCL`) et refuse tout écrasement. Le reçu contient les empreintes du jeu mensuel, du registre géographique, du widget, des contrôles navigateur, des gardes source et la provenance C1/C2.

Pendant le prototype, le reçu final n'est créé que sous `/tmp` pour tester sa mécanique. Aucun `outputs/monthly-receipts/YYYY-MM.json` n'est créé ni promu tant qu'une décision explicite de mise en production n'a pas été prise.

## 9. Calculateur personnel

Le module permet soit de saisir directement un volume de carburant, soit de saisir `kilomètres + consommation L/100 km`, puis de choisir `network` ou `all`. L'effet budgétaire est calculé à partir de l'écart TTC, avec l'écart HT présenté séparément comme indicateur analytique. Aucune hypothèse fixe de réservoir de 50 L n'est imposée.

## 10. Tests avant intégration

La chaîne de test vérifie :

- le contrat global de sécurité CI de `main`, notamment l'épinglage complet des actions GitHub ;
- la readiness à partir d'un reçu C2 réellement validé ;
- des scénarios négatifs : mois incomplet, état C2 altéré ou ancien, reçu mensuel existant et reçu corrompu ;
- les identifiants corses avant éligibilité et le garde-fou BdR de production ;
- des tests unitaires de la rétro-propagation BdR : limite de 7 jours, priorité à C2, exigence de vérification et refus en présence d'une enseigne/catégorie contradictoire ;
- pour août 2026, l'application exacte à `13120012` du 25 au 30 août et l'absence de modification des agrégats Corse/BdR avant/après ;
- l'unicité des 38 lignes EPCI/carburant, les types et cohérences numériques ;
- les **19 EPCI × 2 carburants sur desktop et mobile** dans un vrai Chrome ;
- les cas hors classement, la comparaison entre territoires, le calculateur, les cibles tactiles et l'absence de débordement horizontal de page ;
- l'écriture unique du reçu final de test et le refus d'un second écrasement.

## 11. GitHub Pages et WordPress

Le dépôt C2 est servi par GitHub Pages. En conséquence, **le widget et les fichiers `outputs/monthly-*` ne doivent pas être fusionnés dans `main` tant que leur exposition publique n'a pas été décidée explicitement**. Le fait qu'une page ne soit pas liée depuis `index.html` ne suffit pas à la rendre privée.

Aucun code de création, modification ou publication WordPress ne fait partie de cette chaîne. L'intégration WordPress reste une étape distincte, soumise à autorisation explicite.

## 12. Sécurité de fusion

Le développement reste sur `add-corse-station-geography-2026`. Une éventuelle intégration future doit partir du **`main` courant** et ajouter les fichiers retenus ; elle ne doit jamais remplacer l'arbre de `main` par celui de cette branche historiquement en retard.

Avant toute fusion, un nouvel audit doit contrôler le diff réellement destiné à `main`, l'effet Pages, les workflows déclenchables et l'absence de writer C2 actif au moment de l'opération.

# Architecture d'automatisation A4C — phase 1

Cette branche ne modifie pas encore le rendu public. Elle construit d'abord un moteur vérifiable et un candidat append-only.

## Principe de mutualisation

Le téléchargement et le parsing des archives officielles sont placés dans `a4c_common/official_prices.py`. Le résultat commun conserve les déclarations station / carburant / date et ne contient **aucune règle propre à un observatoire**.

La chaîne visée est :

```text
prix-carburants.gouv.fr
        ↓ téléchargement unique
archive(s) ZIP officielle(s)
        ↓ parsing / normalisation communs
snapshot A4C commun (station, date, carburant, prix, métadonnées)
        ├── profil carburantscorse1 : règle de validité 45 j, 12 régions, moy_regions
        └── profil carburantscorse2 : Corse / BDR, publication append-only, UFIP, marge
```

Le module commun vit provisoirement dans `carburantscorse2` pour la phase de régression. Il est écrit comme un paquet indépendant afin de pouvoir être extrait ensuite dans un dépôt technique A4C ou consommé par `carburantscorse1` sans réécriture.

## Ce qui est commun

- URL et téléchargement des ZIP annuels officiels ;
- validation ZIP/XML ;
- lecture des stations et des déclarations ;
- dernière déclaration d'une journée pour station + carburant ;
- conservation du type `pop`/autoroute ;
- conservation du prix brut ;
- simple indicateur de bande 1,10–3,00 €/L.

## Ce qui reste spécifique

`carburantscorse1` et `carburantscorse2` ne doivent pas partager silencieusement leurs règles de forward-fill et d'exclusion. Le moteur commun s'arrête donc avant ces décisions.

Pour `carburantscorse2`, deux profils sont maintenant séparés :

- `method.py` : profil de recherche prudent récupéré dans la reconstruction du 14 juin 2026 ;
- `publication.py` : profil qui reproduit le dashboard effectivement publié et qui sert à sa continuité.

Le stock annuel gouvernemental est susceptible d'intégrer des corrections rétroactives. Le dashboard est donc actualisé en **append-only** : les dates déjà publiées restent figées et le stock courant ne sert qu'à calculer les dates nouvelles. La justification et la régression sont documentées dans `docs/publication-regression.md`.

## Classification BDR

La vue « réseau traditionnel » nécessite une classification station par station. Le registre publié est conservé dans `config/bdr_categories_published_2026-06-06.csv`. Toute station BDR récente absente de ce registre est signalée et bloque le candidat afin d'éviter une exclusion silencieuse de la moyenne réseau.

## UFIP

Le téléchargement personnalisé UFIP a été audité le 18 août 2026. Un navigateur n'est pas nécessaire : GET du formulaire pour récupérer `ufp_token` + cookie de session, puis POST de `day_from`, `day_to` et `cotations[gazole]=on`. Le serveur renvoie un XLSX à deux colonnes : Date / GAZOLE (Rotterdam) (€ / litre).

`a4c_common/ufip.py` encapsule ce mécanisme et produit également une série journalière où les jours sans cotation sont forward-fill depuis la dernière valeur publiée, sans backfill avant la première observation.

## Validation de branche

À chaque modification de la PR :

1. tests unitaires ;
2. compilation des modules ;
3. téléchargement des sources courantes ;
4. construction du candidat append-only jusqu'à la veille ;
5. ajout des seules semaines complètes ;
6. récupération UFIP pour la marge ;
7. contrôle des stations BDR non classées ;
8. dépôt du candidat et du résumé d'audit comme artefact GitHub Actions.

Aucun de ces contrôles n'écrit dans `main`.

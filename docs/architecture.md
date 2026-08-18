# Architecture d'automatisation A4C — phase 1

Cette branche ne modifie pas encore le rendu public. Elle construit d'abord un moteur vérifiable.

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
        └── profil carburantscorse2 : Corse / BDR, règles de fiabilité, segments, UFIP, marge
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

## UFIP

Le téléchargement personnalisé UFIP a été audité le 18 août 2026. Un navigateur n'est pas nécessaire : GET du formulaire pour récupérer `ufp_token` + cookie de session, puis POST de `day_from`, `day_to` et `cotations[gazole]=on`. Le serveur renvoie un XLSX à deux colonnes : Date / GAZOLE (Rotterdam) (€ / litre).

`a4c_common/ufip.py` encapsule ce mécanisme et produit également une série journalière où les jours sans cotation sont forward-fill depuis la dernière valeur publiée, sans backfill avant la première observation.

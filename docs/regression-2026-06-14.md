# Régression du moteur `carburantscorse2` — référence du 14 juin 2026

Avant toute modification du site public, le nouveau moteur a été confronté à la source historique brute conservée dans l'archive A4C (`prix_corse_bdr_origine.csv`, 441 935 relevés).

Le test ne compare pas seulement quelques moyennes : il reconstruit les relevés journaliers dédupliqués, tout le panel station × carburant × jour, puis les trois indicateurs de fiabilité du pipeline récupéré (`prix_aberrant`, `gap_suspect`, `station_inactive`).

## Résultat

Tous les compteurs historiques sont reproduits **exactement** :

| Indicateur | Référence | Nouveau moteur |
|---|---:|---:|
| Relevés source | 441 935 | 441 935 |
| Relevés dédupliqués par jour | 408 662 | 408 662 |
| Lignes journalières reconstruites | 1 420 478 | 1 420 478 |
| Relevés aberrants | 38 | 38 |
| Lignes portant un prix aberrant | 88 | 88 |
| Lignes `gap_suspect` | 205 921 | 205 921 |
| Lignes `station_inactive` | 144 096 | 144 096 |
| Lignes fiables pour moyennes | 1 214 469 | 1 214 469 |

La répartition par territoire et carburant est également identique, notamment 389 182 lignes BdR E10, 442 789 BdR Gazole, 158 526 BdR SP95, 214 986 Corse Gazole et 214 995 Corse SP95.

Cette régression valide la **reproduction technique du pipeline exécutable récupéré le 14 juin 2026**. Elle ne tranche pas encore la divergence documentaire avec `METHODOLOGIE (1).md` (seuils 30/150 jours et formulation sur les corrections). Cette divergence reste explicitement bloquante avant de modifier la présentation publique : la prochaine régression porte sur les séries d'écarts réellement embarquées dans l'observatoire.

Le gros CSV historique n'est volontairement pas versionné dans Git. Le script `scripts/regression_recovered_snapshot.py` permet de rejouer le contrôle localement lorsqu'il est extrait de l'archive source.

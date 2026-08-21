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

## Calibration Rotterdam C2 — préparée, inactive
Le calibrage est **spécifique à C2**. Il ne doit pas être utilisé pour C1 pour isoler des Total continentales : C1 ne dispose pas du rattachement d'enseigne nécessaire pour ce test.

La source unique est le fichier produit par l'automatisation UFIP :
- `scripts/fetch_ufip.py` télécharge la cotation Rotterdam Gazole ;
- `outputs/ufip/rotterdam_gazole_observed.csv` contient uniquement les cotations réellement observées ;
- `outputs/ufip/rotterdam_gazole_daily.csv` contient la série calendaire avec report des jours sans cotation.

Le module `carburantscorse2/rotterdam_calibration_v2.py` **ne télécharge rien lui-même** : il lit ces fichiers.

### R1
À l'entrée effective dans la phase de plafond, `R1` est la moyenne des trois dernières cotations Rotterdam Gazole réellement observées avant la date d'entrée. Les valeurs reportées des week-ends/jours fériés ne comptent pas plusieurs fois.

Pour l'épisode entrant le 8 avril 2026 : 3 avril 1,037 ; 6 avril 1,048 ; 7 avril 1,061 EUR/L, soit `R1 ≈ 1,048667 EUR/L`.

### R2 et k par territoire
`R2 = k × R1`, avec un `k` distinct par territoire dans C2.

Calibration candidate 2026, non activée :
- Corse : observations de sortie 29 mai, 1er juin, 2 juin ; `k_corse ≈ 0,733`.
- BdR : uniquement `TOTAL_CLASSIQUE`, observations 20, 21, 22 mai ; `k_bdr ≈ 0,824`.

Ces coefficients sont recomputables depuis le CSV UFIP observé ; ils ne remplacent pas la source. En cas de fichier UFIP manquant, de date de calibration absente ou de valeur invalide, l'exception doit échouer fermée.

## Procédure après lundi
1. Contrôler la publication habituelle C1 puis C2.
2. Figer le snapshot publié comme référence.
3. Brancher le moteur préparé uniquement dans un calcul candidat.
4. Comparer actuel / 45-45 prospectif / 45-45 rétroactif.
5. Mesurer jours modifiés, stations gagnées/perdues, moyennes, écarts Corse-BdR et épisodes de bouclier.
6. Décider explicitement de la migration ; pas de réécriture silencieuse de l'historique.

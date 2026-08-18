# Point méthodologique à résoudre avant publication

Deux documents du dossier historique ne décrivent pas exactement la même version de la méthode.

## Référence exécutable récupérée le 14 juin 2026

Le script `nettoyer_series_originaux.py` et son `resume_nettoyage.json` utilisent :

- prix aberrant : < 1,10 €/L ou > 3,00 €/L, sans correction automatique ;
- BDR Gazole/E10 : `gap_suspect` après 30 jours ;
- BDR SP95 : après 21 jours ;
- Corse : après 90 jours ;
- `station_inactive` : BDR après 60 jours, Corse après 180 jours ;
- les moyennes fiables excluent prix aberrant, gap suspect et station inactive ;
- les remises sont documentées comme contexte et ne modifient pas le prix observé.

C'est ce profil qui est codé dans `carburantscorse2/method.py` parce qu'il est intégralement reproductible à partir des scripts sauvegardés.

## Document `METHODOLOGIE (1).md`

Le document de présentation indique quant à lui :

- BDR : 30 jours ; Corse : 150 jours ;
- correction manuelle de quelques valeurs aberrantes ;
- réintégration des remises gouvernementales 2022 dans un `prix_marche`.

Ces différences ne seront pas arbitrées par supposition. Avant toute modification de `main`, la nouvelle chaîne devra être comparée à l'historique embarqué dans le dashboard actuel et aux sorties sauvegardées. Le profil qui reproduit effectivement la série publiée sera documenté comme profil de publication ; toute évolution méthodologique ultérieure sera versionnée explicitement.

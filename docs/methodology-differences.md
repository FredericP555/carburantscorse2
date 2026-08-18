# Profils méthodologiques : recherche vs publication

Deux versions de la méthode ont été retrouvées dans le dossier historique. Elles ne doivent pas être mélangées silencieusement.

## 1. Référence de recherche reconstruite le 14 juin 2026

Le script `nettoyer_series_originaux.py` et son `resume_nettoyage.json` utilisent :

- prix aberrant : < 1,10 €/L ou > 3,00 €/L, sans correction automatique ;
- BDR Gazole/E10 : `gap_suspect` après 30 jours ;
- BDR SP95 : après 21 jours ;
- Corse : après 90 jours ;
- `station_inactive` : BDR après 60 jours, Corse après 180 jours ;
- les moyennes fiables excluent prix aberrant, gap suspect et station inactive ;
- les remises sont documentées comme contexte et ne modifient pas le prix observé.

Ce profil reste codé dans `carburantscorse2/method.py`. Il est utile pour les analyses de recherche et il reproduit exactement les compteurs de la reconstruction sauvegardée le 14 juin 2026.

## 2. Profil effectivement publié dans le dashboard actuel

La comparaison avec `files(1).zip` et avec les séries embarquées dans `index.html` montre que le dashboard actuel repose sur l'ancien profil de publication.

Pour la période courante 2026, ce profil est désormais reproduit de manière déterministe dans `carburantscorse2/publication.py` :

- dernier relevé station + carburant + jour conservé ;
- forward-fill journalier ;
- seuil de gap : BDR 30 jours, Corse 150 jours ;
- lorsqu'un gap *borné par deux relevés* dépasse le seuil, tous les jours reportés à l'intérieur de ce gap sont exclus ;
- après le dernier relevé, une station devient inactive après le même seuil (30 jours BDR, 150 jours Corse) ;
- prix HT d'une station-jour arrondi à 4 décimales avant calcul des moyennes ;
- minimum 5 stations Corse et 10 stations BDR ;
- hebdomadaire = moyenne de toutes les lignes station-jour du lundi au dimanche, et non moyenne des écarts journaliers ;
- pour la vue « réseau traditionnel », la catégorie BDR est reprise du registre qui a servi au dashboard publié.

Avec ces règles, les six séries de prix 2026 du dashboard (Gazole/SP95, BDR toutes stations/réseau, et référence E10) sont reproduites exactement au centième sur la période contrôlée jusqu'au 6 juin 2026. La CI contient désormais un contrôle réseau contre les données réellement embarquées dans `index.html`.

## 3. Particularités historiques 2022

Le premier fichier de publication contient aussi :

- quelques corrections manuelles d'erreurs de saisie ;
- des colonnes `prix_marche_*` intégrant la neutralisation de remises 2022, y compris des remises dépendant de l'enseigne.

Ces traitements ne sont pas devinés par l'automatisation. L'historique déjà publié reste donc figé. Le profil `publication.py` sert à prolonger exactement la période courante, où ces remises 2022 n'interviennent plus. Une éventuelle réécriture complète de l'historique avec la méthode de recherche du 14 juin constituerait une évolution méthodologique distincte et devrait être décidée et versionnée explicitement.

## 4. Règle de production retenue pour la suite

- `method.py` = profil de recherche prudent, conservé pour les analyses et comparaisons méthodologiques ;
- `publication.py` = profil de continuité du dashboard, utilisé pour l'actualisation automatique ;
- aucune modification de `main` tant que la régression prix + marge et la génération du nouveau fichier de données ne sont pas validées.

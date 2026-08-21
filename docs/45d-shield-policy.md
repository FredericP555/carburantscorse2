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

## Point restant volontairement non paramétré
`config/reliability_policy_v2.json` laisse `rotterdam_threshold` à `null`. La branche échoue donc fermée sur cette exception tant que le seuil Rotterdam n'a pas été calibré et validé.

## Procédure après lundi
1. Contrôler la publication habituelle C1 puis C2.
2. Figer le snapshot publié comme référence.
3. Brancher le moteur préparé uniquement dans un calcul candidat.
4. Comparer actuel / 45-45 prospectif / 45-45 rétroactif.
5. Mesurer jours modifiés, stations gagnées/perdues, moyennes, écarts Corse-BdR et épisodes de bouclier.
6. Décider explicitement de la migration ; pas de réécriture silencieuse de l'historique.

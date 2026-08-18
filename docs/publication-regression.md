# Régression du profil publié et règle append-only

## Résultat de la régression sur le snapshot historique

Le dashboard actuel embarque les séries issues de l'ancien fichier de publication (`files(1).zip`). La comparaison avec ce snapshot a permis de reconstituer le profil effectivement publié.

Sur les données source sauvegardées au moment de la reconstruction de juin 2026, le profil `carburantscorse2/publication.py` reproduit exactement au centième, du 1er janvier au 6 juin 2026 :

- Gazole Corse vs toutes BDR, journalier et hebdomadaire ;
- Gazole Corse vs réseau traditionnel BDR, journalier et hebdomadaire ;
- SP95 Corse vs SP95 toutes BDR, journalier et hebdomadaire ;
- SP95 Corse vs SP95 réseau traditionnel BDR, journalier et hebdomadaire ;
- SP95 Corse vs E10 toutes BDR, journalier et hebdomadaire ;
- SP95 Corse vs E10 réseau traditionnel BDR, journalier et hebdomadaire.

Le fichier `MARGES_GZ` embarqué dans `index.html` est par ailleurs identique à `marges_gazole_hebdo.json` du snapshot historique. Sur 2025-2026, les niveaux de marge publiés sont cohérents au centième avec la formule prix HT hebdomadaire - accise - cotation Rotterdam hebdomadaire ; l'écart de marge bénéficie du même benchmark Rotterdam des deux côtés.

## Pourquoi on ne recalcule pas l'historique depuis le ZIP annuel actuel

Le contrôle GitHub Actions du 18 août 2026 a téléchargé à nouveau les stocks annuels officiels 2025 et 2026, puis recalculé janvier-juin 2026. Le stock courant ne reproduit plus exactement le snapshot de juin : des déclarations/corrections rétrospectives ont été intégrées depuis.

Exemple détecté sur Gazole / toutes BDR : le 6 mars 2026, le recalcul avec le stock annuel téléchargé le 18 août donne +5,33 c€/L, alors que le dashboard publié contient +5,35 c€/L. Le contrôle a trouvé 91 jours différents sur les 157 jours comparés, souvent de quelques centièmes mais avec une dérive réelle.

Ce résultat ne remet pas en cause le profil de calcul : le même profil reproduit exactement le snapshot historique. Il montre que **le fichier annuel officiel est une source vivante susceptible d'être corrigée rétroactivement**.

## Règle de production retenue

L'actualisation de `carburantscorse2` est donc strictement append-only :

1. toute date déjà publiée est immuable ;
2. le stock annuel officiel courant sert à calculer uniquement les nouvelles dates ;
3. les nouvelles séries commencent après le dernier jour / la dernière semaine déjà embarqués ;
4. une station BDR nouvelle ou non classée bloque la vue réseau traditionnel jusqu'à classification explicite ;
5. les semaines sont ajoutées seulement lorsqu'elles sont complètes (lundi-dimanche) ;
6. UFIP est téléchargé pour les nouvelles semaines de marge, avec report de la dernière cotation sur les jours sans valeur.

Le script `scripts/build_append_candidate.py` applique cette règle et produit un candidat + un résumé d'audit. Le workflow de validation publie ces deux fichiers comme artefact sans modifier `main`.

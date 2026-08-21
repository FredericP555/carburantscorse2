# Politique préparée — seuil 45 jours et bouclier

> **PRÉPARÉE, NON ACTIVÉE.** `publication.py` continue d'utiliser la méthode actuelle. Rien de cette politique n'est actif dans `main` avant décision explicite après la mise à jour du lundi.

## 1. Règle normale

- 45 jours par station × carburant.
- J0 à J+44 inclus ; J+45 sort de la règle normale sans nouvelle déclaration.
- Une redéclaration au même prix remet le compteur à zéro.
- Rupture, fermeture/inactivité indépendante, prix invalide/non fini ou date future : exclusion prioritaire.

## 2. Bouclier effectif et R2

Le statut **bouclier effectif** est indépendant de R2. R2 ne démarre ni ne termine jamais le bouclier.

R2 sert uniquement à décider si un vieux prix Gazole/SP95 peut encore être retenu dans le cas du double plafond.

## 3. Un seul carburant principal au plafond

### Corse

Après J+44, une déclaration récente de **l'autre carburant principal** peut renouveler une fenêtre glissante de 45 jours. E10 ne prouve pas la vivacité en Corse.

### Bouches-du-Rhône

Après J+44, une déclaration récente de **n'importe quel autre carburant** peut renouveler une fenêtre glissante de 45 jours. Il n'existe aucun J+90 absolu dans C2/BdR.

## 4. Double plafond Gazole + SP95

### Corse

La vivacité croisée Gazole/SP95 ne suffit plus. Le vieux prix est contrôlé par Rotterdam et le R2 de la phase courante.

### Bouches-du-Rhône

Deux conditions sont nécessaires : vivacité récente sur un carburant autre que Gazole/SP95 **et** absence de verrou R2.

Dans les deux territoires, après expiration normale du carburant cible, un premier passage de Rotterdam sous le R2 applicable verrouille ce vieux prix jusqu'à une nouvelle déclaration du carburant cible, même si Rotterdam remonte ensuite.

### R1/R2 recalculés à chaque nouvelle phase effective

Les cotations des **3, 6 et 7 avril 2026** servent uniquement à calibrer les coefficients historiques : `k_corse ≈ 0,733` et `k_bdr ≈ 0,824`. Elles ne définissent pas R1 pour toujours.

Pour toute nouvelle phase de bouclier effectif :

1. prendre les **3 dernières cotations Rotterdam réellement observées avant le début de la phase** ;
2. calculer leur moyenne : `R1_phase` ;
3. conserver le coefficient territorial `k` calibré sur l'épisode de référence 2026 ;
4. calculer `R2_phase = k_territoire × R1_phase`.

Donc si les prix passent sous le plafond, le bouclier cesse d'être effectif, puis les prix reviennent plus tard au plafond et une nouvelle période effective commence, cette nouvelle période reçoit **un nouveau R1 et un nouveau R2**, même si le plafond nominal est identique.

## 5. Phases et non-résurrection

Une phase est une portion continue de bouclier effectif avec un même plafond. Une nouvelle phase commence si :

- le plafond change ;
- le bouclier effectif s'interrompt puis recommence, même au même plafond.

La date de début de phase sert à la fois au garde-fou de non-résurrection et au calcul du nouveau R1/R2.

Un prix déjà périmé à l'entrée de phase n'est jamais ressuscité. Une nouvelle déclaration cible pendant la phase crée un nouveau J0.

## 6. Identité des stations

Trois états : `TOTAL`, `NON_TOTAL_CONFIRMED`, `UNKNOWN`. Un ID `UNKNOWN` n'entre pas dans les calculs sensibles à l'enseigne.

## 7. Source C1 → C2

Architecture préparée : **UFIP → C1 → C2**. C1 publie une release validée contenant snapshot 13/20, métadonnées de bouclier/phases, deux séries Rotterdam et registre Corse. C2 épingle une seule release et ne contacte pas UFIP dans le chemin hebdomadaire normal.

## 8. Garde-fous

- rupture active → exclusion ;
- fermeture / inactivité indépendante → exclusion ;
- prix absent, invalide ou non fini → exclusion ;
- date future → exclusion ;
- prix périmé à l'entrée d'une phase → aucune résurrection ;
- changement de plafond → nouvelle phase et nouvelle vérification.

## 9. Échec fermé

La préparation bloque notamment en cas de release/asset manquant, SHA incohérent, registre invalide, série Rotterdam incomplète, calibration de `k` invalide, moins de trois cotations observées avant une nouvelle phase, ou phase requise absente/invalide.

## Procédure après lundi

1. Contrôler la publication habituelle C1 puis C2.
2. Figer le résultat comme référence.
3. Tester la politique préparée uniquement en candidat.
4. Comparer actuel / prospectif / rétroactif.
5. Mesurer les écarts et stations affectées.
6. Décider explicitement de toute migration.

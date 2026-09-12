# Bilan mensuel territorial A4C — lot d’intégration inerte

Cette branche prépare uniquement le noyau technique destiné à une éventuelle intégration future dans `main`. Elle est créée directement depuis le `main` courant et ne contient aucun mécanisme de publication mensuelle.

## Contenu retenu

Le lot comprend uniquement :

- le registre géographique Corse 2026 ;
- le générateur mensuel fondé sur le moteur C2 V2 ;
- la variante durcie avec rétro-propagation BdR bornée ;
- le contrôle de readiness C2 ;
- les gardes de sources Corse/BdR sur le mois demandé et le mois précédent utilisé pour les variations ;
- le validateur de parité avec les constantes C2 ;
- les audits territoriaux internes ;
- le writer de reçu final, présent mais non activé ;
- les tests unitaires de rétro-propagation BdR ;
- la spécification méthodologique détaillée.

## Éléments volontairement exclus

Ce lot ne contient pas :

- `.github/workflows/monthly-territorial-test.yml` ;
- `scripts/run_monthly_hardening_backfill_test.sh` ;
- `widgets/bilan-territorial/` ;
- `scripts/browser_smoke_monthly_widget.mjs` ;
- `scripts/validate_monthly_widget_contract.py` ;
- aucun fichier `outputs/monthly-*` ;
- aucun audit généré d’août ;
- aucun fichier `outputs/monthly-receipts/YYYY-MM.json` ;
- aucun code WordPress.

Le code retenu peut écrire des fichiers mensuels lorsqu’il est lancé explicitement, mais aucun workflow ajouté par cette branche ne l’exécute. La simple présence de ces scripts dans le dépôt ne déclenche donc ni génération, ni Pages, ni WordPress.

## Règles méthodologiques conservées

Le calcul mensuel doit continuer à utiliser la même release C1 effectivement consommée par C2 et la même logique de fiabilité V2. Les gardes couvrent toute la fenêtre réellement reconstruite : le mois demandé et le mois précédent utilisé pour les évolutions mensuelles.

La rétro-propagation de catégorie BdR reste limitée à sept jours, au même `station_id`, avec une classification future vérifiée et blocage en présence d’une enseigne ou d’une catégorie contradictoire. Elle ne modifie ni les prix ni l’éligibilité.

Le writer de reçu reste fail-closed : mois canonique, justificatifs complets, cohérence C1/C2, cohérence des gardes, identité du dataset contrôlé et refus d’écrasement. Aucun reçu réel n’est créé par ce lot.

## Conditions avant toute fusion

Avant toute fusion vers `main`, il reste obligatoire de :

1. exécuter la suite complète de tests du `main` sur ce lot exact ;
2. auditer le diff exact `main...prepare/monthly-territorial-integration` ;
3. confirmer qu’aucun fichier public mensuel ni workflow de publication n’a été ajouté ;
4. effectuer toute éventuelle fusion hors exécution d’un writer C2.

Aucune activation mensuelle ni publication publique n’est incluse dans cette branche.

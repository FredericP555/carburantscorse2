# Correction ciblée Total — semaine du 26 octobre au 1er novembre 2026

Correction différentielle : valeur publiée + effet du seul passage « au plafond » à « au plafond ou inférieur ». Les deux calculs utilisent les mêmes observations, événements, registres et contrôles R2. Les autres révisions de sources ne sont pas appliquées. Il ne s'agit pas d'une interpolation ou d'un lissage artificiel.

158 observations station-jour sont réintégrées (105 gazole, 53 SP95). Aucune modification d'éligibilité en Bouches-du-Rhône. Les contrôles bouclier, activité, ruptures, fermetures et UFIP/R2 restent actifs.

- C1 : uniquement les 14 prix journaliers corses (TTC et HT), la semaine du 26 octobre, et les mois d'octobre/novembre qui contiennent ces jours. Agrégats recalculés depuis les journées publiées corrigées, avec l'arrondi usuel.
- C2 : les écarts journaliers de ces sept jours et la seule semaine du 26 octobre, les marges gazole correspondantes, et leurs représentations dans homepage-summary.json. Les calculs hebdomadaires conservent la pondération station-jour. Pour les marges, la variation de pondération Rotterdam est incluse ; les valeurs BDR et l'excise sont préservées.
- Tous les points journaliers antérieurs au 26 octobre, les semaines antérieures, les dates, la structure et les métadonnées sources sont conservés.
- Aucun fichier d'automatisation ni moteur de production n'est modifié. Ce script ponctuel n'est appelé par aucun workflow.

## Preuves et reproduction

`source.json` identifie les empreintes du baseline et du replay épinglé (artefact C3 41694981076). `corsica-station-days.csv` conserve les valeurs et décisions comparées. `report.json` liste toutes les différences et les deltas non arrondis. Le retour arrière inverse exactement ces différences.

La branche `backup/before-week-20261026-correction-20261103` conserve l'état publié antérieur. Pour reproduire, extraire son data.json dans un fichier temporaire puis lancer :

```
python scripts/build_week_20261026_transition.py --baseline /tmp/baseline-data.json
```

Pour C2, fournir aussi `--summary-baseline /tmp/baseline-homepage-summary.json`. Le script refuse toute empreinte différente et écrit uniquement des candidats dans ce répertoire. Les fichiers candidate*.json sont des sorties locales non versionnées.

Validation locale : 129 tests C1 et 221 tests C2 réussis ; égalité intégrale du baseline après inversion des changements ; égalité des réintroductions C1/C2 ; génération reproductible ; absence de modification des workflows.

## Publication coordonnée

Ne pas fusionner isolément sans organiser la publication C1 : son certificat de succès exige que data.json corresponde aussi au commit cible de la release partagée. Il faut publier une release cohérente et vérifier Pages, puis C2 et sa synthèse. Les sauvegardes sont créées ; les branches de correction ne changent pas encore la production.

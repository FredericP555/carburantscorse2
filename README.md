# Prix des carburants — Corse vs Bouches-du-Rhône (2022–2026)

Analyse de l'écart de prix hors taxes et de la marge de distribution du carburant entre la Corse et les Bouches-du-Rhône.

## Contenu

La page présente, pour le Gazole et le SP95 :

- **l'écart de prix HT** entre la Corse et les Bouches-du-Rhône, en moyenne journalière ou hebdomadaire ;
- **l'écart de marge de distribution** (Gazole), calculé à partir de la référence Rotterdam partagée par C1 ;
- deux niveaux de comparaison : toutes les stations des Bouches-du-Rhône, ou le seul réseau traditionnel ;
- les périodes du bouclier TotalEnergies effectif transmises par C1 et la remise Total de 2022.

## Sources

- Prix à la pompe : données ouvertes `prix-carburants.gouv.fr`, via la release C1 validée et épinglée par C2.
- Référence Rotterdam Gazole : UFIP / Énergies et Mobilités, **EUR/litre**, source **Thomson-Reuters**, **moyenne mobile sur 5 jours**. C1 effectue le téléchargement unique et publie l'unité, la source, le lissage et les SHA-256 dans le manifeste partagé ; C2 refuse une release qui ne respecte plus ce contrat.
- Décision 25-D-07 de l'Autorité de la concurrence (17 novembre 2025).

## Méthodologie de publication V2

Les déclarations de prix sont reconstruites en état journalier par station. Les valeurs hors de la bande de fiabilité 1,10–3,00 €/L ne sont **jamais corrigées artificiellement** : elles sont exclues jusqu'à une déclaration valide ultérieure. Les règles de fraîcheur, ruptures/fermetures et cas R2 sont appliquées par le moteur V2 avant agrégation.

L'historique déjà publié reste protégé. À partir de l'activation V2, les mises à jour récurrentes sont append-only.

### Enseignes et catégories BdR

Le classement historique par identifiant de station est figé pour les jours publiés jusqu'au **7 septembre 2026**. À partir du **8 septembre 2026**, le registre d'enseignes devient temporel : une nouvelle enseigne/catégorie vérifiée pour le même ID ne s'applique qu'à compter de sa date de vérification. L'ancienne période n'est pas reclassée rétroactivement.

Les IDs nouveaux ou non résolus sont vérifiés en priorité. Les IDs connus sont revérifiés progressivement et de façon bornée afin de détecter les changements d'exploitation sans transformer chaque mise à jour en moissonnage massif des fiches de stations.

### Résumé public

`homepage-summary.json` est une vue aval de `data.json`. Les niveaux de prix, populations et diagnostics peuvent être recalculés depuis la release C1 épinglée, mais **tous les écarts affichés par le résumé sont réconciliés avec les valeurs canoniques de `data.json`**, pas seulement les deux derniers points. Une révision ultérieure de la source est signalée comme réconciliation au lieu de créer silencieusement un désaccord entre le résumé et le graphique historique.

## Marge de distribution Gazole

La marge de distribution correspond au prix HT diminué de l'accise et de la référence Rotterdam en EUR/L.

Pour la période publique 2022–2026, l'accise utilisée est de **0,5940 €/L en Corse** et de **0,6075 €/L dans les Bouches-du-Rhône / PACA** avant 2025 selon le contrat fiscal corrigé C2-01. La réparation C2-01 a modifié uniquement le différentiel fiscal historique concerné ; elle n'a pas reconstruit les séries de prix ni les cotations UFIP.

## Publication et contrôle

C2 épingle une release C1 validée, construit un candidat, vérifie le contrat append-only puis commit ensemble `data.json`, le registre BdR et le résumé public lorsqu'ils changent. Un contrôle métier séparé vérifie ensuite que `data.json` et `homepage-summary.json` réellement servis par GitHub Pages sont ceux attendus et qu'ils correspondent à la même release C1.

## Intégration WordPress

Après publication sur GitHub Pages, la page peut être intégrée dans WordPress avec un bloc HTML personnalisé :

```html
<iframe
  src="https://VOTRE-COMPTE.github.io/VOTRE-REPO/"
  style="width:100%;height:950px;border:0;display:block;"
  loading="lazy"
  title="Écart de prix HT des carburants Corse vs Bouches-du-Rhône">
</iframe>
```

La hauteur de `950px` fonctionne correctement sur smartphone pour la vue par défaut. Sur desktop, une hauteur entre `760px` et `900px` peut suffire selon la place donnée au texte d'analyse.

---

Publié dans le cadre des travaux d'A4C — *Agissons contre la cherté des carburants en Corse*.

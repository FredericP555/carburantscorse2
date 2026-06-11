# Prix des carburants — Corse vs Bouches-du-Rhône (2022–2026)

Analyse de l'écart de prix hors taxes et de la marge de distribution du carburant entre la Corse et les Bouches-du-Rhône, sur la période janvier 2022 – juin 2026.

## Contenu

La page présente, pour le Gazole et le SP95 :

- **L'écart de prix HT** entre la Corse et les Bouches-du-Rhône, en moyenne journalière ou hebdomadaire
- **L'écart de marge de distribution** (Gazole), calculé à partir des cotations Rotterdam de l'UFIP
- Deux niveaux de comparaison : toutes les stations des Bouches-du-Rhône, ou le seul réseau traditionnel (hors grandes surfaces)
- Les périodes d'activation du bouclier tarifaire TotalEnergies et de la remise Total de 2022

## Sources

- Prix à la pompe : données ouvertes du gouvernement français (prix-carburants.gouv.fr)
- Cotations de gros : Union Française des Industries Pétrolières (UFIP)
- Décision 25-D-07 de l'Autorité de la concurrence (17 novembre 2025)

## Méthodologie

Les prix sont reconstruits en série journalière continue par station, avec correction des valeurs aberrantes et neutralisation des remises selon l'enseigne. La marge de distribution correspond au prix hors taxes diminué de l'accise (variable selon la zone et la période) et de la cotation Rotterdam.

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

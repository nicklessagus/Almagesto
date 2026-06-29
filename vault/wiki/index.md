# Índice de la bóveda

Catálogo de la wiki. Se actualiza en cada operación (ingest / query archivada). Bóveda vacía:
ingestá tu primera estrella o tema para poblarla.

## Estrellas
```dataview
TABLE spectral_type AS "Tipo", P_rot_days AS "P_rot (d)", length(planets) AS "Planetas"
FROM "wiki/stars"
SORT file.name ASC
```

## Conceptos (indicadores · métodos · actividad · hipótesis)
```dataview
TABLE status, confidence
FROM "wiki/concepts"
SORT file.folder ASC, file.name ASC
```

## Papers
```dataview
TABLE WITHOUT ID file.link AS "Paper", year AS "Año", relevance AS "Rel."
FROM "wiki/papers"
SORT citation_count DESC
LIMIT 50
```

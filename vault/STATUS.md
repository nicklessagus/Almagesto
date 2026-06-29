# Estado de la bóveda

Punto de entrada: dónde está el proyecto y qué sigue. Vive en el repo (sincroniza entre máquinas).
Para *cómo* operar ver `CLAUDE.md`; para el historial ver `wiki/log.md`; catálogo en `wiki/index.md`.

## Estado actual

- Bóveda **recién instanciada** desde el template **Almagesto** (patrón LLM Wiki).
- **Objetivo:** ver `config/objective.yaml` ← **editar este archivo primero** (define de qué trata la
  bóveda y qué papers son "core").
- Sin estrellas/temas ingestados todavía.

## Próximos pasos

1. Editar `config/objective.yaml` con tu objetivo y tu clasificador de relevancia (`relevance.topics`).
2. Poner el token ADS en `config/ads_dev_key` (o `ADS_DEV_KEY`).
3. Agregar tu primera estrella a `config/stars.yaml` (o tema a `config/topics.yaml`) y correr
   `ingest-star` / `ingest-topic`.

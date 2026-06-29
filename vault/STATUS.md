# Estado de la bóveda

Punto de entrada: dónde está el proyecto y qué sigue. Vive en el repo (sincroniza entre máquinas).
Para *cómo* operar ver `CLAUDE.md`; para el historial ver `vault/wiki/log.md`; catálogo en `vault/wiki/index.md`.

## Estado actual

- Bóveda **recién instanciada** desde el template **Almagesto** (patrón LLM Wiki).
- **Objetivo:** ver `vault/config/objective.yaml` ← **editar este archivo primero** (define de qué trata la
  bóveda y qué papers son "core").
- Sin estrellas/temas ingestados todavía.

## Próximos pasos

1. Editar `vault/config/objective.yaml` con tu objetivo y tu clasificador de relevancia (`relevance.topics`).
2. Poner el token ADS en `vault/config/ads_dev_key` (o `ADS_DEV_KEY`).
3. Agregar tu primera estrella a `vault/config/stars.yaml` (o tema a `vault/config/topics.yaml`) y correr
   `ingest-star` / `ingest-topic`.

## Backlog de framework — validación de áreas de `vault/wiki/concepts/` + config a mano

> Rescatado del scratch `DESIGN-NOTES.md` (discusión 2026-06-27) al borrarlo el 2026-06-28. El escape
> **off-ADS** de esa nota **ya se implementó** (commit `a005257`); lo que sigue **no**. Son cambios de
> **framework** → aplicar en el template, no en una instancia (Regla de oro, ver `CLAUDE.md`).

**Problema raíz.** El set de áreas `vault/wiki/concepts/{indicators, methods, activity, hypotheses}` es **folklore,
no contrato**: no existe como dato declarado; está implícito y repartido en 5 lugares (`CLAUDE.md`,
`README.md`, `ingest-topic/SKILL.md`, comentario de `vault/config/topics.yaml`, y las carpetas reales).
`make_notes.py` hace `dest.parent.mkdir(...)` con el `area` que venga **sin validar** → un typo
(`indicator`, `metods`) crea una **carpeta fantasma en silencio**. Las áreas son **abiertas** (no un set
cerrado de 4): sólo `hypotheses` (estructural: schema `name,status` + roll-up Dataview) y `methods`
(universal) son fijas; el resto depende del foco de la instancia.

**Tres mejoras — son CAPAS, no alternativas.** Orden recomendado: **1 → 2 → 3** (el skill sin la
nomenclatura no tiene a qué adaptarse; el check sin la nomenclatura no tiene contra qué chequear).

1. **Bajar la nomenclatura de áreas a config** (cimiento). Declararla en **un solo lugar** (candidato:
   `vault/config/objective.yaml`, p. ej. `concept_areas: [...]`), reservando `hypotheses`/`methods`, resto abierto.
2. **Skill de setup interactivo** (mayor impacto UX). El agente pregunta el foco y genera
   `vault/config/objective.yaml` + `stars`/`topics` + áreas en la nomenclatura oficial. Valor en las 2 partes
   difíciles: redactar `relevance.topics` (regex) y nombrar los buckets. **Riesgo:** respetar la
   frontera dura — adapta el foco, no toca el sustrato astro ni inventa nada no-citable.
3. **Check de config (lint, versión blanda WARN)** — red de seguridad para ediciones a mano / entre
   máquinas. Guardrail **blando** (un typo y un área nueva se ven igual → whitelist cerrado descartado):
   WARN contra las carpetas existentes en `vault/wiki/concepts/`, no bloqueo. Además: guards amigables para los
   índices duros que hoy tiran `KeyError` crudo (`ads_object`/`simbad` en stars, `query`/`concept` en
   topics) y WARN si `objective.name` sigue siendo el default (olvido de instanciar).

**Preguntas abiertas (resolver al retomar):**
- ¿La nomenclatura vive en `vault/config/objective.yaml` (instance-owned) o en el framework (`CLAUDE.md`/lib)? Tira
  para `vault/config/objective.yaml` (ya es "lo específico de cada instancia"), pero mantener consistencia con la
  prosa del schema en `CLAUDE.md`.
- ¿`methods` se reserva igual que `hypotheses`, o se trata como área normal (universal pero no especial)?
- ¿El check vive en `lint.py` (encaja con su filosofía WARN/backlog) o en un `validate_config.py` aparte?
- ¿El skill de setup reemplaza el flujo "editá `vault/config/objective.yaml`" del `README` o lo complementa?

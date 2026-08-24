# Estado de la bóveda

Punto de entrada: dónde está el proyecto y qué sigue. Vive en el repo (sincroniza entre máquinas).
Para *cómo* operar ver `CLAUDE.md`; para el historial ver `vault/wiki/log.md`; catálogo en `vault/wiki/index.md`.

> **Este archivo es de la INSTANCIA, no del framework.** Acá viene como semilla: lo que ves es lo
> que un clon nuevo encuentra. Está protegido por `merge=ours` en `.gitattributes`, así que traer
> mejoras del template (`git merge upstream/main`) **nunca lo pisa** — tu estado es tuyo.
>
> El historial de desarrollo del framework **no vive acá**: está en los mensajes de commit y en las
> notas de cada tag. Este archivo es para el estado de **tu** bóveda.

## Estado actual

- Bóveda **recién instanciada** desde el template **Almagesto** (patrón LLM Wiki).
- **Objetivo:** ver `vault/config/objective.yaml` ← **editar este archivo primero** (define de qué
  trata la bóveda y qué papers son "core").
- Sin estrellas ni temas ingestados todavía.

## Próximos pasos

1. Definir el objetivo con el skill `setup` (se lo pedís al agente en palabras; genera/afina
   `vault/config/objective.yaml` con su `relevance.facets` — editable a mano si preferís).
2. Poner el token ADS en `vault/config/ads_dev_key` (o la variable `ADS_DEV_KEY`).
   Token gratis en <https://ui.adsabs.harvard.edu/user/settings/token>.
3. Agregar tu primera estrella a `vault/config/stars.yaml` (o un tema a `vault/config/themes.yaml`)
   y correr el skill `ingest-star` / `ingest-theme`.

## Cómo usar este archivo

Cada operación que cambia el estado de la bóveda lo actualiza acá (lo hace el agente; ver
`CLAUDE.md`). Lo que conviene que viva en este archivo:

- **qué hay ingestado** y qué falta;
- **qué quedó a medias** y por dónde retomar;
- **decisiones abiertas** que dependen de vos (qué lente usar, si un candidato dudoso entra);
- **pendientes declarados**: lo que se sabe que falta y no se olvidó.

La regla que hace útil todo esto: **lo que no se pudo medir se declara, no se omite.** Un pendiente
escrito es deuda; un pendiente que nadie anotó es una sorpresa.

# Log de operaciones (append-only)

Registro cronológico de cada operación sobre la bóveda (ingest / query / verify / lint). Append al
final; no reescribir entradas pasadas. **Formato de entrada** (greppable por fecha):
`## AAAA-MM-DD — <op>: <título corto>` + bullets (qué se tocó, decisiones, pendientes).

---

- **Instanciada** desde el template **Almagesto** (patrón LLM Wiki). Pendiente: definir el objetivo
  (skill `setup`), poner token ADS, primer ingest. *(La primera entrada fechada la escribe el agente
  en la primera operación.)*

## 2026-08-24 — framework: tandas 0 a 6 del plan de implementación (v1.24.0 → v1.30.0)

- **Tanda 0** (1.24.0): `check_retractions` exit 0/1/2; `cfg.write_text_atomic`/`write_bytes_atomic`
  como único writer; categoría `⛔ No evaluado` del lint; umbral de legibilidad **medido** sobre los
  672 fulltexts reales (0 ilegibles; el margen fino es el del ratio y son glifos de figura, no
  mojibake).
- **Tanda 1** (1.25.0): **el ancla** — hash del bloque markdown + hash de la fuente por par
  (afirmación, cita); `lint.py --cierre` para las dos severidades.
- **Tanda 2** (1.26.0): `busquedas` acumulativo (unión, no suma), `cadena` con `via` y flags,
  `--no-triage` eliminado, descarte revertido → **anulado explícito**, `extra_core` estructurado.
- **Tanda 3** (1.27.0): `## Papers` **estampada** con estado por paper; las tres fechas separadas;
  recorte de lectura declarado.
- **Tanda 4** (1.28.0): autoridad por campo del ground-truth (`spectral_type` ← SIMBAD, resto ←
  NEA, sin fallback) y **la procedencia en la cabecera de cada ficha** (pedido del usuario).
- **Tanda 5** (1.29.0): identidad por `doi`/`arxiv_id`, `--rename-paper`, reuso de PDFs y fulltext
  entre slugs.
- **Tanda 6** (1.30.0): `sweep_external.py`, la pasada de red unificada; marca `⛔retractada`.
- **Renombre R-5**: `topics` → `facets` (faceta) / `themes` (tema-sujeto). El comando pasa a ser
  `/ingest-theme`. Destapó un bug real de la Tanda 3 (la pertenencia de un paper a un tema se
  buscaba en las facetas).
- **Pendiente declarado**: `sweep_web` no implementado — levanta y la pasada sale 2 a propósito.
- **Próximo**: la pasada retroactiva de marcado `@inv` (77 de 91 invariantes sin trazar), después
  Tanda 7. Ver `vault/STATUS.md`, sección *DÓNDE RETOMAR*.

## 2026-08-24 — framework: auditoría doble del contrato, marcado retroactivo y cinco fixes

- **Método**: dos pasadas **ciegas e independientes** sobre `contrato.md` §3 (el criterio de §7,
  "su valor está en la ceguera"), cruzadas después. Acordaron en 13 de 16 filas de §3.K; las tres
  discrepancias se adjudicaron **corriendo el código**.
- **Cinco defectos vivos**, tres de ellos tapados por un test que pasaba: el falso positivo
  permanente de `cadena_cortada` (`check_retractions` no se estampaba), el traceback del lint ante
  un `stars.yaml` roto, el match por prefijo de catálogo de `subject_in_title` (`GJ 71` ↔ `GJ 710`,
  en la auto-aceptación de nivel 0), el reporte no determinista que el golden neutralizaba, y un
  `assert` sobre un generador (siempre verdadero).
- **Deuda de R-5**: `.gitattributes` protegía `topics.yaml` (inexistente) y dejaba `themes.yaml`
  sin `merge=ours` — el próximo merge del upstream le pisaba el registro de temas a la instancia.
  Más el detector bloqueante que faltaba para el campo viejo (medido: 908/908 notas de la instancia
  lo traen).
- **Contrato**: §3.K de 16 HUECO → 9 medidos, 5 parciales, 2 HUECO; nueve filas de A–J declaraban
  deuda ya saldada y dos afirmaban garantías inexistentes. Estado nuevo `parcial`.
- **Marcado `@inv`: 77 → 7** (67 tests + 51 símbolos; los 7 restantes son huecos reales, listados
  uno por uno en el ratchet). El mayor: **INV-19**, no existe borrado/renombre de entidad.
- **R-9 medida** sobre el corpus real: se consultan **ADS y OpenAlex**, techo declarado 83%.
- **Abierto**: tier 2 (gate del deploy) roto desde la Tanda 2 — no da señal hasta que se despliegue.

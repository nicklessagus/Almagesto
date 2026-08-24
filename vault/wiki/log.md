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

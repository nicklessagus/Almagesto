# Log de operaciones (append-only)

Registro cronológico de cada operación sobre la bóveda (ingest / query / verify / lint). Append al
final; no reescribir entradas pasadas. **Formato de entrada** (greppable por fecha):
`## AAAA-MM-DD — <op>: <título corto>` + bullets (qué se tocó, decisiones, pendientes).

> **Este archivo es de la INSTANCIA, no del framework.** Acá viene vacío: es el diario de **tu**
> bóveda. Está protegido por `merge=ours` en `.gitattributes`, así que traer mejoras del template
> nunca lo pisa. El historial de desarrollo del framework vive en los mensajes de commit y en las
> notas de cada tag, no acá.

Por qué existe: la bóveda afirma cosas sobre el mundo y el mundo cambia. Saber **cuándo** se ingestó
algo, con qué lente se filtró y qué quedó pendiente es lo que permite volver seis meses después y
entender el estado sin re-derivarlo. Un descarte sin fecha ni motivo es indistinguible de un olvido.

---

- **Instanciada** desde el template **Almagesto** (patrón LLM Wiki). Pendiente: definir el objetivo
  (skill `setup`), poner el token ADS, primer ingest. *(La primera entrada fechada la escribe el
  agente en la primera operación.)*

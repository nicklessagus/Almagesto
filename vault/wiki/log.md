# Log de operaciones (append-only)

Registro cronológico de cada operación sobre la bóveda (ingest / query / verify / lint). Append al
final; no reescribir entradas pasadas. **Formato de entrada** (greppable por fecha):
`## AAAA-MM-DD — <op>: <título corto>` + bullets (qué se tocó, decisiones, pendientes).

---

- **Instanciada** desde el template **Almagesto** (patrón LLM Wiki). Pendiente: definir el objetivo
  (skill `setup`), poner token ADS, primer ingest. *(La primera entrada fechada la escribe el agente
  en la primera operación.)*

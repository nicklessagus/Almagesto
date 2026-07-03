---
tags: [matrix]
generator: Almagesto v0.1.0
---

# Matriz método × estrella

> Qué método se aplicó a qué estrella **en la literatura**. Celda = `[[bibcode]]` del paper que lo
> aplica (puede haber más de uno; el más representativo primero); `—` = hueco. Los huecos son el
> **backlog natural** de la bóveda: métodos sin aplicar/reportar para esa estrella.
>
> La mantiene el LLM en cada `ingest-star` (paso *Bookkeeping*): columna nueva al ingestar una
> estrella; fila nueva al aparecer un método (su nota vive en `concepts/methods/`). Espeja
> `methods_applied.literature` del frontmatter de las fichas — ante discrepancia, manda la ficha.

| Método ↓ / Estrella → |
|---|

*(Bóveda vacía: se puebla con el primer `ingest-star`. Columna por estrella, fila por método —
ambos como wikilinks a su nota en `stars/` / `concepts/methods/`; la celda lleva el `[[bibcode]]`.)*

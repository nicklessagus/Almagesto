# Cómo anotar cada valor — los seis mecanismos de error medidos (#103, 1.42.0)

**Referencia de `ingest-star`, apuntada también por `ingest-theme`** (mismo paso 3, mismo modo de
falla). El `SKILL.md` deja la regla en una línea —**línea, régimen, segunda mano, tiempo verbal, y
nada de prosa comparativa**—; acá está **por qué** cada ítem de esa lista existe, con la medición que
lo produjo. Se lee la primera vez y cuando una corrección no cierra; no hace falta tenerlo abierto
para extraer.

## La medición

El fan-out de `verify-citations` sobre una ficha real (2026-08-25, HD 40307: 68 pares, 16 fuentes)
devolvió **54 soportada / 11 parcial / 3 contradice / 0 no-soportada**. Cero `no-soportada` significa
que **no se inventó nada**; los 14 defectos fueron de otro tipo:

| Mecanismo | Casos | Ejemplo real |
|---|---:|---|
| **Cita de segunda mano** — se lee A, que cita a B, y el número se guarda como de B | 3 | «≈12,1 m/s/dex» atribuido a Lovis: está en Díaz **citando** a Lovis, y no aparece en el `.txt` de Lovis |
| **Fila/columna equivocada** de una tabla multi-objeto | 2 | `log R'HK = −5,02` es de HD 1461, no de HD 40307 — misma tabla |
| **Inferencia con voz de cita** | 3 | «las dos familias de P_rot no se solapan»: ninguna fuente lo dice |
| **Cantidades parecidas** confundidas | 3 | error formal (0,77→0,64) vs dispersión (3,53→2,59) |
| **Epígrafe que el cuerpo del paper contradice** | 1 | activa/inactiva invertidas: la Fig. 9 de Díaz dice al revés que su §6 |
| **Régimen omitido** (los 11 `parcial`) | 11 | la Tabla 4 de Tuomi es la **mitad roja** (490–680 nm), no el espectro completo |

**Cuatro de los seis se vuelven chequeo mecánico** si cada valor viaja con su nº de línea: eso es lo
que convierte «prestá atención» en algo que después se puede verificar.

## Por qué la regla es ESTRUCTURAL y no «prestá atención» (1.42.0)

Los tres últimos ítems de la lista del skill no son estilo: son la contramedida a un sesgo medido, y
la **forma** de la contramedida importa. *Generalization bias in LLM summarization of scientific
research* (Royal Society Open Science 2025) comparó **4900 resúmenes de 10 modelos** contra sus
textos originales y encontró una taxonomía de sobre-generalización de tres tipos —**cuantificado →
genérico**, **pasado → presente**, **descriptivo → prescriptivo**—: los mismos tres que salen del
fan-out de esta bóveda, con la diferencia de que los dos primeros la taxonomía de #103 **no los tenía
nombrados** (caían dentro de «régimen omitido»). Dos hallazgos que cambian cómo se escribe este paso:

- ⛔ **Pedir exactitud en el prompt la EMPEORA.** Los prompts que piden explícitamente evitar
  imprecisiones **duplicaron** la sobre-generalización frente a un pedido de resumen simple (los
  autores lo llaman *algorithmic ironic rebound effect*). Por eso en el skill no hay ningún «sé
  preciso», «no inventes» ni «tené cuidado»: **una súplica de exactitud no es una instrucción, es
  ruido que rebota**. Lo que sí funciona es lo verificable — nº de línea, régimen, tiempo verbal —
  porque después se puede **chequear** que esté.
- **Temperatura 0 baja la sobre-generalización un 76 %** (0 vs 0.7) y es la mitigación más barata que
  reporta el paper. **No está aplicada, y hay que decir por qué**: los subagentes de esta cadena se
  lanzan con la herramienta de agentes del harness, que expone modelo y esfuerzo pero **no**
  temperatura. Es deuda declarada, no olvido: si algún día el harness la expone, es el primer cambio
  a hacer, y el gate es `bench_verify`.

## La regla de sombra, en detalle

Al copiar un valor a la nota de paper:

- **el nº de línea del `.txt`** al lado (`grep -n`, nunca `splitlines()` — form feeds);
- **el régimen** en el que la fuente lo afirma: muestra, época, corte de datos, modelo ajustado;
- si la fuente **atribuye el valor a otro trabajo** (*«according to X»*, *«(X et al.)»*), marcarlo
  **segunda mano** y citar a X — el número **no es de esta fuente**;
- **el tiempo verbal y el cuantificador de la fuente, tal cual** (regla de sombra, 1.42.0): si el
  paper dice *«was associated»*, la nota **no** dice *«is associated»*; si dice *«el 75 % de la
  muestra»*, la nota **no** dice *«la muestra»*. Y un resultado descriptivo no se convierte en
  recomendación.
- ⛔ **nada de prosa comparativa en la nota de paper.** Comparar dos papers es `inferencia` y su lugar
  es el `## Inventario por eje` de la ficha (paso 3b). Escribirla acá es lo que produjo los 3 casos
  de «inferencia con voz de cita».

El stub de `## Extracción (LLM)` que genera `make_notes` ya trae esta regla como último bullet: no
depende de que el extractor se acuerde de abrir este archivo.

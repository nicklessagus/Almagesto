# Playbook: spec → tests → implementación con agentes separados

Método para implementar **lotes** de cambios sin que los tests terminen confirmando lo que el código
ya hace. Complementa —no reemplaza— las seis redes de `CLAUDE.md` y los principios de
`tests/README.md`.

## El problema que resuelve, y por qué acá aplica

Cuando la misma cabeza escribe el test y la implementación, el test tiende a describir lo que el
código hace en vez de lo que debería hacer. Nadie lo nota: está verde.

**Este repo ya tiene la evidencia.** El ratchet de mutación (`tools/mutacion-ratchet.yaml`) documenta
cuatro casos medidos: *«un `assert path.glob(...)` siempre truthy, una guarda cuyo test pasaba sin la
guarda, un "espera creciente" que `[2.0, 2.0]` satisface, un test de determinismo corriendo las dos
pasadas en el mismo proceso»*. La respuesta del framework fue la **mutación**, que es detección
post-hoc; esto es **prevención**, y por eso no se superponen.

## Los roles

**Árbitro** (la sesión principal). Escribe la spec, contesta ambigüedades, decide sobre los tests en
disputa, verifica y commitea.

**Agente A — tests.** Recibe **sólo la spec**. Escribe los tests. No toca código de producción.

**Agente B — implementación.** Recibe spec + addendum + tests. Escribe el código. **No toca ningún
test.**

⛔ **Los agentes no se comunican entre sí.** Todo pasa por el árbitro. Si se hablan, el de tests
empieza a escribir lo que al otro le resulta cómodo implementar, que es lo que el método evita.

## Los cinco pasos

1. **Spec (árbitro).** De **comportamiento**, no de implementación. Tres cosas obligatorias:
   - qué DEBE pasar, en términos observables;
   - **contra-casos**: qué no puede romperse. Son la mitad del valor — la mayoría de los fixes son
     guards chicos, fáciles de aplicar de más, y el contra-caso es lo único que impide que el arreglo
     se coma el camino bueno;
   - **la superficie de API que los tests pueden tocar**: nombres de símbolos, firmas, fixtures.
     Parece burocracia y es lo que evita tirar el trabajo: sin eso, el agente de tests inventa un
     nombre y los tests no compilan contra el código.

2. **Tests (agente A).** La spec es la única fuente de verdad sobre **qué** asertar; puede leer el
   código para saber **cómo** montar el test, nunca para decidir qué esperar. Lo que la spec no
   cubra se anota como **pregunta abierta**, no se inventa. Los tests de comportamiento nuevo nacen
   con `@pytest.mark.xfail(strict=True)`; los contra-casos nacen sin marca y **pasan desde ya**.

⛔ **Y el agente de tests audita su propia COBERTURA contra la spec.** No alcanza con «escribí N
tests»: hay que recorrer la spec **requisito por requisito** y decir cuál test verifica cada uno, y
cuáles quedaron sin verificar. **Un requisito que ningún test chequea es un deseo, no un contrato.**

El modo de falla es exactamente el que este método viene a evitar, un piso más arriba: nadie escribe
un test complaciente, simplemente **falta**, y el conteo de tests da la sensación de cobertura. Vale
igual para el **addendum**, que es donde más fácil pasa —son respuestas sueltas, no ítems numerados—.

**Medido en el lote de skills de este repo (2026-08-26):** de 26 tests, la spec quedó con **tres
huecos**: A3 (la fecha estampada), A6 (re-juzgar el mismo par) y el **ítem 5b entero**, que el agente
de implementación reportó como «sin test que lo cubra» y el árbitro no actuó. El carril de
persistencia estaba perfecto y **nada verificaba que el skill lo consultara**, que es justo el
defecto que ese ítem venía a cerrar.

3. **Addendum (árbitro).** Contestar las preguntas abiertas **antes** de lanzar la implementación.
   No es opcional: sin él los dos agentes divergen.

4. **Implementación (agente B).** La única edición permitida sobre un test es **sacar el `xfail`** de
   uno que su fix hizo pasar. Si un test le parece mal, **escala y sigue con el resto**. Esta
   prohibición es el corazón del método: si el implementador puede aflojar el test que le molesta,
   volvimos al principio.

5. **Verificación (árbitro).** Dos cosas, y ninguna es «la suite está verde».

   ⛔ **(a) El árbitro audita la cobertura ÉL MISMO, sin confiar en el reporte del agente.** Recorre
   la spec **y el addendum**, requisito por requisito, contra los tests que hay. Que el agente de
   tests audite su propia cobertura (paso 2) es necesario y **no suficiente**: el sesgo es el mismo
   que el método ataca en todo lo demás —quien escribió los tests no es quien mejor ve lo que le
   falta— y el hueco puede aparecer **después**, cuando el implementador agrega algo que la spec
   pedía y nadie testeó.
   **Medido acá (2026-08-26):** el agente de **implementación** reportó por escrito que el ítem 5b
   se había implementado «sin test que lo cubra», y el árbitro **no actuó**. Quedó un skill cuyo
   paso entero se podía borrar con la suite en verde. El reporte existía; faltó el paso del árbitro.
   De ahí la regla operativa: leer el informe del implementador **buscando lo que reporta y nadie
   acciona**.

   **(b) Verificar que los tests no se aflojaron** — contar tests y aserciones antes/después, buscar
   `assert True`, `skip`, `xfail` nuevos, aserciones reemplazadas por otras más débiles, y confirmar
   que cada `xfail` removido corresponde a un test que hoy pasa de verdad.

## Por qué la cobertura se audita DOS veces

Las dos auditorías —la del agente de tests (paso 2) y la del árbitro (paso 5)— son **redes
independientes**, no una redundante de la otra, y hay evidencia de que cada una atrapa cosas
distintas:

- **La del agente** ve lo que le falta a **su propia tanda de tests** frente a la spec, mientras
  todavía tiene el detalle fresco. En un lote medido con este método aparecieron así **tres**
  requisitos sin cubrir.
- **La del árbitro** ve lo que aparece **después**: lo que el implementador agregó y nadie testeó, y
  lo que el propio addendum sumó sin ítem numerado. En otro lote aparecieron así **dos** que la
  auditoría del agente no podía haber visto, porque todavía no existían.

⛔ **Y ninguna de las dos se sustituye por «contar tests» ni por «la suite está verde»**: los cinco
huecos convivían con una suite entera en verde y con más tests que requisitos. Un requisito sin test
no se manifiesta como rojo — se manifiesta como **nada**.

## La regla que se adopta SIEMPRE, incluso fuera de un lote

⛔ **El test tiene que fallar por la AUSENCIA DEL COMPORTAMIENTO, no por el andamiaje.**

Hay dos rojos legítimos y uno que no lo es:

| Rojo | ¿Sirve? |
|---|---|
| `ImportError` / `AttributeError` porque el símbolo todavía no existe | **sí** — nada más que verificar |
| falla **en la aserción**: el flujo existe y hoy hace lo incorrecto | **sí** — es el rojo que especifica |
| falla armando el escenario (mock con la firma equivocada, fixture incompleta) | **no** — ese test no especifica nada |

El tercero es el caro: va a seguir fallando después de implementado y le hace perder horas a quien
implementa persiguiendo un fantasma que era el mock. **Medido en este repo (2026-08-26):** dos tests
de una misma tanda fallaron primero con `TypeError: list indices must be integers` (el doble devolvía
una tupla donde la función devuelve una lista) y después con `KeyError: 'facets'`. Se vio rojo las
dos veces y no significaba nada.

## Quién decide sobre un test en disputa

- **El implementador, nunca**: tiene conflicto de interés directo — el test es justo lo que le
  bloquea el trabajo.
- **El autor del test** tiene el sesgo opuesto y sirve de contrapeso, pero puede estar equivocado.
- **Decide el árbitro**, y puede editar un test con un límite claro: sólo para **aumentar su
  fidelidad** (arreglar un mock que lo hacía pasar por accidente), **nunca para debilitar una
  aserción**.

El criterio de fondo: *quien decide sobre un test no puede ser quien se beneficia de que sea más
débil*.

## Cuándo se usa, y el canje con la mutación

- **Un fix de un solo ítem** → ciclo test-first normal (`tests/README.md`, principio 6). Montar tres
  roles ahí es overhead puro.
- **Lote de ≥3 ítems que tocan el mismo código** → este método.

⚠ **El canje que hace que esto no sea sólo costo agregado:** un lote hecho con separación de roles
**no necesita el gate de mutación en su tanda** — la mutación queda para los lotes que no la usaron y
para la pasada periódica completa (`tools/mutar.py --todo --ratchet`). La mutación cuesta ~40 min
sobre un diff que toca `make_notes.py`; la spec cuesta un rato de pensar el diseño y se paga en que
la implementación sale sin discusión sobre qué había que hacer.

## Riesgo conocido

«El agente de tests puede leer el código para saber *cómo* montar el test, nunca para decidir *qué*
esperar» es una disciplina que un subagente puede violar **sin que se note**. Mitigación: que la spec
traiga la superficie de fixtures y firmas, para que no *necesite* leer.

## Checklist

- [ ] La spec fija los nombres de API que los tests van a tocar.
- [ ] La spec tiene contra-casos explícitos, no sólo el camino feliz.
- [ ] Al agente de tests se le prohíbe explícitamente tocar el código.
- [ ] Al agente de tests se le pide anotar preguntas abiertas en vez de inventar.
- [ ] El agente de tests **audita su cobertura contra la spec, requisito por requisito**, y reporta
      los que quedaron sin verificar (incluidos los del addendum).
- [ ] El árbitro **audita la cobertura por su cuenta**, spec y addendum en mano, sin confiar en
      el reporte del agente — incluido lo que el implementador haya agregado.
- [ ] El árbitro **cierra esos huecos** antes de dar el lote por terminado, o declara por qué no.
- [ ] Se leyó el informe del implementador **buscando lo que reporta y nadie acciona** (ahí
      vivió el hueco medido).
- [ ] Se verifica que cada test falle por la ausencia del comportamiento y no por el andamiaje.
- [ ] Las preguntas abiertas se contestan **antes** de lanzar implementación.
- [ ] Al implementador se le prohíbe modificar tests, y se le dice qué hacer en cambio (escalar y
      seguir).
- [ ] Al final se verifica que los tests no se aflojaron, no sólo que están verdes.
- [ ] Los agentes no se comunicaron entre sí.

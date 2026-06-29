# Migración: la bóveda pasa a `vault/`

> **Para Claude en una instancia (p. ej. Almagesto-RV).** El template Almagesto movió **todo el
> contenido** de la bóveda a un subdirectorio `vault/`, dejando en la raíz **sólo el andamiaje**
> (framework). Esta guía migra una instancia ya existente a la estructura nueva **sin perder contenido
> ni historia** y dejando los merges futuros limpios. Es una operación **de una sola vez**.

## Qué cambió en el template

```
ANTES (raíz)                          DESPUÉS
config/  wiki/  raw/  STATUS.md        vault/config/  vault/wiki/  vault/raw/
.obsidian/                            vault/STATUS.md  vault/.obsidian/
scripts/ .claude/ CLAUDE.md …  (igual: andamiaje en la raíz)
build/ outputs/                       (igual: scratch gitignored en la raíz, FUERA de vault/)
```

- `scripts/lib_config.py` ahora resuelve `VAULT = ROOT/"vault"` y cuelga `CONFIG/RAW/WIKI` de ahí.
- `.gitattributes`: los `merge=ours` y el filtro git-lfs ahora apuntan a `vault/...`.
- `.gitignore`: `vault/config/ads_dev_key`, `vault/.obsidian/...`.
- Las rutas en `CLAUDE.md` y en los skills llevan prefijo `vault/` (repo-root-relative). **Excepción
  Obsidian-space:** dentro de notas `.md`, los `[[wikilink]]`, las queries Dataview (`FROM "wiki/papers"`)
  y los links relativos (`../../raw/pdfs/…`) **NO** llevan prefijo — son relativos a la raíz del vault.

## Idea de la migración

El problema no es el contenido (está protegido por `merge=ours`), sino que el **template renombró
archivos**. Si mergeás upstream sin preparar nada, git pelea entre "tu `config/objective.yaml` en la
raíz" y "el `vault/config/objective.yaml` del template". **Solución: replicás el movimiento en tu
instancia primero** (mismos destinos `vault/…`), adoptás el `.gitattributes` nuevo, commiteás, y
*recién ahí* mergeás. Con ambos lados apuntando a `vault/`, git detecta los renames y `merge=ours`
protege tu contenido en su ruta nueva.

## Pasos

> Asumen que tu instancia tiene la estructura vieja (`config/ wiki/ raw/ STATUS.md .obsidian/` en la
> raíz) y que `upstream` apunta a Almagesto. Hacé backup o trabajá en una rama por las dudas.

```bash
cd /ruta/a/Almagesto-RV
git switch main && git status      # árbol limpio antes de empezar (commiteá pendientes)
git fetch upstream
git config merge.ours.driver true  # idempotente; necesario para que merge=ours funcione

# (opcional pero recomendado) rama de seguridad
git switch -c migracion-vault

# 1) Replicar EXACTO el movimiento estructural del template (uno por uno; .obsidian al final
#    porque suele tener archivos untracked como workspace.json que se mueven con el rename):
mkdir vault
git mv config   vault/config
git mv wiki     vault/wiki
git mv raw      vault/raw
git mv STATUS.md vault/STATUS.md
git mv .obsidian vault/.obsidian

# 2) Adoptar el .gitattributes nuevo ANTES de mergear, para que el driver merge=ours proteja
#    el contenido en su ruta vault/ durante el merge (y que git-lfs siga trackeando los PDFs):
git checkout upstream/main -- .gitattributes

# 3) Commitear el movimiento (deja tu instancia con la MISMA topología que el template):
git commit -m "refactor: mover la bóveda a vault/ (alinear estructura con el template)"

# 4) Traer el resto de las mejoras de framework. Como ambos lados movieron a vault/, git matchea
#    los renames; tu contenido (config/objective.yaml, stars.yaml, topics.yaml, STATUS.md,
#    wiki/index.md, wiki/log.md) queda intacto por merge=ours:
git merge upstream/main
```

## Verificación (post-merge)

```bash
ls vault/                 # config  wiki  raw  STATUS.md  .obsidian
ls                        # raíz: CLAUDE.md README.md scripts .claude requirements.txt vault  (+ build/outputs si existían)
python scripts/lint.py    # debe dar 0 en wikilinks rotos / huérfanos / contradicciones GT
git diff --stat HEAD~1    # revisá que NO se haya pisado tu contenido con stubs del template
```

Chequeá a mano que `vault/config/objective.yaml`, `vault/config/stars.yaml` y tu `vault/wiki/` sigan
siendo **los tuyos** (no los del template). Si quedó algún archivo tuyo pisado por el stub del
template, restauralo: `git checkout migracion-vault -- vault/config/objective.yaml` (o el que sea).

Si todo está bien, integrá la rama:

```bash
git switch main && git merge --ff-only migracion-vault   # o el flujo que uses
git branch -d migracion-vault
```

## Reabrir en Obsidian

El vault de Obsidian **ya no es la raíz del repo, es `vault/`**. En Obsidian: *Open folder as vault* →
elegí la carpeta **`vault/`**. Así el grafo muestra sólo conocimiento, sin el andamiaje. La config
de Obsidian viaja en `vault/.obsidian/`; reinstalá el plugin Dataview si hiciera falta.

## Si el merge se complica (fallback)

Si el paso 4 da conflictos raros (típicamente porque la instancia divergió del layout viejo), la salida
segura es **tomar el framework del template entero y conservar tu contenido**:

```bash
git merge upstream/main --no-commit
# para cada archivo de FRAMEWORK en conflicto, quedate con el del template:
git checkout upstream/main -- CLAUDE.md README.md requirements.txt .gitignore .gitattributes scripts .claude
# para tu CONTENIDO en conflicto, quedate con el tuyo:
git checkout --ours -- vault/config vault/wiki vault/raw vault/STATUS.md
git add -A && git commit
python scripts/lint.py   # confirmar 0
```

Regla de oro intacta: vos sólo editás contenido (`vault/wiki/`, `vault/raw/`) y los archivos de
instancia `merge=ours`; el framework (incluida esta migración) se origina en el template Almagesto.

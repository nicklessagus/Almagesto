"""entity: borrar / renombrar una ENTIDAD sin dejar nada colgado (INV-19).

Qué protege este archivo. INV-19 estaba en `HUECO (parcial)` con el diagnóstico exacto: *"no existe
herramienta: borrar y renombrar son procedimientos en prosa del skill `maintain`"*. Nueve pasos a
mano sobre siete lugares distintos no son una garantía — son una lista de cosas que se pueden
saltear, y el lint tenía red para `wiki/` y **ninguna** para el registro, `raw/`, el YAML ni
`build/`. Acá cada capa es un assert.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import entity                      # noqa: E402
import lib_config as cfg           # noqa: E402
from conftest import write_yaml    # noqa: E402


def poblar(slug="test_star", nombre="Estrella Test"):
    """Una entidad con SUS SIETE CAPAS en disco, más una nota de paper que la referencia."""
    cfg.save_busqueda(slug, {"fecha": "2026-01-01", "query": "q", "n_total": 2})
    cfg.save_decisiones(slug, {"2020Ruido": {"decision": "descartado", "motivo": "off-topic",
                                             "fecha": "2026-01-01"}})
    (cfg.GROUND_TRUTH / f"{slug}.json").write_text(json.dumps({"host": {}, "planets": []}),
                                                   encoding="utf-8")
    (cfg.PDFS / slug).mkdir(parents=True, exist_ok=True)
    (cfg.PDFS / slug / "2020A.pdf").write_bytes(b"%PDF-1.4")
    (cfg.FULLTEXT / slug).mkdir(parents=True, exist_ok=True)
    (cfg.FULLTEXT / slug / "2020A.txt").write_text("texto", encoding="utf-8")
    cfg.STARS.mkdir(parents=True, exist_ok=True)
    (cfg.STARS / f"{slug}.md").write_text(
        f"---\nname: {nombre}\nslug: {slug}\ntags: [star]\n---\n# {nombre}\n", encoding="utf-8")
    (cfg.ROOT / "build" / slug).mkdir(parents=True, exist_ok=True)
    (cfg.ROOT / "build" / slug / "ads.json").write_text("{}", encoding="utf-8")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020A.md").write_text(
        f"---\nbibcode: 2020A\nstars: [{nombre}]\nmethods: [gp]\ntags: [paper]\n---\n"
        f"# T\n\nExtracción cara.\n", encoding="utf-8")
    return slug, nombre


def run(argv):
    return entity.main(argv)


# ── plan / dry-run ──────────────────────────────────────────────────────────

def test_plan_lista_las_siete_capas_y_no_escribe(toy_vault, capsys):
    slug, nombre = poblar()
    antes = sorted(p for p in cfg.VAULT.rglob("*") if p.is_file())
    assert run(["plan", slug]) == 0
    out = capsys.readouterr().out
    for capa in ("registro", "ground_truth", "pdfs", "fulltext", "nota", "build"):
        assert capa in out, f"falta la capa {capa}: {out}"
    assert "NO REGENERABLE" in out, "el registro tiene que salir marcado"
    assert "1 nota(s) de paper" in out
    assert sorted(p for p in cfg.VAULT.rglob("*") if p.is_file()) == antes


def test_delete_sin_yes_es_dry_run(toy_vault, capsys):
    """⛔ Destructivo: la capa 2 no se regenera, así que no se aplica sin pedirlo."""
    slug, _ = poblar()
    assert run(["delete", slug]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert cfg.registro_path(slug).exists() and (cfg.STARS / f"{slug}.md").exists()


def test_rename_sin_yes_es_dry_run(toy_vault, capsys):
    slug, _ = poblar()
    assert run(["rename", slug, "otro_slug"]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert cfg.registro_path(slug).exists()


# ── delete ──────────────────────────────────────────────────────────────────

def test_delete_borra_las_siete_capas(toy_vault, capsys):
    """INV-19: *"no queda ninguna referencia colgada en ninguna capa ni archivo huérfano en raw/"*.
    @inv INV-19"""
    slug, nombre = poblar()
    assert run(["delete", slug, "--yes"]) == 0
    assert not cfg.registro_path(slug).exists()
    assert not (cfg.GROUND_TRUTH / f"{slug}.json").exists()
    assert not (cfg.PDFS / slug).exists() and not (cfg.FULLTEXT / slug).exists()
    assert not (cfg.STARS / f"{slug}.md").exists()
    assert not (cfg.ROOT / "build" / slug).exists()
    stars = yaml.safe_load(cfg.STARS_YAML.read_text(encoding="utf-8")) or {}
    assert nombre not in stars, "la entrada del YAML es la capa que más fácil queda colgada"


def test_delete_no_borra_el_paper_compartido(toy_vault):
    """Una nota con `stars: [A, B]` pertenece a las dos: al borrar A se le saca A y la nota queda.
    Borrarla sería tirar extracción ya pagada por la otra entidad."""
    poblar()
    (cfg.PAPERS / "2020A.md").write_text(
        "---\nbibcode: 2020A\nstars: [Estrella Test, Otra]\nmethods: [gp]\ntags: [paper]\n---\n"
        "# T\n\nExtracción cara.\n", encoding="utf-8")
    run(["delete", "test_star", "--yes"])
    txt = (cfg.PAPERS / "2020A.md").read_text(encoding="utf-8")
    assert cfg.split_fm(txt)["stars"] == ["Otra"]
    assert "Extracción cara." in txt


def test_delete_avisa_del_paper_que_queda_sin_destino(toy_vault, capsys):
    """Si al sacarle la entidad la nota se queda sin ningún destino pasa a ser un hallazgo
    BLOQUEANTE del lint (D-23). Se avisa y **no** se borra: es extracción ya pagada, y decidir
    borrarla sería decidir por el usuario."""
    poblar()
    (cfg.PAPERS / "2020A.md").write_text(
        "---\nbibcode: 2020A\nstars: [Estrella Test]\nthesis_links: []\nmethods: []\n"
        "tags: [paper]\n---\n# T\n", encoding="utf-8")
    run(["delete", "test_star", "--yes"])
    out = capsys.readouterr().out
    assert "SIN destino" in out and "2020A" in out
    assert (cfg.PAPERS / "2020A.md").exists(), "no se borra sola"


def test_delete_avisa_de_los_wikilinks_que_quedan_rotos(toy_vault, capsys):
    """No se reparan solos: apuntan a una nota que ya no existe y el lint los da BLOQUEANTES.
    Repararlos automáticamente sería decidir qué decía esa frase; dejarlos rotos y visibles es la
    conducta correcta."""
    poblar()
    (cfg.CONCEPTS / "methods").mkdir(parents=True, exist_ok=True)
    (cfg.CONCEPTS / "methods" / "gp.md").write_text(
        "---\nname: gp\ntags: [concept]\n---\n# gp\n\nAplicado a [[Estrella Test]].\n",
        encoding="utf-8")
    run(["delete", "test_star", "--yes"])
    out = capsys.readouterr().out
    assert "wikilink ROTO" in out and "gp.md" in out
    assert "[[Estrella Test]]" in (cfg.CONCEPTS / "methods" / "gp.md").read_text(encoding="utf-8")


# ── rename ──────────────────────────────────────────────────────────────────

def test_rename_mueve_las_capas_y_actualiza_el_slug(toy_vault):
    """@inv INV-19 — el renombre mueve las siete capas, no la mitad."""
    slug, nombre = poblar()
    assert run(["rename", slug, "nuevo_slug", "--yes"]) == 0
    assert cfg.registro_path("nuevo_slug").exists() and not cfg.registro_path(slug).exists()
    assert (cfg.FULLTEXT / "nuevo_slug" / "2020A.txt").exists()
    assert (cfg.PDFS / "nuevo_slug" / "2020A.pdf").exists()
    assert (cfg.GROUND_TRUTH / "nuevo_slug.json").exists()
    assert (cfg.STARS / "nuevo_slug.md").exists()
    assert (cfg.ROOT / "build" / "nuevo_slug").exists()
    stars = yaml.safe_load(cfg.STARS_YAML.read_text(encoding="utf-8"))
    assert stars[nombre]["slug"] == "nuevo_slug"


def test_rename_preserva_el_juicio_de_curacion(toy_vault):
    """El registro es el ÚNICO artefacto no regenerable: si el renombre lo deja atrás, el triage
    re-propone todo lo descartado **sin el motivo** — el bug que #51 cerró, por otra puerta."""
    poblar()
    run(["rename", "test_star", "nuevo_slug", "--yes"])
    dec = cfg.load_decisiones("nuevo_slug")
    assert dec["2020Ruido"]["motivo"] == "off-topic"
    assert cfg.load_busquedas("nuevo_slug")[0]["n_total"] == 2


def test_rename_rehusa_si_el_destino_ya_existe(toy_vault):
    """Renombrar encima de artefactos existentes fusionaría dos entidades **en silencio**."""
    poblar()
    (cfg.FULLTEXT / "ocupado").mkdir(parents=True, exist_ok=True)
    with pytest.raises(SystemExit, match="ya hay artefactos"):
        run(["rename", "test_star", "ocupado", "--yes"])


def test_rename_de_tema_reescribe_wikilinks_y_thesis_links(toy_vault):
    """En un TEMA el slug ES la clave del YAML y aparece en `thesis_links` y en `[[wikilink]]`; en
    una estrella no (ahí lo que se referencia es el NOMBRE, que el renombre de slug no toca)."""
    write_yaml(cfg.THEMES_YAML, {"gp_viejo": {"title": "GP", "area": "methods",
                                              "concept": "procesos-gaussianos", "query": "q"}})
    cfg.save_busqueda("gp_viejo", {"fecha": "2026-01-01", "n_total": 1})
    (cfg.FULLTEXT / "gp_viejo").mkdir(parents=True, exist_ok=True)
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2020G.md").write_text(
        "---\nbibcode: 2020G\nthesis_links: [gp_viejo]\nmethods: []\ntags: [paper]\n---\n"
        "# T\n\nVer [[gp_viejo]].\n", encoding="utf-8")
    assert run(["rename", "gp_viejo", "gp_nuevo", "--yes"]) == 0
    themes = yaml.safe_load(cfg.THEMES_YAML.read_text(encoding="utf-8"))
    assert "gp_nuevo" in themes and "gp_viejo" not in themes
    txt = (cfg.PAPERS / "2020G.md").read_text(encoding="utf-8")
    assert cfg.split_fm(txt)["thesis_links"] == ["gp_nuevo"] and "[[gp_nuevo]]" in txt


def test_entidad_desconocida_no_adivina(toy_vault):
    with pytest.raises(SystemExit, match="entidad desconocida"):
        run(["plan", "no_existe"])


def test_quitar_del_frontmatter_preserva_el_cuerpo_byte_a_byte(toy_vault):
    """El docstring promete «preserva byte a byte el resto, incluida la extracción LLM».

    AUD-38: la reconstrucción era `"---" + "\\n".join(out) + "\\n---\\n" + resto.lstrip("\\n")`, que
    hacía DOS daños a la vez — metía una línea en blanco **dentro** del frontmatter (el `head` de
    `frontmatter_span` ya termina en `\\n`) y borraba la línea en blanco de después del `---`. Se
    declara de la familia de `merge_frontmatter_list`, que sí preserva; la diferencia era el
    `lstrip`. Corre en `entity.py delete` sobre CADA nota que referenciaba la entidad.

    ⚠ **La marca era `@inv INV-90` y estaba MAL ATRIBUIDA (#183).** Este test mide **preservación
    byte a byte del cuerpo** —una cirugía que toca sólo la región derivada y no destruye la prosa,
    que es INV-15— y **no** mide atomicidad: reproducido por mutación, cambiar
    `cfg.write_text_atomic` por `f.write_text` en `entity.py:218` lo deja en VERDE, con la suite
    entera en verde. Que figurara como una de las pruebas que «garantizan y miden» INV-90 le
    adjudicaba al mapa una cobertura que no existía — la regla de método #4. Quien mide INV-90 sobre
    este módulo es `test_lib_config.py::test_sin_escrituras_directas_a_vault`, cuya población se
    derivó en #137 justamente para que `entity.py` entre.  @inv INV-15
    """
    nota = toy_vault.PAPERS / "2020ref.md"
    original = ("---\ntags:\n  - paper\nstars:\n  - Estrella Test\n  - Otra\n---\n\n"
                "# 2020ref\n\n## Extracción\n\nProsa cara.\n")
    nota.write_text(original, encoding="utf-8")
    assert entity._quitar_del_frontmatter(nota, "stars", "Otra") is True
    nuevo = nota.read_text(encoding="utf-8")
    esperado = original.replace("  - Otra\n", "")
    assert nuevo == esperado, f"\n--- esperado ---\n{esperado!r}\n--- obtenido ---\n{nuevo!r}"
    assert cfg.split_fm(nuevo)["stars"] == ["Estrella Test"]


def test_rename_de_tema_no_toca_el_nombre_de_la_nota(toy_vault, capsys):
    """Issue #169 — la capa `nota` se renombraba por SUBSTRING ciego (`p.name.replace(viejo, nuevo,
    1)`), y el guard `if p.name == destino.name: continue` sólo cubría el caso en que el slug no
    aparece en el nombre. Si el `concept` CONTIENE al slug —`ica` → `ica-bss`, la forma normal— la
    nota se movía y `themes.yaml` seguía apuntando al nombre viejo: la entidad quedaba **sin nota
    alcanzable** y los `[[wikilink]]` rotos, mientras el script imprimía que había renombrado y
    cerraba con *"cerrá con `lint --cierre` (tiene que dar 0)"*.

    La nota de un TEMA se llama por `concept`, que es un campo aparte: renombrar el slug no la
    toca. Es lo que INV-19 exige — *"que no quede ninguna referencia colgada en ninguna capa"*."""
    write_yaml(cfg.THEMES_YAML, {"ica": {"title": "ICA", "area": "methods", "concept": "ica-bss"}})
    cfg.save_busqueda("ica", {"fecha": "2026-01-01", "n_total": 1})
    nota = cfg.CONCEPTS / "methods" / "ica-bss.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text("---\nname: ICA\ntags: [methods]\n---\n\n# ICA\n", encoding="utf-8")
    assert run(["rename", "ica", "componentes-independientes", "--yes"]) == 0
    assert nota.exists(), "la nota del tema NO se renombra: se llama por `concept`, no por slug"
    assert not (cfg.CONCEPTS / "methods" / "componentes-independientes-bss.md").exists()
    _, meta = cfg.theme_by_slug("componentes-independientes")
    assert entity.nota_de("theme", "componentes-independientes", meta) == nota, \
        "y la config sigue resolviendo a la nota que existe"

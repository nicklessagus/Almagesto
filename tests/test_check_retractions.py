"""check_retractions: parseo Crossref, fallback por título, estampado idempotente, modo --slug."""
import json
import sys
from types import SimpleNamespace

import pytest
import requests as real_requests

import check_retractions as cr
import lib_config as cfg
from conftest import mk_note, read_fm, write_yaml


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def patch_net(monkeypatch, responses, calls=None):
    seq = list(responses)

    def get(url, headers=None, timeout=None):
        if calls is not None:
            calls.append(url)
        if isinstance(seq[0], Exception):
            raise seq.pop(0) if len(seq) > 1 else seq[0]
        return seq.pop(0) if len(seq) > 1 else seq[0]
    monkeypatch.setattr(cr, "requests",
                        SimpleNamespace(get=get, RequestException=real_requests.RequestException))
    monkeypatch.setattr(cr, "time", SimpleNamespace(sleep=lambda s: None))


RETRACTION_MSG = {"message": {"updated-by": [
    {"type": "Retraction", "DOI": "10.1/notice",
     "updated": {"date-parts": [[2021, 5, 3]]}, "source": "publisher"}]}}


# ── unidades ─────────────────────────────────────────────────────────────────

def test_split_note_preserva_cuerpo(tmp_path):
    body = "\n# Título\n\nProsa.\n\n---\nregla horizontal en el cuerpo\n"
    p = tmp_path / "n.md"
    p.write_text(f"---\nbibcode: x\ntags:\n- paper\n---{body}", encoding="utf-8")
    fm, got_body = cr.split_note(p.read_text(encoding="utf-8"))
    assert fm["bibcode"] == "x"
    assert got_body == body                          # maxsplit=2 preserva el --- del cuerpo


RET = {"type": "retraction", "notice_doi": "10.1/n", "date": "2021-05-03", "source": "publisher"}


def test_stamp_retraction_preserva_comentarios_y_cuerpo(tmp_path):
    """Regresión (hallazgo 3): el estampado es quirúrgico — no re-serializa el YAML,
    los comentarios/orden de la extracción LLM sobreviven."""
    body = "\ncuerpo\n\n---\nregla horizontal\n"
    p = tmp_path / "n.md"
    p.write_text("---\nbibcode: x\nmethods: [gp]  # anotado por el LLM\ntags:\n- paper\n"
                 f"---{body}", encoding="utf-8")
    fm, got_body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, got_body, RET)
    text = p.read_text(encoding="utf-8")
    assert "# anotado por el LLM" in text            # comentario intacto
    assert body in text                              # cuerpo intacto (con su ---)
    fm2, _ = cr.split_note(text)
    assert fm2["retracted"] is True and fm2["retraction"] == RET


def test_stamp_retraction_reemplaza_bloque_previo(tmp_path):
    """Re-chequeo con --force: el bloque retraction viejo se reemplaza, no se duplica."""
    p = tmp_path / "n.md"
    p.write_text("---\nbibcode: x\ntags:\n- paper\n---\ncuerpo\n", encoding="utf-8")
    fm, body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, body, RET)
    fm, body = cr.split_note(p.read_text(encoding="utf-8"))
    cr.stamp_retraction(p, fm, body, dict(RET, date="2022-01-01"))
    text = p.read_text(encoding="utf-8")
    assert text.count("retraction:") == 1 and text.count("retracted:") == 1
    fm2, _ = cr.split_note(text)
    assert fm2["retraction"]["date"] == "2022-01-01"


def test_split_note_sin_frontmatter():
    assert cr.split_note("texto plano") == (None, "texto plano")
    assert cr.split_note("---\nyaml: [roto\n---\n") == (None, "---\nyaml: [roto\n---\n")


NOTA_CON_GUIONES = (
    '---\n'
    'bibcode: 2020aaa...1..1A\n'
    'title: "Un titulo con --- adentro"\n'
    'tags:\n'
    '- paper\n'
    '---\n'
    'cuerpo\n'
)


def test_split_note_no_saltea_el_paper():
    """Tercer sitio de la misma clase que `test_split_fm_no_corta_dentro_de_un_valor`
    (`tests/test_lib_config.py`). `split("---", 2)` parece defensivo (el `maxsplit` preserva las
    reglas horizontales del cuerpo) pero corta igual **dentro del valor**: devuelve `(None, …)`
    y el paper **se saltea del chequeo de retracciones** con el mensaje falso "arreglá el YAML".
    Falso limpio en la frontera dura: una fuente retractada citada rompe la regla #0.
    (Se escribió creyendo que era un control de no-regresión; falló, y por eso está acá.)"""
    fm, _ = cr.split_note(NOTA_CON_GUIONES)
    assert fm and fm.get("bibcode") == "2020aaa...1..1A"


def test_stamp_fields_no_deja_la_nota_a_medias(toy_vault, monkeypatch):
    """`stamp_fields` reescribe notas de `papers/` —con la extracción LLM adentro— sin tmp+rename.
    Medido con `ulimit -f`: 16.071 B → 8.192 B, 198 de 400 ocurrencias de la extracción destruidas.
    Es la misma clase que la 6ª pasada arregló en `save_registro`, sobre lo MENOS regenerable de la
    bóveda. Acá se simula el corte fallando la escritura: el original tiene que sobrevivir."""
    cuerpo = "".join(f"## Extracción {i}\n\nprosa LLM irrecuperable {i}\n\n" for i in range(80))
    p = mk_note(toy_vault.PAPERS, "2020aaa...1..1A",
                {"bibcode": "2020aaa...1..1A", "tags": ["paper"]}, cuerpo)
    original = p.read_bytes()

    real_write = type(p).write_text

    def write_que_se_corta(self, data, *a, **k):
        # El corte se inyecta en CUALQUIER escritura dentro de papers/, no sólo en la ruta destino.
        # Inyectarlo sólo en el destino premiaba la implementación equivocada: con tmp+rename el
        # fallo nunca dispara y el test pasa sin probar nada, así que el test empujaba a escribir
        # directo sobre la nota y "restaurar" desde un backup — que NO sobrevive a un SIGKILL,
        # porque ahí no corre ningún `except`. Lo que se exige es el contrato, no el mecanismo:
        # si la escritura falla, el original queda intacto.
        if self.parent == p.parent:
            real_write(self, data[:len(data) // 2], *a, **k)
            raise OSError("disco lleno")
        return real_write(self, data, *a, **k)

    monkeypatch.setattr(type(p), "write_text", write_que_se_corta)
    fm, body = cr.split_note(p.read_text(encoding="utf-8"))
    with pytest.raises(OSError):
        cr.stamp_fields(p, fm, body, {"retracted": True})
    assert p.read_bytes() == original, "la nota quedó truncada: se perdió la extracción LLM"


def test_stamp_fields_drop_de_la_clave_vieja_no_corrompe_el_frontmatter(toy_vault):
    """El borrado del bloque viejo se corta ante cualquier línea que no empiece con espacio/tab/`-`
    y deja el resto huérfano. Con una línea EN BLANCO el YAML parsea igual y el ítem huérfano se
    absorbe en la clave anterior (`tags: ['paper', {'type': 'corrigendum'}]`) — y **ninguna
    categoría del lint lo ve**. La docstring promete preservar byte a byte."""
    texto = (
        '---\n'
        'bibcode: 2020aaa...1..1A\n'
        'retraction:\n'
        '  type: corrigendum\n'
        '\n'
        '  date: "2021-01-01"\n'
        'tags:\n'
        '- paper\n'
        '---\n'
        'cuerpo\n'
    )
    p = toy_vault.PAPERS / "2020aaa...1..1A.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    fm0, body0 = cr.split_note(texto)
    cr.stamp_fields(p, fm0, body0, {"retraction": {"type": "retraction", "date": "2022-01-01"}})
    fm = cfg.split_fm(p.read_text(encoding="utf-8"))
    assert fm.get("tags") == ["paper"], f"`tags` contaminado por el drop: {fm.get('tags')!r}"


def test_upd_date():
    assert cr._upd_date({"updated": {"date-parts": [[2021, 5, 3]]}}) == "2021-05-03"
    assert cr._upd_date({"updated": {"date-parts": [[2021]]}}) == "2021"
    assert cr._upd_date({}) is None


def test_upd_date_date_parts_escalar_no_inventa_una_fecha():
    """`check_retractions.py:175` — `dp = (upd.get("updated") or {}).get("date-parts") or [[]]`.

    Este NO crashea: miente. Con `date-parts: "2021"` (escalar en vez de `[[2021,5,3]]`) el
    `or [[]]` no dispara, `dp[0]` es el carácter `"2"` y la función devuelve la fecha **"2"**,
    que se estampa en el frontmatter como `retraction.date` / `corrections[].date`. Un dato
    inventado en la capa auditable es peor que una excepción: no deja rastro."""
    assert cr._upd_date({"updated": {"date-parts": "2021"}}) is None, (
        "se fabricó una fecha a partir de un `date-parts` que no es una lista")


def test_title_says_retracted():
    assert cr.title_says_retracted("RETRACTED: On planets")
    assert cr.title_says_retracted("Retraction: something")
    assert cr.title_says_retracted("Withdrawn manuscript")
    assert not cr.title_says_retracted("Retrograde orbits")
    assert not cr.title_says_retracted(None)


def test_crossref_retraction_parsea(monkeypatch):
    patch_net(monkeypatch, [FakeResp(200, RETRACTION_MSG)])
    ret, soft, estado = cr.crossref_retraction("10.1/x", {})
    assert ret == {"type": "retraction", "notice_doi": "10.1/notice",
                   "date": "2021-05-03", "source": "publisher"}
    assert soft == []


def test_crossref_soft_no_retracta(monkeypatch):
    """#52: la corrección no retracta, pero vuelve COMPLETA (se persiste en `corrections`)."""
    patch_net(monkeypatch, [FakeResp(200, {"message": {"updated-by": [
        {"type": "Corrigendum", "DOI": "10.1/corr",
         "updated": {"date-parts": [[2023, 7, 1]]}, "source": "publisher"}]}})])
    ret, soft, estado = cr.crossref_retraction("10.1/x", {})
    assert ret is None
    assert soft == [{"type": "corrigendum", "notice_doi": "10.1/corr",
                     "date": "2023-07-01", "source": "publisher"}]


def test_crossref_tolerante_a_errores(monkeypatch):
    """Sigue siendo tolerante (nunca revienta, nunca AFIRMA retracción sin evidencia), pero desde
    el issue 0.1 dice además **si pudo consultar**. La distinción no es cosmética: "Crossref
    contestó y no hay retracción" y "Crossref no contestó" terminaban las dos en un rc 0 que la
    cadena leía como *chequeado y limpio*.

    Un **404 no es error**: es una respuesta real ("no tengo ese DOI"), y tratarla como fallo
    inundaría de rc 2 a todo corpus con DOIs que Crossref no indexa."""
    patch_net(monkeypatch, [FakeResp(404)])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [], "sin-registro")
    patch_net(monkeypatch, [FakeResp(500)])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [], "error")
    patch_net(monkeypatch, [real_requests.ConnectionError("sin red")])
    assert cr.crossref_retraction("10.1/x", {}) == (None, [], "error")
    patch_net(monkeypatch, [FakeResp(200, None)])    # 200 con cuerpo no-json
    assert cr.crossref_retraction("10.1/x", {}) == (None, [], "error")


def test_crossref_retraction_updated_by_como_mapa_no_revienta(monkeypatch):
    """`check_retractions.py:159` — `for upd in msg.get("updated-by", []) or []`.

    Si Crossref devuelve un mapa donde el lector espera lista, el `for` itera las CLAVES
    (strings) y `upd.get` revienta. `crossref_retraction` promete tolerancia (todos sus otros
    caminos de error devuelven `(None, [])`); esta forma no está cubierta y se lleva puesta la
    cadena de ingest."""
    class FakeResp:
        status_code = 200
        headers: dict = {}

        def json(self):
            return {"message": {"updated-by": {"0": {"type": "retraction", "DOI": "10.1/r"}}}}

    monkeypatch.setattr(cr, "requests",
                        type("R", (), {"get": staticmethod(lambda *a, **k: FakeResp()),
                                       "RequestException": Exception})())
    assert cr.crossref_retraction("10.1/x", {}) == (None, [], "ok")


# ── main() ───────────────────────────────────────────────────────────────────

def run_main(monkeypatch, argv=()):
    monkeypatch.setattr(sys, "argv", ["check_retractions.py", *argv])
    return cr.main()


def test_main_marca_y_es_idempotente(toy_vault, monkeypatch, capsys):
    body = "# Paper\n\nExtracción LLM.\n\n---\nregla horizontal\n"
    mk_note(toy_vault.PAPERS, "2020retR...1..1R",
            {"bibcode": "2020retR...1..1R", "title": "Un paper", "doi": "10.1/x",
             "tags": ["paper"]}, body)
    calls = []
    patch_net(monkeypatch, [FakeResp(200, RETRACTION_MSG)], calls)
    assert run_main(monkeypatch) == 1
    note = toy_vault.PAPERS / "2020retR...1..1R.md"
    fm = read_fm(note)
    assert fm["retracted"] is True
    assert fm["retraction"]["type"] == "retraction" and fm["retraction"]["date"] == "2021-05-03"
    assert body.strip() in note.read_text(encoding="utf-8")   # cuerpo intacto
    assert len(calls) == 1
    # segunda corrida: no re-consulta, sigue saliendo 1 (sigue retractado)
    assert run_main(monkeypatch) == 1
    assert len(calls) == 1
    assert "ya marcado" in capsys.readouterr().out


def test_main_limpio_no_marca(toy_vault, monkeypatch):
    mk_note(toy_vault.PAPERS, "2020okA....1..1A",
            {"bibcode": "2020okA....1..1A", "title": "Sano", "doi": "10.1/ok", "tags": ["paper"]}, "")
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})])
    assert run_main(monkeypatch) == 0
    assert "retracted" not in read_fm(toy_vault.PAPERS / "2020okA....1..1A.md")


def test_main_fallback_por_titulo_sin_doi(toy_vault, monkeypatch, capsys):
    mk_note(toy_vault.PAPERS, "1990oldR...1..1R",
            {"bibcode": "1990oldR...1..1R", "title": "RETRACTED: Old result",
             "doi": None, "tags": ["paper"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 1
    fm = read_fm(toy_vault.PAPERS / "1990oldR...1..1R.md")
    assert fm["retracted"] is True
    assert "title-prefix" in fm["retraction"]["source"]
    assert calls == []                               # sin DOI no consulta Crossref


CORRIGENDUM_MSG = {"message": {"updated-by": [
    {"type": "Corrigendum", "DOI": "10.1/corr",
     "updated": {"date-parts": [[2023, 7, 1]]}, "source": "publisher"}]}}


def test_main_corrección_se_estampa_sin_retractar(toy_vault, monkeypatch, capsys):
    """#52: erratum/corrigendum/EoC NO marcan `retracted` (el paper sigue citable) pero SÍ se
    persisten en `corrections` — antes se imprimían a stdout y se perdían. Exit 0: no bloquea."""
    body = "# Paper\n\nExtracción LLM.\n"
    mk_note(toy_vault.PAPERS, "2020errE...1..1E",
            {"bibcode": "2020errE...1..1E", "title": "Con errata", "doi": "10.1/e",
             "tags": ["paper"]}, body)
    patch_net(monkeypatch, [FakeResp(200, CORRIGENDUM_MSG)])
    assert run_main(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "corrección publicada (corrigendum) — anotada en `corrections`" in out
    note = toy_vault.PAPERS / "2020errE...1..1E.md"
    fm = read_fm(note)
    assert "retracted" not in fm
    assert fm["corrections"] == [{"type": "corrigendum", "notice_doi": "10.1/corr",
                                  "date": "2023-07-01", "source": "publisher"}]
    assert body.strip() in note.read_text(encoding="utf-8")      # cuerpo intacto
    # segunda corrida: mismo estado → no re-estampa (idempotente), pero sigue avisando
    before = note.read_text(encoding="utf-8")
    patch_net(monkeypatch, [FakeResp(200, CORRIGENDUM_MSG)])
    assert run_main(monkeypatch) == 0
    assert "ya anotada" in capsys.readouterr().out
    assert note.read_text(encoding="utf-8") == before


def test_main_corrección_nueva_reemplaza_la_lista(toy_vault, monkeypatch):
    """Una EoC posterior a un corrigendum ya anotado: la lista se reemplaza entera (el bloque
    viejo, ítems `-` incluidos, no queda duplicado) y el resto del frontmatter sobrevive."""
    mk_note(toy_vault.PAPERS, "2020eocE...1..1E",
            {"bibcode": "2020eocE...1..1E", "title": "En duda", "doi": "10.1/eoc",
             "tags": ["paper"], "corrections": [{"type": "corrigendum", "notice_doi": "10.1/corr",
                                                 "date": "2023-07-01", "source": "publisher"}]}, "")
    patch_net(monkeypatch, [FakeResp(200, {"message": {"updated-by": [
        {"type": "Corrigendum", "DOI": "10.1/corr", "updated": {"date-parts": [[2023, 7, 1]]},
         "source": "publisher"},
        {"type": "expression-of-concern", "DOI": "10.1/eoc-notice",
         "updated": {"date-parts": [[2024, 2, 9]]}, "source": "publisher"}]}})])
    assert run_main(monkeypatch) == 0
    fm = read_fm(toy_vault.PAPERS / "2020eocE...1..1E.md")
    assert [c["type"] for c in fm["corrections"]] == ["corrigendum", "expression-of-concern"]
    assert fm["title"] == "En duda" and fm["tags"] == ["paper"]   # el resto del YAML intacto


def test_main_retractado_y_corregido_conviven(toy_vault, monkeypatch):
    """Un paper con las dos señales: `retracted` (bloqueante) y `corrections` (backlog) coexisten
    en el mismo frontmatter — el segundo estampado no pisa al primero."""
    mk_note(toy_vault.PAPERS, "2020bothB..1..1B",
            {"bibcode": "2020bothB..1..1B", "title": "Las dos", "doi": "10.1/b",
             "tags": ["paper"]}, "cuerpo\n")
    patch_net(monkeypatch, [FakeResp(200, {"message": {"updated-by": [
        {"type": "erratum", "DOI": "10.1/err", "updated": {"date-parts": [[2021, 1, 1]]}},
        {"type": "Retraction", "DOI": "10.1/notice",
         "updated": {"date-parts": [[2022, 3, 4]]}, "source": "publisher"}]}})])
    assert run_main(monkeypatch) == 1                             # la retracción sigue gateando
    fm = read_fm(toy_vault.PAPERS / "2020bothB..1..1B.md")
    assert fm["retracted"] is True and fm["retraction"]["type"] == "retraction"
    assert [c["type"] for c in fm["corrections"]] == ["erratum"]


def test_main_nota_no_parseable_es_no_pudo_chequear(toy_vault, monkeypatch, capsys):
    """Regresión (hallazgo 4) + issue 0.1: una nota con YAML roto no se saltea en silencio Y el
    proceso NO cierra en verde. Ese paper quedó SIN chequear contra Crossref, y "no encontré
    retractados" sobre un paper que nadie miró es el falso limpio que D-43 prohíbe — justo en la
    frontera dura. rc 2 = no pudo chequear."""
    p = toy_vault.PAPERS / "2020rotoX..1..1X.md"
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: RETRACTED: sin comillas\ntags:\n- paper\n---\ncuerpo\n",
                 encoding="utf-8")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 2
    assert "sin frontmatter parseable" in capsys.readouterr().out
    assert calls == []


def test_main_saltea_notas_no_paper(toy_vault, monkeypatch):
    mk_note(toy_vault.PAPERS, "no-paper", {"doi": "10.1/x", "tags": ["query"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch) == 0
    assert calls == []


def test_main_paper_puntual(toy_vault, monkeypatch, capsys):
    mk_note(toy_vault.PAPERS, "2020unoA...1..1A",
            {"bibcode": "2020unoA...1..1A", "title": "t", "doi": "10.1/a", "tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2020dosB...1..1B",
            {"bibcode": "2020dosB...1..1B", "title": "t", "doi": "10.1/b", "tags": ["paper"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch, ["--paper", "2020unoA...1..1A"]) == 0
    assert len(calls) == 1
    # issue 0.1: pedir un bibcode que no existe es una PRECONDICIÓN ausente, no un chequeo limpio
    assert run_main(monkeypatch, ["--paper", "2020nadaX..1..1X"]) == 2
    assert "no existe" in capsys.readouterr().out


# ── modo --slug (la cadena chequea SÓLO los papers del ingest, issue #24) ────

def mk_ads_json(root, slug, records):
    d = root / "build" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"records": records}), encoding="utf-8")


def test_main_slug_solo_papers_del_ingest(toy_vault, monkeypatch):
    """--slug: chequea los bibcodes RELEVANTES de build/<slug>/ads.json; el resto de la
    bóveda (otros ingests) no se re-consulta — ese es todo el punto del modo."""
    for bib, doi in (("2020unoA...1..1A", "10.1/a"), ("2020dosB...1..1B", "10.1/b"),
                     ("2020ajenoC..1..1C", "10.1/c")):
        mk_note(toy_vault.PAPERS, bib, {"bibcode": bib, "title": "t", "doi": doi,
                                        "tags": ["paper"]}, "")
    mk_ads_json(toy_vault.ROOT, "test_star",
                [{"bibcode": "2020unoA...1..1A", "relevant": True},
                 {"bibcode": "2020dosB...1..1B", "relevant": False},    # no-core: sin nota real
                 {"bibcode": "2020sinNota.1..1N", "relevant": True}])   # core sin nota en disco
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch, ["--slug", "test_star"]) == 0
    assert len(calls) == 1 and "10.1/a" in calls[0]   # sólo el core CON nota en disco


def test_main_slug_offads_sources_y_extra_core(toy_vault, monkeypatch):
    """Tema off-ADS/mixto sin ads.json: los papers salen de sources[].key + extra_core."""
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "GP", "area": "methods", "concept": "gp",
                                        "source": "web",
                                        "sources": [{"key": "2006Rasmussen", "doi": "10.1/r"}],
                                        "extra_core": [{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "test"}]}})
    mk_note(toy_vault.PAPERS, "2006Rasmussen",
            {"bibcode": "2006Rasmussen", "title": "t", "doi": "10.1/r", "tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2012PASP..124.1015B",
            {"bibcode": "2012PASP..124.1015B", "title": "t", "doi": "10.1/b", "tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2020ajenoC..1..1C",
            {"bibcode": "2020ajenoC..1..1C", "title": "t", "doi": "10.1/c", "tags": ["paper"]}, "")
    calls = []
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], calls)
    assert run_main(monkeypatch, ["--slug", "gp"]) == 0
    assert len(calls) == 2                           # sources + extra_core; el ajeno no


def test_slug_notes_extra_core_escalar_no_se_desarma_en_letras(toy_vault):
    """`check_retractions.py:202` (y sus gemelos `query_ads.py:910`, `ingest_theme.py:263`) —
    `[b for b in (meta.get("extra_core") or []) if b]`.

    `extra_core: 2020ApJ...900....1X` sin corchetes es YAML válido y es lo que sale de agregar UN
    bibcode a mano (el caso que documentan `append-knowledge` y `ingest-star`: "aceptado →
    extra_core"). El `or []` no dispara y la comprensión recorre el string: 18 "bibcodes" de una
    letra. Consecuencia en este sitio: la nota real NUNCA se chequea contra Crossref y el paso de
    retracciones de la cadena cierra en verde sin haber mirado nada — falso limpio en la frontera
    dura de la bóveda."""
    write_yaml(cfg.THEMES_YAML, {"tema": {"title": "T", "area": "methods", "concept": "c",
                                          "source": "ads", "extra_core": [{"bibcode": "2020ApJ...900....1X", "via": "usuario", "motivo": "test"}]}})
    mk_note(cfg.PAPERS, "2020ApJ...900....1X", {"tags": ["paper"], "bibcode": "2020ApJ...900....1X"})
    notas = cr.slug_notes("tema")
    assert [p.stem for p in notas] == ["2020ApJ...900....1X"], (
        "el extra_core se desarmó en letras: la nota real no entró al chequeo de retracciones")


def test_slug_notes_sources_escalar(toy_vault):
    """`check_retractions.py:201` — `[s.get("key") for s in (meta.get("sources") or []) if s.get("key")]`.

    Mismo `sources:` escalar que en `ingest_theme.ingest_offads` (ver `test_ingest_theme.py`),
    otro consumidor: acá ni siquiera hay un `sys.exit` que esquivar — el `AttributeError` sale
    directo. El contrato del paso es "chequear los papers de ESTE ingest"; lo que hace es matar
    la cadena."""
    write_yaml(cfg.THEMES_YAML, {"tema": {"title": "T", "area": "methods", "concept": "c",
                                          "source": "web", "sources": "2006Rasmussen"}})
    mk_note(cfg.PAPERS, "2006Rasmussen", {"tags": ["paper"], "bibcode": "2006Rasmussen"})
    assert [p.stem for p in cr.slug_notes("tema")] == ["2006Rasmussen"]


def test_main_slug_sin_fuentes_es_exit_2(toy_vault, monkeypatch, capsys):
    """Issue 0.1 — el adversario directo del exit 1 sobrecargado: sin `ads.json` ni entrada en
    `themes.yaml` no hay nada que chequear, y hasta 1.23.1 eso salía **1**, el mismo código que
    "detectó papers retractados". `ingest_star` traducía cualquier rc≠0 a esa frase: la cadena
    abortaba con un mensaje falso. Ahora rc 2 = no pudo chequear, y `slug_notes` levanta
    `NothingToCheck` en vez de matar el proceso."""
    assert run_main(monkeypatch, ["--slug", "fantasma"]) == 2
    assert "nada que chequear" in capsys.readouterr().out


def test_slug_notes_no_mata_el_proceso(toy_vault):
    """`slug_notes` es una función de librería: informa con una excepción propia y deja que
    `main()` decida el código de salida (antes hacía `sys.exit`, que fija el 1 desde adentro)."""
    with pytest.raises(cr.NothingToCheck, match="nada que chequear"):
        cr.slug_notes("fantasma")


def test_main_slug_y_paper_excluyentes(toy_vault, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["--slug", "x", "--paper", "y"])
    assert "excluyentes" in capsys.readouterr().err


# ── issue 0.1 · el exit code deja de estar sobrecargado (0 limpio / 1 retractados / 2 no pudo) ──
#
# Hasta 1.23.1 `main()` devolvía 1 SÓLO con retractados, pero `slug_notes` hacía `sys.exit(str)`
# —exit 1 también— cuando no había nada que chequear, y `ingest_star.py:66-67` traducía CUALQUIER
# rc≠0 a "detectó papers retractados". Con D-45 esa misma pasada va a cubrir cinco eventos: el
# código ambiguo se arregla ANTES de apoyarle una feature encima.

def test_exit_2_sin_papers_dir(toy_vault, monkeypatch, capsys):
    """Sin `vault/wiki/papers/` no hay chequeo posible. Salía 0 ("nada que chequear"), que la
    cadena lee como *corrió y está limpio*: un cero que nadie midió."""
    import shutil
    if toy_vault.PAPERS.exists():
        shutil.rmtree(toy_vault.PAPERS)
    assert run_main(monkeypatch) == 2
    assert "no pudo chequear" in capsys.readouterr().out.lower()


def test_exit_2_papers_dir_vacio(toy_vault, monkeypatch):
    toy_vault.PAPERS.mkdir(parents=True, exist_ok=True)
    assert run_main(monkeypatch) == 2


def test_errores_sin_retractados_exit_2(toy_vault, monkeypatch, capsys):
    """El falso limpio que D-43 prohíbe: Crossref revienta en el ÚNICO paper del corpus y el
    proceso salía **0**. Nadie chequeó nada, y la cadena siguió como si la frontera dura estuviera
    verificada.  @inv INV-87"""
    mk_note(toy_vault.PAPERS, "2020netA...1..1A",
            {"bibcode": "2020netA...1..1A", "title": "t", "doi": "10.1/a", "tags": ["paper"]}, "")
    patch_net(monkeypatch, [real_requests.ConnectionError("sin red")])
    assert run_main(monkeypatch) == 2
    out = capsys.readouterr().out
    assert "2020netA...1..1A" in out


def test_404_no_es_error_sale_0(toy_vault, monkeypatch):
    """Crossref contestó "no tengo ese DOI": es información, no un fallo de chequeo. Si contara
    como error, todo corpus con DOIs no indexados quedaría en rc 2 permanente y el código volvería
    a no distinguir nada."""
    mk_note(toy_vault.PAPERS, "2020okD....1..1D",
            {"bibcode": "2020okD....1..1D", "title": "t", "doi": "10.1/d", "tags": ["paper"]}, "")
    patch_net(monkeypatch, [FakeResp(404)])
    assert run_main(monkeypatch) == 0


def test_retractados_mandan_sobre_errores(toy_vault, monkeypatch):
    """"Retractados mandan": con retractados Y errores sale 1 (lo urgente es la fuente retractada;
    los errores van igual en el reporte). Sin esta regla un error de red podría enmascarar una
    retracción detectada bajo un código que dice "precondición ausente"."""
    mk_note(toy_vault.PAPERS, "2020retR...1..1R",
            {"bibcode": "2020retR...1..1R", "title": "t", "doi": "10.1/r", "tags": ["paper"]}, "")
    mk_note(toy_vault.PAPERS, "2020netA...1..1A",
            {"bibcode": "2020netA...1..1A", "title": "t", "doi": "10.1/a", "tags": ["paper"]}, "")
    # orden de glob: ...netA antes que ...retR
    patch_net(monkeypatch, [real_requests.ConnectionError("sin red"),
                            FakeResp(200, RETRACTION_MSG)])
    assert run_main(monkeypatch) == 1


def test_exit_1_solo_con_retractados(toy_vault, monkeypatch):
    """Las dos ramas limpias, explícitas: retractado → 1, sano y chequeado → 0."""
    mk_note(toy_vault.PAPERS, "2020okA....1..1A",
            {"bibcode": "2020okA....1..1A", "title": "Sano", "doi": "10.1/ok", "tags": ["paper"]}, "")
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})])
    assert run_main(monkeypatch) == 0
    patch_net(monkeypatch, [FakeResp(200, RETRACTION_MSG)])
    assert run_main(monkeypatch, ["--force"]) == 1


# ── R-6: cada script se estampa a sí mismo (INV-91) ──────────────────────────

def test_slug_estampa_su_paso_en_la_cadena(toy_vault, monkeypatch):
    """@inv INV-91 — `check_retractions` es el ÚLTIMO paso de `CADENA_ESTRELLA` y era el único que
    no se estampaba: los otros seis sí. Consecuencia medida antes del fix: tras correr la cadena
    COMPLETA, `cadena_cortada()` devolvía `"check_retractions"` para **toda** estrella — un falso
    positivo permanente en la categoría del lint, que es la forma más rápida de que una categoría
    se vuelva ruido y se deje de mirar. El test que existía no lo veía porque estampaba ese paso a
    mano, algo que ninguna corrida real hace."""
    mk_note(toy_vault.PAPERS, "2020ok....1..1X",
            {"bibcode": "2020ok....1..1X", "title": "Sano", "doi": "10.1/ok", "tags": ["paper"]})
    build = cfg.ROOT / "build" / "test_star"
    build.mkdir(parents=True, exist_ok=True)
    (build / "ads.json").write_text(
        json.dumps({"records": [{"bibcode": "2020ok....1..1X", "relevant": True}]}),
        encoding="utf-8")
    patch_net(monkeypatch, [FakeResp(200, {"message": {}})], [])
    for paso in ("query_ads", "fetch_arxiv", "fetch_pdf", "fetch_ground_truth",
                 "make_notes", "extract_fulltext"):
        cfg.save_paso("test_star", paso)
    assert cfg.cadena_cortada("test_star") == "check_retractions"   # el estado previo al paso
    assert run_main(monkeypatch, ["--slug", "test_star"]) == 0
    assert cfg.cadena_cortada("test_star") is None, (
        "la cadena completa no puede reportarse como cortada")
    pasos = [p["paso"] for p in cfg.load_cadena("test_star")]
    assert pasos.count("check_retractions") == 1

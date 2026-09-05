"""ingest_theme: despacho por `source`, validaciones de sources:, pending, copia de PDFs."""
import inspect
from pathlib import Path
import pathlib
import sys
from types import SimpleNamespace

import pytest

import ingest_theme as it
import make_notes
import lib_config as cfg
from conftest import write_yaml


@pytest.fixture
def fake_run(monkeypatch):
    """Reemplaza run(): graba (script, *args) y devuelve el rc configurado por script."""
    state = SimpleNamespace(calls=[], rcs={}, flags=[])

    def run(script, *args, flags=()):
        # firma REAL (red #3): desde INV-44 `run` acepta `flags=` —las escotillas del orquestador—;
        # un doble sin ese parámetro revienta con `TypeError` en producción y deja la suite verde.
        state.calls.append((script, *args))
        state.flags.append((script, list(flags)))
        return state.rcs.get(script, 0)
    monkeypatch.setattr(it, "run", run)
    return state


@pytest.fixture
def fake_notes(monkeypatch):
    state = SimpleNamespace(concepts=[], webs=[])
    monkeypatch.setattr(it.make_notes, "write_concept_note",
                        lambda slug, force=None: state.concepts.append((slug, force)))
    # ⚠ El doble VALIDA LA FIRMA contra la función real (red #3). Un `lambda key, **kw` traga
    # cualquier kwarg: renombrar uno en `write_web_paper_note` deja la suite entera en verde y
    # rompe todo ingest off-ADS en producción con `TypeError`. `Signature.bind` es la forma barata
    # de que el doble tenga el MISMO contrato que el real y no esconda el bug en la diferencia.
    _firma_web = inspect.signature(make_notes.write_web_paper_note)

    def _web_double(key, **kw):
        _firma_web.bind(key, **kw)      # TypeError si la firma real ya no acepta estos kwargs
        state.webs.append((key, kw))
        return True

    monkeypatch.setattr(it.make_notes, "write_web_paper_note", _web_double)
    return state


_QUERY_DEFAULT = object()


def topic(source=None, sources=None, area="methods", concept="gaussian-processes",
          query=_QUERY_DEFAULT, **extra):
    """Entrada de tema. En modo ADS (`source=None`) la `query` va poblada por default (#384: un
    tema ADS sin `query:` ni `extra_core:` no tiene vía de papers y la cadena rehúsa); en off-ADS
    no, como siempre. `query=None` la omite explícitamente."""
    entry = {"title": "Gaussian processes", "area": area, "concept": concept, **extra}
    if query is _QUERY_DEFAULT:
        query = "abs:gp" if source is None else None
    if query is not None:
        entry["query"] = query
    if source:
        entry["source"] = source
    if sources is not None:
        entry["sources"] = sources
    write_yaml(cfg.THEMES_YAML, {"gp": entry})


def run_main(monkeypatch, argv=("gp",)):
    monkeypatch.setattr(sys, "argv", ["ingest_theme.py", *argv])
    return it.main()


# ── despacho ─────────────────────────────────────────────────────────────────

def test_slug_desconocido(toy_vault, fake_run, monkeypatch):
    with pytest.raises(SystemExit, match="desconocido"):
        run_main(monkeypatch, ("no-existe",))


def test_source_invalido(toy_vault, fake_run, monkeypatch):
    topic(source="ftp")
    with pytest.raises(SystemExit, match="source desconocido"):
        run_main(monkeypatch)


def test_cadena_ads_en_orden(toy_vault, fake_run, fake_notes, monkeypatch):
    topic()                                          # sin source → ads
    assert run_main(monkeypatch) == 0
    assert [c[0] for c in fake_run.calls] == ["query_ads.py", "fetch_arxiv.py", "fetch_pdf.py",
                                              "make_notes.py", "extract_fulltext.py",
                                              "check_retractions.py", "fetch_bibtex.py"]
    assert fake_run.calls[0] == ("query_ads.py", "--theme", "gp")
    assert fake_run.calls[3] == ("make_notes.py", "--theme", "gp")
    assert fake_run.calls[-1] == ("fetch_bibtex.py", "--slug", "gp")        # sólo este ingest (#397)


def test_guardia_expansion_frena_la_cadena_ads(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """#37: el checkpoint corre también para temas, entre query_ads y fetch_arxiv."""
    import json
    from conftest import mk_note
    topic()
    recs = [{"bibcode": f"20{i:02d}core...{i:03d}A", "relevant": True, "via": "chain:references"}
            for i in range(200)]
    d = toy_vault.ROOT / "build" / "gp"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ads.json").write_text(json.dumps({"records": recs}), encoding="utf-8")
    for r in recs[:10]:
        mk_note(cfg.PAPERS, r["bibcode"], {"bibcode": r["bibcode"]})
    with pytest.raises(SystemExit, match="frenada"):
        run_main(monkeypatch)
    assert [c[0] for c in fake_run.calls] == ["query_ads.py"]
    assert "EXPANSIÓN" in capsys.readouterr().out


def test_handoff_nombra_los_pasos_salteables(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """Hermano del de `ingest_star`: el hand-off es lo que el operador lee al terminar la cadena.
    Le faltaba el contraste (3c, #72) —saltaba del retro-tag a la síntesis— y el régimen (#74), que
    es la sección propia de un concepto."""
    topic()
    assert run_main(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "(3b)" in out and "(3c)" in out and "(6b)" in out
    assert "CONTRASTE" in out and "régimen de validez" in out


def test_cadena_ads_aborta_al_primer_fallo(toy_vault, fake_run, monkeypatch):
    topic()
    fake_run.rcs["fetch_arxiv.py"] = 1
    with pytest.raises(SystemExit, match="fetch_arxiv.py falló"):
        run_main(monkeypatch)
    assert [c[0] for c in fake_run.calls] == ["query_ads.py", "fetch_arxiv.py"]


def test_ads_retraccion_detectada_no_es_fallo(toy_vault, fake_run, fake_notes, monkeypatch):
    topic()
    fake_run.rcs["check_retractions.py"] = 1
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    assert "retractados" in str(exc.value) and "falló" not in str(exc.value)


def test_ads_con_sources_aborta(toy_vault, fake_run, monkeypatch, capsys):
    """⚠ Contrato cambiado en #78: antes AVISABA y seguía —descartando bibliografía declarada—, hoy
    aborta nombrando el `source:` que sí la procesa. Un aviso que no frena se pierde en el scroll."""
    topic(sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    with pytest.raises(SystemExit, match="sources"):
        run_main(monkeypatch)


# ── validaciones off-ADS ─────────────────────────────────────────────────────

def test_offads_sin_concept(toy_vault, fake_run, monkeypatch):
    write_yaml(cfg.THEMES_YAML, {"gp": {"title": "Gaussian processes", "area": "methods", "source": "web",
                                         "sources": [{"key": "2006Ras", "url": "https://x"}]}})
    with pytest.raises(SystemExit, match="`concept`"):
        run_main(monkeypatch)


def test_offads_sin_sources(toy_vault, fake_run, monkeypatch):
    topic(source="web")
    with pytest.raises(SystemExit, match="sources"):
        run_main(monkeypatch)


def test_offads_sources_escalar_no_revienta_la_cadena(toy_vault, fake_run, monkeypatch):
    """`ingest_theme.py:165` — `sources = meta.get("sources") or []`.

    Un `sources:` escalar es truthy, así que esquiva el `sys.exit` amable de la línea siguiente
    ("no declara `sources:` … listá ahí su bibliografía") y llega al `for s in sources`, que
    recorre el string: `s.get("key")` sobre un `str` → `AttributeError` pelado a mitad de la
    cadena de ingest, sin decir qué hay que arreglar en `themes.yaml`."""
    meta = {"title": "T", "area": "methods", "concept": "gp", "source": "web",
            "sources": "https://example.org/paper"}
    write_yaml(cfg.THEMES_YAML, {"tema": meta})
    with pytest.raises(SystemExit, match="sources"):
        it.ingest_offads("tema", meta, force=False)


def test_offads_key_invalida(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "SinAnio", "url": "https://x"}])
    with pytest.raises(SystemExit, match="key inválida"):
        run_main(monkeypatch)


def test_offads_url_y_pdf_ambiguo(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="local-pdfs+web",
          sources=[{"key": "2006Rasmussen", "url": "https://x", "pdf": "/tmp/x.pdf"}])
    with pytest.raises(SystemExit, match="ambiguo"):
        run_main(monkeypatch)


def test_offads_sin_url_ni_pdf(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen"}])
    with pytest.raises(SystemExit, match="no hay de dónde"):
        run_main(monkeypatch)


def test_offads_kind_no_admitido(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "pdf": "/tmp/x.pdf"}])
    with pytest.raises(SystemExit, match="admite url"):
        run_main(monkeypatch)


# ── flujos off-ADS ───────────────────────────────────────────────────────────

def test_offads_web_llama_fetch_web(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x",
                                  "title": "Gaussian processes", "year": 2000, "n_authors": 2}])
    assert run_main(monkeypatch) == 0
    (script, *args) = fake_run.calls[0]
    assert script == "fetch_web.py"
    assert args[:3] == ["gp", "2006Rasmussen", "https://x"]
    assert "--concept" in args and "gaussian-processes" in args
    assert "--n-authors" in args and "2" in args
    assert "--force" not in args
    assert fake_notes.concepts == [("gp", False)]   # el concept NUNCA se pisa


def test_offads_mixto_extra_core_corre_subcadena_ads(toy_vault, fake_run, fake_notes, monkeypatch):
    """Tema off-ADS con extra_core (papers que SÍ tienen bibcode ADS) → sub-cadena ADS + extract
    + retracciones. Antes extra_core se ignoraba en silencio en modo off-ADS."""
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}],
          extra_core=[{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "test"}])
    assert run_main(monkeypatch) == 0
    assert [c[0] for c in fake_run.calls] == \
        ["fetch_web.py", "query_ads.py", "fetch_arxiv.py", "fetch_pdf.py",
         "make_notes.py", "extract_fulltext.py", "check_sources.py", "check_retractions.py",
         "fetch_bibtex.py"]
    assert ("query_ads.py", "--theme", "gp", "--extra-only") in fake_run.calls
    assert ("make_notes.py", "--theme", "gp") in fake_run.calls


def test_offads_sin_extra_core_no_corre_ads(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    assert run_main(monkeypatch) == 0
    assert "query_ads.py" not in [c[0] for c in fake_run.calls]


def test_offads_mixto_aborta_si_falla_subcadena(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}],
          extra_core=[{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "test"}])
    fake_run.rcs["fetch_pdf.py"] = 1
    with pytest.raises(SystemExit, match="fetch_pdf.py falló"):
        run_main(monkeypatch)
    assert [c[0] for c in fake_run.calls] == ["fetch_web.py", "query_ads.py", "fetch_arxiv.py",
                                              "fetch_pdf.py"]


def test_offads_force_solo_re_baja_fuentes(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    run_main(monkeypatch, ("gp", "--force"))
    (_, *args) = fake_run.calls[0]
    assert "--force" in args
    assert fake_notes.concepts == [("gp", False)]   # --force no llega al concept


def test_offads_web_fallo_aborta_con_aviso(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    fake_run.rcs["fetch_web.py"] = 1
    with pytest.raises(SystemExit, match="1 fuente\\(s\\) fallaron"):
        run_main(monkeypatch)
    assert "FALLARON" in capsys.readouterr().out


def test_offads_pending_deriva_sin_fallar(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    # @inv INV-61
    # #123: con `paywall` la propuesta de copia libre SÍ tiene sentido (describe un fallo, y
    # encontrar no es conseguir), así que acá se mockea el resolver en vez de saltearlo — la suite
    # no sale a la red ni siquiera para el camino que en producción sí la usa.
    monkeypatch.setattr(it.discover, "resolve_pdf", lambda doi: (None, "sin copia libre (doble)"))
    topic(source="web", sources=[{"key": "1999Paywall", "pending": "paywall", "doi": "10.1/x",
                                  "pending_motivo": "IEEE detrás de paywall institucional"}])
    assert run_main(monkeypatch) == 0
    key, kw = fake_notes.webs[0]
    assert key == "1999Paywall" and kw["pending"] == "paywall"
    assert fake_run.calls == [("check_sources.py", "gp"),                   # #353: lo declarado se cruza
                              ("check_retractions.py", "--slug", "gp"),  # doi → chequeo igual
                              ("fetch_bibtex.py", "--slug", "gp")]
    out = capsys.readouterr().out
    assert "Fuentes PENDIENTES" in out and "10.1/x" in out


def test_offads_avisa_si_la_fuente_estaba_descartada(toy_vault, fake_run, fake_notes,
                                                     monkeypatch, capsys):
    """#81: el rechazo registrado tiene que HACER algo, no ser sólo un apunte. Acá la fuente la
    declara el usuario (no hay descubrimiento que filtrar), así que el equivalente de "no
    re-proponer" es avisar con el motivo — y seguir: cambió de opinión a propósito.

    D-52 lo completa: volver a declararla ES el cambio de opinión, así que la decisión vieja queda
    **anulada** en el registro (con el motivo preservado en `previa`) en vez de quedar afirmando
    "descartada por X" sobre una fuente que está ingestada. Antes el aviso pedía editar el YAML a
    mano, y nadie lo hacía."""
    cfg.save_decisiones("gp", {"2006Rasmussen": {"decision": "descartado", "fecha": "2026-01-15",
                                                 "motivo": "libro de texto general",
                                                 "origen": "fuente-declarada"}})
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    assert run_main(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "figuraba DESCARTADA en el registro (2026-01-15)" in out
    assert cfg.load_decisiones("gp")["2006Rasmussen"]["decision"] == "anulada"
    assert "libro de texto general" in out
    assert ("fetch_web.py", "gp", "2006Rasmussen", "https://x",
            "--concept", "gaussian-processes") in fake_run.calls    # avisa pero NO frena


def test_offads_avisa_si_la_fuente_se_descarto_por_url(toy_vault, fake_run, fake_notes,
                                                       monkeypatch, capsys):
    """`--drop-source` acepta la URL como clave (la fuente que no tiene una sintética), pero un item
    de `sources:` SIEMPRE trae una clave con forma de citekey — así que ese descarte no se cruzaba
    nunca con la mitad que lo consume y el aviso quedaba mudo justo en el caso para el que la url
    existe. Se busca por clave y por url."""
    cfg.save_decisiones("gp", {"https://x": {"decision": "descartado", "fecha": "2026-02-01",
                                             "motivo": "blog, no fuente citable",
                                             "origen": "fuente-declarada"}})
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    assert run_main(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "figuraba DESCARTADA en el registro (2026-02-01, por url https://x)" in out
    assert "blog, no fuente citable" in out
    # D-52: volver a declarar la fuente ES cambiar de opinión → la decisión queda ANULADA, no
    # contradiciendo lo hecho; el motivo viejo sobrevive en `previa`.
    d = cfg.load_decisiones("gp")["https://x"]
    assert d["decision"] == "anulada" and d["previa"]["motivo"] == "blog, no fuente citable"


def test_offads_fuente_no_descartada_no_avisa(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """Caso de control: una decisión de OTRA clave (o `aceptado`) no dispara el aviso."""
    cfg.save_decisiones("gp", {"2019Otro": {"decision": "descartado", "motivo": "x"},
                               "2006Rasmussen": {"decision": "aceptado", "motivo": "sí"}})
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    assert run_main(monkeypatch) == 0
    assert "DESCARTADA" not in capsys.readouterr().out


def test_offads_descarte_del_chaining_no_avisa_como_fuente_declarada(toy_vault, fake_run,
                                                                      fake_notes, monkeypatch,
                                                                      capsys):
    """Un descarte del CHAINING (`triage --drop`, sin `origen`) no tiene nada que ver con las
    fuentes declaradas de un tema off-ADS: avisar ahí es la mezcla que #81 vino a separar, y los
    otros dos consumidores del registro sí filtran."""
    cfg.save_decisiones("gp", {"2006Rasmussen": {"decision": "descartado", "fecha": "2026-01-15",
                                                 "motivo": "ruido del grafo de citas"}})
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    run_main(monkeypatch)
    assert "DESCARTADA" not in capsys.readouterr().out, (
        "un descarte del carril chaining se avisa como si fuera de fuente declarada")


def test_offads_pdf_copia_y_extrae(toy_vault, fake_run, fake_notes, monkeypatch, tmp_path):
    # @inv INV-90
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-contenido")
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": str(src)}])
    assert run_main(monkeypatch) == 0
    dest = cfg.PDFS / "gp" / "2006Rasmussen.pdf"
    assert dest.read_bytes() == b"%PDF-contenido"
    assert fake_notes.webs[0][0] == "2006Rasmussen"
    assert "pending" not in fake_notes.webs[0][1] or not fake_notes.webs[0][1].get("pending")
    assert ("extract_fulltext.py", "gp") in fake_run.calls
    assert "check_retractions.py" not in [c[0] for c in fake_run.calls]   # sin doi


def test_offads_pdf_idempotente(toy_vault, fake_run, fake_notes, monkeypatch, tmp_path, capsys):
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-v1")
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": str(src)}])
    run_main(monkeypatch)
    src.write_bytes(b"%PDF-v2")
    run_main(monkeypatch)                            # sin --force: no re-copia
    assert (cfg.PDFS / "gp" / "2006Rasmussen.pdf").read_bytes() == b"%PDF-v1"
    assert "ya existe" in capsys.readouterr().out


def test_offads_pdf_fuente_faltante_falla(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """Regresión (hallazgo 1): UNA fuente fallida → '1 fuente(s) fallaron' (no 2), y
    extract_fulltext NO corre si ningún PDF quedó en disco."""
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": "/no/existe.pdf"}])
    with pytest.raises(SystemExit, match="1 fuente\\(s\\) fallaron"):
        run_main(monkeypatch)
    assert "item salteado" in capsys.readouterr().out
    assert "extract_fulltext.py" not in [c[0] for c in fake_run.calls]


def test_offads_fallo_de_extract_se_reporta_aparte(toy_vault, fake_run, fake_notes, monkeypatch,
                                                   tmp_path):
    """Regresión (hallazgo 1): un fallo de extracción no se cuenta como 'fuente fallida'."""
    src = tmp_path / "externo.pdf"
    src.write_bytes(b"%PDF-x")
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": str(src)}])
    fake_run.rcs["extract_fulltext.py"] = 1
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch)
    assert "extract_fulltext.py falló" in str(exc.value)
    assert "fuente(s) fallaron" not in str(exc.value)


def test_offads_pdf_faltante_pero_copia_versionada(toy_vault, fake_run, fake_notes, monkeypatch, capsys):
    """--force post-clone sin la fuente externa: la copia de la bóveda se conserva, no es fallo."""
    dest = cfg.PDFS / "gp" / "2006Rasmussen.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF-versionado")
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": "/no/existe.pdf"}])
    assert run_main(monkeypatch, ("gp", "--force")) == 0
    assert dest.read_bytes() == b"%PDF-versionado"
    assert "conservo la copia" in capsys.readouterr().out


def test_offads_retraccion_detectada_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x", "doi": "10.1/x"}])
    fake_run.rcs["check_retractions.py"] = 1
    with pytest.raises(SystemExit, match="retractados"):
        run_main(monkeypatch)


def test_run_exporta_la_via_al_paso(toy_vault, monkeypatch):
    """R-6: el paso se estampa a sí mismo, pero necesita saber QUIÉN lo lanzó. `run()` lo exporta
    por entorno —no por flag— para no tocarle el CLI a cada script y para que atraviese el
    `subprocess.run`."""
    visto = {}

    def fake_run(cmd, cwd=None, env=None):
        visto["via"] = (env or {}).get(cfg.VIA_ENV)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(it.subprocess, "run", fake_run)
    assert it.run("query_ads.py", "test_star") == 0
    assert visto["via"] == "orquestador"


# ── gate de mutación: dos funciones que sobrevivían a que les vaciaran el cuerpo ──

def test_listify_curado_preserva_el_escalar(toy_vault, capsys):
    """Un `extra_core: 2020X` sin corchetes es YAML válido y la forma natural de declarar UNO.
    `cfg.as_list` lo degradaría a `[]` —perdiendo la curación en silencio, el defecto medido en
    R13— así que acá se PRESERVA la intención y se avisa para corregir la forma en origen."""
    assert it._listify_curado(["a", "b"], "extra_core") == ["a", "b"]
    assert it._listify_curado(None, "extra_core") == []
    assert it._listify_curado([], "extra_core") == []
    assert it._listify_curado("2020X", "extra_core") == ["2020X"]
    assert "está escrito como escalar" in capsys.readouterr().out


def test_repoint_source_pdf_PROPONE_y_no_edita_themes_yaml(toy_vault, capsys):
    """AUD-160 — esto reescribía `themes.yaml` **solo**, contra la doctrina que el framework escribe
    en otros dos lados: `triage.accept_source` («la config es curada y versionada, y un script que
    la edita solo convierte una decisión en un efecto colateral») y `discover.resolve_pdf` en
    `CLAUDE.md` («propone una URL y para: no edita `sources:`»).

    Tres sitios, la misma regla, y éste era el que no la cumplía. Hoy imprime la línea exacta."""
    cfg.THEMES_YAML.write_text(
        "gp:\n  # comentario que un dump YAML destruiría\n"
        "  sources:\n    - key: 2006R\n      pdf: /tmp/staging/rw.pdf\n", encoding="utf-8")
    antes = cfg.THEMES_YAML.read_text(encoding="utf-8")
    dest = cfg.PDFS / "gp" / "2006R.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF")
    it.repoint_source_pdf("2006R", "/tmp/staging/rw.pdf", dest)
    salida = capsys.readouterr().out
    assert "pdf: vault/raw/pdfs/gp/2006R.pdf" in salida and "a mano" in salida
    assert cfg.THEMES_YAML.read_text(encoding="utf-8") == antes, "la config curada no se edita sola"


def test_el_orquestador_ENTERO_deja_themes_yaml_byte_a_byte_igual(toy_vault, fake_run, fake_notes,
                                                                   monkeypatch, tmp_path, capsys):
    """#299 — el test unitario de arriba cubre la función; éste cubre la **corrida**, que es donde
    el operador (y el agente) miran. La conducta de AUD-160 es la correcta y no se toca; lo que
    faltaba era una red que hiciera fallar cualquier regresión hacia la conducta vieja, y que la
    doc dejara de prometerla — el docstring del módulo decía «se repunta solo» mientras el de su
    propia función, 145 líneas abajo, decía «PROPONE y para». Medido: 8 de 8 fuentes sin repuntar
    en una corrida real, con la doc diciendo que se repuntaban solas."""
    src = tmp_path / "staging" / "rw.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"%PDF-contenido")
    topic(source="local-pdfs", sources=[{"key": "2006Rasmussen", "pdf": str(src)}])
    antes = cfg.THEMES_YAML.read_bytes()
    assert run_main(monkeypatch) == 0
    assert cfg.THEMES_YAML.read_bytes() == antes, "la config curada no se edita sola (AUD-160)"
    salida = capsys.readouterr().out
    assert "vault/raw/pdfs/gp/2006Rasmussen.pdf" in salida and "a mano" in salida


def test_la_doc_del_modulo_no_promete_el_repunte_automatico():
    """#299 — la contradicción vivía **dentro del mismo archivo**, y el skill manda leer el header
    del orquestador («el orden canónico vive en el header — puntero, no copia»). Un agente que lee
    ahí que el repunte ya ocurrió no lo hace, y `themes.yaml` queda apuntando al staging."""
    doc = it.__doc__ or ""
    assert "repunta solo" not in doc
    assert "PROPONE" in doc and "aplicarlo es del operador" in doc
    # #376 — la semilla del schema es `themes.example.yaml`, NO `themes.yaml`. Aquél es framework
    # y viaja; éste es de la instancia y está en `merge=ours`, así que assertar sobre su redacción
    # era exigir un arreglo que por contrato no puede llegarle nunca (medido: rojo permanente en
    # las 3 instancias). La línea muerta `schema = ...` que había acá se fue con #375.
    semilla = (pathlib.Path(it.__file__).resolve().parents[1]
               / "vault" / "config" / "themes.example.yaml")
    texto = semilla.read_text(encoding="utf-8")
    assert "REPUNTA este campo solo" not in texto and "PROPONE repuntar" in texto


def test_repoint_source_pdf_no_hace_nada_sin_copia(toy_vault):
    """Sin la copia en disco no hay a dónde repuntar: repuntar a un archivo inexistente
    cambiaría un puntero muerto por otro."""
    cfg.THEMES_YAML.write_text("gp:\n  sources:\n    - pdf: /tmp/x.pdf\n", encoding="utf-8")
    antes = cfg.THEMES_YAML.read_text(encoding="utf-8")
    it.repoint_source_pdf("2006R", "/tmp/x.pdf", cfg.PDFS / "gp" / "no_existe.pdf")
    assert cfg.THEMES_YAML.read_text(encoding="utf-8") == antes


# ── #80 · un libro no es un fallo de extracción, y `pending` no lo sabía decir ───────────────────

def test_pending_fuera_del_vocabulario_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    """`pending` se escribía **verbatim** en la nota, sin vocabulario ni validación: un typo
    (`paywal`) entraba mudo y el lint lo listaba como precondición legítima.

    Es la familia de `role` y de `via`: un campo con vocabulario cerrado que nadie valida deja al
    consumidor leyendo un valor que no significa nada."""
    topic(source="web", sources=[{"key": "1999Typo", "pending": "paywal", "doi": "10.1/x"}])
    with pytest.raises(SystemExit, match="pending"):
        run_main(monkeypatch)


def test_pending_adquisicion_no_es_un_fallo_y_lleva_motivo(toy_vault, fake_run, fake_notes,
                                                           monkeypatch, capsys):
    """#80: los tres valores viejos (`paywall`/`scan`/`unextractable`) describen **por qué falló la
    extracción**. Un libro que el usuario va a conseguir no es un fallo: es una adquisición con otra
    latencia, y entraba forzado como `paywall`, perdiendo el motivo real.

    Se agrega `adquisicion` y el **motivo libre obligatorio** — mismo argumento que el `--reason`
    del triage: lo que sirve en seis meses es el motivo, no la categoría."""
    topic(source="web", sources=[{"key": "2001HyvarinenBook", "pending": "adquisicion",
                                  "pending_motivo": "libro; el usuario lo consigue en la biblioteca",
                                  "doi": "10.1002/0471221317"}])
    assert run_main(monkeypatch) == 0
    key, kw = fake_notes.webs[0]
    assert key == "2001HyvarinenBook" and kw["pending"] == "adquisicion"
    assert "biblioteca" in kw["pending_motivo"]


def test_pending_sin_motivo_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    """Sin motivo, `pending` vuelve a ser una categoría pelada: en seis meses nadie sabe si la
    fuente se pidió, se descartó o se olvidó. Es la asimetría que #51 cerró del otro lado."""
    topic(source="web", sources=[{"key": "2001Libro", "pending": "adquisicion", "doi": "10.1/x"}])
    with pytest.raises(SystemExit, match="motivo"):
        run_main(monkeypatch)


def test_libro_declara_unidad_de_cita_y_alcance(toy_vault, fake_run, fake_notes, monkeypatch):
    """#80 (2 y 3): un libro rompe dos supuestos del contrato de `verify-citations`.

    (2) El fan-out asume un `.txt` que un subagente lee **entero** y del que devuelve cita textual +
    nº de línea. Un libro de 700 páginas revienta ese fan-out, y «línea 18443» no es una referencia
    utilizable: la unidad tiene que ser **página o sección**.
    (3) Casi nunca querés el libro entero, querés dos capítulos — y eso choca con el chequeo de
    **completitud**, que no tiene cómo saber que el recorte fue deliberado. Sin declararlo, un
    recorte intencional se lee como omisión."""
    topic(source="local-pdfs", sources=[
        {"key": "2001HyvarinenBook", "pdf": "/tmp/x.pdf", "unidad_cita": "pagina",
         "alcance": "caps. 6 (fastICA) y 15 (noisy ICA)", "title": "Independent Component Analysis",
         "author": "Hyvarinen", "year": 2001, "via": "usuario", "motivo": "canon del método"}])
    monkeypatch.setattr(it.Path, "exists", lambda self: True)
    run_main(monkeypatch)
    kw = fake_notes.webs[0][1]
    assert kw["unidad_cita"] == "pagina"
    assert "caps. 6" in kw["alcance"]


def test_unidad_de_cita_fuera_del_vocabulario_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    """Vocabulario CERRADO, como `role` y `via`: un typo deja al verificador sin saber cómo citar."""
    topic(source="web", sources=[{"key": "2001Libro", "url": "https://x",
                                  "unidad_cita": "paginas"}])
    with pytest.raises(SystemExit, match="unidad_cita"):
        run_main(monkeypatch)


def test_unidad_no_linea_sin_alcance_aborta(toy_vault, fake_run, fake_notes, monkeypatch):
    """Si la unidad no es la línea, es un documento largo: declarar qué parte entró es obligatorio,
    porque el chequeo de completitud no puede distinguir recorte de omisión."""
    topic(source="web", sources=[{"key": "2001Libro", "url": "https://x",
                                  "unidad_cita": "seccion"}])
    with pytest.raises(SystemExit, match="alcance"):
        run_main(monkeypatch)


def test_adquisicion_no_sale_a_la_red_a_buscar_lo_que_ya_conseguis_vos(toy_vault, fake_run,
                                                                      fake_notes, monkeypatch,
                                                                      capsys, sin_red):
    """#123: con `pending: adquisicion` la fuente no *falta* — el usuario declaró que la está
    consiguiendo él (un libro, una copia física). Consultar OpenAlex y Unpaywall en cada corrida de
    la cadena es latencia por algo ya resuelto, y la propuesta no puede servir para nada porque no
    hay copia libre que buscar.

    La red la vigila la fixture global `sin_red`, que registra el intento **aunque alguien se trague
    la excepción** — que es lo que pasaba: `resolve_pdf` degrada limpio ante un backend caído, así
    que la violación no se veía.  @inv INV-114"""
    topic(source="web", sources=[{"key": "2001Libro", "pending": "adquisicion", "doi": "10.1/x",
                                  "pending_motivo": "lo saco de la biblioteca"}])
    assert run_main(monkeypatch) == 0
    assert sin_red == [], "no se consulta ninguna API por una adquisición humana"


# ── #78 · el tema MIXTO en la dirección ADS-first ────────────────────────────────────────────────

def test_source_ads_con_sources_declaradas_aborta_diciendo_qué_poner(toy_vault, fake_run,
                                                                     fake_notes, monkeypatch):
    """#78: `source: ads` **ignoraba** `sources:` con un warning y seguía. Eso descarta bibliografía
    que el usuario declaró — el fundamento canónico de un método casi nunca está en ADS, y es
    justamente lo que la lista existe para traer.

    Desde #104 la capacidad existe en la otra dirección (`source: web|local-pdfs*` + `query:` corre
    el descubrimiento ADS **completo**), así que lo que falta no es una feature: es que el modo
    equivocado deje de **tragarse la lista en silencio** y diga qué escribir. Un aviso que no frena
    se pierde en el scroll y la cadena cierra «bien» con la mitad de la bibliografía afuera.

    @inv INV-123"""
    topic(source="ads", query='abs:"independent component"',
          sources=[{"key": "1994Comon", "pdf": "/tmp/x.pdf", "via": "usuario", "motivo": "canon"}])
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch)
    msg = str(e.value)
    assert "sources" in msg and "local-pdfs" in msg, "nombra el `source:` que sí las procesa"
    assert "query" in msg, "y aclara que la mitad ADS se sigue descubriendo igual (#104)"


def test_source_ads_sin_sources_sigue_andando(toy_vault, fake_run, fake_notes, monkeypatch):
    """Contra-caso: el modo ADS puro no se toca. El aborto es sólo para la config contradictoria."""
    topic(source="ads", query='abs:"independent component"')
    assert run_main(monkeypatch) == 0


def test_sin_doi_ni_extra_core_el_chequeo_de_retracciones_lo_DICE(toy_vault, fake_run, fake_notes,
                                                                  monkeypatch, capsys):
    """AUD-159 — el paso se salteaba **en silencio**, y el silencio se lee como «corrió y limpio».

    La cadena cierra igual (sin DOI ni bibcode no hay a quién preguntarle a Crossref: es una
    propiedad de las fuentes, no un fallo), pero un paso que no corrió tiene que decirlo — misma
    doctrina que D-43 y que el `rc 2` de `check_retractions` con población vacía."""
    topic(source="web", sources=[{"key": "2006Rasmussen", "url": "https://x",
                                  "via": "usuario", "fecha": "2026-08-28", "motivo": "canon"}])
    run_main(monkeypatch)
    salida = capsys.readouterr().out
    assert "retracciones NO EVALUADO" in salida and "ninguna fuente declara `doi`" in salida


# ── #211 · deadlock del tema mixto ───────────────────────────────────────────

def test_mixto_con_query_y_sin_sources_corre_la_mitad_ads(toy_vault, fake_run, fake_notes,
                                                          monkeypatch, capsys):
    """#211 — el guard viejo abortaba con `sources:` vacía, o sea medía la premisa que #104 rompió.

    Un tema off-ADS MIXTO con `query:` poblada y las fuentes todavía sin declarar es el caso normal
    de la primera corrida (el paso 0b del skill manda barrer los backends ANTES de declarar nada a
    mano, y el anclaje necesita la mitad ADS ya bajada). Con el guard viejo eso era un deadlock.
    """
    topic(source="local-pdfs", sources=[], query='abs:"independent component"')
    assert run_main(monkeypatch) == 0
    scripts = [c[0] for c in fake_run.calls]
    assert scripts == ["query_ads.py", "fetch_arxiv.py", "fetch_pdf.py", "make_notes.py",
                       "extract_fulltext.py", "check_retractions.py", "fetch_bibtex.py"]
    assert ("query_ads.py", "--theme", "gp") in fake_run.calls      # completa, no --extra-only
    # y lo DICE: sin el aviso, correr la mitad se lee como haber corrido todo
    assert "SIN fuentes declaradas" in capsys.readouterr().out


def test_mixto_con_query_extrae_lo_que_bajo(toy_vault, fake_run, fake_notes, monkeypatch):
    """#211 (segunda mitad) — la mitad ADS baja PDFs con `fetch_pdf` y su extracción sale del
    `extract_fulltext` compartido, cuya condición era `n_pdf or extra`: con `query:` y sin
    `extra_core:` ni PDFs locales, el corpus se bajaba y NO se extraía."""
    topic(source="local-pdfs", sources=[], query='abs:"independent component"')
    assert run_main(monkeypatch) == 0
    assert "extract_fulltext.py" in [c[0] for c in fake_run.calls]


def test_mixto_con_query_chequea_retracciones(toy_vault, fake_run, fake_notes, monkeypatch):
    """#211 — ídem para el cierre de retracciones: los papers ADS del tema mixto traen DOI, así
    que hay a quién preguntarle a Crossref aunque `sources:` esté vacía."""
    topic(source="local-pdfs", sources=[], query='abs:"independent component"')
    assert run_main(monkeypatch) == 0
    assert "check_retractions.py" in [c[0] for c in fake_run.calls]


def test_offads_sin_ninguna_via_de_papers_aborta(toy_vault, fake_run, monkeypatch):
    """#211 — el guard sigue existiendo: aborta cuando NO hay ninguna vía (ni sources, ni query,
    ni extra_core), que es la condición que de verdad deja a la cadena sin nada que hacer."""
    topic(source="web", sources=[])
    with pytest.raises(SystemExit, match="ninguna vía de papers"):
        run_main(monkeypatch)


def test_mixto_solo_con_extra_core_y_sin_sources_no_aborta(toy_vault, fake_run, fake_notes,
                                                           monkeypatch):
    """#211 — la tercera cláusula del guard: `extra_core:` sola también es una vía de papers.
    Sin ella, un tema cuya mitad astro se enumeró a mano (sin `query:`) seguiría abortando."""
    topic(source="web", sources=[],
          extra_core=[{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "test"}])
    assert run_main(monkeypatch) == 0
    assert ("query_ads.py", "--theme", "gp", "--extra-only") in fake_run.calls


# ── #367 · cerrar un `pending` off-ADS copia el PDF y dejaba la nota con `pdf: null` ──

def test_cerrar_un_pending_offads_estampa_pdf_en_la_nota_que_YA_existe(toy_vault, fake_run, fake_notes,
                                                                        monkeypatch, tmp_path):
    """#367 — #304 arregló «el PDF que aparece después nunca se linkea» en el carril ADS y el
    backfill, y el carril off-ADS quedó afuera. Y ahí cerrar un `pending` es el caso NORMAL, no el
    borde: la nota ya existe (el stub nació con `pending_source` en la corrida anterior), así que la
    rama «crear el stub» —la única que estampaba— no se toma nunca. Medido: 1 de 1 fuente cerrada
    desde `pending` quedó con `pdf: null` con el PDF en disco."""
    src = tmp_path / "remes.pdf"; src.write_bytes(b"%PDF-1.4\n")
    cfg.PAPERS.mkdir(parents=True, exist_ok=True)
    (cfg.PAPERS / "2011Remes.md").write_text(
        "---\nbibcode: 2011Remes\ntags: [paper]\npdf: null\nthesis_links: [gp]\n---\n# R\n",
        encoding="utf-8")
    topic(source="local-pdfs", sources=[{"key": "2011Remes", "pdf": str(src), "title": "t",
                                         "author": "Remes", "year": 2011}])
    assert run_main(monkeypatch) == 0
    fm = cfg.split_fm((cfg.PAPERS / "2011Remes.md").read_text(encoding="utf-8"))
    assert fm.get("pdf") == "../../raw/pdfs/gp/2011Remes.pdf", fm.get("pdf")


def test_todo_camino_que_deposita_un_PDF_pasa_por_stamp_pdf(toy_vault, monkeypatch):
    """La red para que no vuelva a rotar (#367): `stamp_pdf` es la única definición de «`pdf:` lo
    escribe la verdad de disco, lo escriba quien lo escriba». AUD-293 (F-03): el assert sobre el
    TEXTO FUENTE de los tres depositantes pasaba con el nombre en un comentario; acá el carril
    `fetch_web` (url que sirve PDF, #242) se corre y se ESPÍA la llamada. Los otros dos tienen
    test propio de comportamiento (`test_fetch_pdf::test_main_baja_todo_relevante_sin_pdf` estampa
    por verdad de disco; `test_offads_pdf_copia_y_extrae` deja `pdf:` linkeado)."""
    import fetch_web as fw
    llamadas = []
    monkeypatch.setattr(fw.make_notes, "stamp_pdf", lambda dest, stem: llamadas.append((dest.name, stem)) or True)
    monkeypatch.setattr(fw, "content_type", lambda url: "application/pdf")
    monkeypatch.setattr(fw, "download_pdf",
                        lambda url, dest: (dest.parent.mkdir(parents=True, exist_ok=True),
                                           dest.write_bytes(b"%PDF-1.4 x"), True)[-1])
    monkeypatch.setattr(sys, "argv", ["fetch_web.py", "gp", "2015Voss",
                                      "https://arxiv.org/pdf/1502.04148", "--concept", "gaussian-processes"])
    assert fw.main() == 0
    assert llamadas == [("2015Voss.md", "2015Voss")], llamadas


# ── #384 · corpus DECLARADO con bibcode ADS: `source: ads` + `query: null` + `extra_core:` ────────

def test_tema_ads_sin_query_con_extra_core_corre_la_subcadena_extra_only(toy_vault, fake_run,
                                                                          fake_notes, monkeypatch,
                                                                          capsys):
    """#384 — un tema cuyo corpus es una lista curada de bibcodes ADS tenía que MENTIR en
    `source:` (`local-pdfs` + `sources: []`) para que la cadena corriera, y encima recibía el aviso
    de #211 («tema mixto SIN fuentes declaradas») que ahí dice lo contrario de la verdad. La
    sub-cadena `--extra-only` existía y sólo la alcanzaba el carril off-ADS."""
    topic(query=None, extra_core=[{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "canon"}])
    assert run_main(monkeypatch) == 0
    assert ("query_ads.py", "--theme", "gp", "--extra-only") in fake_run.calls
    assert [c[0] for c in fake_run.calls] == \
        ["query_ads.py", "fetch_arxiv.py", "fetch_pdf.py", "make_notes.py", "extract_fulltext.py",
         "check_retractions.py", "fetch_bibtex.py"]
    out = capsys.readouterr().out
    assert "corpus declarado" in out and "tema mixto SIN fuentes" not in out, out


def test_tema_ads_con_query_sigue_sin_extra_only(toy_vault, fake_run, fake_notes, monkeypatch):
    """#384 — con `query:` poblada el descubrimiento ADS completo sigue igual (y `extra_core` es
    el override de siempre, que `query_ads` mergea solo)."""
    topic(query="abs:gp", extra_core=[{"bibcode": "2012PASP..124.1015B", "via": "usuario", "motivo": "x"}])
    assert run_main(monkeypatch) == 0
    assert ("query_ads.py", "--theme", "gp") in fake_run.calls
    assert not any("--extra-only" in c for c in fake_run.calls)


def test_tema_ads_sin_query_ni_extra_core_rehusa_con_las_vias(toy_vault, fake_run, fake_notes,
                                                             monkeypatch):
    """#384 — sin `query:` ni `extra_core:` un tema ADS no tiene ninguna vía de papers: se dice
    antes de correr nada, con las dos salidas nombradas (el guard de off-ADS ya lo hacía)."""
    topic(query=None)
    with pytest.raises(SystemExit) as e:
        run_main(monkeypatch)
    assert "ninguna vía" in str(e.value) and "extra_core" in str(e.value) and "query" in str(e.value)
    assert fake_run.calls == []

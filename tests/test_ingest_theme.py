"""ingest_theme: despacho por `source`, validaciones de sources:, pending, copia de PDFs."""
import inspect
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


def topic(source=None, sources=None, area="methods", concept="gaussian-processes", **extra):
    entry = {"title": "Gaussian processes", "area": area, "concept": concept, **extra}
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
                                              "check_retractions.py"]
    assert fake_run.calls[0] == ("query_ads.py", "--theme", "gp")
    assert fake_run.calls[3] == ("make_notes.py", "--theme", "gp")
    assert fake_run.calls[-1] == ("check_retractions.py", "--slug", "gp")   # sólo este ingest


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


def test_ads_con_sources_avisa(toy_vault, fake_run, monkeypatch, capsys):
    topic(sources=[{"key": "2006Rasmussen", "url": "https://x"}])
    run_main(monkeypatch)
    assert "se ignora en modo ADS" in capsys.readouterr().out


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
         "make_notes.py", "extract_fulltext.py", "check_retractions.py"]
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
    topic(source="web", sources=[{"key": "1999Paywall", "pending": "paywall", "doi": "10.1/x"}])
    assert run_main(monkeypatch) == 0
    key, kw = fake_notes.webs[0]
    assert key == "1999Paywall" and kw["pending"] == "paywall"
    assert fake_run.calls == [("check_retractions.py", "--slug", "gp")]   # doi → chequeo igual
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


def test_repoint_source_pdf_repunta_a_la_copia_de_la_boveda(toy_vault, capsys):
    """El path declarado suele ser staging efímero (descargas, scratchpad): al limpiarse deja un
    puntero muerto en `themes.yaml`. La que vale es la copia versionada."""
    write_yaml(cfg.THEMES_YAML, {})
    cfg.THEMES_YAML.write_text(
        "gp:\n  title: GP     # comentario que un dump YAML destruiría\n"
        "  sources:\n    - key: 2006R\n      pdf: /tmp/staging/rw.pdf\n", encoding="utf-8")
    dest = cfg.PDFS / "gp" / "2006R.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF")
    it.repoint_source_pdf("2006R", "/tmp/staging/rw.pdf", dest)
    txt = cfg.THEMES_YAML.read_text(encoding="utf-8")
    assert "vault/raw/pdfs/gp/2006R.pdf" in txt and "/tmp/staging" not in txt
    assert "comentario que un dump YAML destruiría" in txt, "reescritura quirúrgica de la línea"


def test_repoint_source_pdf_no_adivina_si_matchea_varias(toy_vault, capsys):
    """Si el path declarado no matchea exactamente UNA línea `pdf:`, se avisa y se deja a mano:
    repuntar la equivocada es peor que no repuntar."""
    cfg.THEMES_YAML.write_text(
        "gp:\n  sources:\n    - pdf: /tmp/x.pdf\n    - pdf: /tmp/x.pdf\n", encoding="utf-8")
    dest = cfg.PDFS / "gp" / "2006R.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF")
    antes = cfg.THEMES_YAML.read_text(encoding="utf-8")
    it.repoint_source_pdf("2006R", "/tmp/x.pdf", dest)
    assert "no repunté" in capsys.readouterr().out
    assert cfg.THEMES_YAML.read_text(encoding="utf-8") == antes


def test_repoint_source_pdf_no_hace_nada_sin_copia(toy_vault):
    """Sin la copia en disco no hay a dónde repuntar: repuntar a un archivo inexistente
    cambiaría un puntero muerto por otro."""
    cfg.THEMES_YAML.write_text("gp:\n  sources:\n    - pdf: /tmp/x.pdf\n", encoding="utf-8")
    antes = cfg.THEMES_YAML.read_text(encoding="utf-8")
    it.repoint_source_pdf("2006R", "/tmp/x.pdf", cfg.PDFS / "gp" / "no_existe.pdf")
    assert cfg.THEMES_YAML.read_text(encoding="utf-8") == antes

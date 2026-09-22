"""HAL como carril antes de declarar un hueco (#505): la regla de matcheo y la red declarada."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hal  # noqa: E402

COMON = {"halId_s": "hal-00460653", "title_s": ["Handbook of Blind Source Separation"],
         "authLastName_s": ["Comon", "Jutten"], "producedDateY_i": 2010, "doiId_s": None,
         "fileMain_s": None}


class R:
    def __init__(self, docs=None, status=200, text=""):
        self.status_code, self._docs, self.text = status, docs or [], text

    def json(self):
        return {"response": {"docs": self._docs}}


def _get(respuestas):
    pedidos = []

    def get(url, params=None, **k):
        pedidos.append((params or {}).get("q", url))
        return respuestas.pop(0)
    return get, pedidos


def test_505_sin_DOI_en_HAL_lo_encuentra_por_TITULO_EXACTO_autor_y_anio():
    """El registro de Comon & Jutten no lleva el DOI: por DOI no aparece, por título exacto sí."""
    get, pedidos = _get([R([]), R([COMON])])
    rec, por_que, sin_medir = hal.find(get, doi="10.1016/C2009-0-19334-0",
                                       title="Handbook of blind source separation",
                                       first_author="Comon, Pierre", year=2010)
    assert rec and rec["halid"] == "hal-00460653" and not sin_medir, (rec, por_que)
    assert "wt=bibtex" in rec["bibtex_url"] and "halId_s%3Ahal-00460653" in rec["bibtex_url"]
    assert len(pedidos) == 2


def test_505_NUNCA_por_parecido_ni_con_otro_autor_ni_otro_anio():
    """⛔ Título aproximado, primer autor distinto o año a más de ±1: no hay candidato."""
    casi = dict(COMON, title_s=["Handbook of Blind Source Separation: ICA and applications"])
    otro_autor = dict(COMON, authLastName_s=["Jutten", "Comon"])
    otro_anio = dict(COMON, producedDateY_i=2014)
    for doc in (casi, otro_autor, otro_anio):
        get, _ = _get([R([doc])])
        rec, por_que, sin_medir = hal.find(get, title="Handbook of blind source separation",
                                           first_author="Comon, Pierre", year=2010)
        assert rec is None and "ninguno exacto" in por_que and not sin_medir, doc


def test_505_HAL_que_no_contesta_NO_es_un_veredicto():
    """#468 — una caída no se lee como «HAL no tiene nada»: vuelve como no medido."""
    get, _ = _get([R(status=503)])
    rec, por_que, sin_medir = hal.find(get, doi="10.1/x")
    assert rec is None and not por_que and "no contestó" in sin_medir


def test_505_por_DOI_basta_el_DOI():
    get, _ = _get([R([dict(COMON, doiId_s="10.1/X")])])
    rec, _, _ = hal.find(get, doi="10.1/x")
    assert rec and rec["via"] == "HAL por DOI"

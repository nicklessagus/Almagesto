"""El driver de `merge=ours` REGISTRADO destruye al sincronizar entre máquinas (#390, invierte #99).

#99 hizo obligatoria la precondición del mecanismo —`git config merge.ours.driver true`, «una vez
por clon»— porque nada la verificaba. El argumento era correcto y miraba **un solo eje**: el driver
es una regla por **path**, y git no puede condicionarla por remoto. Contra `upstream` (el template)
protege; contra `origin` (la otra máquina del mismo usuario) **descarta en silencio lo del remoto**.

Medido el 2026-09-03 en repos sintéticos, dos clones del mismo `origin` que tocan un archivo
`merge=ours`:

| configuración | resultado |
|---|---|
| driver registrado + merge de `origin` | ⛔ se pierde lo del remoto, sin conflicto |
| **sin driver** + merge de `origin` | ✅ conflicto con marcadores, las dos versiones visibles |
| **sin driver** + `git -c merge.ours.driver=true merge upstream/main` | ✅ gana la local, sin conflicto |
| sin driver + merge de `upstream` sin el `-c` | ⚠ conflicto con marcadores: degradación segura |

O sea que la receta es **no registrar el driver** y pasarlo por comando sólo al traer el template.
El chequeo del lint se invierte: reporta el clon que **sí** lo registró.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lib_config as cfg
import lint


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": str(repo)})


def _init(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    return repo


@pytest.fixture
def clon(tmp_path, monkeypatch):
    """Un repo git de verdad con `.gitattributes` declarando `merge=ours`, y un commit inicial."""
    repo = _init(tmp_path / "clon")
    (repo / ".gitattributes").write_text("vault/config/objective.yaml merge=ours\n", encoding="utf-8")
    (repo / "vault" / "config").mkdir(parents=True)
    (repo / "vault" / "config" / "objective.yaml").write_text("name: X\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "init")
    _git(repo, "remote", "add", "origin", "https://example.invalid/x.git")
    monkeypatch.setattr(cfg, "ROOT", repo)
    return repo


def test_driver_registrado_con_origin_se_reporta(clon):
    # @inv INV-68
    """El caso de #390: el clon registró el driver y tiene `origin`, así que el próximo merge de la
    otra máquina descarta lo del remoto sin conflicto y sin aviso."""
    _git(clon, "config", "merge.ours.driver", "true")
    riesgo, err = lint.merge_ours_driver_risk()
    assert err is None
    assert riesgo == ["vault/config/objective.yaml"], riesgo


def test_sin_driver_no_se_reporta(clon):
    """El estado que la receta pide, y que hasta 1.171.0 el lint reportaba como BLOQUEANTE: sin el
    driver registrado, un merge de `origin` conflictúa con marcadores en vez de perder datos, y la
    protección contra el template se consigue con `-c` en el comando."""
    assert lint.merge_ours_driver_risk() == ([], None)


def test_driver_registrado_sin_origin_no_se_reporta(clon):
    """Sin `origin` no hay eje destructivo: un clon que sólo tiene `upstream` no puede mergear la
    otra máquina. Misma doctrina que el recorte de #99 —sólo cuenta lo que tiene algo que perder—:
    un hallazgo que aparece donde no puede hacer daño se deja de mirar."""
    _git(clon, "config", "merge.ours.driver", "true")
    _git(clon, "remote", "remove", "origin")
    _git(clon, "remote", "add", "upstream", "https://example.invalid/tpl.git")
    assert lint.merge_ours_driver_risk() == ([], None)


def test_sin_gitattributes_el_chequeo_no_aplica(clon):
    """«No aplica» ≠ «no evaluado» (D-43). Sin nada declarado no hay driver que pueda destruir."""
    _git(clon, "config", "merge.ours.driver", "true")
    (clon / ".gitattributes").unlink()
    assert lint.merge_ours_driver_risk() == ([], None)


def test_sin_git_el_chequeo_no_aplica(clon, monkeypatch):
    """`merge=ours` es un mecanismo de git: sin git no hay merge que pueda descartar nada.

    Mandarlo a *no evaluado* —que cuenta para el exit— ponía en rojo toda copia sin `.git`,
    incluida la que arma `tools/mutar.py`, y ahí se detectó: el gate abortó con «la suite ya está
    roja sin mutar»."""
    monkeypatch.setattr(lint, "git_out", lambda *a: None)
    assert lint.merge_ours_driver_risk() == ([], None)


# ── La medición que sostiene la regla, contra git de verdad ──────────────────────────────────────
# Regla de método 1: un doble validaría que el cliente funciona, no que `merge=ours` se comporte
# así. Estos dos merges son los que decidieron la receta.

@pytest.fixture
def dos_maquinas(tmp_path):
    """`origin` con lo de la máquina B ya pusheado, `upstream` (template) con su propia línea, y un
    clon local A que tiene su entrada sin haber traído nada."""
    up = _init(tmp_path / "up")
    (up / ".gitattributes").write_text("log.md merge=ours\n", encoding="utf-8")
    (up / "log.md").write_text("log v1\n", encoding="utf-8")
    _git(up, "add", "-A"); _git(up, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()

    subprocess.run(["git", "clone", "-q", "--bare", str(up), str(tmp_path / "origin.git")],
                   check=True, capture_output=True)
    b = tmp_path / "B"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(b)],
                   check=True, capture_output=True)
    _git(b, "config", "user.email", "t@t"); _git(b, "config", "user.name", "t")
    (b / "log.md").write_text("log v1\nentrada de B\n", encoding="utf-8")
    _git(b, "commit", "-qam", "B"); _git(b, "push", "-q", "origin", "main")

    (up / "log.md").write_text("log v1\nlinea del TEMPLATE\n", encoding="utf-8")
    _git(up, "commit", "-qam", "template")

    a = tmp_path / "A"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(a)],
                   check=True, capture_output=True)
    _git(a, "config", "user.email", "t@t"); _git(a, "config", "user.name", "t")
    _git(a, "reset", "-q", "--hard", base)          # A arrancó atrasada, como en el incidente real
    (a / "log.md").write_text("log v1\nentrada de A\n", encoding="utf-8")
    _git(a, "commit", "-qam", "A")
    _git(a, "remote", "add", "upstream", str(up))
    _git(a, "fetch", "-q", "origin"); _git(a, "fetch", "-q", "upstream")
    return a


def _merge(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args, "-m", "m"],
                          capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(repo)}).returncode


def test_el_driver_registrado_pierde_lo_del_remoto_sin_conflicto(dos_maquinas):
    """El incidente de #390, reproducido: con el driver que #99 exigía, la entrada de la otra
    máquina desaparece del merge sin conflicto y sin aviso."""
    _git(dos_maquinas, "config", "merge.ours.driver", "true")
    rc = _merge(dos_maquinas, "merge", "origin/main")
    texto = (dos_maquinas / "log.md").read_text(encoding="utf-8")
    assert rc == 0                                  # ni siquiera hay conflicto que mirar
    assert "entrada de B" not in texto, texto       # se perdió, en silencio


def test_sin_driver_el_merge_de_origin_conflictua_con_las_dos_versiones(dos_maquinas):
    """La propiedad que hace segura la receta: lo del remoto queda VISIBLE en el working tree."""
    rc = _merge(dos_maquinas, "merge", "origin/main")
    texto = (dos_maquinas / "log.md").read_text(encoding="utf-8")
    assert rc != 0
    assert "entrada de A" in texto and "entrada de B" in texto, texto
    assert "<<<<<<<" in texto, texto


def test_la_receta_con_c_protege_contra_el_template(dos_maquinas):
    """La otra mitad: pasar el driver por comando conserva intacta la protección de #99 contra
    `upstream`, que es para lo que `merge=ours` existe."""
    rc = _merge(dos_maquinas, "-c", "merge.ours.driver=true", "merge", "upstream/main")
    texto = (dos_maquinas / "log.md").read_text(encoding="utf-8")
    assert rc == 0
    assert texto == "log v1\nentrada de A\n", texto      # gana la local, sin conflicto


def test_olvidarse_del_c_conflictua_pero_no_pierde(dos_maquinas):
    """El costo de olvidar el flag es un conflicto, nunca datos: la degradación es segura, y eso
    es lo que hace aceptable mover la protección del `config` al comando."""
    rc = _merge(dos_maquinas, "merge", "upstream/main")
    texto = (dos_maquinas / "log.md").read_text(encoding="utf-8")
    assert rc != 0
    assert "entrada de A" in texto and "linea del TEMPLATE" in texto, texto

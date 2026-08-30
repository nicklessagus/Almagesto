#!/usr/bin/env python3
"""Refresh `tools/issues.json`, the versioned list of issue numbers the repo is allowed to cite (#292).

WHY IT EXISTS, measured in vivo on 2026-08-30. A `(#N)` was written into the code **before** the
issue existed; the next issue opened took that number, and for a few minutes five references in
`scripts/` and `docs/` resolved to an issue about something else. `CLAUDE.md` declares `(#N)` to be
the traceability mechanism of the whole framework, and regla de método nº 4 says a map that
attributes wrongly is worse than an empty one: a dangling `(#N)` is the empty map, a **collided**
one is the wrong map. The repo already guards the two neighbouring shapes —`test_docs_ejecutables`
(every test/script/config the docs name exists) and `mutar.py --trazabilidad` (every row of
`docs/trazabilidad.md` claims real coverage)—; this is the third.

The list is **cached and versioned** on purpose: the check has to run in CI, offline, without a
GitHub token. Refresh it when closing a tanda, next to the version bump.

    python tools/refresh_issues.py            # needs `gh`, writes tools/issues.json
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

DEST = pathlib.Path(__file__).resolve().parent / "issues.json"


def fetch(limit: int = 1000) -> list:
    """`gh issue list` → `[{number, title, state}, …]`, newest first. Raises if `gh` is missing."""
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", str(limit),
         "--json", "number,title,state"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main() -> int:
    """Write the cache, or leave the old one in place saying why (never an empty one)."""
    try:
        issues = fetch()
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"no se pudo refrescar la caché de issues ({exc}) — se deja la que estaba, que es "
              f"lo correcto: una caché vacía volvería VERDE el chequeo entero (D-43).")
        return 2
    if not issues:
        print("`gh` devolvió 0 issues — no se pisa la caché (un cero que nadie midió se lee como "
              "veredicto).")
        return 2
    datos = {"fetched": subprocess.run(["date", "-I"], capture_output=True,
                                       text=True).stdout.strip(),
             "issues": sorted(({"number": i["number"], "title": i["title"], "state": i["state"]}
                               for i in issues), key=lambda i: i["number"])}
    DEST.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(datos['issues'])} issues → {DEST} (máximo: #{datos['issues'][-1]['number']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

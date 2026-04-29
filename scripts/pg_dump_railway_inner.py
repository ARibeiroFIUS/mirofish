#!/usr/bin/env python3
"""
Executar dentro do contentor Railway (railway ssh) onde DATABASE_URL existe
e pg_dump alcance postgres.railway.internal (rede privada).

Uso manual:
  railway ssh -s mirofish -- /app/backend/.venv/bin/python /caminho/para/pg_dump_railway_inner.py

Copia o ficheiro para /tmp primeiro (ex.: scp/cat num one-liner) ou garante-o na imagem.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL está vazio (usa este script apenas via `railway ssh` no serviço da app).", file=sys.stderr)
        return 1

    exe = shutil.which("pg_dump")
    if not exe:
        print("pg_dump não encontrado no PATH; instala postgresql-client-18.", file=sys.stderr)
        return 1

    outp = "/tmp/mirofish_postgres.dump"
    cmd = [
        exe,
        url,
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-f",
        outp,
    ]
    print("running:", exe, "... -f", outp, file=sys.stderr)
    subprocess.check_call(cmd)
    st = os.stat(outp)
    print(outp)
    print(st.st_size, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verificação da cadeia de hashes da trilha de auditoria (v1).

Recalcula `row_hash = sha256(prev_hash + dados canônicos)` de toda a
trilha em ordem total. Qualquer linha adulterada, removida ou inserida
fora de ordem quebra a cadeia e é reportada.

Uso: python scripts/verify_audit.py
Código de saída: 0 = íntegra; 1 = violações encontradas.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import audit_service  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        report = audit_service.verify_chain(db)
    finally:
        db.close()

    print(f"Linhas verificadas: {report.total}")
    print(f"Encadeadas OK:      {report.chained}")
    if report.legacy:
        print(f"Legadas (pré-v1, sem hash): {report.legacy}")
    if report.broken:
        print(f"\nVIOLAÇÕES ({len(report.broken)}):", file=sys.stderr)
        for violation in report.broken:
            print(f"  linha {violation['id']}: {violation['error']}", file=sys.stderr)
        return 1
    print("\nCadeia de auditoria íntegra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

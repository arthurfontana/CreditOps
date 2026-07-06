"""Verificação de integridade: detecta adulteração direta no banco/arquivos.

Re-calcula o content_hash de todas as versões congeladas e o SHA-256 de
todos os anexos, relatando divergências.

Uso: python scripts/verify_data.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Attachment, PolicyVersion  # noqa: E402
from app.services.version_service import content_hash  # noqa: E402


def main() -> int:
    db = SessionLocal()
    problems = 0
    try:
        frozen = db.scalars(
            select(PolicyVersion).where(PolicyVersion.content_hash.is_not(None))
        ).all()
        for version in frozen:
            recalculated = content_hash(version.body_md, version.structured_fields)
            if recalculated != version.content_hash:
                problems += 1
                print(
                    f"ADULTERAÇÃO? versão {version.id} "
                    f"(v{version.version_number}): hash não confere"
                )
        print(f"Versões congeladas verificadas: {len(frozen)}")

        attachments_dir = get_settings().data_path / "attachments"
        attachments = db.scalars(select(Attachment)).all()
        for attachment in attachments:
            path = attachments_dir / attachment.stored_path
            if not path.exists():
                problems += 1
                print(f"ANEXO AUSENTE: {attachment.id} ({attachment.filename})")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != attachment.sha256:
                problems += 1
                print(f"ANEXO ADULTERADO: {attachment.id} ({attachment.filename})")
        print(f"Anexos verificados: {len(attachments)}")
    finally:
        db.close()

    if problems:
        print(f"\n{problems} problema(s) encontrado(s).", file=sys.stderr)
        return 1
    print("\nIntegridade OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

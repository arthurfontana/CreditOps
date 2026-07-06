"""Backup consistente do CreditOps (banco + anexos + manifesto com hashes).

Uso:
    python scripts/backup.py [--dest backups/] [--keep 30]

Usa a API de backup do SQLite (cópia consistente com a aplicação rodando),
tar dos anexos e manifest.json com SHA-256 de todos os arquivos.
Agendar via cron ou Task Scheduler (ver docs/runbook.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do CreditOps")
    parser.add_argument("--dest", default="backups", help="diretório de destino")
    parser.add_argument("--keep", type=int, default=30, help="backups diários retidos")
    args = parser.parse_args()

    settings = get_settings()
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    attachments_dir = settings.data_path / "attachments"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(args.dest) / f"creditops-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)

    # 1. banco: cópia consistente via SQLite backup API
    db_backup = dest / "creditops.db"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(db_backup)
    with target:
        source.backup(target)
    target.close()
    source.close()

    # 2. anexos
    attachments_tar = dest / "attachments.tar.gz"
    with tarfile.open(attachments_tar, "w:gz") as tar:
        if attachments_dir.exists():
            tar.add(attachments_dir, arcname="attachments")

    # 3. manifesto
    manifest = {
        "created_at": datetime.now().isoformat(),
        "files": {
            "creditops.db": sha256_of(db_backup),
            "attachments.tar.gz": sha256_of(attachments_tar),
        },
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Backup criado em {dest}")

    # 4. retenção
    backups = sorted(Path(args.dest).glob("creditops-*"))
    for old in backups[: -args.keep] if len(backups) > args.keep else []:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
        print(f"Backup antigo removido: {old}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

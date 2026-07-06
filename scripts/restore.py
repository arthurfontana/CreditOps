"""Restore de um backup do CreditOps, validando hashes do manifesto.

Uso:
    python scripts/restore.py backups/creditops-20260706-120000

ATENÇÃO: pare a aplicação antes de restaurar. O banco e os anexos atuais
são substituídos (uma cópia .pre-restore é mantida por segurança).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
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
    parser = argparse.ArgumentParser(description="Restore do CreditOps")
    parser.add_argument("backup_dir", help="diretório do backup a restaurar")
    args = parser.parse_args()

    backup = Path(args.backup_dir)
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        print("manifest.json não encontrado — backup inválido.", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # valida integridade ANTES de tocar em qualquer coisa
    for name, expected in manifest["files"].items():
        actual = sha256_of(backup / name)
        if actual != expected:
            print(f"HASH DIVERGENTE em {name}: backup corrompido.", file=sys.stderr)
            return 1
    print("Hashes do manifesto validados.")

    settings = get_settings()
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    data_dir = settings.data_path

    # preserva o estado atual
    if db_path.exists():
        shutil.copy(db_path, db_path.with_suffix(".db.pre-restore"))
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    shutil.copy(backup / "creditops.db", db_path)

    attachments_dir = data_dir / "attachments"
    if attachments_dir.exists():
        shutil.move(str(attachments_dir), str(attachments_dir) + ".pre-restore")
    with tarfile.open(backup / "attachments.tar.gz") as tar:
        tar.extractall(data_dir, filter="data")

    print(f"Restore concluído a partir de {backup}.")
    print("Suba a aplicação e valide o login antes de descartar os .pre-restore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

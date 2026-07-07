"""Diff textual entre versões — difflib da biblioteca padrão.

Diffs nunca são armazenados: sempre deriváveis dos snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff

from app.models import PolicyVersion


def unified(a: PolicyVersion, b: PolicyVersion) -> str:
    return "".join(
        unified_diff(
            a.body_md.splitlines(keepends=True),
            b.body_md.splitlines(keepends=True),
            fromfile=f"v{a.version_number}",
            tofile=f"v{b.version_number}",
        )
    )


@dataclass
class Row:
    """Linha pareada para exibição lado a lado."""

    left_no: int | None
    left: str
    right_no: int | None
    right: str
    kind: str  # equal | added | removed | changed


def side_by_side(a: PolicyVersion, b: PolicyVersion) -> list[Row]:
    left_lines = a.body_md.splitlines()
    right_lines = b.body_md.splitlines()
    matcher = SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    rows: list[Row] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for offset in range(i2 - i1):
                rows.append(
                    Row(i1 + offset + 1, left_lines[i1 + offset],
                        j1 + offset + 1, right_lines[j1 + offset], "equal")
                )
        elif op == "delete":
            for i in range(i1, i2):
                rows.append(Row(i + 1, left_lines[i], None, "", "removed"))
        elif op == "insert":
            for j in range(j1, j2):
                rows.append(Row(None, "", j + 1, right_lines[j], "added"))
        else:  # replace
            span = max(i2 - i1, j2 - j1)
            for offset in range(span):
                li = i1 + offset
                rj = j1 + offset
                rows.append(
                    Row(
                        li + 1 if li < i2 else None,
                        left_lines[li] if li < i2 else "",
                        rj + 1 if rj < j2 else None,
                        right_lines[rj] if rj < j2 else "",
                        "changed",
                    )
                )
    return rows


@dataclass
class FieldChange:
    """Mudança em campo estruturado entre duas versões (v1)."""

    label: str
    before: object | None
    after: object | None
    kind: str  # added | removed | changed


def field_diff(a: PolicyVersion, b: PolicyVersion) -> list[FieldChange]:
    """Diff dos campos estruturados — complementa o diff textual do corpo."""
    from app.services import structured_fields

    left = structured_fields.load(a.structured_fields)
    right = structured_fields.load(b.structured_fields)
    labels = {
        d.name: d.label for d in structured_fields.defs_for(b.policy.policy_type)
    }
    changes: list[FieldChange] = []
    for name in sorted(set(left) | set(right)):
        before, after = left.get(name), right.get(name)
        if before == after:
            continue
        if name not in left:
            kind = "added"
        elif name not in right:
            kind = "removed"
        else:
            kind = "changed"
        changes.append(FieldChange(labels.get(name, name), before, after, kind))
    return changes


def stats(a: PolicyVersion, b: PolicyVersion) -> dict[str, int]:
    added = removed = 0
    matcher = SequenceMatcher(
        None, a.body_md.splitlines(), b.body_md.splitlines(), autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op in ("delete", "replace"):
            removed += i2 - i1
        if op in ("insert", "replace"):
            added += j2 - j1
    return {"added": added, "removed": removed}

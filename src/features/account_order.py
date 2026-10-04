"""
features/account_order.py
Pure helpers for ordering the saved accounts.
"""

from __future__ import annotations


def move_account(
    order: list[str],
    moved: str,
    before: str | None,
    visible: list[str],
) -> list[str]:
    if moved not in order or moved == before or (before is not None and before not in order):
        return list(order)

    result = [name for name in order if name != moved]
    if before is not None:
        index = result.index(before)
    else:
        shown = [name for name in visible if name in result]
        index = result.index(shown[-1]) + 1 if shown else len(result)
    result.insert(index, moved)
    return result

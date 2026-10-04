"""
features/account_filter.py
Pure helpers for filtering the account list by a search query.
"""

from __future__ import annotations

from typing import Mapping


def _searchable_text(username: str, data, group: str | None) -> str:
    fields = [username, group or ""]
    if isinstance(data, dict):
        fields.append(str(data.get("note", "") or ""))
        fields.append(str(data.get("user_id", "") or ""))
    return " ".join(fields).casefold()


def filter_accounts(
    items: list[tuple[str, object]],
    query: str,
    assignments: Mapping[str, str] | None = None,
) -> list[tuple[str, object]]:
    terms = str(query or "").casefold().split()
    if not terms:
        return list(items)
    groups = assignments or {}
    result = []
    for username, data in items:
        text = _searchable_text(str(username), data, groups.get(username))
        if all(term in text for term in terms):
            result.append((username, data))
    return result

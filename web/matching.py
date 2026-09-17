"""Find a typed AirPlay name among the devices on the network.

Case, spaces and punctuation are ignored. When nothing matches, the closest
names are offered as suggestions: names that contain the query first, then
the nearest ones according to difflib.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field


def normalize(name: str) -> str:
    return "".join(ch for ch in name.casefold() if ch.isalnum())


@dataclass
class MatchResult:
    matches: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


def match(query: str, names: list, limit: int = 3) -> MatchResult:
    wanted = normalize(query)
    if not wanted:
        return MatchResult()
    unique = sorted(set(names), key=str.casefold)
    matches = [name for name in unique if normalize(name) == wanted]
    if matches:
        return MatchResult(matches=matches)

    suggestions = [name for name in unique if wanted in normalize(name)]
    by_normal = {}
    for name in unique:
        by_normal.setdefault(normalize(name), name)
    for close in difflib.get_close_matches(wanted, list(by_normal), n=limit, cutoff=0.6):
        name = by_normal[close]
        if name not in suggestions:
            suggestions.append(name)
    return MatchResult(suggestions=suggestions[:limit])

# Org de-dup - merges name-variants of the same org seen in one hearing (an
# acronym + its spelled-out form, minor transcription drift). Two tiers:
# exact-normalized match, and a "safe" containment rule. Plain string
# similarity alone isn't safe here ("Association of Minnesota Counties" vs
# "... Cities" score highly similar despite being different orgs), so
# anything merely similar gets left as a distinct entity with a low
# match_confidence instead of being auto-merged.
import json
import os
import re
from difflib import SequenceMatcher

_QUALIFIERS = {"usa", "us", "inc", "llc", "lp", "co", "corp", "corporation",
               "national", "the", "of", "for", "and", "&"}

DEFAULT_MIN_RATIO = 0.80
_ALIASES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "org_aliases.json")


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _tokens(name):
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split() if t}


def _ratio(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _containment_safe(a, b):
    """One name is a prefix (or singular/plural) of the other and the only
    differing words are qualifiers like "Inc"/"USA" - safe to merge."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    short, long_ = sorted([na, nb], key=len)
    plural = short.endswith("s") and len(short) > 3 and long_.startswith(short[:-1])
    if not (long_.startswith(short) or plural):
        return False

    def _plural_eq(x, y):
        return x == y or x == y + "s" or y == x + "s" or x == y + "es" or y == x + "es"

    ta, tb = _tokens(a), _tokens(b)
    extra = {t for t in ta if not any(_plural_eq(t, u) for u in tb)}
    extra |= {t for t in tb if not any(_plural_eq(t, u) for u in ta)}
    return all(t in _QUALIFIERS for t in extra)


def load_aliases(path=None):
    """User-declared duplicates (acronym + full name, zero string similarity,
    can't be caught by the rules above). JSON: list of groups, each a list of
    same-entity names; first name in a group is the preferred display name."""
    path = path or _ALIASES_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return [], {}
    groups, canon = [], {}
    for grp in raw or []:
        names = [n for n in grp if n]
        if len(names) < 2:
            continue
        groups.append({_norm(n) for n in names})
        for n in names:
            canon[_norm(n)] = names[0]
    return groups, canon


def resolve_orgs(org_names, min_ratio=DEFAULT_MIN_RATIO, aliases_path=None) -> dict:
    """Returns {raw_name: {"canonical", "match_method", "match_confidence"}}
    for the distinct org names observed in one hearing.

    match_method is 'alias' | 'merged' (exact/containment) | 'unmatched'. A
    near-miss 'unmatched' (looks like a dup but unconfirmed) gets confidence
    0.5, below storage.py's 0.75 auto-verify threshold, so it routes to
    manual review.
    """
    alias_groups, alias_canon = load_aliases(aliases_path)
    names = list(dict.fromkeys(n for n in org_names if n))
    n = len(names)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            a, b = names[i], names[j]
            ni, nj = _norm(a), _norm(b)
            if ni == nj or any(ni in g and nj in g for g in alias_groups) or _containment_safe(a, b):
                union(i, j)
            # ratio-only similarity isn't merged, just flagged below

    clusters = {}
    for idx in range(n):
        clusters.setdefault(find(idx), []).append(idx)

    # merely SIMILAR (not merged) to something outside its own cluster -> review
    near_miss = {i: False for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and _ratio(names[i], names[j]) >= min_ratio:
                near_miss[i] = near_miss[j] = True

    out = {}
    for idxs in clusters.values():
        members = [names[k] for k in idxs]
        canon = max(members, key=len)
        is_alias = False
        for nm in members:
            disp = alias_canon.get(_norm(nm))
            if disp:
                canon, is_alias = disp, True
                break
        merged = len(members) > 1
        for k in idxs:
            if merged:
                method, confidence = ("alias" if is_alias else "merged"), 1.0
            elif near_miss[k]:
                method, confidence = "unmatched", 0.5   # looks like a duplicate but unconfirmed -> review
            else:
                method, confidence = "unmatched", 0.9   # nothing else in this hearing resembles it
            out[names[k]] = {"canonical": canon, "match_method": method, "match_confidence": confidence}
    return out

# Legislators rarely introduce themselves - they get addressed ("Representative
# Wirtz, you're recognized") or read off during roll call - so this matches
# transcript mentions against a per-committee roster instead of self-intro
# grammar.
#
# extract_roll_call_candidates() is roster-free, used to bootstrap
# data/committee_rosters.json (see build_committee_rosters.py). extract_roll_call()
# / attribute_legislators() are roster-aware, used at pipeline run time.
#
# Deepgram mangles uncommon surnames inconsistently across hearings ("Nyar" vs
# "Meyer", "Pavlov" vs "Pablo"), so matching is fuzzy, not exact.
import json
import os
import re
from datetime import datetime
from difflib import SequenceMatcher

_ROSTERS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "committee_rosters.json")
_NAME_MATCH_MIN_RATIO = 0.72

_ROLL_CALL_CUE = re.compile(
    r"(?:take|call)\s+the\s+(?:roll|role)|take\s+attendance|calling\s+the\s+roll", re.I)
_RECOGNIZE_RE = re.compile(
    r"\b(?:Chair(?:man|woman)?|Representative|Senator|Rep\.|Sen\.)\s+([A-Z][a-zA-Z'\-]+)")
# roll-call names are short fragments ("Nyar." "Wirtz." "Here.") - require a
# capitalized token right before sentence-end punctuation to skip ordinary
# capitalized prose words
_NAME_TOKEN = re.compile(r"\b([A-Z][a-zA-Z'\-]{2,})[.?]")
_ROLL_CALL_STOP_WORDS = {
    "Here", "Present", "Absent", "Clerk", "Chair", "Chairman", "Chairwoman",
    "Committee", "Mister", "Madam", "Members", "Quorum", "Thank",
}

# House filenames encode committee code + MMDDYY (e.g. "HAGRI-022626");
# Senate ids from Castus are opaque, no code embedded
_STEM_RE = re.compile(r"^([A-Z]{2,6})-(\d{6})$")


def parse_hearing_filename(stem):
    """(committee_code, date) for a House-style '<CODE>-MMDDYY' stem, else (None, None)."""
    m = _STEM_RE.match(stem)
    if not m:
        return None, None
    code, mmddyy = m.groups()
    try:
        d = datetime.strptime(mmddyy, "%m%d%y").date()
    except ValueError:
        d = None
    return code, d


def load_rosters(path=None) -> dict:
    path = path or _ROSTERS_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _norm_last(name):
    return re.sub(r"[^a-z]", "", name.lower())


def _best_roster_match(surname, committee_roster):
    target = _norm_last(surname)
    if not target:
        return None, 0.0
    best, best_score = None, 0.0
    for member in committee_roster:
        last = member["name"].split()[-1]
        score = SequenceMatcher(None, target, _norm_last(last)).ratio()
        if score > best_score:
            best, best_score = member, score
    if best_score >= _NAME_MATCH_MIN_RATIO:
        return best, round(best_score, 3)
    return None, 0.0


_ROLL_CALL_WINDOW = 8


def _find_roll_call_cue_indices(turns) -> list:
    """Every turn matching the roll-call cue - a hearing can call the roll
    more than once (attendance, then again for a recorded vote)."""
    return [i for i, t in enumerate(turns) if _ROLL_CALL_CUE.search(t["text"])]


def _find_roll_call_cue_idx(turns):
    indices = _find_roll_call_cue_indices(turns)
    return indices[0] if indices else None


def extract_roll_call_candidates(turns, window=_ROLL_CALL_WINDOW) -> list:
    """Roster-free: finds the roll-call cue, pulls capitalized name-like tokens
    from the turns right after it. Chair is called first ("Chair X. Here.
    Representative Y. Here. ..."), so callers treat the first result as chair.
    Noisy on purpose - meant to bootstrap a roster a human then skims, not to
    be the final source of truth."""
    cue_idx = _find_roll_call_cue_idx(turns)
    if cue_idx is None:
        return []

    names, seen = [], set()
    # start after the cue turn itself - that's prose ("...call the roll?"),
    # its capitalized words aren't roll-call names
    for t in turns[cue_idx + 1:cue_idx + 1 + window]:
        for tok in _NAME_TOKEN.findall(t["text"]):
            if tok in _ROLL_CALL_STOP_WORDS or tok in seen:
                continue
            seen.add(tok)
            names.append(tok)
    return names


def extract_roll_call(turns, committee_roster) -> list:
    """Roster-aware attendance: names near the roll-call cue, fuzzy-matched to
    the roster. Not attributable to a speaker_id - diarization jumbles the
    rapid clerk/member call-and-response into shared turns, so this only
    means "present", not "said this turn"."""
    if not committee_roster:
        return []
    candidates = extract_roll_call_candidates(turns)
    found, seen = [], set()
    for tok in candidates:
        member, score = _best_roster_match(tok, committee_roster)
        if member and member["name"] not in seen:
            seen.add(member["name"])
            found.append(member["name"])
    return found


def attribute_legislators(turns, committee_roster) -> dict:
    """A turn addressing a roster member by title+name ("Representative
    Wirtz") gets its NEXT turn (different speaker_id) attributed to that
    legislator for the rest of the hearing. Misses legislators never
    addressed by name, but doesn't guess without a textual signal.

    Skips every roll-call zone, not just the first - "Chair Leitner. Here."
    matches the recognition pattern too, but that's exactly where diarization
    is least reliable, and a hearing can call the roll more than once (a
    second call for a recorded vote). The binding is PERMANENT once made: one
    bad match there silently relabels every later turn from that speaker_id.
    Seen this misattribute a whole hearing's testimony to the chair before -
    hence skipping roll-call zones this aggressively.

    Returns {speaker_id: {"name", "chamber_role", "confidence"}}."""
    if not committee_roster:
        return {}
    cue_indices = _find_roll_call_cue_indices(turns)
    if not cue_indices:
        start, skip = 0, set()
    else:
        start = cue_indices[0] + 1 + _ROLL_CALL_WINDOW
        skip = set()
        for cue_idx in cue_indices[1:]:
            skip.update(range(cue_idx + 1, cue_idx + 1 + _ROLL_CALL_WINDOW))

    attributed = {}
    for i in range(start, len(turns)):
        if i in skip:
            continue
        t = turns[i]
        for m in _RECOGNIZE_RE.finditer(t["text"]):
            member, score = _best_roster_match(m.group(1), committee_roster)
            if not member:
                continue
            for nxt in turns[i + 1:i + 3]:
                if nxt["speaker_id"] != t["speaker_id"] and nxt["speaker_id"] not in attributed:
                    attributed[nxt["speaker_id"]] = {
                        "name": member["name"],
                        "chamber_role": member.get("role", "member"),
                        "confidence": score,
                    }
                    break
    return attributed

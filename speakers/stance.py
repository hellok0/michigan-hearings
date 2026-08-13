# Deterministic position (support/oppose/neutral) and quote capture for one
# speaker turn. Fixed lexicon of how witnesses/legislators actually phrase a
# position on a bill - confidence scales with how many cues fired.
import re

# word-boundary matched, not substrings ("commend" would fire inside
# "recommendation"). Cues are first-person declarations ("I support...", "we
# oppose...") since that's how real testimony phrases things, not bare adjectives.
_SUPPORT_CUES = [
    "i support", "we support", "in support of", "in favor of", "urge you to pass",
    "urge the committee to pass", "urge passage", "ask for your support",
    "vote yes", "strongly support", "i commend", "we commend", "voice (?:my|our) support",
]
_OPPOSE_CUES = [
    "i oppose", "we oppose", "i(?:'m| am) opposed to", "we(?:'re| are) opposed to",
    "urge you to reject", "urge the committee to reject", "vote no",
    "strongly oppose", "concerns about this bill", "voice (?:my|our) opposition",
]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _compile(cues):
    return [re.compile(r"\b" + c + r"\b", re.I) for c in cues]


_SUPPORT_RE = _compile(_SUPPORT_CUES)
_OPPOSE_RE = _compile(_OPPOSE_CUES)


def classify_position(text, max_quotes=4):
    """Returns (position, quotes, confidence). position is one of
    support|oppose|neutral|unknown. quotes are up to max_quotes verbatim
    sentences - the ones containing a cue when any fired, else the turn's
    opening sentences."""
    support_hits = sum(1 for c in _SUPPORT_RE if c.search(text))
    oppose_hits = sum(1 for c in _OPPOSE_RE if c.search(text))
    total = support_hits + oppose_hits

    if total == 0:
        position = "unknown"
    elif support_hits > oppose_hits:
        position = "support"
    elif oppose_hits > support_hits:
        position = "oppose"
    else:
        position = "neutral"

    confidence = round(min(1.0, total / 2.0), 2) if total else 0.2
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    cue_res = _SUPPORT_RE + _OPPOSE_RE
    quotes = [s for s in sentences if any(c.search(s) for c in cue_res)][:max_quotes]
    if not quotes:
        quotes = sentences[:2]
    return position, quotes, confidence

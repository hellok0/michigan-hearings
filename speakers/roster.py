# Witness identification: self-introductions ("My name is X", "I'm X ...
# representing Y") and chair introductions ("we have X from Y"). Deepgram
# gives us a stable per-hearing speaker_id for each turn, so attribution is
# simple - a self-intro's speaker_id is just that turn's, a chair intro's is
# the next turn spoken by someone else.
import re

_CUE = re.compile(r"(?:my name is|i am|i'm|this is)\s+", re.I)
_NAME = re.compile(r"([A-Z][a-zA-Z'\-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'\-]+){1,2})")
_CHAIR = re.compile(
    r"(?:next,?\s+we have|we have|joining us(?:\s+is|\s+are)?|please welcome|welcome)\s+"
    r"([A-Z][a-zA-Z'\-]+\s+[A-Z][a-zA-Z'\-]+)\s+"
    r"(?:from|with|of|representing)\s+(?:the\s+)?([A-Z][\w&'\- ]+)")

_CONN = r"(?:on behalf of|representing|with|from|of|for|at|represent)"
_ORGW = r"[A-Z][\w&'\-]+"
_ORG = re.compile(
    _CONN + r"\s+(?:the\s+)?(" + _ORGW +
    r"(?:\s+(?:of|and|for|the|&)\s+" + _ORGW + r"|\s+" + _ORGW + r")*)")

_TW = (r"(?:president|ceo|cfo|chief\s+\w+\s+officer|executive director|"
       r"deputy commissioner|assistant commissioner|commissioner|superintendent|"
       r"director|general counsel|counsel|secretary|administrator|professor|"
       r"coordinator|representative|attorney|vice president|founder|owner|"
       r"partner|manager|analyst|supervisor|lobbyist|chair)")
_TITLE = re.compile(
    r"(?:,\s*|(?:i am|i'm)\s+|serving as\s+)(?:the\s+|an?\s+)?"
    r"(" + _TW + r"(?:\s+of\s+\w+(?:\s+\w+)?)?)", re.I)

_NONNAME = {"happy", "pleased", "glad", "honored", "grateful", "here", "sorry",
            "going", "not", "really", "our", "the", "also", "sure", "concerned"}


def _clean_org(s):
    s = re.split(r"[.,;:]| three | which | who | that | and good | and I ", s)[0]
    return s.strip(" .,&")


def _clean_title(s):
    s = s.strip(" .,").lower()
    s = re.sub(r"\s+of\s+the\s+.*$", "", s)
    s = re.sub(r"\s+(of|for|at|with|the)$", "", s)
    return s.strip()


def build_witness_roster(turns) -> list:
    """Scan turns for self- and chair-introductions. Returns, de-duped by name
    and in order of first appearance:
        [{"name", "title", "org", "speaker_id", "source": "self"|"chair"}, ...]
    """
    found, seen = [], set()

    def add(name, title, org, speaker_id, source):
        name = re.sub(r"\s+", " ", name).strip(" .,")
        if not name or name.split()[0].lower() in _NONNAME:
            return
        if name in seen:
            for e in found:
                if e["name"] == name:
                    if org and not e["org"]:
                        e["org"] = org
                    if title and not e["title"]:
                        e["title"] = title
                    if e["speaker_id"] is None and speaker_id is not None:
                        e["speaker_id"] = speaker_id
            return
        seen.add(name)
        found.append({"name": name, "title": title, "org": org,
                       "speaker_id": speaker_id, "source": source})

    for i, t in enumerate(turns):
        text = t["text"]
        for m in _CUE.finditer(text):
            nm = _NAME.match(text, m.end())
            if not nm:
                continue
            tail = text[m.end():m.end() + 280]
            om = _ORG.search(tail)
            tm = _TITLE.search(tail)
            # self-introduction: the speaker of THIS turn is the person named
            add(nm.group(1),
                _clean_title(tm.group(1)) if tm else "",
                _clean_org(om.group(1)) if om else "",
                t["speaker_id"], "self")
        for cm in _CHAIR.finditer(text):
            # third-party introduction: the person introduced speaks in a LATER
            # turn under a different speaker_id, never the chair's own
            speaker_id = None
            for nxt in turns[i + 1:i + 4]:
                if nxt["speaker_id"] != t["speaker_id"]:
                    speaker_id = nxt["speaker_id"]
                    break
            add(cm.group(1), "", _clean_org(cm.group(2)), speaker_id, "chair")

    return found

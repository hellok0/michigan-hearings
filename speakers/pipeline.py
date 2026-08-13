# Orchestrates one hearing's speaker identification: turns -> witness roster +
# legislator name-spotting -> per-turn role/org/position/quotes -> org
# resolution. All deterministic, no LLM calls (see roster.py, legislators.py,
# resolve.py, stance.py).
import logging

from speakers.legislators import attribute_legislators, extract_roll_call, load_rosters
from speakers.resolve import resolve_orgs
from speakers.roster import build_witness_roster
from speakers.stance import classify_position
from speakers.transcript import turns_from_deepgram

logger = logging.getLogger(__name__)

# Drop pure-procedural turns ("Here.", "Present.") - no testimony signal, and
# they'd otherwise flood the testimony table with noise.
MIN_TURN_CHARS = 15


def identify_speakers(transcript_json, committee_code=None) -> dict:
    """Returns:
        {"attendance": [{"name", "match_confidence"}],
         "testimony": [{"name", "role", "affiliation", "affiliation_canonical",
                         "org_match_method", "org_match_confidence", "title",
                         "position", "quotes", "confidence", "start", "end",
                         "match_method", "match_confidence"}]}
    committee_code keys data/committee_rosters.json - pass None if unknown and
    legislator name-spotting is skipped (unrecognized speakers get dropped,
    not guessed at).
    """
    turns = turns_from_deepgram(transcript_json)
    if not turns:
        return {"attendance": [], "testimony": []}

    witness_roster = build_witness_roster(turns)
    witness_by_speaker = {}
    for w in witness_roster:
        if w["speaker_id"] is not None:
            witness_by_speaker.setdefault(w["speaker_id"], w)

    rosters = load_rosters()
    committee_roster = rosters.get(committee_code, []) if committee_code else []
    attendance_names = extract_roll_call(turns, committee_roster)
    legislator_speakers = attribute_legislators(turns, committee_roster)

    testimony = []
    for t in turns:
        if len(t["text"].strip()) < MIN_TURN_CHARS:
            continue
        sid = t["speaker_id"]
        if sid in legislator_speakers:
            info = legislator_speakers[sid]
            role, name, org, title = "legislator", info["name"], None, info.get("chamber_role")
            match_method, match_conf = "fuzzy_name_match", info["confidence"]
        elif sid in witness_by_speaker:
            w = witness_by_speaker[sid]
            role, name, org, title = "witness", w["name"], w["org"] or None, w["title"] or None
            match_method = "self_intro" if w["source"] == "self" else "chair_intro"
            match_conf = 0.8 if w["source"] == "self" else 0.6
        else:
            continue  # no identity signal for this turn - procedural/unattributed

        position, quotes, pos_conf = classify_position(t["text"])
        testimony.append({
            "name": name, "role": role, "affiliation": org, "title": title,
            "position": position, "quotes": quotes,
            "confidence": round((match_conf + pos_conf) / 2, 3),
            "start": t["start"], "end": t["end"],
            "match_method": match_method, "match_confidence": match_conf,
        })

    org_names = sorted({row["affiliation"] for row in testimony if row["affiliation"]})
    resolved = resolve_orgs(org_names)
    for row in testimony:
        aff = row["affiliation"]
        if aff and aff in resolved:
            r = resolved[aff]
            row["affiliation_canonical"] = r["canonical"]
            row["org_match_method"] = r["match_method"]
            row["org_match_confidence"] = r["match_confidence"]

    attendance = [{"name": n, "match_confidence": 0.5} for n in attendance_names]
    logger.info("identify_speakers: %d attendance, %d testimony rows", len(attendance), len(testimony))
    return {"attendance": attendance, "testimony": testimony}

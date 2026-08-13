# Human-readable speaker-identification report for one or more hearings in
# transcripts/, for manually reviewing extraction quality. Writes
# speaker_reports/<hearing_id>.txt for each.
#
# usage: python write_speaker_report.py HJUDI-062426 HOVER-062326 ...
import json
import os
import sys
from datetime import date, timedelta

from mi_scrapers import senate_scraper
from speakers.legislators import parse_hearing_filename
from speakers.pipeline import identify_speakers

TRANSCRIPT_DIR = "transcripts"
OUT_DIR = "speaker_reports"
# same reach-back as build_senate_committee_rosters.py, for the same reason
SENATE_LOOKBACK_DAYS = 365

_senate_codes = None


def committee_code_for(hearing_id):
    """House filenames encode the code directly. Senate ids are opaque, so
    fall back to a live Castus lookup (fetched once, cached) the same way
    build_senate_committee_rosters.py resolves them."""
    global _senate_codes
    code, _ = parse_hearing_filename(hearing_id)
    if code:
        return code
    if _senate_codes is None:
        cutoff = date.today() - timedelta(days=SENATE_LOOKBACK_DAYS)
        _senate_codes = senate_scraper.fetch_video_committee_codes(cutoff)
    return _senate_codes.get(hearing_id)


def _ts(seconds):
    if seconds is None:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def render_report(hearing_id, result, committee_code):
    lines = [f"HEARING: {hearing_id}",
             f"Committee code: {committee_code or '(none - no roster available)'}",
             "=" * 80, ""]

    attendance = result.get("attendance", [])
    lines.append(f"ATTENDANCE (roll call, {len(attendance)}) - presence signal only, not tied to a turn")
    lines.append("-" * 80)
    lines += [f"  - {a['name']}" for a in attendance] or ["  (none detected)"]
    lines.append("")

    testimony = result.get("testimony", [])
    lines.append(f"TESTIMONY ({len(testimony)} turns)")
    lines.append("-" * 80)

    # Group turns by (role, name, affiliation) in order of first appearance,
    # so everything one person said reads together instead of interleaved.
    order, groups = [], {}
    for row in testimony:
        key = (row["role"], row["name"], row.get("affiliation"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    marker = {"support": "+", "oppose": "-", "neutral": "~", "unknown": " "}
    for role, name, org in order:
        rows = groups[(role, name, org)]
        header = f"[{role.upper()}] {name}"
        if org:
            canon = rows[0].get("affiliation_canonical")
            header += f"  -  {org}"
            if canon and canon != org:
                header += f"  (resolved: {canon})"
        header += f"   [{len(rows)} turn(s)]"
        lines.append(header)
        for r in rows:
            lines.append(f"  {_ts(r['start'])}  ({marker.get(r['position'], ' ')}{r['position']})  conf={r['confidence']}")
            for q in r["quotes"]:
                lines.append(f'      "{q}"')
        lines.append("")

    lines.append(f"TESTIMONY IN ORDER SPOKEN ({len(testimony)} turns)")
    lines.append("-" * 80)
    for r in sorted(testimony, key=lambda r: r["start"] if r["start"] is not None else -1):
        who = f"[{r['role'].upper()}] {r['name']}"
        if r.get("affiliation"):
            who += f"  -  {r['affiliation']}"
        lines.append(f"{_ts(r['start'])}  {who}  ({marker.get(r['position'], ' ')}{r['position']})")
        for q in r["quotes"]:
            lines.append(f'    "{q}"')
    lines.append("")

    return "\n".join(lines)


def main():
    ids = sys.argv[1:]
    if not ids:
        print("usage: python write_speaker_report.py <hearing_id> [more...]")
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    for hearing_id in ids:
        path = os.path.join(TRANSCRIPT_DIR, hearing_id + ".json")
        if not os.path.exists(path):
            print(f"skip {hearing_id}: no transcript at {path}")
            continue
        with open(path, encoding="utf-8") as f:
            transcript = json.load(f)
        committee_code = committee_code_for(hearing_id)
        result = identify_speakers(transcript, committee_code)
        out_path = os.path.join(OUT_DIR, hearing_id + ".txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(render_report(hearing_id, result, committee_code))
        print(f"wrote {out_path} ({len(result.get('testimony', []))} testimony rows)")


if __name__ == "__main__":
    main()

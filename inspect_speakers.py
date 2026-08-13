# Read-only summary of _hearings.db_'s speaker-identification tables, for
# spot-checking backfill_speakers.py / build_committee_rosters.py output.
#
# usage: python inspect_speakers.py              (overview + sample of each)
#        python inspect_speakers.py HAGRI-022626  (everything for one hearing_id)
import sqlite3
import sys


def overview(c):
    print("=== entities by type ===")
    for row in c.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"):
        print(" ", row)

    print("\n=== mentions needing review (confidence < 0.75) ===")
    for row in c.execute("""
        SELECT hearing_id, raw_name, match_method, match_confidence
        FROM entity_mentions WHERE review_status = 'unreviewed'
        ORDER BY match_confidence ASC LIMIT 10
    """):
        print(" ", row)

    print("\n=== testimony by role/position ===")
    for row in c.execute("SELECT role, position, COUNT(*) FROM testimony GROUP BY role, position ORDER BY 1, 2"):
        print(" ", row)

    print("\n=== sample witness testimony (highest confidence first) ===")
    for row in c.execute("""
        SELECT t.hearing_id, em.raw_name, t.affiliation, t.position, t.quotes
        FROM testimony t JOIN entity_mentions em ON em.mention_id = t.mention_id
        WHERE t.role = 'witness' AND t.position IN ('support', 'oppose')
        ORDER BY t.confidence DESC LIMIT 8
    """):
        print(" ", row)


def one_hearing(c, hearing_id):
    print(f"=== attendance/mentions for {hearing_id} ===")
    for row in c.execute("""
        SELECT raw_name, match_method, match_confidence, review_status
        FROM entity_mentions WHERE hearing_id = ? ORDER BY raw_name
    """, (hearing_id,)):
        print(" ", row)

    print(f"\n=== testimony for {hearing_id} ===")
    for row in c.execute("""
        SELECT em.raw_name, t.role, t.affiliation, t.position, t.quotes
        FROM testimony t JOIN entity_mentions em ON em.mention_id = t.mention_id
        WHERE t.hearing_id = ? ORDER BY t.rowid
    """, (hearing_id,)):
        print(" ", row)


def main():
    conn = sqlite3.connect('_hearings.db_')
    c = conn.cursor()
    if len(sys.argv) > 1:
        one_hearing(c, sys.argv[1])
    else:
        overview(c)
    conn.close()


if __name__ == "__main__":
    main()

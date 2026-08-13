# MI Legislative Hearings Pipeline

I built this to solve a specific problem: Michigan House and Senate committee
hearings get posted as raw video with no transcript and no searchable record
of who said what. This pipeline watches both archives, picks up new hearings
automatically, downloads and transcribes them, and (partially - see below)
works out who's actually talking.

## How it's organized

- `main.py` - the live pipeline. The one thing meant to run unattended: find
  new hearings, download them, transcribe them, run speaker ID, and record
  each one in `_hearings.db_` so it never gets reprocessed.
- `download_hearing.py` / `transcribe_hearing.py` - I use these to test a
  single hearing without running the whole pipeline or touching the db.
  Useful when I'm changing a scraper and don't want to burn a Deepgram call
  or pollute my records just to test it.
- `speakers/` - the actual speaker-identification logic: roster-gated
  legislator matching, detecting when a witness introduces themselves or
  gets introduced by the chair, resolving orgs/acronyms, pulling out
  position and quotes. All deterministic - no LLM in the loop.
- `build_committee_rosters.py` / `build_senate_committee_rosters.py` -
  one-off scripts I run occasionally to rebuild `data/committee_rosters.json`
  from roll calls already sitting in `transcripts/`. Not part of the live
  pipeline.
- `write_speaker_report.py` / `inspect_speakers.py` - how I spot-check
  whether the speaker ID is actually working, in human-readable form.

## Setup

1. Python 3.11+, then `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and drop in a `DEEPGRAM_API_KEY`.

## Running it

Everything centers on one command:

```
python main.py
```

That scrapes both archives, grabs anything new from the last 60 days,
transcribes it, runs speaker ID, and logs each hearing in `_hearings.db_` so
a future run skips it. This is what I have running daily on a schedule (a
Windows Task Scheduler job, on this machine - `0 6 * * * cd /path/to/repo &&
python main.py` is the cron equivalent on Linux/Mac).

If I just want to poke at one hearing without touching the db or separate a hearing download

- `python download_hearing.py <house|senate> <url>` - download only
- `python transcribe_hearing.py <house|senate> <url>` (or `--file <path>`) -
  download + transcribe

And once there are transcripts on disk, these are how I check the
speaker-ID output:

- `python write_speaker_report.py <hearing_id> [more...]` - human-readable
  report written to `speaker_reports/`
- `python inspect_speakers.py [hearing_id]` - dumps the relevant db tables

Honestly, the easiest path is not to run it at all. `transcripts/`,
`speaker_reports/`, and `_hearings.db_` are checked in on purpose - they're
real output from letting this run for a few days against the live House and
Senate archives, so you can see it actually works without spending your own
time or a Deepgram API call re-running it yourself.

## Future implementations 

- **Roster data is inconsistent.** The bootstrap scripts pull roll-call names out
  with regex, and I always meant to hand-check the output before
  committing it - said as much in the scripts' own comments. I've only
  actually done that pass for one committee (`6217f365f6f1c20008cbbc84`),
  as proof the fix works. The rest of `data/committee_rosters.json` still
  has some junk in it (state names, filler words) that got mistaken for
  people.
- **Roll call gets missed in one specific case.** If a legislator's
  roll-call answer gets diarized into the same turn as "will you please
  call the roll," I throw it out rather than risk false positives from
  ordinary prose in that turn. So that person just doesn't show up in
  attendance.
- **Voice memorization - not built.** The original idea was to eventually
  recognize legislators by voice as a library builds up over time. That's
  a different kind of system entirely - speaker embeddings, voice
  fingerprinting - not something I could bolt onto a scraping-and-
  transcription pipeline without doing it properly. I deferred it instead
  of half-building it.
- **Video storage.** Right now `process_hearing()` downloads each video,
  transcribes it, then deletes the local copy - the transcript is the
  actual deliverable, and keeping every multi-GB video on local disk
  forever doesn't scale. What I'd actually do in production: push each video to S3
  instead of deleting it, with a lifecycle policy to move it to Glacier
  after some retention window. That gets permanence (source videos can
  disappear from the state's own archive over time) and reprocessing
  flexibility (re-transcribe with a different model, build the voice
  fingerprinting above) without paying full-price storage forever. The db
  would hold a pointer to the S3 object instead of nothing at all.

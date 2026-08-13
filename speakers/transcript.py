# Turn reconstruction from a Deepgram nova-2 (diarize=true, smart_format=true)
# response, as produced by transcriber.py::transcribe().


def turns_from_deepgram(transcript_json) -> list:
    """smart_format paragraphs are already turn-segmented by speaker, so no
    word-level grouping needed. Returns, in order:
        [{"speaker_id": int, "text": str, "start": float, "end": float}, ...]
    [] if the transcript has no diarized paragraphs.
    """
    try:
        paragraphs = (transcript_json["results"]["channels"][0]
                      ["alternatives"][0]["paragraphs"]["paragraphs"])
    except (KeyError, IndexError, TypeError):
        return []

    turns = []
    for p in paragraphs:
        text = " ".join(s.get("text", "") for s in p.get("sentences", [])).strip()
        if not text:
            continue
        turns.append({
            "speaker_id": p.get("speaker"),
            "text": text,
            "start": p.get("start"),
            "end": p.get("end"),
        })
    return turns

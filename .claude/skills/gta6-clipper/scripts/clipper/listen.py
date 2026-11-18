"""Listen to the stream: what was said (word by word, with times), how loud each second
was, and on YouTube replays how fast chat moved. Everything is cached in the job folder,
so a stopped run continues where it stopped."""

import json
import os
import subprocess
import threading
from pathlib import Path

import numpy as np

from .media import FFMPEG, ClipError, cookie_args, pcm, ytdlp

MODELS_DIR = Path(__file__).resolve().parents[2] / ".models"
os.environ.setdefault("HF_HOME", str(MODELS_DIR))          # models stay inside the skill folder
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("CT2_VERBOSE", "-1")
_LOCK = threading.Lock()
_MODELS = {}


def model(name):
    with _LOCK:
        if name not in _MODELS:
            from faster_whisper import WhisperModel
            _MODELS[name] = WhisperModel(name, device="cpu", compute_type="int8")
        return _MODELS[name]


def whisper_words(audio, offset=0.0, name="base", language=None, fast=False):
    """[{s, e, w}] for a float32 16 kHz array; times shifted by `offset`."""
    np.seterr(all="ignore")
    segments, info = model(name).transcribe(
        audio, language=language, word_timestamps=True, vad_filter=True,
        beam_size=1 if fast else 5, condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"s": round(w.start + offset, 2), "e": round(w.end + offset, 2), "w": text})
    return words, info.language


def youtube_captions(url, work, base, cookies=None):
    """YouTube's own auto-captions, if the replay has them: seconds instead of minutes.
    Returns [{s, e, w}] in stream time, or None."""
    try:
        ytdlp(["--skip-download", "--write-auto-subs", "--write-subs", "--sub-format", "json3",
               "--sub-langs", "en-orig,en,.*-orig", "-o", str(Path(work) / "subs"),
               *cookie_args(cookies), url], timeout=240, what="reading YouTube's captions")
    except ClipError:
        return None
    files = sorted(Path(work).glob("subs*.json3"), key=lambda p: ("-orig" not in p.name, p.name))
    if not files:
        return None
    words = []
    for ev in json.loads(files[0].read_text(encoding="utf-8")).get("events", []):
        t0, segs = ev.get("tStartMs", 0), ev.get("segs") or []
        end = t0 + ev.get("dDurationMs", 0)
        parts = [(t0 + s.get("tOffsetMs", 0), s.get("utf8", "").strip()) for s in segs]
        parts = [(t, w) for t, w in parts if w]
        for i, (t, w) in enumerate(parts):
            nxt = parts[i + 1][0] if i + 1 < len(parts) else min(end, t + 800)
            words.append({"s": round(t / 1000, 2), "e": round(max(nxt, t + 150) / 1000, 2), "w": w})
    words.sort(key=lambda w: w["s"])
    if len(words) < 50:
        return None
    lo, hi = base
    return [w for w in words if lo <= w["s"] < hi] or None


def transcript(url, audio, work, base, site, cookies=None, log=print):
    """Words of the whole stream (or section). base = (stream second where the audio
    starts, stream second where it ends)."""
    cache = Path(work) / "transcript.json"
    if cache.exists():
        return json.loads(cache.read_text())
    words, source, language = None, "", None
    if "youtube" in site:
        log("reading YouTube's own captions (fast path)...")
        words = youtube_captions(url, work, base, cookies)
        source = "youtube captions" if words else ""
    if not words:
        log("listening to the stream on this computer (Whisper, about 1-2 min per stream hour)...")
        words, block = [], 600.0
        length = base[1] - base[0]
        for i, t in enumerate(np.arange(0, length, block)):
            part = Path(work) / f"heard_{i:03d}.json"
            if part.exists():
                got = json.loads(part.read_text())
            else:
                arr = pcm(audio, 16000, float(t), float(min(block, length - t)))
                got, language = whisper_words(arr, base[0] + float(t), "tiny", language, fast=True)
                part.write_text(json.dumps(got))
            words += got
            log(f"  heard {min(t + block, length) / 60:.0f} of {length / 60:.0f} min")
        source = "whisper tiny"
    if len(words) < 40:
        raise ClipError("almost nobody talks in this stream, so there is nothing to clip")
    data = {"words": words, "source": source}
    cache.write_text(json.dumps(data))
    for p in Path(work).glob("heard_*.json"):
        p.unlink()
    return data


def loudness(audio, work, base):
    """How much louder each stream second is than the minute around it (dB).
    Yelling and screaming show up as big positive numbers."""
    cache = Path(work) / "loud.json"
    if cache.exists():
        return json.loads(cache.read_text())
    rate, db = 4000, []
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-nostdin", "-i", str(audio), "-vn", "-ac", "1",
                             "-ar", str(rate), "-f", "s16le", "-"], stdout=subprocess.PIPE)
    while True:                                   # one minute at a time: long streams fit in memory
        buf = proc.stdout.read(rate * 2 * 60)
        if not buf:
            break
        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        k = len(x) // rate
        if k:
            db += (20 * np.log10(np.sqrt((x[: k * rate].reshape(k, rate) ** 2).mean(axis=1)) + 1e-5)).tolist()
    proc.wait()
    db = np.asarray(db)
    n = len(db)
    if n < 10:
        rel = np.zeros(n)
    else:
        pad = np.pad(db, 30, mode="edge")
        win = np.lib.stride_tricks.sliding_window_view(pad, 61)[:n]
        rel = db - np.percentile(win[:, ::3], 50, axis=1)
    data = {"start": base[0], "rel": [round(float(v), 1) for v in rel]}
    cache.write_text(json.dumps(data))
    return data


def chat_speed(url, work, info, cookies=None, log=print, timeout=300):
    """Chat messages per 10 s from a YouTube live replay, or None (best effort)."""
    if "youtube" not in info["site"] or info.get("live_status") != "was_live":
        return None
    cache = Path(work) / "chat.json"
    if cache.exists():
        return json.loads(cache.read_text())
    log("reading the chat replay (where chat went wild)...")
    try:
        ytdlp(["--skip-download", "--write-subs", "--sub-langs", "live_chat",
               "-o", str(Path(work) / "chat"), *cookie_args(cookies), url],
              timeout=timeout, what="reading the chat replay")
    except ClipError as exc:
        log(f"  chat replay skipped ({str(exc).splitlines()[0][:80]})")
    files = list(Path(work).glob("chat*.live_chat.json*"))
    if not files:
        return None
    counts = {}
    with open(files[0], encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                act = json.loads(line)["replayChatItemAction"]
                k = int(act.get("videoOffsetTimeMsec", 0)) // 10000
            except (ValueError, KeyError, TypeError):
                continue
            counts[k] = counts.get(k, 0) + len(act.get("actions", []))
    for f in files:
        f.unlink()
    if not counts:
        return None
    rate = [counts.get(i, 0) for i in range(max(counts) + 1)]
    cache.write_text(json.dumps(rate))
    return rate

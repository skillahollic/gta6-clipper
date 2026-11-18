"""ffmpeg and yt-dlp helpers. Same ffmpeg on every computer (the one inside the
imageio-ffmpeg package), so a clip that works on one Mac works on every Mac and PC."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


class ClipError(RuntimeError):
    """An error with a plain-English message for the user."""


def _ffmpeg():
    forced = os.environ.get("GTA6CLIP_FFMPEG")
    if forced:
        return forced
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if not found:
            raise ClipError("ffmpeg is missing. Run the setup again: it installs its own copy.")
        return found


FFMPEG = _ffmpeg()
# yt-dlp and deno come from this skill's own .venv; put it first on PATH.
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")


def run(cmd, timeout=None, what=None):
    """Run a command, return stdout. On failure raise ClipError with the last lines."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise ClipError(f"{what or Path(cmd[0]).name} took too long (over {timeout} s)")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-8:])
        raise ClipError(f"{what or Path(cmd[0]).name} failed:\n{tail}")
    return proc.stdout


def ffmpeg(args, timeout=1800, what="ffmpeg"):
    return run([FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", *args], timeout, what)


def probe(path):
    """{duration, width, height, fps, audio} read from ffmpeg's own report (no ffprobe needed)."""
    proc = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", str(path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = proc.stderr
    out = {"duration": 0.0, "width": 0, "height": 0, "fps": 30.0, "audio": " Audio:" in text}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if m:
        out["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if m:
        out["width"], out["height"] = int(m[1]), int(m[2])
    m = re.search(r"([\d.]+) fps", text)
    if m:
        out["fps"] = float(m[1]) or 30.0
    return out


def pcm(path, rate=16000, start=0.0, duration=None):
    """Mono float32 audio, decoded by ffmpeg straight into memory."""
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-ss", f"{max(0.0, start):.3f}", "-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise ClipError(f"could not read the audio of {Path(path).name}")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


# ---------- yt-dlp ----------

def ytdlp(args, timeout=600, what="download"):
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings", "--ignore-config",
           "--ffmpeg-location", FFMPEG, *args]
    try:
        return run(cmd, timeout, what)
    except ClipError as exc:
        raise ClipError(explain(str(exc))) from None


def explain(msg):
    """Turn yt-dlp's errors into one plain sentence plus the original detail."""
    low = msg.lower()
    hints = [
        ("confirm your age", "YouTube wants a signed-in viewer for this stream (age limit)."
         " Pick another stream, or see 'Age-limited streams' in SKILL.md."),
        ("private video", "This video is private."),
        ("members-only", "This stream is for channel members only."),
        ("subscriber", "This VOD is for subscribers only."),
        ("http error 403", "The site refused the download (403). Try again in a few minutes."),
        ("http error 429", "The site is rate-limiting this computer (429). Wait 15 minutes."),
        ("is not a valid url", "That link does not look like a stream link."),
        ("unsupported url", "That site is not supported. Use YouTube, Twitch or Kick links."),
    ]
    for key, text in hints:
        if key in low:
            return f"{text}\n  (detail: {msg.splitlines()[-1][:200]})"
    return msg


def info(url, cookies=None):
    raw = ytdlp(["-J", *cookie_args(cookies), url], timeout=180, what="looking up the stream")
    full = json.loads(raw)
    keep = {k: full.get(k) for k in ("id", "title", "channel", "uploader", "uploader_id", "duration",
                                     "live_status", "extractor_key", "webpage_url", "timestamp")}
    keep["name"] = keep.get("channel") or keep.get("uploader") or "streamer"
    keep["site"] = (keep.get("extractor_key") or "").lower()
    return keep


def cookie_args(browser):
    return ["--cookies-from-browser", browser] if browser else []


def download_audio(url, workdir, section=None, cookies=None):
    """Audio only (a 4-hour stream is about 100 MB). With section=(a, b) only that part."""
    done = [p for p in Path(workdir).glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if done:
        return done[0]
    args = ["-f", "wa/ba/w", "-o", str(Path(workdir) / "audio.%(ext)s"), "-N", "4"]
    if section:
        args += ["--download-sections", f"*{section[0]:.0f}-{section[1]:.0f}"]
    ytdlp([*args, *cookie_args(cookies), url], timeout=4 * 3600, what="downloading the audio")
    done = [p for p in Path(workdir).glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if not done:
        raise ClipError("the audio download finished but no file appeared")
    return done[0]


def download_part(url, start, end, dest, cookies=None):
    """Video for one clip only (1080p at most, H.264 first because every computer decodes it)."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    fmt = ("bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080][vcodec^=vp]+ba/"
           "bv*[height<=1080]+ba/b[height<=1080]/b")
    ytdlp(["-f", fmt, "--merge-output-format", "mp4", "--download-sections",
           f"*{max(0, start):.2f}-{end:.2f}", "-o", str(dest), *cookie_args(cookies), url],
          timeout=1800, what="downloading the clip's video")
    if not dest.exists():
        raise ClipError(f"no video came back for {start:.0f}-{end:.0f} s")
    return dest


# ---------- lining the clip video up with the stream audio ----------

def _envelope(x, hop=80):
    n = len(x) // hop
    return np.log1p(50 * np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1)))


def align(part, audio, audio_start, guess, search=40.0):
    """Stream second where `part` begins, found by matching its sound against the stream
    audio (yt-dlp cuts on keyframes, so a part can start a few seconds early).
    Returns (seconds, confidence 0..1). Sound is sampled at 8 kHz, envelope at 100 Hz."""
    a = _envelope(pcm(part, 8000, 0, 25))
    lo = max(audio_start, guess - search)
    b = _envelope(pcm(audio, 8000, lo - audio_start, 25 + 2 * search))
    if len(a) < 300 or len(b) <= len(a):
        return guess, 0.0
    a = (a - a.mean()) / (a.std() + 1e-9)
    n = len(a)
    csum, csq = np.cumsum(np.r_[0, b]), np.cumsum(np.r_[0, b * b])
    mean = (csum[n:] - csum[:-n]) / n
    std = np.sqrt(np.maximum((csq[n:] - csq[:-n]) / n - mean ** 2, 1e-12))
    size = 1 << int(np.ceil(np.log2(len(b) + n)))
    dot = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)[: len(b) - n + 1]
    corr = dot / (n * std)
    k = int(np.argmax(corr))
    return lo + k / 100.0, float(corr[k])

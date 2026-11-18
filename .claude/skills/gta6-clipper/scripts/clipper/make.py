"""Make one clip: fetch only its minute of video, line it up with the stream audio,
write exact captions, frame it 9:16, add the hook bar, encode, and save a check image."""

import json
import re
from pathlib import Path

from . import frame, listen, overlay
from .media import ClipError, align, download_part, ffmpeg, pcm, probe

PAD = 6.0          # extra seconds fetched on each side of a clip


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", overlay.clean(text).lower()).strip("-")
    return s[:n].strip("-") or "clip"


def prepare(job, m, idx, cfg, cams, log=print):
    """Everything about a clip that does not depend on its style: the video part, the sound
    match, the exact words and the look. Saved in work/prep_NN.json, so a new style only
    draws and encodes again (no download, no listening, no face search)."""
    job, work = Path(job), Path(job) / "work"
    (work / "parts").mkdir(parents=True, exist_ok=True)
    start, end = m["start"], m["end"]
    dur = end - start
    part = work / "parts" / f"{idx:02d}_{start:.1f}_{end:.1f}.mp4"     # new times = new download
    for stale in (work / "parts").glob(f"{idx:02d}_*.mp4"):
        if stale != part:
            stale.unlink()
    part = download_part(cfg["url"], start - PAD, end + PAD, part, cfg["cookies"])
    info = probe(part)
    if not info["width"]:
        raise ClipError("the downloaded part has no picture")
    cache = work / f"prep_{idx:02d}.json"
    prep = json.loads(cache.read_text()) if cache.exists() else {}
    if prep.get("part") != part.name:
        prep = {"part": part.name}
    if "off" not in prep:
        at, conf = align(part, cfg["audio"], cfg["audio_start"], start - PAD)
        if conf < 0.5:
            log(f"  sound match weak ({conf:.2f}); using the requested times")
            at = start - PAD
        off = min(max(start - at, 0.0), max(0.0, info["duration"] - dur))
        try:
            words, _ = listen.whisper_words(pcm(part, 16000, off, dur), 0.0, "base")
        except Exception as exc:                   # captions from the stream transcript instead
            log(f"  careful captions failed ({exc}); using the stream transcript")
            words = [dict(w, s=w["s"] - start, e=w["e"] - start) for w in cfg.get("words", [])
                     if start <= w["s"] < end]
        prep |= {"off": off, "conf": conf, "words": words}
    name = cfg["name"].lower()
    key = json.dumps([cfg["layout"], cfg["cam"], cams.get(name)])
    looks = prep.setdefault("looks", {})
    if key not in looks:
        looks[key] = frame.decide(part, prep["off"], dur, info, cfg["layout"], cfg["cam"], cams.get(name))
    cache.write_text(json.dumps(prep))
    look, cam, cx, note = looks[key]
    return {"part": part, "info": info, "off": prep["off"], "dur": dur, "conf": prep["conf"],
            "words": prep["words"], "look": look, "cam": cam, "cx": cx, "note": note}


def _chain(p, st, hook_h, cap_h, hook_in, cap_in):
    """The ffmpeg graph: framing, then the hook bar and the caption track on top."""
    c, h = st["captions"], st["hook"]
    cam_h = frame.cam_px(st["layout"]["cam_height"])
    hook_y, cap_y = frame.place(p["look"], p["info"], cam_h, h["position"], hook_h if h["show"] else 0,
                                c["position"], c["size"] if c["show"] else 0)
    chain = frame.graph(p["look"], p["info"], p["cam"], p["cx"] if p["cx"] is not None else 0.5, cam_h)
    last = "base"
    if h["show"]:
        chain += f";[{last}][{hook_in}:v]overlay=(W-w)/2:{int(hook_y - hook_h / 2)}[h]"
        last = "h"
    if c["show"]:
        chain += f";[{last}][{cap_in}:v]overlay=0:{int(cap_y - cap_h / 2)}:eof_action=pass[c]"
        last = "c"
    return chain + f";[{last}]format=yuv420p[v]"


def make(job, m, idx, cfg, cams, log=print):
    """cfg: url, audio, audio_start, cookies, layout, cam (box or None), name, style.
    Returns a summary dict for clips.json."""
    job, work = Path(job), Path(job) / "work"
    st = cfg["style"]
    log(f"clip {idx}: {m.get('hook', '')}  ({m['end'] - m['start']:.0f} s at {m['start'] / 60:.1f} min)")
    p = prepare(job, m, idx, cfg, cams, log)
    info, off, dur, look = p["info"], p["off"], p["dur"], p["look"]
    log(f"  look: {look} ({p['note']}); style: {st['preset']}")
    stem = f"{idx:02d}_{slug(m.get('hook') or m.get('kind', 'clip'))}"
    for old in job.glob(f"{idx:02d}_*"):
        old.unlink()
    ins = ["-ss", f"{off:.3f}", "-t", f"{dur:.3f}", "-i", str(p["part"])]
    hook_h = cap_h = 0
    if st["hook"]["show"]:
        hook_png, hook_h = overlay.hook_png(m.get("hook") or "", work / f"hook_{idx:02d}.png", st=st["hook"])
        ins += ["-i", str(hook_png)]
    if st["captions"]["show"]:
        caps, cap_h = overlay.caption_track(p["words"], dur, work / f"caps_{idx:02d}", st["captions"])
        ins += ["-f", "concat", "-safe", "0", "-i", str(caps)]
    chain = _chain(p, st, hook_h, cap_h, 1, 2 if st["hook"]["show"] else 1)
    audio = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" if info["audio"] else None
    out = job / f"{stem}.mp4"
    ffmpeg([*ins, "-filter_complex", chain + (";" + audio if audio else ""), "-map", "[v]",
            *(["-map", "[a]", "-c:a", "aac", "-b:a", "160k"] if audio else []),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(min(60, round(info["fps"]))),
            "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)], what="encoding the clip")
    check = job / f"{stem}_check.jpg"
    marks = [dur * 0.15, dur * 0.5, dur * 0.85]
    ins = [a for t in marks for a in ("-ss", f"{t:.2f}", "-i", str(out))]
    ffmpeg([*ins, "-filter_complex", "".join(f"[{i}:v]scale=360:640[s{i}];" for i in range(3))
            + "[s0][s1][s2]hstack=inputs=3[v]", "-map", "[v]", "-frames:v", "1", "-q:v", "3", str(check)],
           what="making the check image")
    got = probe(out)
    log(f"  -> {out.name} ({got['width']}x{got['height']}, {got['duration']:.0f} s)")
    return {"file": out.name, "check_image": check.name, "hook": m.get("hook"), "kind": m.get("kind"),
            "caption": m.get("caption"), "hashtags": m.get("hashtags", []), "score": m.get("score"),
            "why": m.get("why"), "look": look, "look_note": p["note"], "cam": p["cam"],
            "style": st["preset"], "stream_start": round(m["start"], 1), "duration": round(dur, 1),
            "sound_match": round(p["conf"], 2)}


def style_frame(job, m, idx, cfg, cams, st, t, out, label=None):
    """One 1080x1920 frame of clip idx at clip time t in style st (for the style sheet)."""
    job, work = Path(job), Path(job) / "work"
    p = prepare(job, m, idx, cfg, cams, lambda *_: None)
    tmp = work / "sheet"
    tmp.mkdir(exist_ok=True)
    ins = ["-ss", f"{p['off'] + t:.3f}", "-i", str(p["part"])]
    hook_h = cap_h = 0
    show = {"hook": st["hook"]["show"], "captions": st["captions"]["show"]}
    if show["hook"]:
        hook_png, hook_h = overlay.hook_png(m.get("hook") or "", tmp / "hook.png", st=st["hook"])
        ins += ["-i", str(hook_png)]
    got = overlay.caption_at(p["words"], p["dur"], t, tmp / "cap.png", st["captions"]) if show["captions"] else None
    if got:
        ins += ["-loop", "1", "-i", str(got[0])]          # one still image: keep it for the frame
        cap_h = got[1]
    st2 = dict(st, captions=dict(st["captions"], show=bool(got)))
    chain = _chain(p, st2, hook_h, cap_h, 1, 2 if show["hook"] else 1)
    ffmpeg([*ins, "-filter_complex", chain, "-map", "[v]", "-frames:v", "1", str(out)],
           what="making a style frame")
    return out


def still(job, idx, part_time=None):
    """Full 16:9 frame from clip idx's video with a 10% grid, to place a facecam by hand."""
    job = Path(job)
    found = sorted((job / "work" / "parts").glob(f"{idx:02d}_*.mp4"))
    part = found[-1] if found else None
    if part is None:
        raise ClipError(f"clip {idx} has no downloaded video yet; make the clips first")
    info = probe(part)
    t = part_time if part_time is not None else info["duration"] / 2
    grid = ",".join(
        [f"drawbox=x=iw*{i / 10}:y=0:w=2:h=ih:color=yellow@0.8:t=fill" for i in range(1, 10)]
        + [f"drawbox=x=0:y=ih*{i / 10}:w=iw:h=2:color=yellow@0.8:t=fill" for i in range(1, 10)])
    out = job / f"{idx:02d}_grid.jpg"
    ffmpeg(["-ss", f"{t:.2f}", "-i", str(part), "-vf", f"scale=1280:-2,{grid}", "-frames:v", "1",
            "-q:v", "3", str(out)], what="making the grid still")
    return out


def post_sheet(job, stream, clips):
    lines = [f"# {stream['name']}: {stream.get('title', '')}", "", f"Source: {stream['url']}", "",
             "Watch every clip before you post it. Credit the streamer. Post only where the streamer "
             "allows clips (most big streamers run clipping programs).", ""]
    for c in clips:
        t = int(c["stream_start"])
        lines += [f"## {c['file']}", f"On screen: **{c['hook']}** ({c['kind']}, {c['duration']:.0f} s, "
                  f"score {c['score']})", "", "Caption to paste:", "", "```",
                  f"{c['caption']}\n\n{' '.join(c['hashtags'])}\n\nclip: {stream['name']}", "```",
                  f"From the stream at {t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}. Why: {c['why']}", ""]
    (Path(job) / "POST.md").write_text("\n".join(lines), encoding="utf-8")
    (Path(job) / "clips.json").write_text(json.dumps({"stream": stream, "clips": clips}, indent=2))

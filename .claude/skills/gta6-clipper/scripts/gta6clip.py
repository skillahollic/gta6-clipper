"""gta6clip: GTA 6 streams in, ready-to-post vertical clips out.

  doctor                      set up and test everything; prints READY
  find [--list]               today's biggest GTA 6 streams (and clip them without --list)
  clip URL [URL ...]          clip these streams (YouTube, Twitch, Kick)
  render JOB [--only 1,3]     make clips again from JOB/moments.json (after edits, or in a new style)
  still JOB --clip N          a full frame with a % grid, to place a facecam by hand
  styles [JOB]                list the looks; with a JOB, a sheet: one frame of a clip in every look

Change the look with no code edits: --style NAME|FILE.json and --set part.setting=value
(e.g. --style karaoke --set captions.text_color=yellow --set captions.position=top).
The job keeps its style in JOB/style.json; `render JOB` uses it again.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clipper import find as finder  # noqa: E402
from clipper import frame, listen, make, media, pick, style  # noqa: E402
from clipper.media import ClipError  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
_print = threading.Lock()


def logger(tag=""):
    def log(msg):
        with _print:
            print(f"[{time.strftime('%H:%M:%S')}] {tag + ': ' if tag else ''}{msg}", flush=True)
    return log


def hms(text):
    total = 0.0
    for p in str(text).split(":"):
        total = total * 60 + float(p)
    return total


def load_cams(root):
    p = root / "cams.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_cam(root, name, box):
    cams = load_cams(root)
    cams[name.lower()] = [round(v, 4) for v in box]
    (root / "cams.json").write_text(json.dumps(cams, indent=2))


# ---------------- doctor ----------------

def doctor(args):
    ok, bad = [], []
    def check(label, fn):
        try:
            ok.append(f"{label}: {fn()}")
            print(f"  OK   {ok[-1]}", flush=True)
        except Exception as exc:
            bad.append(f"{label}: {str(exc).splitlines()[0][:200]}")
            print(f"  FIX  {bad[-1]}", flush=True)

    print("Checking this computer for the GTA 6 clipper...")
    check("Python", lambda: sys.version.split()[0])
    check("ffmpeg (own copy)", lambda: media.run([media.FFMPEG, "-version"]).split()[2])
    check("yt-dlp", lambda: media.ytdlp(["--version"]).strip())
    check("deno (for YouTube)", lambda: media.run(["deno", "--version"]).split()[1])
    check("Claude Code", lambda: media.run([pick.claude_path(), "--version"]).strip())
    if not args.skip_claude:
        check("Claude answers (uses your subscription, a few tokens)",
              lambda: "yes" if pick.ask("Reply with ok=true.", {"type": "object", "required": ["ok"],
                                        "properties": {"ok": {"type": "boolean"}}}, "haiku")["ok"] else "no")
    check("free disk", lambda: _disk(args.out))
    check("Whisper speech models (one-time ~220 MB download)",
          lambda: [listen.model(n) for n in ("tiny", "base")] and f"ready in {listen.MODELS_DIR}")
    check("facecam finder (OpenCV YuNet, 0.2 MB, checksum verified)",
          lambda: frame.ensure_face_model().name)
    check("test clip (render chain)", lambda: _selftest(args.out))
    print()
    if bad:
        print("NOT READY. Fix the FIX lines, then run doctor again.")
        sys.exit(1)
    args.out.mkdir(parents=True, exist_ok=True)
    wl = args.out / "streamers.txt"
    if not wl.exists():
        shutil.copy(SKILL / "streamers.txt", wl)
    print(f"READY. Clips go to {args.out}")


def _disk(root):
    root.mkdir(parents=True, exist_ok=True)
    gb = shutil.disk_usage(root).free / 1e9
    if gb < 3:
        raise ClipError(f"only {gb:.1f} GB free; keep at least 3 GB free")
    return f"{gb:.0f} GB"


def _selftest(root):
    """Renders a 6-second clip from a made-up stream through the real pipeline."""
    t = root / ".selftest"
    (t / "work" / "parts").mkdir(parents=True, exist_ok=True)
    src = t / "work" / "parts" / "01.mp4"
    media.ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=8",
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                  "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src)])
    words = [{"s": 0.5 + i * 0.4, "e": 0.85 + i * 0.4, "w": w}
             for i, w in enumerate("this is the clipper self test running fine".split())]
    info = media.probe(src)
    for look, cam in (("stack", [0.7, 0.62, 0.3, 0.38]), ("fit", None)):
        hook, hh = make.overlay.hook_png("SELF TEST hook bar", t / "hook.png")
        caps, _ = make.overlay.caption_track(words, 6, t / "caps")
        y1, y2 = frame.text_spots(look, info)
        out = t / f"{look}.mp4"
        media.ffmpeg(["-ss", "1", "-t", "6", "-i", str(src), "-i", str(hook), "-f", "concat", "-safe", "0",
                      "-i", str(caps), "-filter_complex", frame.graph(look, info, cam)
                      + f";[base][1:v]overlay=(W-w)/2:{int(y1 - hh / 2)}[h];[h][2:v]overlay=0:{y2 - 165}"
                      ":eof_action=pass,format=yuv420p[v];[0:a]loudnorm=I=-14[a]",
                      "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
                      "-c:a", "aac", "-t", "6", str(out)])
        got = media.probe(out)
        if (got["width"], got["height"]) != (1080, 1920) or abs(got["duration"] - 6) > 0.5:
            raise ClipError(f"test clip came out {got['width']}x{got['height']}, {got['duration']:.1f} s")
    shutil.rmtree(t)
    return "two 1080x1920 test clips made"


# ---------------- clip ----------------

def span(text):
    """'20m', '1h30m', '90s', '20:00' or '1200' -> seconds."""
    t = str(text).strip().lower()
    if t and t[-1] in "hms":
        total, num = 0.0, ""
        for ch in t:
            if ch in "hms":
                total += float(num or 0) * {"h": 3600, "m": 60, "s": 1}[ch]
                num = ""
            else:
                num += ch
        return total
    return hms(t)


def resolve(url, cookies):
    """Stream info. A live Twitch channel becomes its in-progress VOD (the part saved so far).
    A Twitch VOD link is used as it is, also while it is still recording."""
    info = media.info(url, cookies)
    if info.get("live_status") != "is_live":
        return info
    if info["site"] == "twitchvod":                    # a VOD that is still recording
        return info | {"recording": True}
    if "twitch" in info["site"]:                       # a live channel: find its saved VOD
        login = info.get("uploader_id") or url.rstrip("/").split("/")[-1]
        got = finder._flat(f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time", 1)
        if got and got[0].get("url"):
            vod = media.info(got[0]["url"], cookies)
            if vod.get("live_status") == "is_live":    # the newest VOD is this live stream
                return vod | {"recording": True}
        raise ClipError("this Twitch stream is live, but the channel does not save it as a VOD "
                        "(or the VOD is not up yet). Try again in a few minutes, or clip a past VOD.")
    raise ClipError("this YouTube stream is still live. Clip it when it ends (the replay "
                    "appears right after), or use a Twitch link.")


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def choose_section(info, section=None, last=None):
    """((start, end) in stream seconds, or None for the whole stream; a note for the user).
    A stream that is still recording is cut at the part saved so far."""
    saved = float(info.get("duration") or 0)
    live = bool(info.get("recording"))
    so_far = " so far" if live else ""
    if live and not saved:
        raise ClipError("this live stream has no saved minutes yet. Try again in a few minutes.")
    if last:
        if not saved:
            raise ClipError("--last needs a stream with a known length. Use --section instead.")
        want = span(last)
        got = (max(0.0, saved - want), saved)
        note = f"the last {fmt(got[1] - got[0])} ({fmt(got[0])}-{fmt(got[1])})"
        if want > saved:
            note += f"; you asked for {fmt(want)}, but only {fmt(saved)} is saved{so_far}"
        return got, note
    if section:
        a, _, b = section.partition("-")
        a = hms(a)
        b = hms(b) if b else (saved or a + 3600)
        if saved and a >= saved:
            raise ClipError(f"the stream has only {fmt(saved)} saved{so_far}; {fmt(a)} is past the end.")
        if saved and b > saved:
            return (a, saved), (f"{fmt(a)}-{fmt(saved)}; you asked up to {fmt(b)}, "
                                f"but only {fmt(saved)} is saved{so_far}")
        return (a, b), f"{fmt(a)}-{fmt(b)}"
    if live:                                           # never follow the live edge: it never ends
        return (0.0, saved), f"all {fmt(saved)} saved so far"
    return None, "the whole stream"


def one_stream(url, args, root):
    log = logger(url.split("/")[-1][:20])
    t0 = time.time()
    info = resolve(url, args.cookies)
    url = info.get("webpage_url") or url
    log = logger(info["name"][:20])
    section, note = choose_section(info, args.section, args.last)
    if info.get("recording"):
        log(f"LIVE: using the VOD it is saving now ({url})")
    log(f"clipping {note}")
    tag = f"_{int(section[0])}-{int(section[1])}" if section else ""
    day = datetime.date.today().isoformat()
    job = root / f"{day}_{make.slug(info['name'], 24)}_{info['id']}{tag}"
    work = job / "work"
    work.mkdir(parents=True, exist_ok=True)
    (job / "job.json").write_text(json.dumps({"url": url, "info": info, "section": section}, indent=2))
    log(f"{info.get('title', '')[:70]} ({(info.get('duration') or 0) / 3600:.1f} h)")

    if not any(work.glob("audio.*")):
        log("downloading the audio only (the video comes later, just for the clips)...")
    audio = media.download_audio(url, work, section, args.cookies)
    length = media.probe(audio)["duration"]
    base = (section[0] if section else 0.0, (section[0] if section else 0.0) + length)
    data = listen.transcript(url, audio, work, base, info["site"], args.cookies, log)
    loud = listen.loudness(audio, work, base)
    chat = None if args.no_chat else listen.chat_speed(url, work, info, args.cookies, log)
    log(f"heard {len(data['words']):,} words ({data['source']}), "
        f"chat {'used' if chat else 'not available'}")

    moments_file = job / "moments.json"
    if moments_file.exists() and not args.repick:
        moments = json.loads(moments_file.read_text())
        log(f"reusing {len(moments)} picked moment(s) (add --repick to pick again)")
    else:
        moments = pick.pick(info, data, loud, chat, args.clips, work, args.model, log=log)
        moments_file.write_text(json.dumps(moments, indent=2))
        for f in list(job.glob("[0-9][0-9]_*")) + [job / "clips.json"]:
            f.unlink(missing_ok=True)                  # new picks: old clips no longer match
    t_pick = time.time() - t0
    render(job, args, root, log, words=data["words"], resume=not args.repick)
    log(f"done in {(time.time() - t0) / 60:.1f} min (picking took {t_pick / 60:.1f} min)")
    return job


def render(job, args, root, log=None, words=None, resume=False):
    job = Path(job)
    log = log or logger(job.name[:20])
    meta = json.loads((job / "job.json").read_text())
    info, url = meta["info"], meta["url"]
    work = job / "work"
    audio = next(p for p in work.glob("audio.*") if p.suffix not in (".part", ".ytdl"))
    if words is None and (work / "transcript.json").exists():
        words = json.loads((work / "transcript.json").read_text())["words"]
    cam = frame.parse_cam(args.cam)
    if cam:
        save_cam(root, info["name"], cam)
    st = job_style(job, args, root)
    log(f"style: {st['preset']} (saved in {job / 'style.json'})")
    moments = json.loads((job / "moments.json").read_text())
    only = {int(x) for x in args.only.split(",")} if getattr(args, "only", None) else None
    old = {}
    if (job / "clips.json").exists():
        old = {int(c["file"][:2]): c for c in json.loads((job / "clips.json").read_text())["clips"]}
    cfg = {"url": url, "audio": audio, "audio_start": (meta["section"] or [0])[0], "cookies": args.cookies,
           "layout": st["layout"]["look"], "cam": cam, "name": info["name"], "words": words or [], "style": st}
    cams = load_cams(root)
    for i, m in enumerate(moments, 1):
        if only and i not in only:
            continue
        if resume and i in old and (job / old[i]["file"]).exists():
            continue                                   # made in an earlier run

        try:
            old[i] = make.make(job, m, i, cfg, cams, log)
        except ClipError as exc:
            log(f"clip {i} failed: {exc}")
    clips = [old[k] for k in sorted(old)]
    make.post_sheet(job, {"name": info["name"], "title": info.get("title"), "url": url}, clips)
    log(f"{len(clips)} clip(s) in {job}")
    for c in clips:
        log(f"  [{c['score']}] {c['file']}  look={c['look']}  check: {c['check_image']}")
    return clips


def job_style(job, args, root):
    """The style for this run: --style, else the job's own style.json, else the viewer's saved
    `default` style, else classic. --layout and every --set apply on top. Saved to JOB/style.json."""
    saved = root / "styles"
    spec = getattr(args, "style", None)
    if spec:
        st = style.load(spec, saved)
    elif (Path(job) / "style.json").exists():
        st = style.load(Path(job) / "style.json")
    elif (saved / "default.json").exists():
        st = style.load(saved / "default.json")
    else:
        st = style.load(style.DEFAULT)
    sets = list(getattr(args, "set", None) or [])
    if getattr(args, "layout", None):
        sets.append(f"layout.look={args.layout}")
    st = style.apply_sets(st, sets)
    c = st["captions"]
    if c["show"] and c["text_color"] == c["highlight_color"] and c["box"] != "word":
        print("NOTE: the spoken word has the same colour as the other words. Also set "
              "captions.highlight_color (for example white) so it still stands out.", flush=True)
    style.save(st, Path(job) / "style.json")
    if getattr(args, "save_style", None):
        style.save(st, saved / f"{style_name(args.save_style)}.json")
    return st


def style_name(text):
    name = make.slug(text, 30)
    if name in style.PRESETS:
        raise style.StyleError(f"'{name}' is a built-in preset; save your style under another name")
    return name


def styles(args, root):
    """No job: list the presets. With a job: a sheet with one frame of a clip in each style."""
    if not args.targets:
        print(style.listing())
        saved = sorted(p.stem for p in (root / "styles").glob("*.json"))
        if saved:
            print(f"\nYour saved styles (in {root / 'styles'}): {', '.join(saved)}")
        return
    from PIL import Image, ImageDraw
    job = Path(args.targets[0])
    meta = json.loads((job / "job.json").read_text())
    moments = json.loads((job / "moments.json").read_text())
    idx = args.clip
    if not 1 <= idx <= len(moments):
        raise ClipError(f"this job has clips 1-{len(moments)}")
    m = moments[idx - 1]
    names = [n.strip() for n in (args.style or ",".join(style.PRESETS)).split(",") if n.strip()]
    looks = [(n, style.apply_sets(style.load(n, root / "styles"), args.set)) for n in names]
    work = job / "work"
    audio = next(p for p in work.glob("audio.*") if p.suffix not in (".part", ".ytdl"))
    cam = frame.parse_cam(args.cam)
    base = job_style(job, argparse.Namespace(style=None, set=None, layout=args.layout, save_style=None), root)
    cfg = {"url": meta["url"], "audio": audio, "audio_start": (meta["section"] or [0])[0],
           "cookies": args.cookies, "layout": base["layout"]["look"], "cam": cam,
           "name": meta["info"]["name"], "words": []}
    cams = load_cams(root)
    p = make.prepare(job, m, idx, cfg, cams, logger(job.name[:20]))
    t = args.at
    if t is None:                                  # a full 3-word phrase near the middle; 2nd word lit
        said = make.overlay.groups([w for w in p["words"] if 0 <= w["s"] < p["dur"] - 1], 3)
        best = max(said, key=lambda g: (len(g), -abs(g[0]["s"] - p["dur"] / 2)), default=None)
        t = best[min(1, len(best) - 1)]["s"] + 0.05 if best else p["dur"] / 2
    tiles = []
    for n, st in looks:
        if st["layout"] == style.CLASSIC["layout"]:    # a look that leaves the framing alone
            st = dict(st, layout=base["layout"])
        cfg["layout"] = st["layout"]["look"]
        out = work / "sheet" / f"{make.slug(n)}.png"
        make.style_frame(job, m, idx, cfg, cams, st, t, out)
        tile = Image.open(out).convert("RGB").resize((432, 768), Image.LANCZOS)
        card = Image.new("RGB", (432, 830), (18, 18, 18))
        card.paste(tile, (0, 62))
        ImageDraw.Draw(card).text((216, 31), Path(n).stem.upper()[:18], font=make.overlay.font(34, "archivo-black"),
                                  fill=(255, 255, 255), anchor="mm")
        tiles.append(card)
    cols = min(len(tiles), 5)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 432 + (cols + 1) * 16, rows * 830 + (rows + 1) * 16), (18, 18, 18))
    for i, card in enumerate(tiles):
        sheet.paste(card, (16 + (i % cols) * 448, 16 + (i // cols) * 846))
    path = job / f"{idx:02d}_styles.jpg"
    sheet.save(path, quality=90)
    print(f"style sheet ({', '.join(names)}; clip {idx} at {t:.1f} s): {path}")


def quiet_mac_warnings():
    """On Macs, two bundled libraries print a harmless 'Class ... implemented in both'
    warning. Run the work in a child process and drop those lines from its errors."""
    if sys.platform != "darwin" or os.environ.get("GTA6CLIP_CHILD"):
        return
    proc = subprocess.Popen([sys.executable, __file__, *sys.argv[1:]], stderr=subprocess.PIPE,
                            env=dict(os.environ, GTA6CLIP_CHILD="1"), text=True, errors="replace")
    for line in proc.stderr:
        if not line.startswith("objc[") and "One of the two will be used" not in line:
            sys.stderr.write(line)
    sys.exit(proc.wait())


def main(argv=None):
    if argv is None:
        quiet_mac_warnings()
    p = argparse.ArgumentParser(prog="gta6clip", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["doctor", "find", "clip", "render", "still", "styles"])
    p.add_argument("targets", nargs="*", help="stream links (clip) or a job folder (render, still)")
    p.add_argument("--out", type=Path, default=Path(os.environ.get("GTA6CLIP_OUT") or Path.home() / "gta6-clips"),
                   help="where clips go (default ~/gta6-clips, or $GTA6CLIP_OUT)")
    p.add_argument("--clips", type=int, default=3, help="clips per stream (default 3)")
    p.add_argument("--section", help='only part of the stream, e.g. "1:00:00-2:30:00"')
    p.add_argument("--last", help='only the most recent part, e.g. "20m" (live Twitch: up to now)')
    p.add_argument("--streams",type=int, default=5, help="find: how many streams")
    p.add_argument("--list", action="store_true", help="find: only list the streams")
    p.add_argument("--parallel", type=int, default=2, help="streams at the same time")
    p.add_argument("--model", help="Claude model for picking, e.g. sonnet (uses less of your plan)")
    p.add_argument("--layout", choices=["auto", "stack", "crop", "fit"],
                   help="framing (default: the style's layout.look, which is auto)")
    p.add_argument("--style", help="a look: a preset (see `styles`), a saved style name or a .json file; "
                   "styles JOB: a comma list to compare")
    p.add_argument("--set", action="append", metavar="PART.SETTING=VALUE",
                   help="change one setting, e.g. captions.text_color=yellow, captions.size=+20%%, hook.show=off")
    p.add_argument("--save-style", metavar="NAME", help="also save this look as NAME (NAME default = "
                   "used for every new job)")
    p.add_argument("--at", type=float, help="styles JOB: the second of the clip to show")
    p.add_argument("--cam", help="facecam spot: top-left, top-right, bottom-left, bottom-right or x,y,w,h in %%")
    p.add_argument("--only", help="render: only these clip numbers, e.g. 1,3")
    p.add_argument("--clip", type=int, default=1, help="still, styles: which clip")
    p.add_argument("--repick", action="store_true", help="pick the moments again")
    p.add_argument("--no-chat", action="store_true", help="do not read the YouTube chat replay")
    p.add_argument("--cookies", choices=["chrome", "safari", "firefox", "edge", "brave"],
                   help="use your browser's login (only for age-limited or Kick streams)")
    p.add_argument("--skip-claude", action="store_true", help="doctor: do not test a Claude call")
    args = p.parse_args(argv)
    root = args.out.expanduser()
    args.out = root
    try:
        if args.command == "doctor":
            return doctor(args)
        if args.command == "styles":
            return styles(args, root)
        if args.command == "still":
            print(make.still(args.targets[0], args.clip))
            return
        if args.command == "render":
            for job in args.targets:
                render(job, args, root)
            return
        urls = list(args.targets)
        if args.command == "find":
            found = finder.find(root / "streamers.txt", args.streams)
            if not found:
                raise ClipError("no GTA streams found right now. Paste links, or add streamers to "
                                f"{root / 'streamers.txt'}")
            for i, s in enumerate(found, 1):
                print(f"{i}. {s['name'][:24]:24} {s['views']:>10,} views {'LIVE ' if s['live'] else ''}"
                      f"| {s['title'][:60]} ({s['source']})\n   {s['url']}")
            if args.list:
                return
            urls += [s["url"] for s in found if not s["live"] or "twitch" in s["url"]]
        if not urls:
            raise ClipError("give me stream links, or use find")
        jobs = []
        with ThreadPoolExecutor(max(1, args.parallel)) as pool:
            futures = [(u, pool.submit(one_stream, u, args, root)) for u in urls]
            for u, fut in futures:
                try:
                    jobs.append(fut.result())
                except ClipError as exc:
                    logger()(f"{u}: {exc}")
        print("\nFinished. Clip folders:" if jobs else "\nNo clips were made.")
        for j in jobs:
            print(f"  {j}")
        if not jobs:
            sys.exit(1)
    except ClipError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

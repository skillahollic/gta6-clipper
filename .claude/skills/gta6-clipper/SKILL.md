---
name: gta6-clipper
description: Turns GTA 6 (or any GTA) streams into ready-to-post vertical clips, locally and free. Finds the biggest GTA streams or takes YouTube, Twitch or Kick links, listens to the stream, has Claude pick the best moments (first reactions, discoveries, freak-outs, funny fails, hot takes) with the viewer's own Claude subscription, and makes 9:16 clips with the facecam on top, gameplay below, a hook title, word-by-word captions and a paste-ready caption with hashtags. Use when someone says "set up the GTA 6 clipper", "clip this stream", "find today's biggest GTA 6 streams", or wants Shorts/Reels/TikToks from a stream VOD. Also use it to change the look of made clips (caption style, colours, subtitle size or position, hook title, facecam size).
---

# GTA 6 Clipper

You run the commands; the user only gives links or says "find streams". Speak in plain words: most users do not code.
`SKILL` = the folder of this file. Every command is `uv run --project "SKILL" "SKILL/scripts/gta6clip.py" <command>`
(written `gta6clip <command>` below). Clips go to `~/gta6-clips/<date>_<streamer>_<id>/`.

## 1. Set up (first time, or when something fails)
1. `uv --version`. If missing, ask the user, then install uv the official way (no admin password):
   Mac: `curl -LsSf https://astral.sh/uv/install.sh | sh` · Windows PowerShell:
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Open a new terminal after.
2. `gta6clip doctor`. It installs everything into this folder (Python, ffmpeg, yt-dlp, deno, speech
   models; about 700 MB), makes a test clip and makes one tiny Claude call. Wait for **READY**.
   Fix each `FIX` line it prints, then run it again.

## 2. Clip
- `gta6clip clip URL [URL ...]` (3 clips per stream; `--clips N`). Long streams: `--section 1:00:00-3:00:00`.
- `gta6clip find --list` shows today's biggest GTA streams; `gta6clip find --streams 5` clips them.
- Run it in the background (a 4-hour stream: 10-20 minutes). Tell the user each stage in plain words.
- Re-running the same command resumes. `--repick` picks moments again. `--model sonnet` uses less of the plan.
- YouTube replays use YouTube's own captions (fast); Twitch and Kick are transcribed on the computer.
- Most recent part only: `--last 20m` (also `1h`, `90s`). "Clip the last 20 minutes of kaicenat" =
  `gta6clip clip https://www.twitch.tv/kaicenat --last 20m`. A live Twitch channel or its VOD link
  is clipped from the VOD it is saving now, up to now. If less is saved than asked, it clips what is
  saved and says so in the log: tell the user. Each run on a live stream makes a new job folder.
- A live YouTube stream cannot be clipped until it ends.

## 3. Check every clip before you call it done (this is your job)
For each clip, open `NN_..._check.jpg` (3 frames from the clip) with the Read tool and check:
- top panel (look `stack`) shows the streamer's face, not gameplay or a logo;
- captions are readable and match the speech; the hook names the right streamer and is not a spoiler.
If the facecam is wrong: `gta6clip still JOB --clip N`, open `NN_grid.jpg` (yellow lines every 10%),
read the cam's box as x,y,w,h in percent, then `gta6clip render JOB --only N --cam x,y,w,h`.
The spot is saved for that streamer and used first next time. Other fixes: edit the clip's
`hook`, `caption`, `start` or `end` in `JOB/moments.json`, then `gta6clip render JOB --only N`. No facecam: `--layout fit` (the whole frame).

## 4. Change the look (never edit the code for this)
Captions, hook title and layout come from a style. `gta6clip styles` lists the presets (classic,
karaoke, minimal, bold, neon) and every setting; offer them by name. Turn the user's words into
`gta6clip render JOB [--style NAME] --set part.setting=value ...` (fast: no new download or picking;
the job keeps its style in `JOB/style.json`). Read `reference/styles.md` first (phrases, files, saving).
To compare looks: `gta6clip styles JOB` makes `NN_styles.jpg` (one frame per preset); show it.

## 5. Hand over
Tell the user: the clip files, the hook of each, and that `POST.md` has the caption to paste.
Never post, upload or log in for the user. Remind them once: watch each clip, credit the streamer,
and clip only streamers who allow it (most big ones run clipping programs).
`JOB/work/` (audio and video parts, about 0.2 GB per job) can be deleted after posting.

## 6. Problems
- "age limit" or Kick 403: the stream needs a signed-in browser. Explain this, and only with the user's
  OK add `--cookies chrome` (or safari, firefox, edge, brave). Never use cookies without asking.
- "sound match weak": the clip may start up to a few seconds off; check the check image, `--repick` or edit times.
- "Claude found nothing": a quiet stream. Try another stream or a different `--section`.
- Claude usage limit: wait for the limit to reset, then run the same command (it resumes).

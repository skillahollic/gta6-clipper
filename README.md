# GTA 6 Clipper (a free Claude Code skill)

Give it a GTA 6 stream link (YouTube, Twitch or Kick), or let it find today's biggest GTA 6 streams.
It gives you ready-to-post vertical clips:

- the best moments: first reactions, crazy discoveries, freak-outs, funny fails, hot takes
- facecam on top, gameplay below (or a smart crop when there is no facecam)
- a hook title and word-by-word captions
- a `POST.md` with a caption and hashtags to paste for every clip

It runs on your computer and costs nothing extra. Claude picks the moments with your own
Claude subscription (no API key). It downloads only the stream's audio plus the minutes that become clips.

## What you need

- A Mac (Apple Silicon or Intel) or a Windows 10/11 PC, with about 3 GB of free disk.
- [Claude Code](https://claude.com/claude-code), signed in with a Claude plan (Pro or higher).
- An internet connection. You do **not** need Homebrew, Python, ffmpeg or any coding.
  The setup puts everything it needs (about 700 MB) inside the skill's own folder.

## Install

1. Download this repository as a ZIP and unzip it. The skill is the folder
   `.claude/skills/gta6-clipper` (on a Mac, press Cmd+Shift+. in Finder to see folders that start with a dot).
2. Open Claude Code and paste:

   > Copy the folder `.claude/skills/gta6-clipper` from the unzipped GTA 6 Clipper download in my Downloads
   > folder into my personal skills folder (`~/.claude/skills/` on Mac, `%USERPROFILE%\.claude\skills\` on
   > Windows). Then set up the GTA 6 clipper.

   Claude installs `uv` if it is missing (a free, official installer, no admin password; Claude asks you first),
   then runs the setup. It makes a test clip and stops when it says **READY** (about 2-5 minutes).

   Shortcut: open Claude Code inside the unzipped folder and say "set up the GTA 6 clipper".
   The skill works from there too, just not in your other folders.

## Try it in 3 steps

1. In Claude Code, say: **"set up the GTA 6 clipper"** and wait for READY.
2. Say: **"clip this stream: <paste a YouTube, Twitch or Kick link>"**
   (or **"find today's biggest GTA 6 streams and clip them"**).
3. Open the folder Claude names (in `gta6-clips` in your home folder). Watch each clip, then post it with
   the caption from `POST.md`.

Claude checks every clip before it says it is done. If the facecam is cut wrong, say
"the facecam is wrong on clip 2" and Claude fixes it, and remembers that streamer's facecam spot next time.

## Change the look

Everything you see is a setting, so you just ask Claude, and it changes no code:

- "Use the karaoke style" (or classic, minimal, bold, neon). "Show me all the styles" makes one picture
  with the same moment in every style, side by side.
- "Make the captions yellow", "bigger subtitles", "captions at the top", "one word at a time",
  "no all caps", "no hook title", "black title box", "make the facecam bigger".
- "Save this look as my default": new clips come out that way.

A new look re-uses the downloaded video and the words, so it takes seconds per clip. Behind the scenes,
each clip folder has a small `style.json`. Claude can also write that file for you.

Fonts: the classic look uses your computer's Arial Black. The other looks use two free fonts that come
with the skill (in `fonts/`): Archivo (Copyright 2020 The Archivo Project Authors) and Big Shoulders
(Copyright 2019 The Big Shoulders Project Authors), both under the SIL Open Font License 1.1
(`fonts/OFL.txt`). You may share and re-use them, but not sell the fonts by themselves.

## Good to know

- A 4-hour stream takes about 10-20 minutes. YouTube replays are fastest (Claude reads YouTube's own captions).
- For long streams, ask for a part: "clip 1:00:00 to 3:00:00 of this stream".
- A live Twitch stream can be clipped while it runs: "clip the last 20 minutes of twitch.tv/kaicenat".
  It clips what the channel has saved so far (if less than 20 minutes is saved, it clips that and tells you).
  A YouTube stream that is still live can be clipped after it ends.
- Age-limited YouTube streams and some Kick streams need your browser's login. Claude asks before it uses it.
- Picking uses your Claude plan: about one short message per 9 minutes of stream (about 28 for 4 hours).
  Say "use sonnet" to use less.
- Watch every clip before you post it. Credit the streamer, and clip streamers who allow it
  (most big streamers run clipping programs that pay per view). You post. The skill never posts for you.
- To uninstall, delete the `gta6-clipper` skill folder. Your clips stay in `gta6-clips`.

## Files

`SKILL.md` (what Claude follows) · `reference/styles.md` (how Claude turns your words into a look) ·
`scripts/gta6clip.py` (the command) · `scripts/clipper/` (download, listen, pick, frame, captions, `style.py`
for the looks) · `fonts/` (OFL fonts) · `tests/` (offline tests of the live-stream logic and the styles:
`uv run --project <skill folder> python -m unittest discover -s <skill folder>/tests`) · `pyproject.toml` + `uv.lock` (exact package versions) · `streamers.txt` (watchlist).
`TEST.md` shows the tests. MIT licence.

# TEST.md: GTA 6 Clipper, round 1

Date: Sun Nov 15 2026, 08:58-09:23 IST (clock checked with `date`).
Machine: MacBook, Apple Silicon, macOS 15 (Darwin 24.3.0). Claude Code 2.1.318.
All test files were in `/tmp/gta6clip-r1/` (removed at the end). The skill's own `.venv` and `.models`
were made inside the skill folder (git-ignored) and removed before the commit.
`SKILL` below = `.claude/skills/gta6-clipper`. `UV_CACHE_DIR` was set to the temp folder for every run.

## Test stream

One public stream only: Kai Cenat's Twitch VOD `https://www.twitch.tv/videos/2924282282`
(35 h long, title says GTA 4, the picture shows GTA V; GTA 6 is not out yet). Downloaded: the audio of
10:00:00-10:20:00 only, plus the video minutes of the picked clips. No cookies, no login.

## Commands and results

| # | Command | Result |
|---|---|---|
| 1 | `uv sync` of the package list in a temp project | PASS: all packages install; the bundled ffmpeg 9.0 has libx264, overlay, gblur, loudnorm; `deno` 2.9.8 comes from PyPI |
| 2 | `uv run --project SKILL SKILL/scripts/gta6clip.py --help` | PASS |
| 3 | `... gta6clip.py doctor --out /tmp/gta6clip-r1/clips` | PASS: READY in 42 s (Python, ffmpeg, yt-dlp, deno, Claude call, disk, Whisper models, two 1080x1920 test clips) |
| 4 | `... find --list` | PASS: 5 streams in 6 s. Found a problem: a "#shorts" live and a 10-min news video were listed. FIXED: skip `#shorts` and videos under 20 min |
| 5 | `... clip <VOD> --section 10:00:00-10:20:00 --clips 2` | PASS: 2 clips in 3.0 min (audio 11 s, Whisper 20 s, Claude 18 s, 2 renders). FAIL in quality: both clips used the `fit` look, the facecam was not found |
| 6 | Debug of face finding on the two clip parts | Found: OpenCV's built-in Haar finder misses Kai's 40-px face and finds faces in dark gameplay. FIXED: OpenCV YuNet model (0.2 MB, SHA-256 pinned) + a full-size second pass + a new "stillness" clue for the cam border |
| 7 | `... render JOB` | PASS: both clips now `stack` (face in 100% / 75% of frames, 4/4 cam sides found). Frames checked: face on top, gameplay below, hook on the seam, captions readable |
| 8 | `... render JOB --only 2 --cam 0,25,20.5,20` | PASS: hand-placed cam used and saved to `cams.json` for this streamer |
| 9 | `... still JOB --clip 1` | PASS: full frame with a 10% grid; used it to read the cam box for test 8 |
| 10 | Same `clip` command again (resume) | PASS: 3 s, nothing downloaded or re-made |
| 11 | `... clip ... --clips 3 --repick` (new prompts) | PASS: 2 clips in 1.2 min, scores 72 and 66 (before: 58, 48). Saved cam spot reused. The editor kept 2 of 3 (the third candidate was weak; allowed by design) |
| 12 | Viewer test, setup: clean copy of the repo, PATH = only `uv` + `claude` + `/usr/bin:/bin` (no Homebrew ffmpeg, deno, yt-dlp or Python), uv forced to download its own Python. Headless `claude -p "set up the GTA 6 clipper"` inside the unzipped folder (README shortcut), tools limited to `Bash(uv:*)`, Read, Glob, Grep | PASS: Claude found the skill, read its code, ran `doctor`, got READY (Python 3.13), and explained the result in plain words |
| 13 | Viewer test, clips: the same clean install renders the job (video parts downloaded again through the bundled ffmpeg) | PASS: 2 clips, 1080x1920, 60 fps, AAC 48 kHz, in 1.1 min |
| 14 | `py_compile` + `ruff check --select F,E9` | PASS |

Checks on the output files: `ffprobe` (1080x1920 H.264 + AAC 48 kHz, lengths 41 s and 52 s);
3-frame check images and 540-px stills opened and looked at; captions match the game's own
on-screen subtitles ("GO TOSS A" / "...go toss a salad"), so caption timing is right; sound match
between clip video and stream audio = 1.00 and 0.98; loudness -12 LUFS (target -14, one-pass loudnorm).

## Problems found and fixed in this round

1. Facecam not found (test 5): replaced the face finder, added full-size pass and stillness clue (test 6-7).
2. Prompts said "GTA 6" for every stream: the first clips got `#gta6` on a GTA 4 stream. Now the game
   comes from the title; after the fix the hashtags were `#gta4 #gtaiv`.
3. `find` listed Shorts and short videos (test 4).
4. A re-run re-made every clip; now finished clips are skipped, and `--repick` clears old clips.
5. Edited clip times reused the old video part; parts are now named by their times.
6. Mac printed a scary "Class ... implemented in both" warning (two bundled libraries); now hidden.
7. Hook lines were unbalanced (one word alone on line 3); lines are now balanced.

## What is better than the creator's version, and how we know

| Creator's version | This skill | How we know |
|---|---|---|
| Captions use ffmpeg's `ass` filter, and the README says `brew install ffmpeg`. Homebrew's ffmpeg 8.0.1 on this Mac has **no** `ass` (or `drawtext`) filter, so every clip would fail at the caption step | Captions and hook are drawn as images (Pillow) and laid over by the skill's own ffmpeg | `ffmpeg -vf ass=...` with Homebrew ffmpeg: "No such filter: 'ass'" (exit 8). Our clips render with no Homebrew at all (tests 12-13) |
| Mac only: bash scripts, `df -g`, Mac font and emoji paths. Needs Homebrew, ffmpeg, deno by hand | One Python command for Mac and Windows; uv installs Python, ffmpeg, yt-dlp and deno inside the skill folder; Windows fonts listed | Test 12 on a PATH with no Homebrew tools. Windows NOT tested |
| `claude -p` with the user's full tools, settings and MCP servers, stream speech pasted into the prompt, answers found with a regex, bad answers dropped silently | `claude -p --tools "" --setting-sources "" --strict-mcp-config`, a JSON schema, speech in `<transcript>` tags as data, one retry, clear error on usage limits | Tests 3, 5, 11: `structured_output` returned every call |
| One pass: 12-min parts with no overlap, scores compared across parts | Overlapping 10-min parts (no moment cut at a border), then an editor round that sees all candidates with their exact words and picks the best, different clips | Test 11: same stream, scores 72/66 vs 58/48 in test 5, hooks name the right game |
| Always Whisper tiny for the whole stream | YouTube replays use YouTube's own captions first (seconds instead of minutes) | NOT tested (only one stream allowed, and it was Twitch) |
| Facecam model downloaded from GitHub with no checksum | Same public model, SHA-256 checked | Test 3 |
| No check step; a wrong crop is posted | Every clip gets a 3-frame check image; SKILL.md tells Claude to look at it, fix the cam with `still` + `--cam`, and the spot is remembered per streamer | Tests 7-9, 11 ("face is inside this streamer's saved facecam spot") |
| Suggests `--cookies chrome` freely | Cookies only with the user's OK | SKILL.md section 5 |
| Moments re-used, but no edit loop | Edit `moments.json` (hook, caption, times), `render --only N` | Test 8 |

## What a viewer needs

- Mac (Apple Silicon or Intel) or Windows 10/11; about 3 GB free disk (700 MB install + about 0.2 GB per job).
- Claude Code signed in with a Claude plan (Pro, $20/month, or higher). Picking uses one short tool-less
  `claude -p` call per 9 minutes of stream plus one editor call (4 in our 20-minute test, about 28 for a
  4-hour stream). `--model sonnet` uses less of the plan.
- `uv` (free; Claude installs it with the official one-line installer, no admin password).
- Internet. No API keys, no Twitch developer key, no paid tools. No GPU needed (Whisper runs on the CPU).

## Not tested in this round

- **Windows** (no Windows machine was used). The code has no bash and lists Windows fonts, but is unproven there.
- Intel Macs, and a Mac without Claude Code already signed in.
- **YouTube** streams: the YouTube captions fast path, the chat-speed signal, the deno JavaScript step,
  age-limited streams, and the `crop` look (big face). **Kick** links. Live streams (Twitch "so far", YouTube refusal).
- `find` followed by clipping (only `find --list` ran), and `--parallel` with several streams.
- A full 4-hour stream (only a 20-minute part); the "10-20 minutes per 4 hours" in README is an estimate.
- The README install path that copies the skill to `~/.claude/skills/` (the test used the README
  shortcut: open Claude Code in the unzipped folder), and installing `uv` from scratch.
- Real GTA 6 footage (the game is not out until Nov 19, 2026).
- Scene changes inside one clip (one look is used per clip; the creator's version can switch looks mid-clip).

---

# Round 2: live Twitch streams

Date: Mon Nov 16 2026, 03:07-03:25 IST (clock checked with `date`). Same MacBook, Claude Code 2.1.318.
Test files in `/tmp/gta6clip-r2/` (removed at the end). `.venv` and `.models` made in the skill folder
(git-ignored) and removed before the commit. `UV_CACHE_DIR` was in the temp folder.

## The bug (found by Jarvis, fix approved by Yoki)

`clip https://www.twitch.tv/jynxzi --section 0:20:00-0:40:00` on a live channel failed in 7 s with
"this Twitch stream is live and has no saved VOD to clip yet", although the channel had a saved VOD.
Cause: yt-dlp reports a VOD that is still recording as `live_status: is_live`. `resolve()` found the VOD,
called itself on it, took the video ID as the channel name, and found nothing. A pasted VOD link of a
live stream failed the same way.

## Fix

- A Twitch VOD link is clipped as it is, also while it is still recording.
- A live channel link becomes its newest VOD, but only when that VOD is still recording (so an old
  stream is never clipped by mistake). The channel name comes from yt-dlp (`uploader_id`), not the URL.
- New `--last 20m` (also `1h`, `90s`, `20:00`): the most recent part of the stream.
- A live stream is always cut at the part saved when the job starts (without that, the download would
  follow the live edge and never end). If `--section` or `--last` asks for more than is saved, it clips
  what is saved and says so in the log. A section that starts after the saved part stops with a clear error.
- SKILL.md tells Claude how to turn "clip the last 20 minutes of <channel>" into the command.
- Not changed: everything else, including the known close-face `crop` look.

## Commands and results

`R` = `uv run --project SKILL SKILL/scripts/gta6clip.py`. Live channel: Jynxzi on Twitch (Kai Cenat was
not live during the test; jynxzi, zackrawrr, tarik and hasanabi were, checked with
`yt-dlp --simulate --print "%(is_live)s"`). In-progress VOD: `twitch.tv/videos/2929975105`.

| # | Command | Result |
|---|---|---|
| 1 | `uv run --project SKILL python -m unittest discover -s SKILL/tests -v` (new, no network: yt-dlp answers faked from real ones) | PASS: 12 tests in 0.004 s (live channel -> recording VOD, VOD link as it is, old VOD not used, YouTube live still refused, `--last`, cut at the saved part, finished VOD unchanged) |
| 2 | `R clip https://www.twitch.tv/jynxzi --last 20m --clips 2` (live channel) | PASS: "LIVE: using the VOD it is saving now", clipped 0:06:49-0:26:49, 2 clips in 4.3 min. Sound match 0.98 / 0.99 |
| 3 | `R clip https://www.twitch.tv/videos/2929975105 --section 0:20:00-0:40:00 --clips 2` (VOD link, still recording) | PASS: "clipping 0:20:00-0:31:22; you asked up to 0:40:00, but only 0:31:22 is saved so far", 2 clips in 2.0 min. Sound match 0.98 / 1.00 |
| 4 | `R clip https://www.twitch.tv/jynxzi --section 0:20:00-0:40:00 --clips 2` (Jarvis's exact failing command) | PASS: cut at 0:35:27 saved so far, 2 clips in 2.0 min |
| 5 | `R doctor` (round 1 test) | PASS: READY in 13 s |
| 6 | `R clip https://www.twitch.tv/videos/2924282282 --section 10:00:00-10:20:00 --clips 2` (round 1 finished VOD) | PASS: 2 clips in 1.5 min, both `stack`, facecam found (75% / 100%), same "GO TOSS A" caption as round 1 |
| 7 | Viewer test: clean copy of the repo (no `.venv`, `.models`, `.git`), PATH = only `uv` + `claude` + `/usr/bin:/bin`, uv forced to download its own Python (3.13.18). Following README ("open Claude Code inside the unzipped folder"): `claude -p "set up the GTA 6 clipper. Then clip the last 20 minutes of https://www.twitch.tv/jynxzi (he is live right now), 2 clips."`, tools limited to `Bash(uv:*)`, Read, Glob, Grep | PASS: Claude ran doctor (READY), chose `--last 20m` from SKILL.md, clipped 0:19:06-0:39:06 of the live stream, checked both check images and reported in plain words (also that the stream is not GTA). 4 min in total |
| 8 | `ruff check --select F,E9` + `py_compile` | PASS |

Output checks: `ffprobe` on all 10 clips: 1080x1920, H.264 + AAC, 25-49 s. Check images opened:
tests 2 and 6 show the face and the right captions; tests 3, 4 and 7 used the `crop` look on Jynxzi's
close face (the known look fault Yoki chose to keep); test 2 used `fit` (his cam moves between scenes).

## Problems found and fixed in this round

1. Live channel link failed with "no saved VOD" (the bug above). Fixed; tests 1-4.
2. A pasted VOD link of a live stream failed the same way. Fixed; tests 1 and 3.
3. Found while fixing: a live stream with no `--section` would have downloaded up to the live edge and
   kept going until the stream ended. It is now cut at the saved part (test 1).

## What a viewer needs (new in round 2)

Nothing new to install. For a live stream the Twitch channel must save past broadcasts (VODs); most big
streamers do. If it does not, the skill says so. The new test needs no network and no extra package.

## Not tested in round 2

- Kai Cenat live (he was not live during the test); the same code path ran on Jynxzi's live stream.
- A live channel with VODs turned off (only faked in the unit test), subscriber-only VODs, and a stream
  that restarts (new VOD) during a job.
- Windows, YouTube live and replays, Kick. Real GTA 6 footage. The `crop` look fault is unchanged.
- A long live stream (`--last 20m` ran on a 27-39 min stream only).

---

# Round 3: change the look by chat (caption styles, hook style, facecam size)

Date: Tue Nov 17 2026, 03:53-04:10 IST (clock checked with `date`). Same MacBook, Claude Code 2.1.318.
Test files in `/tmp/gta6clip-r3/` (removed at the end). `.venv` and `.models` made in the skill folder
(git-ignored) and removed before the commit. `UV_CACHE_DIR` was in the temp folder.

## What is new

- A style = caption style + hook title style + layout, in one small JSON file (`JOB/style.json`, or any
  file that names a preset and lists only its changes). Code: `scripts/clipper/style.py`.
- 5 presets: `classic` (round 1-2 look, unchanged), `karaoke` (spoken word in a coloured box), `minimal`
  (small sentence-case lower third on a dark bar), `bold` (huge condensed words, thick outline), `neon`
  (wide letters, glow on the spoken word).
- Settings: caption text, highlight, outline and box colours; size (px, small/medium/large/huge, or
  `+20%`); position (auto, top, middle, bottom of the gameplay area); words per line (1-8); upper case
  on/off; captions on/off; box (none, word, line); outline; glow; font. Hook: on/off, text and box
  colours, position (auto, top, middle, bottom), font. Layout: look (auto, stack, crop, fit) and
  `cam_height` (facecam share of the clip in `stack`, 25-55%, default 36.5% = the old 700 px).
- `--style NAME|FILE.json`, `--set part.setting=value` (repeatable), `--save-style NAME` (`default` =
  used for every new job). Every value is checked; a wrong one stops with the allowed values.
- `render JOB` re-uses the video part, sound match, words and facecam decision (cached in
  `work/prep_NN.json`), so a new look only draws and encodes.
- `styles` lists presets and settings; `styles JOB` makes `NN_styles.jpg`: one frame of a clip in
  each look, side by side (`--style a,b,file.json` to compare any looks, `--at` to pick the second).
- Captions and hook never overlap: if a chosen position would touch the hook, the captions move off it.
- A NOTE when the caption colour equals the highlight colour (the spoken word would not stand out).
- Two OFL fonts bundled in `fonts/` (Archivo variable, Big Shoulders Black) with `fonts/OFL.txt`.
  The classic look still uses the system Arial Black, as before.
- SKILL.md: a short "Change the look" section (59 lines in total); the phrase list is in `reference/styles.md`.
- Not changed: picking, download, facecam finding, the close-face `crop` look (Yoki chose to keep it).

## Commands and results

`R` = `uv run --project SKILL SKILL/scripts/gta6clip.py`. Stream: Kai Cenat's VOD
`https://www.twitch.tv/videos/2924282282` (the round 1 stream).

| # | Command | Result |
|---|---|---|
| 1 | `R clip <VOD> --section 10:00:00-10:20:00 --clips 3` | PASS: 1 clip (the editor kept 1 of 2 candidates), 3.2 min. Ran before `doctor` on this machine, so the face model was missing and the look was `fit` |
| 2 | `R doctor` | PASS: READY in 11 s (all round 1 checks and the two test clips through the new code) |
| 3 | `R render JOB` (first render with the new code: face search + Whisper + encode) | PASS: 17.7 s; look `stack`, facecam found (75% of frames, 4/4 sides) |
| 4 | `R render JOB --style X` for each of the 5 presets | PASS: 12.4-13.4 s each for a 41 s clip (**style-only re-render**; no download, no listening, no picking) |
| 5 | `R styles JOB` | PASS: 3 s; the sheet shows the same moment in all 5 looks (copied to `~/Downloads/gta6-clipper-ours/round3-styles.jpg`) |
| 6 | `R render JOB --style classic --set captions.text_color=yellow --set captions.position=top` | PASS: yellow captions at the top of the gameplay area, under the hook; NOTE printed (same colour as the highlight) |
| 7 | Style files: yellow-top (cyan highlight, top, cam 45%), karaoke-nohook (orange, large, bottom, no hook, cam 30%), bold-red (sentence case, 3 words, black hook at the bottom, cam 50%), no-captions (minimal, gold hook) | PASS: 4 renders; every setting visible in the frames and in a sheet of the 4 files + classic |
| 8 | `R render JOB --layout fit --style neon`, `R render JOB --layout crop --style karaoke` | PASS: both render; `fit` takes 36 s (blur), crop is the known close-face look |
| 9 | `R render JOB --set captions.size=500`, `--style fancy` | PASS: clear errors ("must be from 36 to 160", "no style called 'fancy'. Presets: ...") |
| 10 | `R render JOB --style classic --set captions.text_color=yellow --save-style mine`, then `R styles` | PASS: "Your saved styles: mine" |
| 11 | `R clip <VOD> --section 10:20:00-10:32:00 --clips 2 --style karaoke --set captions.highlight_color=green` (fresh job, new code end to end) | PASS: 2 clips in 1.8 min (audio, Whisper, Claude picking, 2 renders), both `stack` (facecam in 96% of frames), karaoke with a green spoken word; `style.json` saved. Two clips' check frames fell in pauses (no words on screen); a frame at 21.8 s and `styles JOB --clip 2 --style karaoke,JOB/style.json` showed the captions |
| 12 | `uv run --project SKILL python -m unittest discover -s SKILL/tests -v` | PASS: 28 tests in 0.08 s (12 round 2 + 16 new: presets valid and different, classic = round 1 values, colours, viewer phrases, bad values and bad files refused, file round trip, saved styles, placement inside the gameplay area, no hook overlap in 36 look/position mixes, facecam height, words per line and case, every preset draws with its bundled font, karaoke text contrast) |
| 13 | Viewer test: clean copy of the repo (no `.git`, `.venv`, `.models`) in a new git repo, a copy of the job without `style.json`. `claude -p "My GTA 6 clips from yesterday are in <JOB>. Make the captions yellow and put them at the top."` from the copy, tools `Bash(uv:*)`, Read, Glob, Grep, **Edit, Write** | PASS: Claude loaded the skill, read `reference/styles.md`, ran `render JOB --set captions.text_color=yellow --set captions.highlight_color=white --set captions.position=top`, opened the check image and reported in plain words. `git status` in the copy: no file changed (no code edit). 41 s in total |
| 14 | `ruff check --select F,E9` + `py_compile` | PASS |

Output checks: `ffprobe` on all 12 round-3 renders of test 4-8: 1080x1920, H.264 + AAC, 41.0 s.
Test 11: 2 clips, 1080x1920, H.264 + AAC, 56.8 s and 50.8 s. Sheets and check images opened and looked at: each preset reads clearly on the dark
gameplay; facecam heights 30/36.5/45/50% crop the cam panel as expected; hook off and captions off work.

## Problems found and fixed in this round

1. The style sheet showed no captions: a single still image with `eof_action=pass` was dropped by
   ffmpeg. Fixed: the still is looped for the one frame.
2. The sheet first picked a one-word phrase ("BRO,"); it now picks a full 3-word phrase near the middle.
3. The karaoke box touched the word before it; words now get extra space in the `word` box style.
4. `minimal` first put the hook at the top, where it covered the face in the `stack` look; it now uses the seam.
5. "Make the captions yellow" on `classic` made the spoken word yellow on yellow: SKILL reference now
   also sets the highlight to white, and the command prints a NOTE.

## Not tested in round 3

- Windows (fonts and paths), and a computer without Arial Black (the classic look then uses Arial Bold,
  Impact or DejaVu, as before; the 4 other presets use the bundled fonts everywhere).
- Big Shoulders has Latin letters only (263 glyphs): captions in other alphabets show empty boxes in `bold`.
- YouTube and Kick jobs, more than 2 clips in a job, a job made before round 3 rendered by the
  committed round 2 code first (test 13 used a round-3 job copy with its `style.json` removed).
- `--save-style default` applied to a new `clip` job (the code path is the same `job_style` as test 10).

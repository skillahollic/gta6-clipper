# Styles: change the look of the clips by chat

Never edit the Python code to change a look. Use `--style` and `--set`; the skill checks every value
and says what is allowed when a value is wrong. `gta6clip` = the command in SKILL.md.

## The commands
- `gta6clip styles`: the presets and every setting with its allowed values. Run it before you offer options.
- `gta6clip render JOB --style karaoke`: all clips of the job again in a preset. No new download,
  no new listening, no new picking: about 10-15 s per 40-second clip. `--only 2` for one clip.
- `gta6clip render JOB --set captions.text_color=yellow --set captions.position=top`: change only
  these settings. Without `--style`, the job's own `JOB/style.json` is the start point, so changes add up.
- `--style FILE.json`: a style file (below). `--style NAME`: a preset or a style saved with `--save-style`.
- `--save-style NAME` (with render or clip): also keep this look as NAME for later jobs.
  `--save-style default` = every new job uses this look. Saved looks are in `~/gta6-clips/styles/`.
- `gta6clip styles JOB [--clip N] [--style a,b,FILE.json] [--at SECONDS]`: `JOB/NN_styles.jpg`, one
  frame of clip N in each look, side by side. Open it with Read and show the user. `--set` applies to all.
- `clip URL ... --style NAME --set ...` makes new clips in that look from the start.

## The user's words -> the settings
| The user says | Add |
|---|---|
| "make the captions yellow" | `--set captions.text_color=yellow --set captions.highlight_color=white` (keep the spoken word different) |
| "make the highlighted / spoken word red" | `--set captions.highlight_color=red` |
| "bigger subtitles" / "smaller" | `--set captions.size=+25%` / `--set captions.size=-20%` (or small, medium, large, huge) |
| "captions at the top" / "middle" / "bottom" | `--set captions.position=top` (top, middle, bottom of the gameplay area; auto = the default spot) |
| "more words at a time" / "one word at a time" | `--set captions.words_per_line=5` / `=1` |
| "no all caps" / "normal case" | `--set captions.uppercase=off` |
| "no captions" | `--set captions.show=off` |
| "no hook title" / "remove the title" | `--set hook.show=off` |
| "hook at the bottom" / "title at the top" | `--set hook.position=bottom` / `top` (auto = on the seam in stack) |
| "black title box with white text" | `--set hook.box_color=black --set hook.text_color=white` |
| "use the karaoke style" / "minimal" / "bold" / "neon" / "the original" | `--style karaoke` / `minimal` / `bold` / `neon` / `classic` |
| "make the facecam bigger" / "smaller" | `--set layout.cam_height=45` / `=30` (25-55, percent of the clip; default 36.5) |
| "show the whole screen" | `--set layout.look=fit` (or `--layout fit`) |
| "thicker outline" / "no outline" | `--set captions.outline=14` / `=0` |
| "a glow" | `--set captions.glow=on` |
| "a box behind the words" | `--set captions.box=line` (a dark bar) or `word` (karaoke box on the spoken word) |

Colours: a name (white, black, yellow, gold, orange, red, pink, purple, blue, cyan, green, lime, grey)
or a hex code like `#FFE13B`; 8 digits add see-through (`#000000A6`). Fonts: system (Arial Black, the
classic look), archivo, archivo-black, archivo-condensed, archivo-wide, big-shoulders (bundled, OFL).

## A style file
For a look with many changes, write a small JSON file and use `--style FILE.json`. It names a preset
and lists only what changes:

```json
{"preset": "karaoke",
 "captions": {"highlight_color": "orange", "size": "large", "position": "bottom"},
 "hook": {"show": false},
 "layout": {"cam_height": 30}}
```

## After a change
Open the new `NN_..._check.jpg` of each clip (or make a style sheet) and check that the words are
readable and do not cover the face. Then tell the user what changed and how to go back
(`--style classic`).

"""The look of a clip: caption style, hook title style and layout, in one small JSON file.

A style file names a preset and changes only what it needs, for example
    {"preset": "karaoke", "captions": {"highlight_color": "yellow", "position": "top"}}
Claude writes this from the viewer's words; `--style FILE` or `--style NAME` applies it and
`--set captions.size=+20%` changes one setting. The full, checked style of each job is saved as
JOB/style.json, so the next `render JOB` keeps it."""

import copy
import json
import re
from pathlib import Path

from .media import ClipError


class StyleError(ClipError):
    """A style setting the skill cannot use; the message says what is allowed."""


FONTS = ("system", "archivo", "archivo-black", "archivo-condensed", "archivo-wide", "big-shoulders")
POSITIONS = ("auto", "top", "middle", "bottom")
BOXES = ("none", "word", "line")
LOOKS = ("auto", "stack", "crop", "fit")
SIZES = {"small": 60, "medium": 84, "large": 104, "huge": 128}
COLORS = {
    "white": "#FFFFFF", "black": "#000000", "yellow": "#FFE13B", "gold": "#FFC300", "orange": "#FF8A00",
    "red": "#FF3B30", "pink": "#FF2D95", "purple": "#9B5CFF", "blue": "#2F80FF", "cyan": "#00E5FF",
    "green": "#22C55E", "lime": "#39FF14", "grey": "#9CA3AF", "gray": "#9CA3AF",
}

CLASSIC = {
    "captions": {"show": True, "font": "system", "size": 84, "text_color": "#FFFFFF",
                 "highlight_color": "#FFE13B", "outline_color": "#000000", "outline": "auto",
                 "box": "none", "box_color": "#000000A6", "glow": False, "uppercase": True,
                 "words_per_line": 3, "position": "auto"},
    "hook": {"show": True, "font": "system", "text_color": "#0F0F0F", "box_color": "#FFFFFF",
             "position": "auto"},
    "layout": {"look": "auto", "cam_height": 36.5},
}
# Each preset lists only what differs from "classic".
PRESETS = {
    "classic": ("Round 1 look: big white upper-case words, yellow spoken word, black outline", {}),
    "karaoke": ("Spoken word in a coloured box (TikTok karaoke), 4 words, white text",
                {"captions": {"font": "archivo-black", "size": 76, "highlight_color": "#9B5CFF",
                              "box": "word", "outline": 5, "words_per_line": 4},
                 "hook": {"font": "archivo-black", "text_color": "#FFFFFF", "box_color": "#9B5CFF"}}),
    "minimal": ("Small sentence-case lower third on a dark bar, 6 words, dark hook bar",
                {"captions": {"font": "archivo", "size": 56, "outline": 0, "box": "line",
                              "highlight_color": "#FFE13B", "uppercase": False, "words_per_line": 6,
                              "position": "bottom"},
                 "hook": {"font": "archivo", "text_color": "#FFFFFF", "box_color": "#000000B3"}}),
    "bold": ("Huge condensed words with a thick outline, lime spoken word, 2 words, middle",
             {"captions": {"font": "big-shoulders", "size": 132, "highlight_color": "#39FF14",
                           "outline": 12, "words_per_line": 2, "position": "middle"},
              "hook": {"font": "big-shoulders", "text_color": "#000000", "box_color": "#39FF14"}}),
    "neon": ("Wide letters with a pink glow on the spoken word, 3 words",
             {"captions": {"font": "archivo-wide", "size": 66, "highlight_color": "#FF2D95",
                           "outline": 3, "glow": True},
              "hook": {"font": "archivo-wide", "text_color": "#FFFFFF", "box_color": "#FF2D95"}}),
}
DEFAULT = "classic"
ALIASES = {"caption": "captions", "subtitles": "captions", "subtitle": "captions", "title": "hook",
           "color": "text_color", "colour": "text_color", "text_colour": "text_color",
           "highlight": "highlight_color", "highlight_colour": "highlight_color",
           "box_colour": "box_color", "outline_colour": "outline_color", "words": "words_per_line",
           "upper": "uppercase", "caps": "uppercase", "pos": "position", "where": "position",
           "on": "show", "cam": "cam_height", "facecam": "cam_height"}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def color(value, what="colour"):
    """'yellow', '#ff0', '#FFE13B' or '#000000A6' (with see-through) -> '#RRGGBB[AA]'."""
    v = str(value).strip().lower().replace(" ", "")
    v = COLORS.get(v, v)
    if re.fullmatch(r"#?[0-9a-fA-F]{3}", v):
        v = "#" + "".join(c * 2 for c in v.lstrip("#"))
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", v):
        raise StyleError(f"{what} '{value}' is not a colour. Use a name ({', '.join(sorted(COLORS))}) "
                         "or a hex code like #FFE13B")
    return "#" + v.lstrip("#").upper()


def rgba(value):
    v = color(value).lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in range(0, len(v), 2)) + ((255,) if len(v) == 6 else ())


def _bool(value, what):
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("true", "on", "yes", "1", "show"):
        return True
    if v in ("false", "off", "no", "0", "hide", "none"):
        return False
    raise StyleError(f"{what} must be on or off, not '{value}'")


def _num(value, what, lo, hi, names=None):
    if names and str(value).strip().lower() in names:
        return names[str(value).strip().lower()]
    try:
        n = float(value)
    except (TypeError, ValueError):
        extra = f" or {', '.join(names)}" if names else ""
        raise StyleError(f"{what} must be a number from {lo} to {hi}{extra}, not '{value}'") from None
    if not lo <= n <= hi:
        raise StyleError(f"{what} must be from {lo} to {hi}, not {value}")
    return int(n) if n == int(n) else n


def _choice(value, what, allowed):
    v = str(value).strip().lower()
    if v not in allowed:
        raise StyleError(f"{what} must be one of {', '.join(allowed)}, not '{value}'")
    return v


def validate(st):
    """Checks every setting and writes it in its plain form. Unknown keys are errors
    (a typo must not be ignored silently)."""
    st = copy.deepcopy(st)
    for part in ("captions", "hook", "layout"):
        if not isinstance(st.get(part), dict):
            raise StyleError(f"'{part}' must be a group of settings, like {{\"show\": false}}")
        extra = set(st.get(part, {})) - set(CLASSIC[part])
        if extra:
            raise StyleError(f"unknown {part} setting(s): {', '.join(sorted(extra))}. "
                             f"Allowed: {', '.join(CLASSIC[part])}")
    extra = set(st) - {"preset", "captions", "hook", "layout"}
    if extra:
        raise StyleError(f"unknown style part(s): {', '.join(sorted(extra))}. Use captions, hook, layout")
    c, h, lay = st["captions"], st["hook"], st["layout"]
    for d, name in ((c, "captions"), (h, "hook")):
        d["show"] = _bool(d["show"], f"{name}.show")
        d["font"] = _choice(d["font"], f"{name}.font", FONTS)
        d["position"] = _choice(d["position"], f"{name}.position", POSITIONS)
        for k in ("text_color", "box_color") + (("highlight_color", "outline_color") if d is c else ()):
            d[k] = color(d[k], f"{name}.{k}")
    c["size"] = _num(c["size"], "captions.size", 36, 160, SIZES)
    c["outline"] = "auto" if c["outline"] == "auto" else _num(c["outline"], "captions.outline", 0, 24)
    c["box"] = _choice(c["box"], "captions.box", BOXES)
    c["glow"] = _bool(c["glow"], "captions.glow")
    c["uppercase"] = _bool(c["uppercase"], "captions.uppercase")
    c["words_per_line"] = int(_num(c["words_per_line"], "captions.words_per_line", 1, 8))
    lay["look"] = _choice(lay["look"], "layout.look", LOOKS)
    lay["cam_height"] = _num(lay["cam_height"], "layout.cam_height (percent of the clip height)", 25, 55)
    return st


def from_dict(data):
    """A style file's content (a preset name plus changes) -> the full, checked style."""
    if not isinstance(data, dict):
        raise StyleError("a style file must be a JSON object like {\"preset\": \"karaoke\"}")
    name = str(data.get("preset") or DEFAULT).lower()
    if name not in PRESETS:
        raise StyleError(f"no preset called '{name}'. Presets: {', '.join(PRESETS)}")
    full = merge(merge(CLASSIC, PRESETS[name][1]), {k: v for k, v in data.items() if k != "preset"})
    return validate(full) | {"preset": name}


def load(spec, saved_dir=None):
    """`spec` is a preset name, a JSON file, or a style saved with --save-style in `saved_dir`."""
    p = Path(str(spec)).expanduser()
    if p.suffix.lower() == ".json" or p.is_file():
        if not p.is_file():
            raise StyleError(f"style file {p} not found")
        try:
            return from_dict(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise StyleError(f"style file {p} is not valid JSON ({exc})") from None
    name = str(spec).strip().lower()
    if name in PRESETS:
        return from_dict({"preset": name})
    if saved_dir and (Path(saved_dir) / f"{name}.json").is_file():
        return load(Path(saved_dir) / f"{name}.json")
    mine = sorted(q.stem for q in Path(saved_dir).glob("*.json")) if saved_dir and Path(saved_dir).is_dir() else []
    raise StyleError(f"no style called '{spec}'. Presets: {', '.join(PRESETS)}"
                     + (f"; saved styles: {', '.join(mine)}" if mine else ""))


def apply_sets(st, sets):
    """['captions.text_color=yellow', 'captions.size=+20%', 'hook.show=off', 'preset=bold'] -> style.
    `preset=NAME` first resets to that preset; the other settings then apply on top."""
    sets = list(sets or [])
    for s in [s for s in sets if s.split("=", 1)[0].strip().lower() == "preset"]:
        st = from_dict({"preset": s.split("=", 1)[1].strip()})
    data = copy.deepcopy(st)
    for s in sets:
        key, eq, value = s.partition("=")
        if not eq:
            raise StyleError(f"--set needs part.setting=value, like captions.text_color=yellow (got '{s}')")
        parts = [ALIASES.get(k, k) for k in key.strip().lower().replace("-", "_").split(".")]
        if parts == ["preset"]:
            continue
        if len(parts) != 2 or parts[0] not in CLASSIC:
            raise StyleError(f"--set {key}: use captions.<setting>, hook.<setting> or layout.<setting>")
        part, name = parts
        value = value.strip()
        m = re.fullmatch(r"([+-]\d+(?:\.\d+)?)%", value)
        if m and isinstance(data[part].get(name), (int, float)) and not isinstance(data[part][name], bool):
            value = round(data[part][name] * (1 + float(m.group(1)) / 100))     # "+20%": relative
        data[part][name] = value
    return validate({k: v for k, v in data.items() if k != "preset"}) | {"preset": st.get("preset", DEFAULT)}


def save(st, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")


def listing():
    lines = ["Caption and hook presets (use: --style NAME; change one thing: --set captions.size=+20%):"]
    lines += [f"  {n:8} {d}" for n, (d, _) in PRESETS.items()]
    lines += ["", "Settings (--set part.setting=value, or the same keys in a style .json file):",
              "  captions.show / hook.show       on, off",
              "  captions.text_color, captions.highlight_color (the spoken word), captions.outline_color,",
              f"  captions.box_color, hook.text_color, hook.box_color   a name or #RRGGBB[AA]: "
              f"{', '.join(c for c in COLORS if c != 'gray')}",
              f"  captions.size                   36-160 px, {', '.join(f'{k} ({v})' for k, v in SIZES.items())}, "
              "or +20% / -20%",
              f"  captions.position / hook.position   {', '.join(POSITIONS)} (captions: of the gameplay area)",
              "  captions.words_per_line         1-8      captions.uppercase   on, off",
              f"  captions.box                    {', '.join(BOXES)} (word = karaoke box, line = dark bar)",
              "  captions.outline                auto or 0-24 px     captions.glow   on, off",
              f"  captions.font / hook.font       {', '.join(FONTS)}",
              f"  layout.look                     {', '.join(LOOKS)}",
              "  layout.cam_height               25-55 (facecam share of the clip height in the stack look; "
              "default 36.5)"]
    return "\n".join(lines)

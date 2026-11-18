"""The hook bar and the word-by-word captions, drawn as images with Pillow.
Why images and not ffmpeg subtitles: many ffmpeg builds (Homebrew's too) have no
subtitle or text filter, and fonts differ per computer. Images look the same everywhere.
Every colour, font, size and box comes from the clip's style (see style.py)."""

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .style import CLASSIC, rgba

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",       # Mac
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/ariblk.ttf",                              # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # Linux
]
# Fonts bundled in the skill (SIL Open Font License, see fonts/OFL.txt): file, (weight, width).
FONT_DIR = Path(__file__).resolve().parents[2] / "fonts"
BUNDLED = {
    "archivo": ("Archivo.ttf", (600, 100)),
    "archivo-black": ("Archivo.ttf", (900, 100)),
    "archivo-condensed": ("Archivo.ttf", (800, 75)),
    "archivo-wide": ("Archivo.ttf", (900, 125)),
    "big-shoulders": ("BigShoulders-Black.woff", None),
}
YELLOW, WHITE = (255, 225, 59, 255), (255, 255, 255, 255)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")
CAPTION_BOX = (1080, 330)


@lru_cache(maxsize=64)
def font(size, name="system"):
    if name in BUNDLED and (FONT_DIR / BUNDLED[name][0]).exists():
        file, axes = BUNDLED[name]
        f = ImageFont.truetype(str(FONT_DIR / file), size)
        if axes:
            f.set_variation_by_axes(list(axes))
        return f
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def readable_on(fill):
    """Black or white text, whichever reads better on the colour `fill`."""
    r, g, b = fill[:3]
    return (15, 15, 15, 255) if 0.299 * r + 0.587 * g + 0.114 * b > 150 else WHITE


def clean(text):
    return re.sub(r"\s+", " ", EMOJI.sub("", text or "")).strip()


def _wrap(words, f, limit, draw):
    lines, cur = [], []
    for w in words:
        if cur and draw.textlength(" ".join(cur + [w]), font=f) > limit:
            lines.append(cur)
            cur = []
        cur.append(w)
    return lines + ([cur] if cur else [])


def hook_png(text, path, width=1080, st=None):
    """Rounded bar with bold text, up to 3 lines. `st` = the style's "hook" part. Returns (path, height)."""
    st = st or CLASSIC["hook"]
    words = clean(text).split() or ["GTA", "6"]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in (60, 54, 48, 42):
        f = font(size, st["font"])
        lines = _wrap(words, f, width - 220, probe)
        if len(lines) <= 3:
            break
    limit = width - 220
    while limit > 300 and len(_wrap(words, f, limit - 20, probe)) == len(lines):
        limit -= 20                                   # balance the lines: no lonely last word
    lines = _wrap(words, f, limit, probe)
    line_h, pad_x, pad_y = int(size * 1.25), 34, 22
    widths = [probe.textlength(" ".join(ln), font=f) for ln in lines]
    bw, bh = int(max(widths) + 2 * pad_x), int(len(lines) * line_h + 2 * pad_y)
    img = Image.new("RGBA", (bw + 16, bh + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = rgba(st["box_color"])
    d.rounded_rectangle((8, 12, bw + 8, bh + 12), radius=26, fill=(0, 0, 0, 90 * box[3] // 255))  # soft shadow
    bar = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle((8, 8, bw + 8, bh + 8), radius=26, fill=box)
    img = Image.alpha_composite(img, bar) if box[3] < 255 else img
    d = ImageDraw.Draw(img)
    if box[3] == 255:
        d.rounded_rectangle((8, 8, bw + 8, bh + 8), radius=26, fill=box)
    for i, (ln, lw) in enumerate(zip(lines, widths)):
        d.text((8 + (bw - lw) / 2, 8 + pad_y + i * line_h), " ".join(ln), font=f, fill=rgba(st["text_color"]))
    img.save(path)
    return path, img.height


def groups(words, size=3):
    """Short caption phrases: break on punctuation, pauses and every `size` words."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["s"] - w["e"] if i + 1 < len(words) else 9
        if len(cur) >= size or w["w"].endswith((".", "?", "!", ",")) or gap > 0.5:
            out.append(cur)
            cur = []
    return out + ([cur] if cur else [])


def box_height(st):
    """Height of every caption image of a clip (all images of one track must match)."""
    return max(CAPTION_BOX[1], int(2 * st["size"] * 1.15 + 60) // 2 * 2)


def _caption_img(texts, hi, f, path, box=CAPTION_BOX, st=None):
    st = st or CLASSIC["captions"]
    img = Image.new("RGBA", box, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(4, f.size // 11) if st["outline"] == "auto" else int(st["outline"])
    text_c, hi_c, line_c = rgba(st["text_color"]), rgba(st["highlight_color"]), rgba(st["outline_color"])
    lines, cur = [], []
    for i in range(len(texts)):
        if cur and d.textlength(" ".join(texts[j] for j in cur + [i]), font=f) > box[0] - 120:
            lines.append(cur)
            cur = []
        cur.append(i)
    lines += [cur] if cur else []
    pad = f.size * 0.16
    f_space = f.size * 0.12 if st["box"] == "word" else 0   # room for the karaoke box between words
    y = (box[1] - len(lines) * f.size * 1.15) / 2
    spots = []                                       # (x, y, text, i) of every word
    for ln in lines:
        lw = d.textlength(" ".join(texts[i] for i in ln), font=f) + f_space * (len(ln) - 1)
        x = (box[0] - lw) / 2
        for i in ln:
            spots.append((x, y, texts[i], i, lw, (box[0] - lw) / 2))
            x += d.textlength(texts[i] + " ", font=f) + f_space
        y += f.size * 1.15
    if st["box"] == "line":                          # a dark bar behind each line
        bar = Image.new("RGBA", box, (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        for x, y, _, _, lw, x0 in {(s[1], s[4], s[5]): s for s in spots}.values():
            top, bottom = d.textbbox((x0, y), "Hg", font=f)[1::2]
            bd.rounded_rectangle((x0 - 2 * pad, top - pad, x0 + lw + 2 * pad, bottom + pad),
                                 radius=int(f.size * 0.3), fill=rgba(st["box_color"]))
        img = Image.alpha_composite(img, bar)
        d = ImageDraw.Draw(img)
    if st["glow"]:                                   # a soft halo in the highlight colour
        halo = Image.new("RGBA", box, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        for x, y, t, i, _, _ in spots:
            hd.text((x, y), t, font=f, fill=hi_c[:3] + (255 if i == hi else 110,),
                    stroke_width=max(2, f.size // 14), stroke_fill=hi_c[:3] + (255 if i == hi else 110,))
        halo = halo.filter(ImageFilter.GaussianBlur(f.size / 5))
        img = Image.alpha_composite(img, Image.alpha_composite(halo, halo))
        d = ImageDraw.Draw(img)
    for x, y, t, i, _, _ in spots:
        fill = hi_c if i == hi else text_c
        if st["box"] == "word" and i == hi:          # karaoke: the spoken word sits in a coloured box
            l, top, r, bottom = d.textbbox((x, y), t, font=f)
            d.rounded_rectangle((l - pad * 0.6, top - pad, r + pad * 0.6, bottom + pad), radius=int(f.size * 0.22),
                                fill=hi_c)
            fill = readable_on(hi_c)
            d.text((x, y), t, font=f, fill=fill)
            continue
        if stroke:
            d.text((x, y), t, font=f, fill=fill, stroke_width=stroke, stroke_fill=line_c)
        else:
            d.text((x, y), t, font=f, fill=fill)
    img.save(path)


def caption_states(words, dur, st=None):
    """[(start, end, texts, index of the spoken word)] in clip time."""
    st = st or CLASSIC["captions"]
    states = []
    for g in groups([w for w in words if w["e"] > 0 and w["s"] < dur], st["words_per_line"]):
        texts = [clean(w["w"]).upper() if st["uppercase"] else clean(w["w"]) for w in g]
        if not any(texts):
            continue
        for i, w in enumerate(g):
            s = max(0.0, w["s"])
            e = g[i + 1]["s"] if i + 1 < len(g) else min(dur, w["e"] + 0.35)
            states.append((s, max(e, s + 0.05), texts, i))
    return states


def caption_at(words, dur, t, path, st=None):
    """The caption image shown at clip time `t` (for a still). Returns (path, height) or None."""
    st = st or CLASSIC["captions"]
    for s, e, texts, i in caption_states(words, dur, st):
        if s <= t < e:
            _caption_img(texts, i, font(st["size"], st["font"]), path, (1080, box_height(st)), st)
            return path, box_height(st)
    return None


def caption_track(words, dur, folder, st=None):
    """Writes one image per caption state and a concat list ffmpeg reads as a video
    track. Returns (list path, image height). `words` are in clip time (0 = clip start)."""
    st = st or CLASSIC["captions"]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("c*.png"):
        old.unlink()
    f = font(st["size"], st["font"])
    box = (1080, box_height(st))
    Image.new("RGBA", box, (0, 0, 0, 0)).save(folder / "blank.png")
    states = []                                     # (start, end, image name)
    for s, e, texts, i in caption_states(words, dur, st):
        name = f"c{len(states):04d}.png"
        _caption_img(texts, i, f, folder / name, box, st)
        states.append((s, e, name))
    lines, t = ["ffconcat version 1.0"], 0.0
    for s, e, name in states:
        s = max(s, t)
        if s - t > 0.02:
            lines += ["file blank.png", f"duration {s - t:.3f}"]
        if e - s > 0.02:
            lines += [f"file {name}", f"duration {e - s:.3f}"]
            t = e
    lines += ["file blank.png", f"duration {max(0.1, dur - t):.3f}", "file blank.png"]
    (folder / "list.txt").write_text("\n".join(lines) + "\n")
    return folder / "list.txt", box[1]

"""Styles (round 3): presets, style files, --set, checks and placement. No network, no ffmpeg.
Run: uv run --project SKILL python -m unittest discover -s SKILL/tests -v"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from clipper import frame, overlay, style  # noqa: E402
from clipper.style import StyleError  # noqa: E402

INFO = {"width": 1920, "height": 1080}
WORDS = [{"s": 0.2 + i * 0.4, "e": 0.5 + i * 0.4, "w": w}
         for i, w in enumerate("no way he just did that, bro what is going on.".split())]


class Presets(unittest.TestCase):
    def test_at_least_four_presets_all_valid(self):
        self.assertGreaterEqual(len(style.PRESETS), 4)
        for name in style.PRESETS:
            st = style.load(name)
            self.assertEqual(st["preset"], name)
            self.assertEqual(style.validate(st), st, name)        # checked form is stable

    def test_classic_is_the_round_1_look(self):
        st = style.load("classic")
        c, h = st["captions"], st["hook"]
        self.assertEqual((c["font"], c["size"], c["text_color"], c["highlight_color"]),
                         ("system", 84, "#FFFFFF", "#FFE13B"))
        self.assertEqual((c["uppercase"], c["words_per_line"], c["position"], c["box"]), (True, 3, "auto", "none"))
        self.assertEqual((h["text_color"], h["box_color"], h["position"]), ("#0F0F0F", "#FFFFFF", "auto"))
        self.assertEqual(frame.cam_px(st["layout"]["cam_height"]), frame.CAM_H)

    def test_presets_look_different(self):
        seen = {json.dumps(style.load(n)["captions"], sort_keys=True) for n in style.PRESETS}
        self.assertEqual(len(seen), len(style.PRESETS))

    def test_listing_names_every_preset_and_setting(self):
        text = style.listing()
        for name in style.PRESETS:
            self.assertIn(name, text)
        for key in ("highlight_color", "words_per_line", "uppercase", "position", "cam_height", "hook.show"):
            self.assertIn(key, text)


class Settings(unittest.TestCase):
    base = style.load("classic")

    def test_colours(self):
        self.assertEqual(style.color("yellow"), "#FFE13B")
        self.assertEqual(style.color("#f80"), "#FF8800")
        self.assertEqual(style.color("00ff00"), "#00FF00")
        self.assertEqual(style.rgba("#000000A6"), (0, 0, 0, 166))
        for bad in ("yelow", "#12345", "rgb(1,2,3)"):
            with self.assertRaisesRegex(StyleError, "not a colour"):
                style.color(bad)

    def test_viewer_phrases(self):
        st = style.apply_sets(self.base, ["captions.text_color=yellow", "captions.position=top"])
        self.assertEqual((st["captions"]["text_color"], st["captions"]["position"]), ("#FFE13B", "top"))
        st = style.apply_sets(self.base, ["captions.size=+25%"])                        # bigger subtitles
        self.assertEqual(st["captions"]["size"], 105)
        st = style.apply_sets(self.base, ["captions.size=large", "hook.show=off", "captions.uppercase=no"])
        self.assertEqual((st["captions"]["size"], st["hook"]["show"], st["captions"]["uppercase"]),
                         (104, False, False))
        st = style.apply_sets(self.base, ["preset=karaoke", "caption.highlight=green"])  # use the karaoke style
        self.assertEqual((st["preset"], st["captions"]["box"], st["captions"]["highlight_color"]),
                         ("karaoke", "word", "#22C55E"))
        st = style.apply_sets(self.base, ["layout.cam_height=45", "layout.look=stack", "captions.words=2"])
        self.assertEqual((st["layout"]["cam_height"], st["layout"]["look"], st["captions"]["words_per_line"]),
                         (45, "stack", 2))

    def test_bad_values_are_refused_with_the_allowed_ones(self):
        cases = [("captions.size=500", "36 to 160"), ("captions.position=left", "auto, top, middle, bottom"),
                 ("captions.colr=red", "Allowed"), ("captions.words_per_line=0", "1 to 8"),
                 ("hook.show=maybe", "on or off"), ("layout.cam_height=80", "25 to 55"),
                 ("layout.look=wide", "auto, stack, crop, fit"), ("captions.font=comic", "big-shoulders"),
                 ("size=90", "captions.<setting>"), ("captions.size", "part.setting=value"),
                 ("preset=fancy", "Presets")]
        for s, msg in cases:
            with self.assertRaisesRegex(StyleError, msg, msg=s):
                style.apply_sets(self.base, [s])


class Files(unittest.TestCase):
    def test_style_file_preset_plus_changes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "mine.json"
            f.write_text(json.dumps({"preset": "bold", "captions": {"highlight_color": "red"},
                                     "hook": {"position": "bottom"}}))
            st = style.load(f)
            self.assertEqual((st["preset"], st["captions"]["font"], st["captions"]["highlight_color"],
                              st["hook"]["position"]), ("bold", "big-shoulders", "#FF3B30", "bottom"))
            style.save(st, Path(d) / "styles" / "saved.json")       # a saved style loads by name
            self.assertEqual(style.load("saved", Path(d) / "styles"), st)
            self.assertEqual(style.load(Path(d) / "styles" / "saved.json"), st)   # the round trip is exact

    def test_bad_files(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.json"
            for text, msg in (("{nope", "not valid JSON"), ('["karaoke"]', "JSON object"),
                              ('{"captions": "off"}', "group of settings"), ('{"colour": "red"}', "unknown style part"),
                              ('{"preset": "fancy"}', "no preset")):
                f.write_text(text)
                with self.assertRaisesRegex(StyleError, msg, msg=text):
                    style.load(f)
            with self.assertRaisesRegex(StyleError, "not found"):
                style.load(Path(d) / "missing.json")
            with self.assertRaisesRegex(StyleError, "no style called"):
                style.load("fancy", d)


class Placement(unittest.TestCase):
    def test_auto_keeps_round_1_spots(self):
        for look in ("stack", "crop", "fit"):
            got = frame.place(look, INFO, frame.CAM_H, "auto", 150, "auto", 84)
            self.assertEqual(got, frame.text_spots(look, INFO), look)

    def test_positions_inside_the_gameplay_area(self):
        for look in ("stack", "crop", "fit"):
            top, bottom = frame.game_area(look, INFO)
            ys = [frame.place(look, INFO, frame.CAM_H, "auto", 0, p, 84)[1] for p in ("top", "middle", "bottom")]
            self.assertEqual(ys, sorted(ys), look)
            self.assertTrue(all(top <= y <= bottom for y in ys), (look, ys, top, bottom))

    def test_captions_move_off_the_hook(self):
        for look in ("stack", "crop", "fit"):
            for hook_pos in ("auto", "top", "middle", "bottom"):
                for pos in ("top", "middle", "bottom"):
                    hy, cy = frame.place(look, INFO, frame.CAM_H, hook_pos, 200, pos, 104)
                    self.assertGreaterEqual(abs(cy - hy), 100 + 104 * 1.2, (look, hook_pos, pos))

    def test_cam_height(self):
        self.assertEqual(frame.cam_px(30), 576)
        self.assertEqual(frame.cam_px(50), 960)
        self.assertIn("scale=1080:960", frame.graph("stack", INFO, [0.7, 0.6, 0.3, 0.4], cam_h=960))
        self.assertIn("scale=1080:960:", frame.graph("stack", INFO, [0.7, 0.6, 0.3, 0.4], cam_h=960).split(";")[2])
        self.assertIn("scale=1080:1344:", frame.graph("stack", INFO, [0.7, 0.6, 0.3, 0.4], cam_h=576))


class Drawing(unittest.TestCase):
    def test_words_per_line_and_case(self):
        st = style.load("minimal")["captions"]
        states = overlay.caption_states(WORDS, 10, st)
        self.assertEqual(states[0][2], ["no", "way", "he", "just", "did", "that,"])  # 6 words, sentence case
        st = style.load("bold")["captions"]
        self.assertEqual(overlay.caption_states(WORDS, 10, st)[0][2], ["NO", "WAY"])

    def test_every_preset_draws_with_its_bundled_font(self):
        with tempfile.TemporaryDirectory() as d:
            for name in style.PRESETS:
                st = style.load(name)
                f = overlay.font(st["captions"]["size"], st["captions"]["font"])
                if st["captions"]["font"] != "system":
                    self.assertIn(Path(f.path).parent.name, "fonts", name)
                got = overlay.caption_at(WORDS, 10, 0.7, Path(d) / f"{name}.png", st["captions"])
                self.assertIsNotNone(got, name)
                from PIL import Image
                img = Image.open(got[0])
                self.assertEqual(img.size, (1080, got[1]), name)
                self.assertGreater(img.getbbox()[2] - img.getbbox()[0], 200, name)   # something was drawn
                _, hh = overlay.hook_png("Kai can't believe this", Path(d) / f"h_{name}.png", st=st["hook"])
                self.assertGreater(hh, 80)

    def test_karaoke_text_reads_on_its_box(self):
        self.assertEqual(overlay.readable_on((255, 225, 59, 255))[0], 15)       # dark text on yellow
        self.assertEqual(overlay.readable_on((155, 92, 255, 255)), overlay.WHITE)   # white on purple


if __name__ == "__main__":
    unittest.main()

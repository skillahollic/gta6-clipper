"""Live Twitch logic, with no network: yt-dlp's answers are faked.
Run: uv run --project SKILL python -m unittest discover -s SKILL/tests -v"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gta6clip  # noqa: E402
from clipper.media import ClipError  # noqa: E402

# Shapes copied from real yt-dlp answers for a live Twitch channel (2026-11-16).
CHANNEL = {"id": "322430953563", "title": "Jynxzi (live)", "uploader": "Jynxzi", "uploader_id": "jynxzi",
           "duration": None, "live_status": "is_live", "site": "twitchstream", "name": "Jynxzi",
           "webpage_url": "https://www.twitch.tv/jynxzi"}
VOD_LIVE = {"id": "v2929975105", "title": "1 Champion vs 5 Coppers", "uploader": "Jynxzi",
            "uploader_id": "jynxzi", "duration": 1488, "live_status": "is_live", "site": "twitchvod",
            "name": "Jynxzi", "webpage_url": "https://www.twitch.tv/videos/2929975105"}
VOD_OLD = dict(VOD_LIVE, id="v2928767125", duration=23293, live_status="was_live",
               webpage_url="https://www.twitch.tv/videos/2928767125")
LISTING = [{"id": "v2929975105", "url": "https://www.twitch.tv/videos/2929975105", "duration": 1481.0}]


def fake_info(table):
    return lambda url, cookies=None: dict(table[url])


class Resolve(unittest.TestCase):
    def run_resolve(self, url, infos, listing):
        with mock.patch.object(gta6clip.media, "info", side_effect=fake_info(infos)), \
             mock.patch.object(gta6clip.finder, "_flat", return_value=listing) as flat:
            return gta6clip.resolve(url, None), flat

    def test_live_channel_becomes_its_recording_vod(self):
        infos = {CHANNEL["webpage_url"]: CHANNEL, VOD_LIVE["webpage_url"]: VOD_LIVE}
        info, flat = self.run_resolve(CHANNEL["webpage_url"], infos, LISTING)
        self.assertEqual(info["id"], "v2929975105")
        self.assertTrue(info["recording"])
        self.assertIn("twitch.tv/jynxzi/videos", flat.call_args[0][0])   # login, not a video id

    def test_vod_link_of_a_live_stream_is_used_as_it_is(self):
        info, flat = self.run_resolve(VOD_LIVE["webpage_url"], {VOD_LIVE["webpage_url"]: VOD_LIVE}, [])
        self.assertEqual(info["id"], "v2929975105")
        self.assertTrue(info["recording"])
        flat.assert_not_called()

    def test_finished_vod_unchanged(self):
        info, _ = self.run_resolve(VOD_OLD["webpage_url"], {VOD_OLD["webpage_url"]: VOD_OLD}, [])
        self.assertNotIn("recording", info)

    def test_live_channel_without_a_recording_vod_fails_clearly(self):
        listing = [{"url": VOD_OLD["webpage_url"]}]                       # newest VOD is an old one
        infos = {CHANNEL["webpage_url"]: CHANNEL, VOD_OLD["webpage_url"]: VOD_OLD}
        with self.assertRaisesRegex(ClipError, "does not save it"):
            self.run_resolve(CHANNEL["webpage_url"], infos, listing)
        with self.assertRaisesRegex(ClipError, "does not save it"):
            self.run_resolve(CHANNEL["webpage_url"], infos, [])

    def test_live_youtube_still_refused(self):
        yt = dict(CHANNEL, site="youtube", webpage_url="https://youtu.be/x")
        with self.assertRaisesRegex(ClipError, "YouTube"):
            self.run_resolve("https://youtu.be/x", {"https://youtu.be/x": yt}, [])


class Section(unittest.TestCase):
    live = dict(VOD_LIVE, recording=True)

    def test_span(self):
        for text, sec in (("20m", 1200), ("1h30m", 5400), ("90s", 90), ("20:00", 1200), ("1200", 1200)):
            self.assertEqual(gta6clip.span(text), sec, text)

    def test_last_20m_of_live(self):
        sec, note = gta6clip.choose_section(dict(self.live, duration=3000), last="20m")
        self.assertEqual(sec, (1800.0, 3000.0))
        self.assertNotIn("only", note)

    def test_last_longer_than_saved_clips_what_is_saved(self):
        sec, note = gta6clip.choose_section(self.live, last="40m")
        self.assertEqual(sec, (0.0, 1488.0))
        self.assertIn("only 0:24:48 is saved so far", note)

    def test_section_past_saved_part_is_cut(self):
        sec, note = gta6clip.choose_section(self.live, section="0:20:00-0:40:00")
        self.assertEqual(sec, (1200.0, 1488.0))
        self.assertIn("saved so far", note)

    def test_section_start_past_saved_part_fails(self):
        with self.assertRaisesRegex(ClipError, "past the end"):
            gta6clip.choose_section(self.live, section="1:00:00-1:20:00")

    def test_live_without_section_stops_at_saved_part(self):
        self.assertEqual(gta6clip.choose_section(self.live)[0], (0.0, 1488.0))

    def test_finished_vod_unchanged(self):
        self.assertEqual(gta6clip.choose_section(VOD_OLD)[0], None)
        self.assertEqual(gta6clip.choose_section(VOD_OLD, section="1:00:00-1:20:00")[0], (3600.0, 4800.0))
        self.assertEqual(gta6clip.choose_section(VOD_OLD, last="20m")[0], (22093.0, 23293.0))


if __name__ == "__main__":
    unittest.main()

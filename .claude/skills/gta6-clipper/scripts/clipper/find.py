"""Find GTA 6 streams worth clipping, biggest first, one per streamer. No keys needed:
  1. YouTube search: GTA 6 streams live now, and long GTA 6 streams from today, by views.
  2. The watchlist (streamers.txt in the clips folder): each streamer's newest VOD with
     GTA in the title, on Twitch or YouTube."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media import ClipError, ytdlp

# YouTube search filters (sorted by view count): live now / uploaded today + longer than 20 min.
SEARCHES = {"live": "CAMSAkAB", "today": "CAMSBAgCGAI%3D"}


def _flat(url, limit):
    try:
        raw = ytdlp(["--flat-playlist", "--playlist-end", str(limit), "-J", url],
                    timeout=120, what="searching")
        return json.loads(raw).get("entries") or []
    except (ClipError, ValueError):
        return []


def youtube(query):
    out = []
    for kind, sp in SEARCHES.items():
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}&sp={sp}"
        for e in _flat(url, 15):
            long_enough = kind == "live" or (e.get("duration") or 0) >= 1200
            if (e.get("id") and e.get("ie_key", "Youtube") == "Youtube" and long_enough
                    and "#shorts" not in (e.get("title") or "").lower()):
                out.append({"url": f"https://www.youtube.com/watch?v={e['id']}",
                            "name": e.get("channel") or e.get("uploader") or "?",
                            "title": e.get("title") or "", "views": e.get("view_count") or 0,
                            "live": kind == "live" or e.get("live_status") == "is_live",
                            "source": f"youtube {kind}"})
    return out


def watchlist(path, max_age_h=48):
    entries = []
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            site, _, handle = line.split("#")[0].strip().partition(":")
            if site in ("twitch", "youtube") and handle.strip():
                entries.append((site, handle.strip().lstrip("@")))

    def newest(entry):
        site, handle = entry
        listing = (f"https://www.twitch.tv/{handle}/videos?filter=archives&sort=time" if site == "twitch"
                   else f"https://www.youtube.com/@{handle}/streams")
        for e in _flat(listing, 3):
            title = e.get("title") or ""
            ts = e.get("timestamp") or 0
            if "gta" not in title.lower() or (ts and time.time() - ts > max_age_h * 3600):
                continue
            url = e.get("url") or ""
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={e.get('id')}"
            return {"url": url, "name": e.get("channel") or e.get("uploader") or handle, "title": title,
                    "views": e.get("view_count") or 0, "live": e.get("live_status") == "is_live",
                    "source": f"watchlist ({site})"}
        return None

    with ThreadPoolExecutor(6) as pool:
        return [r for r in pool.map(newest, entries) if r]


def find(watchlist_path, limit=5, query="GTA 6"):
    best = {}
    for s in watchlist(watchlist_path) + youtube(query):
        title = s["title"].lower()
        if "gta" not in title and "grand theft auto" not in title:
            continue
        key = s["name"].lower()
        if key not in best or s["views"] > best[key]["views"]:
            best[key] = s
    return sorted(best.values(), key=lambda s: -s["views"])[:limit]

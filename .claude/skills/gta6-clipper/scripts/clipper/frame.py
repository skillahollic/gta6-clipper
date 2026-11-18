"""16:9 stream -> 9:16 clip. Three looks:
  stack - a small face that stays in one place (a facecam): facecam on top, gameplay below
  crop  - a big face (just chatting, full-screen cam): a 9:16 crop around the face
  fit   - no steady face: the whole frame over a blurred copy of itself
A facecam spot can also be given by hand (--cam) and is then remembered per streamer."""

import hashlib
import subprocess
import urllib.request
from pathlib import Path

import numpy as np

from .media import FFMPEG

W, H = 1080, 1920
CAM_H = 700                    # height of the facecam panel in the stack look
SAMPLE_W = 960
MODEL = Path(__file__).resolve().parents[2] / ".models" / "face_detection_yunet_2023mar.onnx"
MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
CORNERS = {"top-left": (0, 0), "top-right": (70, 0), "bottom-left": (0, 62), "bottom-right": (70, 62)}


def even(v):
    v = int(round(v))
    return v - v % 2


def frames(path, start, dur, info, n=24, width=SAMPLE_W):
    """n grey frames spread over [start, start+dur], `width` pixels wide."""
    h = even(info["height"] * width / info["width"])
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(path),
           "-vf", f"fps={n / max(dur, 1):.4f},scale={width}:{h}", "-pix_fmt", "gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    k = len(raw) // (width * h)
    return np.frombuffer(raw[: k * width * h], np.uint8).reshape(k, h, width)


def ensure_face_model():
    """OpenCV's YuNet face finder (0.2 MB, MIT licence), checked by its SHA-256."""
    if MODEL.exists() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == MODEL_SHA256:
        return MODEL
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(MODEL_URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise RuntimeError("the face model download did not match its checksum")
    MODEL.write_bytes(data)
    return MODEL


def faces(stack):
    """Every face in every frame: (frame index, x, y, w, h) in sample pixels.
    YuNet finds small, turned and headset-wearing faces; OpenCV's older built-in
    finder is the fallback when the model file is missing."""
    import cv2
    out = []
    hgt, wid = stack.shape[1:]
    if MODEL.exists():
        net = cv2.FaceDetectorYN.create(str(MODEL), "", (wid, hgt), 0.7, 0.3, 500)
        for i, g in enumerate(stack):
            _, found = net.detect(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
            out += [(i, *map(float, f[:4])) for f in (found if found is not None else [])]
        return out
    finder = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    for i, g in enumerate(stack):
        for f in finder.detectMultiScale(cv2.equalizeHist(g), 1.08, 6, minSize=(22, 22)):
            out.append((i, *map(float, f)))
    return out


def steady_face(found, stack):
    """The face that sits in the same place in most frames AND moves a little (a real
    person, not a poster or thumbnail). Returns (x, y, w, h, share) or None."""
    n = len(stack)
    if not found or n < 4:
        return None
    best = None
    for f in found:
        cx, cy = f[1] + f[3] / 2, f[2] + f[4] / 2
        near = [g for g in found if abs(g[1] + g[3] / 2 - cx) < 0.6 * f[3]
                and abs(g[2] + g[4] / 2 - cy) < 0.6 * f[4]]
        share = len({g[0] for g in near}) / n
        if best is None or share > best[1]:
            best = (near, share)
    near, share = best
    if share < 0.35:
        return None
    x, y, w, h = np.median(np.array([g[1:] for g in near]), axis=0)
    patch = stack[:, int(y):int(y + h), int(x):int(x + w)].astype(np.float32)
    if patch.size and patch.std(axis=0).mean() < 2.0:
        return None                                     # frozen: not a live person
    return float(x), float(y), float(w), float(h), share


def cam_box(stack, face):
    """The facecam rectangle around a small face, from two clues:
    1. a border: a straight edge that stays in the same place in (almost) every frame;
    2. stillness: a webcam's room barely changes, gameplay changes all the time, so the
       cam ends where the picture starts to move.
    A side with no clue gets a safe default. Returns (box in 0..1, sides found)."""
    import cv2
    fx, fy, fw, fh = face[:4]
    hgt, wid = stack.shape[1:]
    edges = np.mean([cv2.Canny(g, 40, 120) > 0 for g in stack], axis=0) >= 0.7
    still = stack.astype(np.float32).std(axis=0) < 6
    band_r = slice(int(max(0, fy - 0.5 * fh)), int(min(hgt, fy + 2.0 * fh)))
    band_c = slice(int(max(0, fx - 1.0 * fw)), int(min(wid, fx + 2.0 * fw)))

    def widen(v):                                  # a border may wobble by one pixel
        return np.maximum(v, np.maximum(np.r_[0, v[:-1]], np.r_[v[1:], 0]))

    def scan(edge_score, still_score, start, limit, step, size):
        """Walk out from the face; stop at a border or where stillness ends."""
        start, limit = int(start), int(limit)
        low = 0
        for i in range(start, limit, step):
            if i < 0 or i >= size:
                return (0 if step < 0 else size), True          # reached the frame edge
            if edge_score[i] >= 0.6:
                return i, True
            low = low + 1 if still_score[i] < 0.35 else 0
            if low >= 4:
                return i - 3 * step, True
        return None, False

    col_e, row_e = widen(edges[band_r, :].mean(axis=0)), widen(edges[:, band_c].mean(axis=1))
    col_s, row_s = still[band_r, :].mean(axis=0), still[:, band_c].mean(axis=1)
    left, a = scan(col_e, col_s, fx - 1.2 * fw, fx - 12 * fw, -1, wid)
    right, b = scan(col_e, col_s, fx + 2.2 * fw, fx + 13 * fw, 1, wid)
    top, c = scan(row_e, row_s, fy - 0.6 * fh, fy - 6 * fh, -1, hgt)
    bottom, d = scan(row_e, row_s, fy + 2.0 * fh, fy + 8 * fh, 1, hgt)
    x0 = left if left is not None else max(0.0, fx - 3 * fw)
    x1 = right if right is not None else min(wid, fx + 4 * fw)
    y0 = top if top is not None else max(0.0, fy - 1.2 * fh)
    y1 = bottom if bottom is not None else min(hgt, fy + 3 * fh)
    return [x0 / wid, y0 / hgt, (x1 - x0) / wid, (y1 - y0) / hgt], a + b + c + d


def parse_cam(spec):
    """'top-right' or 'x,y,w,h' in percent of the frame -> box in 0..1, or None."""
    if not spec or spec == "auto":
        return None
    if spec in CORNERS:
        x, y = CORNERS[spec]
        return [x / 100, y / 100, 0.30, 0.38]
    try:
        x, y, w, h = [float(v) / 100 for v in spec.split(",")]
    except ValueError:
        raise SystemExit(f"--cam must be auto, a corner ({', '.join(CORNERS)}) or x,y,w,h in percent")
    return [x, y, w, h]


def decide(path, start, dur, info, layout="auto", cam=None, remembered=None):
    """Returns (look, cam box in 0..1 or None, crop centre x in 0..1 or None, note)."""
    if layout == "fit":
        return "fit", None, None, "fit chosen by hand"
    if cam:
        return "stack", cam, None, "facecam given by hand"
    stack = frames(path, start, dur, info)
    face = steady_face(faces(stack), stack) if len(stack) else None
    if face is None and info["width"] > SAMPLE_W:      # small facecams: look again at full size
        stack = frames(path, start, dur, info, n=16, width=min(1920, even(info["width"])))
        face = steady_face(faces(stack), stack) if len(stack) else None
    sw = stack.shape[2] if len(stack) else SAMPLE_W
    sh = stack.shape[1] if len(stack) else 1
    if face is None:
        if remembered:
            return "stack", remembered, None, "no clear face; using this streamer's saved facecam spot"
        return ("fit" if layout == "auto" else layout), None, 0.5, "no steady face found"
    x, y, w, h, share = face
    if layout == "crop" or (layout == "auto" and w / sw >= 0.12):
        return "crop", None, (x + w / 2) / sw, f"big face ({share:.0%} of frames): crop on it"
    if remembered:
        rx, ry, rw, rh = remembered
        if rx <= (x + w / 2) / sw <= rx + rw and ry <= (y + h / 2) / sh <= ry + rh:
            return "stack", remembered, None, "face is inside this streamer's saved facecam spot"
    box, sides = cam_box(stack, face)
    return "stack", box, None, f"facecam found ({share:.0%} of frames, {sides}/4 border sides seen)"


def cam_px(share=None):
    """Facecam panel height in pixels from its share of the clip height in percent (25-55)."""
    return CAM_H if share is None else even(H * min(55.0, max(25.0, float(share))) / 100)


def graph(look, info, cam=None, cx=0.5, cam_h=CAM_H):
    """ffmpeg filter graph from [0:v] to [base] (1080x1920)."""
    sw, sh = info["width"], info["height"]
    if look == "stack":
        x, y, w, h = cam[0] * sw, cam[1] * sh, cam[2] * sw, cam[3] * sh
        want = W / cam_h
        if w / h > want:                                  # wider than the panel: trim the sides
            cw, ch = h * want, h
            x += (w - cw) / 2
        else:                                             # taller: keep the head, trim below
            cw, ch = w, w / want
            y += min((h - ch) * 0.25, h - ch)
        cw, ch = min(cw, sw), min(ch, sh)
        x, y = min(max(x, 0), sw - cw), min(max(y, 0), sh - ch)
        gh = sh
        gw = min(sw, gh * W / (H - cam_h))
        gx = (sw - gw) / 2
        cam_l, cam_r = cam[0] * sw, (cam[0] + cam[2]) * sw
        if cam_r > gx and cam_l < gx + gw:                # gameplay crop would show the cam: move it
            gx = cam_r if cam_l < sw / 2 and cam_r + gw <= sw else max(0, cam_l - gw)
        return (f"[0:v]split=2[a][b];"
                f"[a]crop={even(cw)}:{even(ch)}:{even(x)}:{even(y)},scale={W}:{cam_h}:flags=lanczos,setsar=1[cam];"
                f"[b]crop={even(gw)}:{even(gh)}:{even(gx)}:0,scale={W}:{H - cam_h}:flags=lanczos,setsar=1[game];"
                f"[cam][game]vstack=inputs=2[base]")
    if look == "crop":
        cw = even(min(sw, sh * W / H))
        x = min(max(cx * sw - cw / 2, 0), sw - cw)
        return f"[0:v]crop={cw}:{even(sh)}:{even(x)}:0,scale={W}:{H}:flags=lanczos,setsar=1[base]"
    return (f"[0:v]split=2[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma=30,eq=brightness=-0.12[bg];[b]scale={W}:-2:flags=lanczos,setsar=1[fg];"
            f"[bg][fg]overlay=0:(H-h)/2[base]")


def text_spots(look, info, cam_h=CAM_H):
    """(y of the hook bar centre, y of the caption centre) for each look (the "auto" spots)."""
    if look == "stack":
        return cam_h, int(H * 0.68) + (cam_h - CAM_H) // 2
    if look == "fit":
        fg = W * info["height"] / max(1, info["width"])
        return int((H - fg) / 2 - 120), int((H + fg) / 2 + 170)
    return int(H * 0.14), int(H * 0.70)


def game_area(look, info, cam_h=CAM_H):
    """(top, bottom) of the gameplay picture in the 1080x1920 clip."""
    if look == "stack":
        return cam_h, H
    if look == "fit":
        fg = W * info["height"] / max(1, info["width"])
        return int((H - fg) / 2), int((H + fg) / 2)
    return 0, H


HOOK_SPOTS = {"top": 0.12, "middle": 0.5, "bottom": 0.88}       # share of the clip height
CAPTION_SPOTS = {"top": 0.17, "middle": 0.5, "bottom": 0.82}    # share of the gameplay area


def place(look, info, cam_h, hook_pos, hook_h, cap_pos, cap_size):
    """(hook bar centre y, caption centre y). "auto" keeps the round 1 spots. If the hook bar
    and the caption words would touch, the captions move off the hook."""
    hook_y, cap_y = text_spots(look, info, cam_h)
    if hook_pos != "auto":
        hook_y = int(H * HOOK_SPOTS[hook_pos])
    if cap_pos != "auto":
        top, bottom = game_area(look, info, cam_h)
        cap_y = int(top + (bottom - top) * CAPTION_SPOTS[cap_pos])
    half = cap_size * 1.2                             # up to two lines of words
    if hook_h and abs(cap_y - hook_y) < hook_h / 2 + half + 12:
        cap_y = int(hook_y + hook_h / 2 + half + 12) if cap_y >= hook_y else int(hook_y - hook_h / 2 - half - 12)
        if cap_y + half > H - 40:                    # no room below: go above the hook
            cap_y = int(hook_y - hook_h / 2 - half - 12)
    return hook_y, int(min(max(cap_y, half + 40), H - half - 40))

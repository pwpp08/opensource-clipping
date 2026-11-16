import html
import importlib.util
import json
import math
import os
import random
import re
import shutil
import string
import subprocess
import textwrap
import time
import urllib.parse
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import requests
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PIL import Image, ImageDraw, ImageFont
from yt_dlp import YoutubeDL

def _load_studio_internal_module(file_name: str, module_alias: str):
    module_path = os.path.join(os.path.dirname(__file__), file_name)
    spec = importlib.util.spec_from_file_location(module_alias, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

utils = _load_studio_internal_module("utils.py", "clipping_studio_utils")
_resize_frame = utils._resize_frame
_is_vertical_ratio = utils._is_vertical_ratio

FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"


_helpers = _load_studio_internal_module("helpers.py", "clipping_studio_helpers")
_ffmpeg_utils = _load_studio_internal_module("ffmpeg_utils.py", "clipping_studio_ffmpeg_utils")
format_seconds = _helpers.format_seconds
escape_ffmpeg_filter_value = _helpers.escape_ffmpeg_filter_value
detect_video_encoder = _ffmpeg_utils.detect_video_encoder
get_ts_encode_args = _ffmpeg_utils.get_ts_encode_args
get_mp4_encode_args = _ffmpeg_utils.get_mp4_encode_args
open_ffmpeg_video_writer = _ffmpeg_utils.open_ffmpeg_video_writer
build_ffmpeg_progress_cmd = _ffmpeg_utils.build_ffmpeg_progress_cmd
run_ffmpeg_with_progress = _ffmpeg_utils.run_ffmpeg_with_progress

USED_PEXELS_IDS = set()


def download_pexels_broll(query, rasio, output_filename, pexels_api_key):
    global USED_PEXELS_IDS
    api_key = (pexels_api_key or os.getenv("PIXABAY_API_KEY") or os.getenv("PEXELS_API_KEY") or "").strip()
    if not api_key:
        print(" ⚠️ PIXABAY/PEXELS_API_KEY tidak ditemukan. B-roll dilewati.")
        return False

    want_vertical = _is_vertical_ratio(rasio)
    params = urllib.parse.urlencode({"key": api_key, "q": query, "per_page": 30, "safesearch": "true"})
    req = urllib.request.Request(f"https://pixabay.com/api/videos/?{params}", headers={"User-Agent": FIREFOX_UA})

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.load(response)
    except Exception as e:
        print(f" ⚠️ Error API Pixabay saat mencari '{query}': {e}")
        return False

    hits = data.get("hits", [])
    if not hits:
        print(f" ⚠️ Pixabay tidak menemukan video untuk '{query}'.")
        return False

    available_videos = [v for v in hits if v.get("id") not in USED_PEXELS_IDS] or hits

    def _matches_orientation(hit):
        vids = hit.get("videos", {})
        sample = vids.get("medium") or vids.get("large") or vids.get("small") or {}
        w, h = sample.get("width") or 0, sample.get("height") or 0
        return ((h > w) if want_vertical else (w >= h)) if (w and h) else False

    oriented_pool = [v for v in available_videos if _matches_orientation(v)]
    video_data = random.choice(oriented_pool or available_videos)
    if "id" in video_data:
        USED_PEXELS_IDS.add(video_data["id"])

    videos_dict = video_data.get("videos", {})
    candidates = [
        (rank, -(videos_dict.get(q, {}).get("width") or 0), videos_dict[q]["url"])
        for rank, q in enumerate(("large", "medium", "small", "tiny"))
        if (videos_dict.get(q) or {}).get("url")
    ]
    if not candidates:
        return False

    candidates.sort()
    download_req = urllib.request.Request(candidates[0][2], headers={"User-Agent": FIREFOX_UA})
    try:
        temp_path = output_filename + ".part"
        with urllib.request.urlopen(download_req, timeout=30) as response, open(temp_path, "wb") as f:
            shutil.copyfileobj(response, f)
        os.replace(temp_path, output_filename)
        return True
    except Exception as e:
        print(f" ⚠️ Error saat mengunduh B-roll Pixabay '{query}': {e}")
        return False


def crop_center_broll(img, target_w, target_h):
    """
    Center-crop an image frame to the exact target aspect ratio, then resize it.

    Args:
        img (np.ndarray): Input image frame array (from OpenCV).
        target_w (int): Desired output width in pixels.
        target_h (int): Desired output height in pixels.

    Returns:
        np.ndarray: The cropped and resized frame.

    Side Effects:
        None.

    Raises:
        cv2.error: If the input image format is invalid or resizing fails.
    """
    h, w = img.shape[:2]
    target_ratio = target_w / target_h
    img_ratio = w / h

    if img_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        img = img[:, x : x + new_w]
    elif img_ratio < target_ratio:
        new_h = int(w / target_ratio)
        y = (h - new_h) // 2
        img = img[y : y + new_h, :]

    return _resize_frame(img, (target_w, target_h))



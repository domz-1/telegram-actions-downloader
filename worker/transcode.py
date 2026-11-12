#!/usr/bin/env python3
"""
Worker script executed inside GitHub Actions runner.
Downloads media with yt-dlp, transcodes with ffmpeg, and uploads directly to
Telegram using Pyrogram (MTProto) supporting up to 2GB native video/audio files.
"""

import asyncio
import glob
import os
import subprocess
import sys
import time
from pathlib import Path
import requests
import yt_dlp

# Configuration from Environment Variables
TARGET_URL = os.environ.get("TARGET_URL", "").strip()
QUALITY = os.environ.get("QUALITY", "720p").lower().strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
MESSAGE_ID = os.environ.get("MESSAGE_ID", "").strip()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API_ID = os.environ.get("TELEGRAM_API_ID", "").strip()
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()

OUTPUT_DIR = Path("downloads")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def update_telegram_status(text: str):
    """Update status message in Telegram chat via Bot HTTP API."""
    if not (BOT_TOKEN and CHAT_ID and MESSAGE_ID):
        print(f"[STATUS] {text}")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": CHAT_ID,
        "message_id": int(MESSAGE_ID),
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[WARN] Failed to update status in Telegram: {e}")


class DownloadProgressHook:
    def __init__(self):
        self.last_update = 0

    def __call__(self, d):
        if d.get("status") == "downloading":
            now = time.time()
            if now - self.last_update >= 5:  # Throttle updates to every 5s
                self.last_update = now
                downloaded = d.get("downloaded_bytes", 0) / (1024 * 1024)
                total = (d.get("total_bytes") or d.get("total_bytes_estimate") or 0) / (
                    1024 * 1024
                )
                speed = (d.get("speed") or 0) / (1024 * 1024)
                pct = d.get("_percent_str", "0%").strip()
                update_telegram_status(
                    f"⬇️ *Downloading from link...*\n\n"
                    f"• Progress: `{pct}`\n"
                    f"• Size: `{downloaded:.1f} MB` / `{total:.1f} MB`\n"
                    f"• Speed: `{speed:.1f} MB/s`"
                )


def build_ydl_opts(quality: str, progress_hook) -> dict:
    """Build yt-dlp options based on selected quality."""
    out_template = str(OUTPUT_DIR / "%(title).200s.%(ext)s")

    opts = {
        "outtmpl": out_template,
        "writethumbnail": True,
        "progress_hooks": [progress_hook],
        "quiet": False,
        "no_warnings": False,
        "remote_components": ["ejs:github"],
        "extractor_args": {
            "youtube": {
                "player_client": ["tv_samsung", "visionos", "android"],
            }
        },
    }

    # Optional Cookies support if user sets YOUTUBE_COOKIES secret
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if cookies_content:
        cookies_file = Path("cookies.txt")
        cookies_file.write_text(cookies_content)
        opts["cookiefile"] = str(cookies_file)

    if quality == "mp3":
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    },
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "1080p":
        opts.update(
            {
                "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "720p":
        opts.update(
            {
                "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "480p":
        opts.update(
            {
                "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    else:  # original
        opts.update(
            {
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata"}],
            }
        )

    return opts


def extract_media_info(file_path: Path):
    """Extract duration, width, height using ffprobe."""
    info = {"duration": 0, "width": 1280, "height": 720}
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=width,height",
            "-of",
            "default=noprint_wrappers=1",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if line.startswith("width="):
                info["width"] = int(line.split("=")[1])
            elif line.startswith("height="):
                info["height"] = int(line.split("=")[1])
            elif line.startswith("duration="):
                info["duration"] = int(float(line.split("=")[1]))
    except Exception as e:
        print(f"[WARN] ffprobe failed: {e}")
    return info


def generate_thumbnail(video_path: Path) -> Path | None:
    """Generate a JPEG thumbnail for video."""
    thumb_path = video_path.with_suffix(".jpg")
    if thumb_path.exists():
        return thumb_path
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(thumb_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        if thumb_path.exists():
            return thumb_path
    except Exception as e:
        print(f"[WARN] Failed to generate thumbnail: {e}")
    return None


async def upload_via_pyrogram(file_path: Path, title: str, is_audio: bool):
    """Upload media directly to Telegram chat using Pyrogram MTProto (up to 2GB)."""
    from pyrogram import Client

    app = Client(
        "gha_worker",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True,
    )

    last_pct = [0]
    last_time = [0]

    def upload_progress(current, total):
        now = time.time()
        pct = int(current * 100 / total)
        if (pct - last_pct[0] >= 5 or now - last_time[0] >= 5) and pct <= 100:
            last_pct[0] = pct
            last_time[0] = now
            curr_mb = current / (1024 * 1024)
            tot_mb = total / (1024 * 1024)
            update_telegram_status(
                f"⬆️ *Uploading to Telegram (MTProto 2GB)...*\n\n"
                f"• Progress: `{pct}%`\n"
                f"• Uploaded: `{curr_mb:.1f} MB` / `{tot_mb:.1f} MB`"
            )

    async with app:
        chat = int(CHAT_ID)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        info = extract_media_info(file_path)

        caption = f"🎬 *{title}*\n\n📦 *Size:* `{file_size_mb:.1f} MB`\n🎯 *Quality:* `{QUALITY.upper()}`"

        if is_audio:
            await app.send_audio(
                chat_id=chat,
                audio=str(file_path),
                caption=caption,
                duration=info["duration"],
                title=title,
                progress=upload_progress,
            )
        else:
            thumb = generate_thumbnail(file_path)
            await app.send_video(
                chat_id=chat,
                video=str(file_path),
                caption=caption,
                duration=info["duration"],
                width=info["width"],
                height=info["height"],
                thumb=str(thumb) if thumb else None,
                supports_streaming=True,
                progress=upload_progress,
            )


def upload_via_bot_api(file_path: Path, title: str, is_audio: bool):
    """Fallback upload method using standard Telegram Bot HTTP API (max 50MB)."""
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 49.5:
        raise ValueError(
            f"File size ({file_size_mb:.1f} MB) exceeds Telegram Bot API 50MB limit! "
            "Please configure TELEGRAM_API_ID and TELEGRAM_API_HASH secrets in your GitHub repository "
            "to enable MTProto streaming up to 2GB."
        )

    endpoint = "sendAudio" if is_audio else "sendVideo"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"

    update_telegram_status(
        f"⬆️ *Uploading to Telegram (HTTP API)...*\nSize: `{file_size_mb:.1f} MB`"
    )

    with open(file_path, "rb") as f:
        field_name = "audio" if is_audio else "video"
        files = {field_name: f}
        caption = f"🎬 *{title}*\n\n📦 *Size:* `{file_size_mb:.1f} MB`\n🎯 *Quality:* `{QUALITY.upper()}`"
        data = {
            "chat_id": CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown",
            "supports_streaming": "true",
        }
        res = requests.post(url, data=data, files=files, timeout=300)
        res.raise_for_status()


async def main():
    if not TARGET_URL:
        print("[ERROR] TARGET_URL is not set!")
        sys.exit(1)

    print(f"Starting job for URL: {TARGET_URL} (Quality: {QUALITY})")
    update_telegram_status(
        f"⚙️ *GitHub Actions Runner Started*\n\nTarget URL: {TARGET_URL}\nPreparing download..."
    )

    hook = DownloadProgressHook()
    ydl_opts = build_ydl_opts(QUALITY, hook)

    media_title = "Converted Media"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(TARGET_URL, download=True)
            if meta:
                media_title = meta.get("title", media_title)
    except Exception as e:
        err_msg = f"❌ *Download Failed:*\n`{str(e)}`"
        update_telegram_status(err_msg)
        print(f"[ERROR] yt-dlp failed: {e}")
        sys.exit(1)

    # Locate generated output file
    target_files = [
        f
        for f in OUTPUT_DIR.iterdir()
        if f.is_file()
        and not f.name.endswith((".jpg", ".png", ".webp", ".part", ".ytdl"))
    ]

    if not target_files:
        err_msg = "❌ *No media file found after download.*"
        update_telegram_status(err_msg)
        print("[ERROR] Output file not found!")
        sys.exit(1)

    media_file = max(target_files, key=lambda f: f.stat().st_size)
    is_audio = QUALITY == "mp3" or media_file.suffix.lower() in [
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
    ]

    print(
        f"Media file ready: {media_file} (Size: {media_file.stat().st_size / (1024 * 1024):.2f} MB)"
    )

    # Upload to Telegram
    try:
        if API_ID and API_HASH:
            print("Using Pyrogram MTProto Client for direct 2GB upload...")
            await upload_via_pyrogram(media_file, media_title, is_audio)
        else:
            print(
                "No MTProto credentials found. Falling back to Telegram Bot API (50MB limit)..."
            )
            upload_via_bot_api(media_file, media_title, is_audio)

        update_telegram_status(
            f"✅ *Processing & Upload Complete!*\n\nEnjoy your media! 🎉"
        )
    except Exception as e:
        err_msg = f"❌ *Upload Failed:*\n`{str(e)}`"
        update_telegram_status(err_msg)
        print(f"[ERROR] Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

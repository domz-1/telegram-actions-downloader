#!/usr/bin/env python3
"""
Worker script executed inside GitHub Actions runner.
Downloads media with yt-dlp or direct HTTP/HTTPS streaming, transcodes with ffmpeg
into requested video (4K down to 144p) or audio (FLAC, MP3 320k down to 24k),
and uploads directly to Telegram using Pyrogram (MTProto) supporting up to 2GB native media.
"""

import asyncio
import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

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
            if now - self.last_update >= 4:  # Throttle updates to every 4s
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
        try:
            decoded = base64.b64decode(cookies_content).decode("utf-8")
            if "# Netscape" in decoded or "\t" in decoded:
                cookies_content = decoded
        except Exception:
            pass
        cookies_file = Path("cookies.txt")
        cookies_file.write_text(cookies_content)
        opts["cookiefile"] = str(cookies_file)

    # Audio formats
    if quality == "flac":
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "flac"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality in ["mp3", "mp3_320"]:
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
    elif quality == "mp3_128":
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "128",
                    },
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "mp3_48":
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "48",
                    },
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "mp3_24":
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "24",
                    },
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    # Video formats
    elif quality == "4k":
        opts.update(
            {
                "format": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "1440p":
        opts.update(
            {
                "format": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
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
    elif quality == "360p":
        opts.update(
            {
                "format": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
    elif quality == "144p":
        opts.update(
            {
                "format": "bestvideo[height<=144]+bestaudio/best[height<=144]/best",
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


def direct_stream_download(url: str) -> Path:
    """Download a direct media URL chunk-by-chunk with Telegram progress updates."""
    parsed = urlparse(url)
    raw_name = Path(parsed.path).name or "direct_media"
    clean_name = re.sub(r"[^\w\-.]", "_", raw_name)
    if not clean_name or clean_name == "_":
        clean_name = f"media_{int(time.time())}.mp4"

    dest_path = OUTPUT_DIR / clean_name

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    update_telegram_status(f"⬇️ *Connecting to Direct Media Link...*\n\n`{clean_name}`")

    with requests.get(
        url, headers=headers, stream=True, timeout=60, allow_redirects=True
    ) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        downloaded = 0
        last_update = time.time()

        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_update >= 4:
                        last_update = now
                        dl_mb = downloaded / (1024 * 1024)
                        tot_mb = total_size / (1024 * 1024)
                        pct = (
                            f"{int(downloaded * 100 / total_size)}%"
                            if total_size > 0
                            else "Streaming"
                        )
                        update_telegram_status(
                            f"⬇️ *Downloading Direct File...*\n\n"
                            f"• Progress: `{pct}`\n"
                            f"• Size: `{dl_mb:.1f} MB` / `{tot_mb:.1f} MB`"
                        )

    return dest_path


def transcode_direct_file(input_file: Path, quality: str) -> Path:
    """Transcode a directly downloaded file using ffmpeg according to requested quality."""
    if quality == "original":
        return input_file

    update_telegram_status(
        f"⚙️ *Transcoding media with FFmpeg...*\n\nTarget Format: `{quality.upper()}`"
    )

    # Audio conversions
    if quality in ["flac", "mp3", "mp3_320", "mp3_128", "mp3_48", "mp3_24"]:
        out_ext = "flac" if quality == "flac" else "mp3"
        out_file = input_file.with_name(f"{input_file.stem}_{quality}.{out_ext}")

        cmd = ["ffmpeg", "-y", "-i", str(input_file), "-vn"]
        if quality == "flac":
            cmd += ["-c:a", "flac"]
        elif quality in ["mp3", "mp3_320"]:
            cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]
        elif quality == "mp3_128":
            cmd += ["-c:a", "libmp3lame", "-b:a", "128k"]
        elif quality == "mp3_48":
            cmd += ["-c:a", "libmp3lame", "-b:a", "48k"]
        elif quality == "mp3_24":
            cmd += ["-c:a", "libmp3lame", "-b:a", "24k"]

        cmd.append(str(out_file))
        subprocess.run(cmd, check=True)
        return out_file

    # Video height mappings
    height_map = {
        "4k": 2160,
        "1440p": 1440,
        "1080p": 1080,
        "720p": 720,
        "480p": 480,
        "360p": 360,
        "144p": 144,
    }

    target_h = height_map.get(quality)
    if target_h:
        out_file = input_file.with_name(f"{input_file.stem}_{quality}.mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-vf",
            f"scale=-2:'min({target_h},ih)'",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_file),
        ]
        subprocess.run(cmd, check=True)
        return out_file

    return input_file


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
        if (pct - last_pct[0] >= 5 or now - last_time[0] >= 4) and pct <= 100:
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

        caption = (
            f"🎬 *{title}*\n\n"
            f"📦 *Size:* `{file_size_mb:.1f} MB`\n"
            f"🎯 *Quality:* `{QUALITY.upper()}`"
        )

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
        caption = (
            f"🎬 *{title}*\n\n"
            f"📦 *Size:* `{file_size_mb:.1f} MB`\n"
            f"🎯 *Quality:* `{QUALITY.upper()}`"
        )
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
        f"⚙️ *GitHub Actions Runner Started*\n\n"
        f"Target URL: {TARGET_URL}\n"
        f"Requested Format: `{QUALITY.upper()}`\n"
        f"Analyzing link and downloading..."
    )

    media_file = None
    media_title = "Converted Media"

    # Step 1: Try with yt-dlp first
    try:
        hook = DownloadProgressHook()
        ydl_opts = build_ydl_opts(QUALITY, hook)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(TARGET_URL, download=True)
            if meta:
                media_title = meta.get("title", media_title)

        target_files = [
            f
            for f in OUTPUT_DIR.iterdir()
            if f.is_file()
            and not f.name.endswith((".jpg", ".png", ".webp", ".part", ".ytdl"))
        ]
        if target_files:
            media_file = max(target_files, key=lambda f: f.stat().st_size)
    except Exception as ydl_err:
        err_str = str(ydl_err)
        print(f"[WARN] yt-dlp attempt failed: {err_str}")

        if "confirm you’re not a bot" in err_str or "Sign in to confirm" in err_str:
            err_msg = (
                "⚠️ *تنبيه حماية يوتيوب:*\n\n"
                "سيرفرات GitHub تقع ضمن مراكز بيانات مايكروسوفت (Datacenter IPs)، ويوتيوب يطلب تسجيل الدخول للتأكد من أنك لست روبوتاً.\n\n"
                "💡 *الحل:* أضف كوكيز حسابك في يوتيوب كـ Secret في GitHub باسم `YOUTUBE_COOKIES` لتجاوز هذا التحقق نهائياً.\n\n"
                "*(ملاحظة: باقي المواقع مثل تيك توك، تويتر/X، إنستغرام والروابط المباشرة تعمل فوراً بدون كوكيز)*"
            )
            update_telegram_status(err_msg)
            sys.exit(1)

        # Step 2: Fallback for Direct Media URLs (HTTP/HTTPS file links)
        print("[INFO] Attempting direct HTTP stream download...")
        try:
            downloaded_raw = direct_stream_download(TARGET_URL)
            media_title = downloaded_raw.stem
            media_file = transcode_direct_file(downloaded_raw, QUALITY)
        except Exception as direct_err:
            err_msg = f"❌ *Download Failed:*\n\nBoth yt-dlp and Direct Download failed:\n`{direct_err}`"
            update_telegram_status(err_msg)
            print(f"[ERROR] Direct download failed: {direct_err}")
            sys.exit(1)

    if not media_file or not media_file.exists():
        err_msg = "❌ *No media file found after processing.*"
        update_telegram_status(err_msg)
        print("[ERROR] Output file not found!")
        sys.exit(1)

    is_audio = QUALITY in [
        "flac",
        "mp3",
        "mp3_320",
        "mp3_128",
        "mp3_48",
        "mp3_24",
    ] or media_file.suffix.lower() in [
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".flac",
        ".wav",
    ]

    print(
        f"Media file ready: {media_file} (Size: {media_file.stat().st_size / (1024 * 1024):.2f} MB)"
    )

    # Step 3: Upload to Telegram
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
            f"✅ *Processing & Upload Complete!*\n\nFormat: `{QUALITY.upper()}`\nEnjoy your media! 🎉"
        )
    except Exception as e:
        err_msg = f"❌ *Upload Failed:*\n`{str(e)}`"
        update_telegram_status(err_msg)
        print(f"[ERROR] Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

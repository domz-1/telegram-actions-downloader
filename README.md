# 🎬 Telegram ↔ GitHub Actions Media Converter & Uploader

A serverless, zero-VPS media downloader, transcoder, and uploader built with:

- **Telegram Bot** as the chat interface.
- **Vercel Serverless Function** (`Bun` + `TypeScript`) as the instant receiver and dispatcher.
- **GitHub Actions** as the free ephemeral computing engine running `yt-dlp` and `ffmpeg`.
- **Pyrogram (MTProto)** in the GitHub Actions runner for direct native uploads up to **2 GB** into Telegram chats.

---

## 🚀 Architecture Overview

1. User sends a link (YouTube, TikTok, Twitter/X, Instagram, or direct video/audio) to the Telegram bot.
2. The Vercel webhook validates the user ID against `ALLOWED_USER_IDS` and responds with inline buttons for quality:
   - `🎬 Best Video (1080p+)`
   - `📺 Standard (720p)`
   - `📱 Mobile (480p)`
   - `🎵 Audio (MP3 320k)`
   - `📦 Best Original`
3. When the user taps a button, Vercel triggers a GitHub Actions workflow via `repository_dispatch`.
4. GitHub Actions boots up an Ubuntu runner, downloads and transcodes the media using `yt-dlp` and `ffmpeg`.
5. Pyrogram streams the media directly back into the user's chat with live progress editing and native player support.

---

## 🛠️ Step-by-Step Setup Guide

### 1. Telegram Bot Token

Your bot token:

```text
9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M
```

Test your bot connection using `curl`:

```bash
curl -s "https://api.telegram.org/bot9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M/getMe" | jq .
```

---

### 2. Get MTProto API Credentials (for 2GB Uploads)

To upload files up to 2 GB (instead of the 50MB HTTP Bot API limit):

1. Go to [https://my.telegram.org](https://my.telegram.org) and log in with your phone number.
2. Click **API development tools**.
3. Create an application (any title/short name).
4. Copy your **`api_id`** and **`api_hash`**.

---

### 3. Configure GitHub Repository Secrets

In your GitHub repository, navigate to **Settings > Secrets and variables > Actions** and add:

- `TELEGRAM_BOT_TOKEN`: `9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M`
- `TELEGRAM_API_ID`: Your numeric API ID from my.telegram.org
- `TELEGRAM_API_HASH`: Your API Hash string from my.telegram.org

_(Note: If `TELEGRAM_API_ID` is omitted, the bot falls back to standard Bot API with a 50MB limit)._

---

### 4. Create GitHub Personal Access Token (PAT)

To allow Vercel to dispatch workflows on GitHub:

1. Go to **GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)**.
2. Generate a token with the **`repo`** scope (or **`workflow`** scope).
3. Copy the token.

---

### 5. Deploy to Vercel

Deploy the repository to Vercel:

```bash
bun x vercel
```

Or connect your GitHub repository directly on [vercel.com](https://vercel.com).

Add the following **Environment Variables** in Vercel:

- `TELEGRAM_BOT_TOKEN`: `9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M`
- `GITHUB_TOKEN`: Your GitHub Personal Access Token
- `GITHUB_REPO`: `your-username/telegram-actions-downloader`
- `ALLOWED_USER_IDS`: Your Telegram numeric User ID (get it from `@userinfobot` on Telegram)

---

### 6. Set Telegram Webhook

Once your Vercel deployment URL is ready (e.g. `https://your-app.vercel.app`), set the Telegram webhook using `curl`:

```bash
curl -s -F "url=https://your-app.vercel.app/api/webhook" \
  "https://api.telegram.org/bot9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M/setWebhook" | jq .
```

Check the webhook status:

```bash
curl -s "https://api.telegram.org/bot9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M/getWebhookInfo" | jq .
```

---

## 🧪 Local Testing & Verification

Run type checks:

```bash
bun run typecheck
```

Format code:

```bash
bun x prettier --write .
```

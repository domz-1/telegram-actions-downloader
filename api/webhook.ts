import type { VercelRequest, VercelResponse } from "@vercel/node";

interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
}

interface TelegramChat {
  id: number;
  type: string;
}

interface TelegramMessage {
  message_id: number;
  from?: TelegramUser;
  chat: TelegramChat;
  text?: string;
  reply_to_message?: TelegramMessage;
}

interface TelegramCallbackQuery {
  id: string;
  from: TelegramUser;
  message?: TelegramMessage;
  data?: string;
}

interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
  callback_query?: TelegramCallbackQuery;
}

const BOT_TOKEN =
  process.env.TELEGRAM_BOT_TOKEN ||
  "9189317935:AAHTlKCuX42Use3My-hwyfY9bc5L2NK9G8M";
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || "";
const GITHUB_REPO = process.env.GITHUB_REPO || "";
const ALLOWED_USER_IDS = (process.env.ALLOWED_USER_IDS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

async function callTelegram(method: string, payload: Record<string, unknown>) {
  const url = `https://api.telegram.org/bot${BOT_TOKEN}/${method}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

async function triggerGitHubWorkflow(clientPayload: Record<string, unknown>) {
  if (!GITHUB_TOKEN || !GITHUB_REPO) {
    throw new Error(
      "Missing GITHUB_TOKEN or GITHUB_REPO in environment variables.",
    );
  }

  const url = `https://api.github.com/repos/${GITHUB_REPO}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github.v3+json",
      Authorization: `Bearer ${GITHUB_TOKEN}`,
      "User-Agent": "telegram-actions-bot",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      event_type: "convert-media",
      client_payload: clientPayload,
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`GitHub API ${response.status}: ${errorBody}`);
  }

  return true;
}

function isUserAllowed(userId?: number): boolean {
  if (!ALLOWED_USER_IDS.length) return true; // If empty, open to all
  if (!userId) return false;
  return ALLOWED_USER_IDS.includes(userId.toString());
}

function extractUrl(text?: string): string | null {
  if (!text) return null;
  const match = text.match(/https?:\/\/[^\s]+/i);
  return match ? match[0] : null;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method === "GET") {
    return res.status(200).json({
      status: "online",
      service: "telegram-actions-downloader",
      hasBotToken: Boolean(BOT_TOKEN),
      hasGithubToken: Boolean(GITHUB_TOKEN),
      hasGithubRepo: Boolean(GITHUB_REPO),
    });
  }

  if (req.method !== "POST") {
    return res.status(405).send("Method Not Allowed");
  }

  try {
    const update: TelegramUpdate = req.body;

    // 1. Handle Callback Query (Button click for Quality selection)
    if (update.callback_query) {
      const cb = update.callback_query;
      const userId = cb.from.id;
      const chatId = cb.message?.chat.id;
      const messageId = cb.message?.message_id;
      const data = cb.data || "";

      await callTelegram("answerCallbackQuery", {
        callback_query_id: cb.id,
      });

      if (!chatId || !messageId) {
        return res.status(200).json({ ok: true });
      }

      if (!isUserAllowed(userId)) {
        await callTelegram("editMessageText", {
          chat_id: chatId,
          message_id: messageId,
          text: `⛔ Access Denied.\nYour User ID: \`${userId}\` is not in the whitelist.`,
          parse_mode: "Markdown",
        });
        return res.status(200).json({ ok: true });
      }

      if (data.startsWith("q:")) {
        const quality = data.replace("q:", "");
        const originalText = cb.message?.text || "";
        const targetUrl = extractUrl(originalText);

        if (!targetUrl) {
          await callTelegram("editMessageText", {
            chat_id: chatId,
            message_id: messageId,
            text: "❌ Error: Could not locate media URL in message.",
          });
          return res.status(200).json({ ok: true });
        }

        await callTelegram("editMessageText", {
          chat_id: chatId,
          message_id: messageId,
          text: `🚀 *Queued for Processing!*\n\n🔗 *Link:* ${targetUrl}\n🎯 *Format:* \`${quality.toUpperCase()}\`\n\n⚙️ *Spawning GitHub Actions Runner...*`,
          parse_mode: "Markdown",
        });

        try {
          await triggerGitHubWorkflow({
            url: targetUrl,
            quality: quality,
            chat_id: chatId,
            message_id: messageId,
            user_id: userId,
          });

          await callTelegram("editMessageText", {
            chat_id: chatId,
            message_id: messageId,
            text: `⏳ *Job Dispatched to GitHub Actions!*\n\n🔗 *Link:* ${targetUrl}\n🎯 *Format:* \`${quality.toUpperCase()}\`\n\nWorker is starting up to download, convert, and upload directly back here.`,
            parse_mode: "Markdown",
          });
        } catch (err: unknown) {
          const errorMessage = err instanceof Error ? err.message : String(err);
          await callTelegram("editMessageText", {
            chat_id: chatId,
            message_id: messageId,
            text: `❌ *GitHub Actions Dispatch Failed*\n\n\`${errorMessage}\`\n\nPlease check that your \`GITHUB_TOKEN\` and \`GITHUB_REPO\` are properly configured in Vercel.`,
            parse_mode: "Markdown",
          });
        }
      }

      return res.status(200).json({ ok: true });
    }

    // 2. Handle Incoming Message
    if (update.message) {
      const msg = update.message;
      const chatId = msg.chat.id;
      const userId = msg.from?.id;
      const text = msg.text?.trim() || "";

      // Authorization Check
      if (!isUserAllowed(userId)) {
        await callTelegram("sendMessage", {
          chat_id: chatId,
          text: `⛔ *Access Denied*\nYour Telegram User ID is: \`${userId}\`\nAsk the admin to add your ID to \`ALLOWED_USER_IDS\`.`,
          parse_mode: "Markdown",
        });
        return res.status(200).json({ ok: true });
      }

      // /start or /help command
      if (text.startsWith("/start") || text.startsWith("/help")) {
        await callTelegram("sendMessage", {
          chat_id: chatId,
          text: `👋 *Welcome to Serverless Media Converter Bot!*\n\nSimply send me any video or media link (YouTube, TikTok, Instagram, Twitter/X, direct video/audio URLs).\n\nI will ask you for your preferred format/quality, launch a free **GitHub Actions** runner to process it, and upload it right back into this chat up to **2 GB**!`,
          parse_mode: "Markdown",
        });
        return res.status(200).json({ ok: true });
      }

      const foundUrl = extractUrl(text);
      if (!foundUrl) {
        await callTelegram("sendMessage", {
          chat_id: chatId,
          text: "⚠️ Please send a valid link starting with `http://` or `https://`.",
          parse_mode: "Markdown",
        });
        return res.status(200).json({ ok: true });
      }

      // Display Quality Selection Keyboard
      const inlineKeyboard = [
        [
          { text: "🎬 Best Video (1080p+)", callback_data: "q:1080p" },
          { text: "📺 Standard (720p)", callback_data: "q:720p" },
        ],
        [
          { text: "📱 Mobile (480p)", callback_data: "q:480p" },
          { text: "🎵 Audio (MP3 320k)", callback_data: "q:mp3" },
        ],
        [
          {
            text: "📦 Best Original (No Re-encode)",
            callback_data: "q:original",
          },
        ],
      ];

      await callTelegram("sendMessage", {
        chat_id: chatId,
        text: `📥 *Media Link Detected:*\n${foundUrl}\n\nSelect your desired format/quality:`,
        parse_mode: "Markdown",
        reply_markup: {
          inline_keyboard: inlineKeyboard,
        },
      });

      return res.status(200).json({ ok: true });
    }

    return res.status(200).json({ ok: true });
  } catch (err: unknown) {
    const errorDetails = err instanceof Error ? err.stack : String(err);
    console.error("Webhook Error:", errorDetails);
    return res.status(500).json({ error: "Internal Server Error" });
  }
}

# -*- coding: utf-8 -*-
"""
MetaBull Universe Telegram Bot (no Q/A)
- 6 bottom buttons: Start, Create Post, Create Landing Page, Service Demos, Follow Us, Cancel
- Create Post: user sends image + phone/email/URL -> CTA buttons
- Create Landing Page: logo via URL OR direct photo upload (embedded base64 data URI), color theme JSON, CTA link
- Logs all user messages + bot replies to Google Sheet + Google Doc

ENV (.env) expected:
- BOT_TOKEN=...
- SOCIAL_TELEGRAM=...
- SOCIAL_INSTAGRAM=...
- SOCIAL_GOOGLE=...
- SOCIAL_LINKEDIN=...
- SOCIAL_WHATSAPP=...
- GOOGLE_SERVICE_ACCOUNT_JSON=C:\\path\\to\\service_account.json
- GSHEET_ID=...
- GDRIVE_DOC_ID=...

Run:
  python bot.py
"""

import os
import re
import io
import html
import json
import base64
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv

load_dotenv()

# ---------------- Telegram ----------------
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN in .env")

FOLLOW_LINKS = {
    "Telegram": os.getenv("SOCIAL_TELEGRAM", "https://t.me/"),
    "Instagram": os.getenv("SOCIAL_INSTAGRAM", "https://instagram.com/"),
    "Google": os.getenv("SOCIAL_GOOGLE", "https://google.com/"),
    "LinkedIn": os.getenv("SOCIAL_LINKEDIN", "https://www.linkedin.com/"),
    "WhatsApp": os.getenv("SOCIAL_WHATSAPP", "https://wa.me/918982285510"),
    "Discord": "https://discord.com/",  # optional
}

SERVICE_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
if SERVICE_JSON and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_JSON

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID", "").strip()

# ---------------- Google APIs (Docs + Sheets) ----------------
SHEETS_WS = None
service_docs = None

try:
    if SERVICE_JSON:
        import gspread
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(SERVICE_JSON, scopes=scopes)
        gc = gspread.authorize(creds)

        if GSHEET_ID:
            SHEET = gc.open_by_key(GSHEET_ID)
            SHEETS_WS = SHEET.sheet1

        if GDRIVE_DOC_ID:
            service_docs = build("docs", "v1", credentials=creds)
except Exception as e:
    print("[WARN] Google APIs init issue:", e)


def log_to_google(user: str, message: str, reply: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Sheet
    try:
        if SHEETS_WS:
            SHEETS_WS.append_row(
                [ts, user, message, reply], value_input_option="USER_ENTERED"
            )
    except Exception as e:
        print("[WARN] Sheet log failed:", e)
    # Doc
    try:
        if service_docs and GDRIVE_DOC_ID:
            body = {
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": f"[{ts}] {user}\nUser: {message}\nBot: {reply}\n\n",
                        }
                    }
                ]
            }
            service_docs.documents().batchUpdate(
                documentId=GDRIVE_DOC_ID, body=body
            ).execute()
    except Exception as e:
        print("[WARN] Doc log failed:", e)


# ---------------- UI (Reply Keyboard) ----------------
MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 Start")],
        [KeyboardButton("🖼️ Create a Post"), KeyboardButton("🌐 Create a Landing Page")],
        [KeyboardButton("🧪 Service Demos"), KeyboardButton("🌟 Follow Us")],
        [KeyboardButton("⛔ Cancel")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)

# ---------------- States ----------------
(
    STATE_IDLE,
    STATE_CREATE_POST_WAIT_IMAGE,
    STATE_CREATE_POST_WAIT_LINK,
    STATE_CREATE_LP_NAME,
    STATE_CREATE_LP_LOGO,
    STATE_CREATE_LP_SUB,
    STATE_CREATE_LP_DESC,
    STATE_CREATE_LP_COLORS,
    STATE_CREATE_LP_NICHE,
) = range(9)


def get_userpad(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    if "pad" not in context.user_data:
        context.user_data["pad"] = {}
    return context.user_data["pad"]


# ---------------- Helpers ----------------
def _bytes_to_data_uri(data: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Hey! 👋 Main **MetaBull Universe** ka assistant hoon.\n\n"
        "Neeche buttons se choose karein:\n"
        "• 🖼️ Create a Post — Image + link se CTA post\n"
        "• 🌐 Create a Landing Page — URL ya photo se logo, custom colors, HTML\n"
        "• 🧪 Service Demos — Sample links\n"
        "• 🌟 Follow Us — Social links\n"
        "• ⛔ Cancel — Current flow stop\n\n"
        "Ready when you are. 🚀"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "/start", "Shown main menu")
    return STATE_IDLE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Ok, sab cancel ho gaya. ✅", reply_markup=MAIN_KB)
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Cancel pressed", "Cleared state")
    return STATE_IDLE


# ----- Create a Post -----
async def create_post_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad.clear()
    await update.message.reply_text(
        "🖼️ Send **an image/photo** for the post. Then send **phone/email/website/link**."
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Create a Post selected", "Waiting image")
    return STATE_CREATE_POST_WAIT_IMAGE


async def create_post_got_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    if not update.message.photo:
        await update.message.reply_text("Please send a **photo** (image) first.")
        return STATE_CREATE_POST_WAIT_IMAGE
    pad["post_image_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "Great! Ab **phone/email/website/link** bhejein (ek line me)."
    )
    return STATE_CREATE_POST_WAIT_LINK


def _build_post_cta_buttons(link: str) -> InlineKeyboardMarkup:
    btns = []
    if link.startswith("http"):
        btns.append([InlineKeyboardButton("🌐 Visit Link", url=link)])
    elif re.match(r"^\+?\d{8,}$", link):
        btns.append([InlineKeyboardButton("📞 Call Now", url=f"tel:{link}")])
        btns.append(
            [
                InlineKeyboardButton(
                    "💬 WhatsApp", url=f"https://wa.me/{link.replace('+','')}"
                )
            ]
        )
    elif "@" in link:
        btns.append([InlineKeyboardButton("✉️ Send Email", url=f"mailto:{link}")])
    else:
        btns.append(
            [
                InlineKeyboardButton(
                    "🔗 Open",
                    url=f"{link if link.startswith('http') else 'https://' + link}",
                )
            ]
        )
    return InlineKeyboardMarkup(btns)


async def create_post_got_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    link = (update.message.text or "").strip()
    pad["post_link"] = link
    caption = (
        "✨ MetaBull Universe — Creative + IT + Marketing\n"
        "Fast delivery • Affordable pricing • Proven results.\n\n"
        "Need this service? Tap the buttons below 👇"
    )
    await update.message.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=pad["post_image_file_id"],
        caption=caption,
        reply_markup=_build_post_cta_buttons(link),
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, f"[Create Post] link={link}", caption)
    await update.message.reply_text("Post ready ✅", reply_markup=MAIN_KB)
    pad.clear()
    return STATE_IDLE


# ----- Create a Landing Page (supports URL or direct photo upload for logo) -----
LP_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{TITLE}</title>
    <meta name="description" content="{DESCRIPTION}" />
    <meta name="keywords" content="{KEYWORDS}" />
    <meta name="author" content="{TITLE}" />
    <meta name="robots" content="index, follow" />
    <link rel="icon" href="{LOGO_URL}" type="image/jpeg" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {{
        theme: {{
          extend: {{
            colors: {{
              primary: "{PRIMARY}",
              secondary: "{SECONDARY}",
              accent: "{ACCENT}",
              light: "{LIGHT}"
            }},
            fontFamily: {{ sans: ['"Inter"', "system-ui", "sans-serif"] }},
          }},
        }},
      }};
    </script>
    <style>
      body {{
        background: linear-gradient(120deg, #e0f2fe 0%, #dbeafe 100%);
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: start;
      }}
      .whatsapp-btn {{ transition: all 0.3s ease; }}
      .whatsapp-btn:hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(30, 64, 175, 0.3), 0 5px 10px rgba(14, 165, 233, 0.2);
      }}
    </style>
  </head>
  <body class="bg-white text-slate-800 font-sans min-h-screen flex justify-center items-start">
    <div class="w-full max-w-7xl p-4 mx-auto">
      <section class="text-center p-2">
        <img src="{LOGO_URL}" alt="{TITLE}" class="w-4/5 max-w-[300px] rounded-xl mx-auto mb-5" />
        <h1 class="text-3xl md:text-4xl mb-4 font-extrabold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
          {HEADING}
        </h1>
        <h2 class="text-lg md:text-xl opacity-80 mb-4">{SUBHEADING}</h2>
        <p class="text-base leading-relaxed max-w-[700px] mx-auto mb-6">
          {DESCRIPTION}
        </p>
        <div class="flex flex-col md:flex-row justify-center gap-3">
          <a href="{CTA_LINK}" class="whatsapp-btn bg-gradient-to-r from-primary to-secondary text-white py-3 px-6 rounded-full font-bold inline-flex items-center justify-center gap-2">
            <i class="fa-solid fa-bolt"></i> Get Started
          </a>
          <a href="tel:+918982285510" class="whatsapp-btn bg-white border border-slate-200 text-slate-800 py-3 px-6 rounded-full font-semibold inline-flex items-center justify-center gap-2">
            <i class="fa-solid fa-phone"></i> Call Sales
          </a>
        </div>
        <p class="text-[12px] leading-relaxed max-w-[650px] mx-auto mt-4 opacity-70">Disclaimer: Information is for educational & marketing purposes only.</p>
      </section>
    </div>
  </body>
</html>
"""


async def create_lp_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad.clear()
    await update.message.reply_text("🌐 Landing Page: Page ka **name/title** bhejein.")
    return STATE_CREATE_LP_NAME


async def create_lp_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad["lp_title"] = update.message.text.strip()
    await update.message.reply_text(
        "Logo/Image ka **URL** bhejein (https://...) **ya** seedha **photo upload** kar dein."
    )
    return STATE_CREATE_LP_LOGO


async def create_lp_get_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)

    # Photo path
    if update.message and update.message.photo:
        try:
            file_id = update.message.photo[-1].file_id
            file = await context.bot.get_file(file_id)
            bio = io.BytesIO()
            await file.download_to_memory(out=bio)
            bio.seek(0)
            data_uri = _bytes_to_data_uri(bio.read(), mime="image/jpeg")
            pad["lp_logo"] = data_uri
            await update.message.reply_text(
                "✅ Image received. Ab **Subheading** bhejein."
            )
            return STATE_CREATE_LP_SUB
        except Exception as e:
            await update.message.reply_text(
                f"Image read failed: {e}\nPlease URL ya photo dobara bhejein."
            )
            return STATE_CREATE_LP_LOGO

    # URL path
    if update.message and update.message.text:
        pad["lp_logo"] = update.message.text.strip()
        await update.message.reply_text("**Subheading** bhejein.")
        return STATE_CREATE_LP_SUB

    await update.message.reply_text(
        "Please send **image URL** ya **photo upload** karke try karein."
    )
    return STATE_CREATE_LP_LOGO


async def create_lp_get_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad["lp_sub"] = update.message.text.strip()
    await update.message.reply_text("**Description** bhejein (1–3 lines).")
    return STATE_CREATE_LP_DESC


async def create_lp_get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad["lp_desc"] = update.message.text.strip()
    await update.message.reply_text(
        "**Color theme** JSON bhejein (primary, secondary, accent, light). Example:\n"
        """```{"primary":"#1d4ed8","secondary":"#15803d","accent":"#000000","light":"#111827"}```""",
        parse_mode="Markdown",
    )
    return STATE_CREATE_LP_COLORS


async def create_lp_get_colors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    raw = update.message.text.strip().strip("`")
    try:
        colors = json.loads(raw)
    except Exception:
        colors = {
            "primary": "#1d4ed8",
            "secondary": "#15803d",
            "accent": "#000000",
            "light": "#111827",
        }
    pad["lp_colors"] = colors
    await update.message.reply_text(
        "Business/Channel **niche** + **CTA link** bhejein. Example: `marketing https://wa.me/918982285510`",
        parse_mode="Markdown",
    )
    return STATE_CREATE_LP_NICHE


async def create_lp_get_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    txt = update.message.text.strip().split()
    niche = txt[0] if txt else "marketing"
    cta = (
        txt[-1]
        if txt and txt[-1].startswith("http")
        else FOLLOW_LINKS.get("WhatsApp", "https://wa.me/918982285510")
    )

    title = pad.get("lp_title", "Your Brand")
    logo = pad.get("lp_logo", "logo.jpg")
    sub = pad.get("lp_sub", "We build results, not just pages.")
    desc = pad.get("lp_desc", "Done-for-you creative, IT & marketing solutions.")
    colors = pad.get(
        "lp_colors",
        {
            "primary": "#1d4ed8",
            "secondary": "#15803d",
            "accent": "#000000",
            "light": "#111827",
        },
    )
    kws = f"{niche}, MetaBull Universe, {title}, services, pricing, contact"

    html_code = LP_TEMPLATE.format(
        TITLE=html.escape(title),
        HEADING=html.escape(title),
        SUBHEADING=html.escape(sub),
        DESCRIPTION=html.escape(desc),
        KEYWORDS=html.escape(kws),
        LOGO_URL=html.escape(logo),
        PRIMARY=colors.get("primary", "#1d4ed8"),
        SECONDARY=colors.get("secondary", "#15803d"),
        ACCENT=colors.get("accent", "#000000"),
        LIGHT=colors.get("light", "#111827"),
        CTA_LINK=html.escape(cta),
    )

    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in title)
    fn = f"{safe_name}.html"
    with open(fn, "w", encoding="utf-8") as f:
        f.write(html_code)

    await update.message.reply_document(
        document=InputFile(fn),
        filename=fn,
        caption="Landing page ready ✅ — HTML attached.",
    )
    await update.message.reply_text(
        "All set! Edits chahiye to command dubara run kar lo.", reply_markup=MAIN_KB
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, f"[Create LP] niche={niche}, cta={cta}", f"generated {fn}")
    pad.clear()
    return STATE_IDLE


# ----- Service Demos (replace with real links) -----
SERVICE_DEMOS = {
    "Websites (Samples)": "https://example.com/websites",
    "Drive (Showreel)": "https://drive.google.com/",
    "Ads Portfolio": "https://example.com/ads",
    "YouTube Playlist": "https://youtube.com/",
}


async def service_demos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [[InlineKeyboardButton(f"🔗 {k}", url=v)] for k, v in SERVICE_DEMOS.items()]
    kb = InlineKeyboardMarkup(rows)
    await update.message.reply_text(
        "🧪 **Service Demos** — samples & portfolios:", reply_markup=kb
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Service Demos opened", "Links shown")
    return STATE_IDLE


# ----- Follow Us -----
async def follow_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows, row = [], []
    for name, url in FOLLOW_LINKS.items():
        row.append(InlineKeyboardButton(f"⭐ {name}", url=url))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    kb = InlineKeyboardMarkup(rows)
    await update.message.reply_text("🌟 **Follow Us**", reply_markup=kb)
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Follow Us opened", "Links shown")
    return STATE_IDLE


# ----- Bottom router -----
async def bottom_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if txt == "🔄 Start":
        return await start(update, context)
    if txt == "🖼️ Create a Post":
        return await create_post_entry(update, context)
    if txt == "🌐 Create a Landing Page":
        return await create_lp_entry(update, context)
    if txt == "🧪 Service Demos":
        return await service_demos(update, context)
    if txt == "🌟 Follow Us":
        return await follow_us(update, context)
    if txt == "⛔ Cancel":
        return await cancel(update, context)

    # default nudge
    await update.message.reply_text(
        "Choose an option from the keyboard below 🙂", reply_markup=MAIN_KB
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    from_text = txt if txt else "[non-text]"
    log_to_google(user, from_text, "Prompted to pick a menu option")
    return STATE_IDLE


# ----- Raw logger (optional) -----
async def log_all_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
        msg = (
            update.message.text
            if (update.message and update.message.text)
            else "[non-text message]"
        )
        log_to_google(user, f"[RAW] {msg}", "received")
    except Exception:
        pass


# ---------------- App ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^🔄 Start$"), bottom_router),
            MessageHandler(filters.Regex("^🖼️ Create a Post$"), bottom_router),
            MessageHandler(filters.Regex("^🌐 Create a Landing Page$"), bottom_router),
            MessageHandler(filters.Regex("^🧪 Service Demos$"), bottom_router),
            MessageHandler(filters.Regex("^🌟 Follow Us$"), bottom_router),
            MessageHandler(filters.Regex("^⛔ Cancel$"), bottom_router),
        ],
        states={
            STATE_IDLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bottom_router)
            ],
            STATE_CREATE_POST_WAIT_IMAGE: [
                MessageHandler(filters.PHOTO, create_post_got_image),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_POST_WAIT_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_post_got_link),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_name),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_LOGO: [
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.PHOTO,
                    create_lp_get_logo,
                ),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_SUB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_sub),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_desc),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_COLORS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_colors),
                CommandHandler("cancel", cancel),
            ],
            STATE_CREATE_LP_NICHE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_niche),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # Global raw logger (after conv, separate group)
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, log_all_incoming), group=1
    )

    app.add_handler(conv)

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MetaBull Universe Telegram Bot (env-driven)
Uses your .env keys:
- BOT_TOKEN
- SOCIAL_TELEGRAM, SOCIAL_INSTAGRAM, SOCIAL_GOOGLE, SOCIAL_LINKEDIN, SOCIAL_WHATSAPP
- GOOGLE_SERVICE_ACCOUNT_JSON (full path to service account json)
- GSHEET_ID, GDRIVE_DOC_ID
- (optional) GEMINI_API_KEY
"""

import os
import re
import html
import json
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()

# --- Telegram
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
    CallbackQueryHandler,
    filters,
)

# ============ ENV ============

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN in .env")

# Social links
FOLLOW_LINKS = {
    "Telegram": os.getenv("SOCIAL_TELEGRAM", "https://t.me/"),
    "Instagram": os.getenv("SOCIAL_INSTAGRAM", "https://instagram.com/"),
    "Google": os.getenv("SOCIAL_GOOGLE", "https://google.com/"),
    "LinkedIn": os.getenv("SOCIAL_LINKEDIN", "https://www.linkedin.com/"),
    "WhatsApp": os.getenv("SOCIAL_WHATSAPP", "https://wa.me/918982285510"),
    "Discord": "https://discord.com/",  # optional; change if you have
}

# Google service account JSON
SERVICE_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
if SERVICE_JSON and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    # set for google libraries
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_JSON

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID", "").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ============ Google APIs ============

GSPREAD_READY = False
DOCS_READY = False
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
            DOCS_READY = True

        GSPREAD_READY = SHEETS_WS is not None and service_docs is not None
except Exception as e:
    print("[WARN] Google APIs init issue:", e)


def log_to_google(user: str, message: str, reply: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Sheets
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


# ============ Gemini ============

GEMINI_READY = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")
        GEMINI_READY = True
    except Exception as e:
        print("[WARN] Gemini init failed:", e)


async def gemini_answer(prompt: str) -> str:
    if not GEMINI_READY:
        return "Gemini is not configured yet. (Set GEMINI_API_KEY in .env)"
    try:
        resp = GEMINI_MODEL.generate_content(prompt)
        return (
            resp.text.strip()
            if getattr(resp, "text", None)
            else "No response from Gemini."
        )
    except Exception as e:
        return f"Gemini error: {e}"


# ============ Knowledge Base ============

KB_RAW = """
Company Name: Metabull Universe
Type: Corporate Service Provider (Creative + IT + Marketing)
Founded: 5 years ago
Founder & CEO: Neeraj Soni
Headquarters: MP nagar. zone-2 ,Bhopal, Madhya Pradesh (Near Rani Kamlapati Station, Maharana Pratap Nagar)

Email: metabull2@gmail.com
Contact Number: +91 8982285510
Employees: 20+
Active Clients: 100+ per month

--- Services ---
1. Advertisement Services (ADS)
2. Video Editing: Ads, Social Media, Application Ads
3. Graphic Designing: Logos, Branding, Custom Design
4. Web Development: Static, Dynamic, Fully Functional Websites
5. Account Handling: Business account handling
6. Social Media Management: Posts, Growth, Strategy

--- Pricing ---
Video Editing:
- ai video = 600–700
- high ai quality video = 1000–1200
- ai model video = 1500–2000
- ugc video = 2500–3000
- white board animation = 1000–1500
- editing (1 min) = 500, bulk = 2000–2500
- spoke person video = 5000–10000+
- Social Media Videos: 5 min = 1000, 10 min = 2000, 15+ min = 2500
- Application Ads: 1 min = 800

Web Development:
- Static = 4000 (single page with free domain)
- Dynamic Normal = 7000 (multi page, free domain)
- Fully Functional Aesthetic = 8000–15000 (payment + DB)

Graphic Designing:
- Logo = 600 / 2D 800–1000 / 3D 1500+
- Others = Custom

Ads:
- Multi-platform = depends on budget & needs

Social Media Management:
- Single Account = 5000/month (3 posts/day)

Target Clients:
- Startups, Enterprises, Promotional clients, Individual Professionals
"""

SUGGESTED_QUESTIONS = [
    "Web development ke prices kya hain?",
    "Video editing me UGC ka rate?",
    "Graphic logo 2D vs 3D price?",
    "Social media management monthly plan?",
    "Office location & contact?",
]

KB_MAP: Dict[str, str] = {
    r"\b(name|company)\b": "Humara company naam **Metabull Universe** hai.",
    r"\b(type|company type|what do you do)\b": "Hum Creative + IT + Marketing services provide karte hain.",
    r"\b(founder|ceo|neeraj)\b": "Founder & CEO: **Neeraj Soni**.",
    r"\b(head|addr|location|address|bhopal|office)\b": "HQ: **MP Nagar Zone-2, Bhopal** (Near Rani Kamlapati Station, Maharana Pratap Nagar).",
    r"\b(contact|email|phone|call)\b": "Email: **metabull2@gmail.com** | Call: **+91 8982285510**.",
    r"\b(services?|offer)\b": "Hum **Ads, Video Editing, Graphic Designing, Web Development, Account Handling, Social Media Management** provide karte hain.",
    r"\b(video|edit|ugc|white\s?board|spoke|application)\b": "Video Editing pricing: ai 600–700, high-ai 1000–1200, ai-model 1500–2000, UGC 2500–3000, whiteboard 1000–1500, 1-min edit 500, bulk 2000–2500, spokesperson 5000–10000+, social 5m=1000,10m=2000,15m+=2500, app ad 1m=800.",
    r"\b(web|website|static|dynamic|payment|gateway|db|development)\b": "Web Dev: Static 4000 (1-page + free domain), Dynamic 7000, Full Aesthetic 8000–15000 (Payment+DB).",
    r"\b(graphic|logo|branding|design)\b": "Graphic/Logo: Logo 600, 2D 800–1000, 3D 1500+, other designs custom.",
    r"\b(social|management|posts|growth|strategy)\b": "Social Media Mgmt: 5000/month (3 posts/day).",
    r"\b(price|pricing|cost|rate)\b": "Short rates: Web (4k–15k), Video (500–10k+), Logo (600–1500+), SMM (5k/m).",
}


def kb_lookup(q: str) -> Optional[str]:
    ql = q.lower()
    for pattern, ans in KB_MAP.items():
        if re.search(pattern, ql):
            return ans
    return None


def qa_footer_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Services", callback_data="qa_services"),
                InlineKeyboardButton("💰 Prices", callback_data="qa_prices"),
            ],
            [
                InlineKeyboardButton("📍 Location", callback_data="qa_location"),
                InlineKeyboardButton("📞 Call Sales", url="tel:+918982285510"),
            ],
        ]
    )


# ============ UI ============

MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 Start"), KeyboardButton("❓ Q/A")],
        [KeyboardButton("🖼️ Create a Post"), KeyboardButton("🌐 Create a Landing Page")],
        [KeyboardButton("🧪 Service Demos"), KeyboardButton("🌟 Follow Us")],
        [KeyboardButton("⛔ Cancel")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)

(
    STATE_IDLE,
    STATE_QA,
    STATE_CREATE_POST_WAIT_IMAGE,
    STATE_CREATE_POST_WAIT_LINK,
    STATE_CREATE_LP_NAME,
    STATE_CREATE_LP_LOGO,
    STATE_CREATE_LP_SUB,
    STATE_CREATE_LP_DESC,
    STATE_CREATE_LP_COLORS,
    STATE_CREATE_LP_NICHE,
) = range(10)


def get_userpad(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    if "pad" not in context.user_data:
        context.user_data["pad"] = {}
    return context.user_data["pad"]


# ============ Handlers ============


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Hey! 👋 Main **MetaBull Universe** ka assistant hoon.\n\n"
        "Neeche buttons se choose karein:\n"
        "• ❓ Q/A — KB/Gemini se jawaab + suggestions\n"
        "• 🖼️ Create a Post — Image + link se CTA post\n"
        "• 🌐 Create a Landing Page — Details dekar HTML\n"
        "• 🧪 Service Demos — Samples\n"
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


# --- Q/A
async def qa_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Apna sawal bhejein (Hinglish chalega). Pehle KB check hoga; agar na mila toh Gemini help karega.\n"
        "Examples: “Web development ke prices?”, “UGC video rate?”, “Office location?”"
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Q/A selected", "Awaiting question")
    return STATE_QA


async def qa_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text or ""
    kb_ans = kb_lookup(q)
    if kb_ans:
        ans = f"**Answer (KB):** {kb_ans}\n\n_Suggestions:_ " + "; ".join(
            SUGGESTED_QUESTIONS[:3]
        )
    else:
        prompt = f"""
You are an assistant for MetaBull Universe (Creative + IT + Marketing).
User question: {q}

If the answer exists in this KB, stay consistent; else freely answer, but keep it short, helpful, and sales-friendly.

KB:
{KB_RAW}
"""
        ans = "**Answer (Gemini):** " + (await gemini_answer(prompt))
    await update.message.reply_text(
        ans, reply_markup=qa_footer_buttons(), parse_mode="Markdown"
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, q, ans)
    return STATE_QA


async def qa_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data
    if key == "qa_services":
        txt = "Services: Ads • Video Editing • Graphic Design • Web Dev • Account Handling • Social Media Mgmt."
    elif key == "qa_prices":
        txt = "Quick Prices:\n• Web: 4k–15k\n• Video: 500–10k+\n• Logo: 600–1500+\n• SMM: 5k/m\nDetails poochna ho toh message karein 🙂"
    elif key == "qa_location":
        txt = "HQ: MP Nagar Zone-2, Bhopal (Near Rani Kamlapati Station, Maharana Pratap Nagar)."
        # else case covered by Call Sales URL in button
    else:
        txt = "Sales: +91 8982285510"
    await query.edit_message_reply_markup(reply_markup=qa_footer_buttons())
    await query.message.reply_text(txt)
    user = f"{query.from_user.full_name} (@{query.from_user.username})"
    log_to_google(user, f"[QA footer] {key}", txt)


# --- Create a Post
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
        "✨ **MetaBull Universe** — Creative + IT + Marketing\n"
        "Fast delivery • Affordable pricing • Proven results.\n\n"
        "Need this service? Tap the buttons below 👇"
    )
    await update.message.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=pad["post_image_file_id"],
        caption=caption,
        parse_mode="Markdown",
        reply_markup=_build_post_cta_buttons(link),
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, f"[Create Post] link={link}", caption)
    await update.message.reply_text("Post ready ✅", reply_markup=MAIN_KB)
    pad.clear()
    return STATE_IDLE


# --- Create a Landing Page
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
            keyframes: {{
              fadeInUp: {{
                "0%": {{ opacity: "0", transform: "translateY(30px)" }},
                "100%": {{ opacity: "1", transform: "translateY(0)" }},
              }},
              zoomIn: {{
                "0%": {{ opacity: "0", transform: "scale(0.8)" }},
                "100%": {{ opacity: "1", transform: "scale(1)" }},
              }},
              fadeInBody: {{
                from: {{ opacity: "0" }},
                to: {{ opacity: "1" }},
              }},
            }},
            animation: {{
              fadeInUp: "fadeInUp 1s ease forwards",
              zoomIn: "zoomIn 1s ease forwards",
              fadeInBody: "fadeInBody 1s ease-in",
            }},
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
    await update.message.reply_text("Logo/Image ka **URL** bhejein (https://...)")
    return STATE_CREATE_LP_LOGO


async def create_lp_get_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pad = get_userpad(context)
    pad["lp_logo"] = update.message.text.strip()
    await update.message.reply_text("**Subheading** bhejein.")
    return STATE_CREATE_LP_SUB


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


# --- Service Demos (replace with real)
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
        "🧪 **Service Demos** — samples & portfolios:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Service Demos opened", "Links shown")
    return STATE_IDLE


# --- Follow Us
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
    await update.message.reply_text(
        "🌟 **Follow Us**", reply_markup=kb, parse_mode="Markdown"
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Follow Us opened", "Links shown")
    return STATE_IDLE


# --- Bottom bar router
async def bottom_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if txt == "🔄 Start":
        return await start(update, context)
    if txt == "❓ Q/A":
        return await qa_entry(update, context)
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
        "Aap **❓ Q/A** select karke sawal pooch sakte hain 🙂", reply_markup=MAIN_KB
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    from_text = txt if txt else "[non-text]"
    log_to_google(user, from_text, "Prompted to use Q/A")
    return STATE_IDLE


# --- Raw logger (optional)
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


# ============ App ============


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^🔄 Start$"), bottom_router),
            MessageHandler(filters.Regex("^❓ Q/A$"), bottom_router),
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
            STATE_QA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, qa_message),
                CommandHandler("cancel", cancel),
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_lp_get_logo),
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

    # Global raw logger (runs after the conv so it doesn't eat messages)
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, log_all_incoming), group=1
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(qa_callbacks))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MetaBull Universe Telegram Bot (env-driven, keyword intents + Gemini Q/A, image-upload LP)

ENV REQUIRED (your .env):
- BOT_TOKEN=...
- SOCIAL_TELEGRAM=...
- SOCIAL_INSTAGRAM=...
- SOCIAL_GOOGLE=...
- SOCIAL_LINKEDIN=...
- SOCIAL_WHATSAPP=...
- GOOGLE_SERVICE_ACCOUNT_JSON=C:\\path\\to\\service_account.json
- GSHEET_ID=...
- GDRIVE_DOC_ID=...
- (RECOMMENDED for AI Q/A) GEMINI_API_KEY=...

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
from typing import Dict, Any, Optional

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
    CallbackQueryHandler,
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
    "Discord": "https://discord.com/",
}

SERVICE_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
if SERVICE_JSON and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_JSON

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ---------------- Google APIs (Docs + Sheets) ----------------
GSPREAD_READY = False
SHEETS_WS = None
DOCS_READY = False
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


# ---------------- Gemini (for Q/A) ----------------
GEMINI_READY = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")
        GEMINI_READY = True
    except Exception as e:
        print("[WARN] Gemini init failed:", e)


async def gemini_answer_with_kb(question: str, kb_text: str) -> str:
    """
    Ground Gemini with the provided KB. Keep short, helpful, sales-friendly Hinglish.
    """
    if not GEMINI_READY:
        return (
            "Gemini not configured (add GEMINI_API_KEY in .env). "
            "Filhaal, KB-based quick reply try karein."
        )
    try:
        system = (
            "You are MetaBull Universe's assistant. Use ONLY the given Knowledge Base as the primary source. "
            "If something is not in KB, you may infer sensible, safe, brief guidance. "
            "Style: short, Hinglish, friendly, helpful, sales-oriented. "
            "Prefer KB prices if present. Return plain text."
        )
        prompt = f"{system}\n\nKnowledge Base:\n{kb_text}\n\nUser Question: {question}\n\nAnswer:"
        resp = GEMINI_MODEL.generate_content(prompt)
        return (
            resp.text.strip()
            if getattr(resp, "text", None)
            else "Mujhe thoda unclear laga — please question dubara likho 🙂"
        )
    except Exception as e:
        return f"Gemini error: {e}"


# ---------------- Knowledge Base (from your prompt) ----------------
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
- video editing (1 min) = 500, bulk = 2000–2500
- spoke person video = 5000–10000+
- Social Media Videos: 5 min = 1000, 10 min = 2000, 15+ min = 2500
- Application Ads: 1 min = 800

Web Development:
- Static Website = 4000 (single page + free domain)
- Dynamic Normal Website = 7000 (multiple pages + Free domain)
- Fully Functional Aesthetic = 8000–15000 (multiple pages with payment gateway + database)

Graphic Designing:
- Logo Design = 600, 2D 800–1000, 3D 1500+
- Other Designs = Custom pricing

Ads:
- Multi-platform Ads = depends on budget & needs

Social Media Management:
- Single Account = 5000 per month (3 posts/day)

Target Clients:
- Startups, Enterprises, Promotional clients, Individual Professionals
"""

SUGGESTED_QUESTIONS = [
    "Web development ke prices kya hain?",
    "UGC video editing ka rate?",
    "Logo 2D vs 3D price?",
    "Social media management monthly plan?",
    "Office location & contact?",
]

# ---------------- Keyword Intents (multiple synonyms → one answer) ----------------
INTENTS = [
    {
        "name": "services",
        "patterns": [
            r"\bservices?\b",
            r"\boffer\b",
            r"\bprovide\b",
            r"\bwhat\s+do\s+you\s+do\b",
            r"\badvertis(e|ement|ing)\b",
            r"\bvideo\s*editing\b",
            r"\bgraphic\b",
            r"\bweb\s*dev(elopment)?\b",
            r"\bsocial\s*media\b",
            r"\baccount\s*handling\b",
        ],
        "answer": (
            "Hum **Creative + IT + Marketing** me ye services dete hain:\n"
            "• Ads\n• Video Editing\n• Graphic Designing\n• Web Development\n• Account Handling\n• Social Media Management"
        ),
    },
    {
        "name": "pricing_web",
        "patterns": [
            r"\b(web|website|site)\b.*\b(price|pricing|cost|rate|charges)\b",
            r"\b(price|pricing|cost|rate|charges)\b.*\b(web|website|site)\b",
            r"\bstatic\b|\bdynamic\b|\bpayment\s*gateway\b|\bdatabase\b",
        ],
        "answer": (
            "💻 **Web Dev Prices**:\n"
            "• Static (1 page + free domain): **₹4,000**\n"
            "• Dynamic (multi-page + free domain): **₹7,000**\n"
            "• Fully Functional (Payment + DB): **₹8,000 – ₹15,000**"
        ),
    },
    {
        "name": "pricing_video",
        "patterns": [
            r"\b(video|edit|editing|ugc|white\s*board|whiteboard|spokes?person|application\s*ad|app\s*ad)\b",
            r"\b(ai\s*video|high\s*ai|ai\s*model)\b",
            r"\b(5\s*min|10\s*min|15\+?\s*min)\b",
        ],
        "answer": (
            "🎬 **Video Editing Prices**:\n"
            "• AI: 600–700 | High-AI: 1000–1200 | AI-Model: 1500–2000\n"
            "• UGC: 2500–3000 | Whiteboard: 1000–1500 | 1-min edit: 500\n"
            "• Bulk: 2000–2500 | Spokesperson: 5000–10000+\n"
            "• Social: 5m=1000, 10m=2000, 15m+=2500 | App Ad (1m)=800"
        ),
    },
    {
        "name": "pricing_logo_graphic",
        "patterns": [
            r"\b(logo|graphic|branding|design)\b.*\b(price|pricing|cost|rate|charges)\b",
            r"\b(price|pricing|cost|rate|charges)\b.*\b(logo|graphic|branding|design)\b",
            r"\b2d\b|\b3d\b",
        ],
        "answer": (
            "🎨 **Graphic/Logo Prices**:\n"
            "• Logo: 600 | 2D: 800–1000 | 3D: 1500+\n"
            "• Other designs: requirement ke hisaab se custom pricing"
        ),
    },
    {
        "name": "pricing_smm",
        "patterns": [
            r"\b(smm|social\s*media\s*manage|social\s*media\s*management|account\s*handling)\b",
            r"\bposts?\s*/?\s*day\b",
            r"\bmonthly\b",
        ],
        "answer": (
            "📱 **Social Media Management**:\n"
            "• Single account: **₹5,000/month** (3 posts/day)"
        ),
    },
    {
        "name": "location",
        "patterns": [
            r"\b(location|address|where|office|bhopal|headquarters|hq)\b",
            r"\brani\s*kamlapati\b|\bmp\s*nagar\b|\bzone-?2\b",
        ],
        "answer": "📍 **HQ**: MP Nagar Zone-2, Bhopal (Near Rani Kamlapati Station, Maharana Pratap Nagar).",
    },
    {
        "name": "contact",
        "patterns": [
            r"\b(contact|call|phone|mobile|email|reach|support)\b",
            r"\bwhats?app\b",
        ],
        "answer": "📧 **Email**: metabull2@gmail.com | ☎️ **Call**: +91 8982285510 | WhatsApp pe bhi ping kar sakte ho.",
    },
    {
        "name": "about_company",
        "patterns": [
            r"\b(name|company)\b",
            r"\btype\b",
            r"\bfounded\b",
            r"\byears?\b",
            r"\bexperience\b",
            r"\bfounder\b|\bceo\b|\bneeraj\b",
            r"\bteam|employees?\b|\bclients?\b",
        ],
        "answer": (
            "**Metabull Universe** — Corporate Service Provider (Creative + IT + Marketing), "
            "founded **5 years** ago by **Neeraj Soni**. Team **20+**, active clients **100+ per month**."
        ),
    },
    {
        "name": "ads",
        "patterns": [
            r"\bads?\b|\badvertis(e|ement|ing)\b|\bgoogle\s*ads\b|\bmeta\s*ads\b|\bfacebook\s*ads\b|\binstagram\s*ads\b"
        ],
        "answer": "📢 **Multi-platform Ads** — pricing depends on aapke budget & needs. Strategy discuss kar lete hain!",
    },
]


def detect_intent(question: str) -> Optional[str]:
    q = question.lower()
    for intent in INTENTS:
        if any(re.search(p, q) for p in intent["patterns"]):
            return intent["answer"]
    return None


# ---------------- Minimal KB-map fallback (last resort) ----------------
KB_MAP: Dict[str, str] = {
    r"\b(name|company)\b": "Humara company naam Metabull Universe hai.",
    r"\b(type|company type|what do you do)\b": "Hum Creative + IT + Marketing services provide karte hain.",
    r"\b(founder|ceo|neeraj)\b": "Founder & CEO: Neeraj Soni.",
    r"\b(head|addr|location|address|bhopal|office)\b": "HQ: MP Nagar Zone-2, Bhopal (Near Rani Kamlapati Station, Maharana Pratap Nagar).",
    r"\b(contact|email|phone|call)\b": "Email: metabull2@gmail.com | Call: +91 8982285510.",
    r"\b(services?|offer)\b": "Hum Ads, Video Editing, Graphic Designing, Web Development, Account Handling, Social Media Management provide karte hain.",
    r"\b(video|edit|ugc|white\s?board|spoke|application)\b": "Video pricing: ai 600–700, high-ai 1000–1200, ai-model 1500–2000, UGC 2500–3000, whiteboard 1000–1500, 1-min edit 500, bulk 2000–2500, spokesperson 5000–10000+, social 5m=1000/10m=2000/15m+=2500, app ad 1m=800.",
    r"\b(web|website|static|dynamic|payment|gateway|db|development)\b": "Web Dev: Static 4000 (1-page + free domain), Dynamic 7000, Full Aesthetic 8000–15000 (Payment+DB).",
    r"\b(graphic|logo|branding|design)\b": "Logo: 600, 2D 800–1000, 3D 1500+, others custom.",
    r"\b(social|management|posts|growth|strategy)\b": "Social Media Mgmt: 5000/month (3 posts/day).",
    r"\b(price|pricing|cost|rate)\b": "Quick rates: Web (4k–15k), Video (500–10k+), Logo (600–1500+), SMM (5k/m).",
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


# ---------------- UI (Reply Keyboard) ----------------
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

# ---------------- States ----------------
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


# ---------------- Helpers ----------------
def _bytes_to_data_uri(data: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Hey! 👋 Main **MetaBull Universe** ka assistant hoon.\n\n"
        "Neeche buttons se choose karein:\n"
        "• ❓ Q/A — Keyword intents + Gemini (KB-grounded)\n"
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


# ----- Q/A (Keyword intents → Gemini+KB → minimal KB fallback) -----
async def qa_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Q/A mode ON — apna sawal bhejein (Hinglish). Pehle keywords detect honge; warna Gemini + KB se answer milega.\n"
        "Eg: “website price?”, “UGC video rate?”, “logo 3D price?”, “office location?”"
    )
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Q/A selected", "Awaiting question")
    return STATE_QA


async def qa_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text or ""

    # 1) Keyword-intent first (multiple synonyms → one answer)
    intent_ans = detect_intent(q)
    if intent_ans:
        ans_main = intent_ans
    else:
        # 2) Gemini grounded by KB
        if GEMINI_READY:
            ans_main = await gemini_answer_with_kb(q, KB_RAW)
        else:
            # 3) Minimal KB-map fallback (last resort)
            kb_ans = kb_lookup(q)
            ans_main = (
                kb_ans
                if kb_ans
                else (
                    "Mujhe clear keyword nahi mila. Better AI answers ke liye GEMINI_API_KEY add karen."
                )
            )

    suggestions_line = "Suggestions: " + " | ".join(SUGGESTED_QUESTIONS[:3])
    final_ans = f"{ans_main}\n\n{suggestions_line}"

    await update.message.reply_text(final_ans, reply_markup=qa_footer_buttons())
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, q, final_ans)
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
    else:
        txt = "Sales: +91 8982285510"
    await query.edit_message_reply_markup(reply_markup=qa_footer_buttons())
    await query.message.reply_text(txt)
    user = f"{query.from_user.full_name} (@{query.from_user.username})"
    log_to_google(user, f"[QA footer] {key}", txt)


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
    app.add_handler(CallbackQueryHandler(qa_callbacks))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

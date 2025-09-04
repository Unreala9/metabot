# bot.py
# Metabull Universe Telegram Bot (env-based, auto-cancel flow switching + Gemini fallback + inline-logo HTML)
# Python 3.10+ | python-telegram-bot==20.7

import asyncio
import base64
import json
import mimetypes
import os
import re
import textwrap
import time
from io import BytesIO
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv

load_dotenv()

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

COMPANY_CHANNEL_URL = os.getenv("COMPANY_CHANNEL_URL", "").strip()
UPI_ID = os.getenv("UPI_ID", "").strip()
UPI_NAME = os.getenv("UPI_NAME", "Metabull Universe").strip()

SOCIAL_TELEGRAM = os.getenv("SOCIAL_TELEGRAM", "")
SOCIAL_INSTAGRAM = os.getenv("SOCIAL_INSTAGRAM", "")
SOCIAL_GOOGLE = os.getenv("SOCIAL_GOOGLE", "")
SOCIAL_LINKEDIN = os.getenv("SOCIAL_LINKEDIN", "")
SOCIAL_WHATSAPP = os.getenv("SOCIAL_WHATSAPP", "")
SOCIAL_DISCORD = os.getenv("SOCIAL_DISCORD", "")  # optional

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()  # full URL or plain id
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

# Gemini fallback
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro").strip()

# Meta Pixel (optional for LP)
META_PIXEL_ID = os.getenv("META_PIXEL_ID", "").strip()

# ---------------- OPTIONAL: Google Sheets logging ----------------
USE_SHEETS = False
try:
    if GSHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON:
        import gspread
        from google.oauth2.service_account import Credentials

        sa_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
        gc = gspread.authorize(creds)

        if "/spreadsheets/d/" in GSHEET_ID:
            GSHEET_ID_EXTRACTED = GSHEET_ID.split("/spreadsheets/d/")[1].split("/")[0]
        else:
            GSHEET_ID_EXTRACTED = GSHEET_ID

        sh = gc.open_by_key(GSHEET_ID_EXTRACTED)

        def get_or_create(ws_title, header):
            try:
                ws = sh.worksheet(ws_title)
            except Exception:
                ws = sh.add_worksheet(title=ws_title, rows=1000, cols=20)
                ws.append_row(header)
            return ws

        SHEET_POSTS = get_or_create(
            "posts",
            ["ts", "user_id", "caption", "urls", "phones", "emails", "image_path"],
        )
        SHEET_LP = get_or_create(
            "landing_pages",
            ["ts", "user_id", "name", "sub", "desc", "color", "logo_path"],
        )
        SHEET_QUERIES = get_or_create("queries", ["ts", "user_id", "question", "topic"])
        USE_SHEETS = True
except Exception:
    USE_SHEETS = False

# ---------------- COMPANY STATIC DATA ----------------
COMPANY = {
    "name": "Metabull Universe",
    "type": "Corporate Service Provider (Creative + IT + Marketing)",
    "founded_years": "5 years ago",
    "founder": "Neeraj Soni",
    "hq": "MP nagar. zone-2 ,Bhopal, Madhya Pradesh (Near Rani Kamlapati Station, Maharana Pratap Nagar)",
    "email": "metabull2@gmail.com",
    "phone": "+91 8982285510",
    "employees": "20+",
    "active_clients": "100+ per month",
    "gmap_url": "https://maps.google.com/?q=Metabull+Universe,+MP+Nagar+Zone+2+Bhopal",
}

SERVICES = [
    "Advertisement Services (ADS)",
    "Video Editing: Ads, Social Media, Application Ads, AI Videos, UGC Videos",
    "Graphic Designing: Logos, Branding, Custom Design",
    "Web Development: Static, Dynamic, Fully Functional Websites",
    "Account Handling: Business account handling",
    "Social Media Management: Posts, Growth, Strategy",
]

PRICING = {
    "Video Editing": [
        "AI video: ₹600 – ₹700",
        "High-quality AI: ₹1000 – ₹1200",
        "AI model video: ₹1500 – ₹2000",
        "UGC video: ₹2500 – ₹3000",
        "Whiteboard animation: ₹1000 – ₹1500",
        "Editing: 1 min ₹500, bulk project ₹2000 – ₹2500",
        "Spokesperson video: ₹5000 – ₹10,000+",
        "Social media: 5 min ₹1000, 10 min ₹2000, 15+ min ₹2500",
        "Application ad: 1 min ₹800",
    ],
    "Web Development": [
        "Static website: ₹4000 (single page with free domain)",
        "Dynamic website: ₹7000 (multi-page with free domain)",
        "Fully functional aesthetic website: ₹8000 – ₹15,000 (multi-page + Payment Gateway + Database)",
    ],
    "Graphic Designing": [
        "Logo: ₹600 (2D logo ₹800 – ₹1000, 3D logo ₹1500+)",
        "Other designs: Custom as per requirements",
    ],
    "Ads": ["Multi-platform Ads: depends on your budget & needs"],
    "Social Media Management": ["Single account: ₹5000 / month (3 posts/day)"],
}

DEMO_LINKS = {
    "Websites": [
        ("Agency Site Demo", "https://example.com/demo/website-1"),
        ("Portfolio Demo", "https://example.com/demo/website-2"),
    ],
    "Videos (Drive)": [
        ("Ad Reels", "https://drive.google.com/"),
        ("Explainers", "https://drive.google.com/"),
    ],
    "Ads": [
        ("Meta Ads Showcase", "https://example.com/ads/meta"),
        ("Google Ads Showcase", "https://example.com/ads/google"),
    ],
}

SOCIALS = {
    "Telegram": SOCIAL_TELEGRAM or "https://t.me/metabulluniverse",
    "Instagram": SOCIAL_INSTAGRAM or "https://www.instagram.com/metabulluniverse/",
    "Google": SOCIAL_GOOGLE or "https://www.google.com/search?q=metabull+universe",
    "LinkedIn": SOCIAL_LINKEDIN or "https://www.linkedin.com/company/metabulluniverse/",
    "WhatsApp": SOCIAL_WHATSAPP or "https://wa.me/918982285510",
    "Discord": SOCIAL_DISCORD or "https://discord.gg/",
}

# ---------------- MENUS ----------------
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🔄 Start"), KeyboardButton("🖼️ Create a Post")],
        [
            KeyboardButton("🧱 Create a Landing Page"),
            KeyboardButton("🎬 Service Demos"),
        ],
        [KeyboardButton("💼 Pricing"), KeyboardButton("📣 Follow Us")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)


def quick_actions_markup() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧰 Services", callback_data="QA_SERVICES"),
            InlineKeyboardButton("💰 Pricing", callback_data="QA_PRICING"),
        ],
        [
            InlineKeyboardButton("📍 Location", callback_data="QA_LOCATION"),
            InlineKeyboardButton("✉️ Contact", callback_data="QA_CONTACT"),
        ],
        [InlineKeyboardButton("📞 Call Sales (WhatsApp)", url=SOCIALS["WhatsApp"])],
    ]
    if COMPANY_CHANNEL_URL:
        rows.append(
            [InlineKeyboardButton("📣 Join Our Channel", url=COMPANY_CHANNEL_URL)]
        )
    return InlineKeyboardMarkup(rows)


def suggestion_markup(labels: List[str], topic_key: str) -> InlineKeyboardMarkup:
    # compact callback tokens -> reliable
    rows = [
        [InlineKeyboardButton(f"❓ {label}", callback_data=f"SG::{topic_key}")]
        for label in labels[:6]
    ]
    return InlineKeyboardMarkup(rows)


# ---------------- Local persistence ----------------
USER_DATA_FILE = "user_data.json"


def load_user_data() -> Dict:
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_user_data(data: Dict):
    try:
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------- Helpers ----------------
def list_to_bullets(items: List[str]) -> str:
    return "\n".join([f"• {i}" for i in items])


def pricing_to_text() -> str:
    parts = []
    for k, v in PRICING.items():
        parts.append(f"<b>{k}</b>\n" + "\n".join([f"• {line}" for line in v]))
    return "\n\n".join(parts)


def safe_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_followups_for_topic(topic: str) -> List[str]:
    topic = (topic or "").lower()
    if topic in {"web", "website", "webdev"}:
        return [
            "Static vs Dynamic website?",
            "Do you include domain & hosting?",
            "Timeline for 5-page site?",
            "Tech stack options?",
            "Can you integrate payments?",
        ]
    if topic in {"video", "editing", "ugc"}:
        return [
            "What’s your bulk discount?",
            "UGC sample turnaround time?",
            "Do you provide scripts/voiceover?",
            "Can you edit reels for Instagram?",
            "Do you do whiteboard videos?",
        ]
    if topic in {"graphic", "logo", "branding"}:
        return [
            "Logo + Brand Kit bundle price?",
            "How many revisions included?",
            "Do you deliver source files?",
            "Turnaround for a logo?",
            "3D logo options?",
        ]
    if topic in {"ads", "advertisement"}:
        return [
            "What ad platforms do you use?",
            "How do you report performance?",
            "Creative + Media plan bundle?",
            "What’s the minimum budget?",
            "Case studies available?",
        ]
    if topic in {"smm", "social", "management"}:
        return [
            "Number of posts per month?",
            "Content calendar sample?",
            "Do you shoot photos/videos?",
            "Growth strategy example?",
            "What’s the onboarding?",
        ]
    return [
        "Can you share a portfolio?",
        "What’s the onboarding process?",
        "Any discounts on bundles?",
        "How soon can we start?",
    ]


KEYWORDS = {
    "services": ["service", "services", "offer", "provide"],
    "pricing": ["price", "pricing", "cost", "rate", "charges", "package", "packages"],
    "location": ["location", "address", "bhopal", "mp nagar", "headquarter", "hq"],
    "contact": ["contact", "email", "phone", "call", "reach"],
    "web": ["web", "website", "development", "frontend", "backend", "payment"],
    "video": ["video", "edit", "editing", "ugc", "whiteboard", "spokesperson"],
    "graphic": ["graphic", "logo", "branding", "design"],
    "ads": ["ads", "advertisement", "campaign", "media"],
    "smm": ["social", "instagram", "facebook", "management", "smm"],
    "founder": ["founder", "ceo", "neeraj"],
    "clients": ["clients", "active clients", "portfolio"],
    "employees": ["employee", "employees", "team", "staff"],
    "timeline": ["timeline", "deliver", "how long", "turnaround"],
}


def classify(text: str) -> Tuple[str, List[str], int]:
    t = (text or "").lower()
    scores = {k: 0 for k in KEYWORDS}
    for k, words in KEYWORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", t):
                scores[k] += 1
    best = max(scores, key=scores.get)
    max_score = scores[best]
    suggestions = get_followups_for_topic(best)
    return best, suggestions, max_score


def answer_for_class(topic: str) -> str:
    if topic == "services":
        return "<b>Our Services</b>\n" + list_to_bullets(SERVICES).replace("&", "&amp;")
    if topic == "pricing":
        txt = "<b>Pricing Overview</b>\n\n" + pricing_to_text()
        if UPI_ID:
            txt += f"\n\n<b>Pay via UPI:</b> {UPI_NAME} — {UPI_ID}"
        return txt
    if topic == "location":
        return f"<b>Our Location</b>\n{COMPANY['hq']}\n\n<a href=\"{COMPANY['gmap_url']}\">Open in Google Maps</a>"
    if topic == "contact":
        return (
            f"<b>Contact Us</b>\nEmail: {COMPANY['email']}\nPhone: {COMPANY['phone']}"
        )
    if topic == "web":
        return (
            "<b>Web Development</b>\n"
            "• Static, Dynamic, Full-stack websites\n"
            "• Payment Gateway & Database integration\n"
            "• Starter from ₹4000, dynamic from ₹7000, full stack ₹8k–₹15k\n"
            "• Timeline: 7–10 days for small sites"
        )
    if topic == "video":
        return (
            "<b>Video Editing</b>\n"
            "• Ads, Social, UGC, AI videos, Whiteboard, Spokesperson\n"
            "• 1-min edit from ₹500 │ UGC ₹2.5k–₹3k │ AI ₹600–₹1200\n"
            "• Fast turnaround; bulk discounts available"
        )
    if topic == "graphic":
        return (
            "<b>Graphic & Branding</b>\n"
            "• Logos (2D/3D), Brand kit, Custom creatives\n"
            "• Logo from ₹600 (2D ₹800–₹1000, 3D ₹1500+)\n"
            "• Source files & revisions included"
        )
    if topic == "ads":
        return (
            "<b>Ads & Performance</b>\n"
            "• Meta & Google Ads, creative + media planning\n"
            "• Budget-aligned strategy & reporting\n"
            "• Pricing depends on budget & scope"
        )
    if topic == "smm":
        return (
            "<b>Social Media Management</b>\n"
            "• Content, growth & strategy — 3 posts/day\n"
            "• Single account: ₹5000/month\n"
            "• Calendar & analytics included"
        )
    if topic == "founder":
        return f"<b>Founder & CEO</b>\n{COMPANY['founder']}"
    if topic == "clients":
        return f"<b>Active Clients</b>\n{COMPANY['active_clients']}"
    if topic == "employees":
        return f"<b>Team Size</b>\n{COMPANY['employees']}"
    if topic == "timeline":
        return "<b>Delivery Timelines</b>\nLogos: 1 day │ Small websites: 7–10 days │ Larger projects: on scope."
    return (
        "<b>About Metabull Universe</b>\n"
        f"{COMPANY['type']} with {COMPANY['founded_years']} experience. "
        "Ask us about services, pricing, timelines, or demos."
    )


async def send_with_quick_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    suggestions: Optional[List[str]] = None,
    topic_key: Optional[str] = None,
):
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=quick_actions_markup(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    if suggestions and topic_key:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Try asking one of these for a more specific answer:",
            reply_markup=suggestion_markup(suggestions, topic_key),
        )


# ---------------- Global flow control (AUTO-CANCEL) ----------------
def set_flow(context, name: Optional[str]):
    context.user_data["current_flow"] = name


def is_flow(context, name: str) -> bool:
    return context.user_data.get("current_flow") == name


# ---------------- Conversations ----------------
CP_IMAGE, CP_CAPTION, CP_LINKS = range(100, 103)
LP_NAME, LP_LOGO, LP_SUB, LP_DESC, LP_COLOR, LP_NICHE = range(200, 206)


# ========= Landing Page HTML with inline base64 logo =========
def _file_to_data_uri(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            data = f.read()
        mime, _ = mimetypes.guess_type(path)
        if not mime:
            mime = "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


def build_landing_html(
    name: str, sub: str, desc: str, color: str, logo_filename: Optional[str]
) -> bytes:
    """
    Renders a landing page matching the Crypto Bazaar style.
    If logo is provided, it is embedded inline as a base64 data-URI -> single .html file works everywhere.
    """
    brand = safe_html(name or "Your Brand")
    subh = safe_html(sub or "Expert insights. Real-time updates.")
    descr = safe_html(
        desc
        or "We share educational content only; not financial advice. Do your own research."
    )

    primary = color if color.startswith("#") else f"#{color}"
    secondary = "#be185d"
    accent = "#0891b2"

    cta_url = COMPANY_CHANNEL_URL or SOCIALS.get("Telegram", "#")

    # Optional Meta Pixel
    meta_pixel = ""
    if META_PIXEL_ID:
        meta_pixel = f"""
<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '{META_PIXEL_ID}');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={META_PIXEL_ID}&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->
"""

    # Inline logo (if any)
    logo_img_tag = ""
    favicon_href = ""
    og_image = ""
    if logo_filename:
        data_uri = _file_to_data_uri(logo_filename)
        if data_uri:
            logo_img_tag = (
                f'<img src="{data_uri}" alt="Brand Logo" '
                'class="w-4/5 max-w-[400px] md:max-w-[300px] rounded-xl mx-auto mb-5 mt-8 '
                'shadow-[0_10px_30px_rgba(225,29,72,0.3)] opacity-0 animate-[zoomIn_1s_ease_forwards] [animation-delay:1s]" />'
            )
            favicon_href = f'<link rel="icon" href="{data_uri}" type="image/png" />'
            og_image = f'<meta property="og:image" content="{data_uri}" />'

    html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1.0" />
    <title>{brand} | Expert Insights</title>

    <meta name="description" content="{subh}"/>
    <meta name="keywords" content="{brand}, Trading, Tips, Crypto, Forex, Market Analysis, Investing, Nifty, BankNifty"/>
    <meta name="author" content="{brand}" />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="{cta_url}" />

    <meta property="og:title" content="{brand} - Expert Market Insights" />
    <meta property="og:description" content="{subh}"/>
    {og_image}
    <meta property="og:url" content="{cta_url}" />
    <meta property="og:type" content="website" />

    {favicon_href}

    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {{
        theme: {{
          extend: {{
            colors: {{
              primary: "{primary}",
              secondary: "{secondary}",
              accent: "{accent}",
              light: "#f0f3f4",
            }},
            fontFamily: {{
              sans: ['"Segoe UI"', "Tahoma", "Geneva", "Verdana", "sans-serif"],
            }},
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
    {meta_pixel}
  </head>
  <body class="bg-[radial-gradient(circle_at_center,_#1f2937,_#111827,_#000000)] text-light font-sans overflow-x-hidden min-h-screen flex justify-center items-start animate-[fadeInBody_0.6s_ease-in]">
    <div class="w-full max-w-7xl p-4 animate-[fadeInUp_1s_ease_forwards]">
      <section class="text-center p-2 opacity-0 animate-[fadeInUp_1s_ease_forwards] [animation-delay:0.8s]">
        {logo_img_tag}
        <h2 class="text-3xl md:text-3xl mb-4 font-bold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent opacity-0 animate-[fadeInUp_1s_ease_forwards] [animation-delay:1.2s]">
          {brand}
        </h2>

        <p class="md:text-lg text-xl leading-relaxed max-w-[680px] mx-auto mb-6 opacity-0 animate-[fadeInUp_1s_ease_forwards] [animation-delay:1.4s]">
          {subh}<br/>{descr}
        </p>

        <a href="{cta_url}" target="_blank"
           class="relative bg-gradient-to-r from-primary to-accent text-white py-4 px-8 rounded-full font-bold text-lg transition-all duration-300 ease-in-out inline-block opacity-0 animate-[zoomIn_1s_ease_forwards] [animation-delay:1.6s] hover:-translate-y-1 shadow-[0_8px_20px_rgba(0,0,0,0.4),_0_0_20px_rgba(225,29,72,0.4)] hover:shadow-[0_12px_30px_rgba(0,0,0,0.5),_0_0_30px_rgba(225,29,72,0.6)] hover:scale-105"
           onclick="window.fbq && fbq('trackCustom','JoinTelegramClick')">
          <i class="fab fa-telegram mr-3 text-xl"></i>
          <span class="relative z-10">Join Telegram Channel</span>
          <span class="absolute inset-0 animate-pulse bg-white opacity-20 rounded-full"></span>
        </a>

        <p class="text-[12px] leading-relaxed max-w-[700px] mx-auto mt-8 opacity-0 animate-[fadeInUp_1s_ease_forwards] [animation-delay:1.8s]">
          <strong>Disclaimer:</strong>
          This channel/page shares content for informational and educational purposes only — this is not financial or investment advice.
          Trading (stocks/crypto/forex) carries high risk; always do your own research and consult a professional before investing.
          The channel and admins are not responsible for any losses.
        </p>
      </section>
    </div>
  </body>
</html>"""
    return html.encode("utf-8")


def gen_desc_from_niche(niche: str) -> str:
    niche = (niche or "").strip() or "your business"
    return (
        f"We help {niche} grow with a blend of creativity, technology and marketing. "
        f"From high-converting websites to performance ads and consistent content, "
        f"{COMPANY['name']} crafts everything end-to-end. Book a free consultation today."
    )


# ---------------- Gemini Fallback ----------------
_gemini_ready = False
try:
    if GEMINI_API_KEY:
        import google.generativeai as genai  # pip install google-generativeai

        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_ready = True
except Exception:
    _gemini_ready = False


def _read_file(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


async def gemini_answer(query: str) -> Optional[str]:
    if not _gemini_ready:
        return None
    kb = _read_file("knowledgebase.txt")
    cmds = _read_file("llm_commands.txt")

    system_prompt = textwrap.dedent(
        f"""
    You are Metabull Universe assistant. Answer crisply in Hinglish (English+Hindi).
    Use the given Knowledge Base and Commands if relevant. If something isn't in KB,
    give best helpful answer without fabricating company facts.

    === KNOWLEDGE BASE (optional) ===
    {kb if kb else "[empty]"}

    === COMMANDS (optional) ===
    {cmds if cmds else "[empty]"}

    Company quick facts:
    Name: {COMPANY['name']}; Type: {COMPANY['type']}; Email: {COMPANY['email']}; Phone: {COMPANY['phone']}; HQ: {COMPANY['hq']}.
    """
    )

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp = await asyncio.to_thread(
            model.generate_content,
            [
                {"role": "user", "parts": [system_prompt]},
                {"role": "user", "parts": [query]},
            ],
        )
        text = getattr(resp, "text", "") or ""
        return text.strip() or None
    except Exception:
        return None


# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    context.user_data.setdefault("history", [])
    context.user_data["last_action"] = "start"
    welcome = (
        f"👋 Hi {update.effective_user.first_name or 'there'}!\n"
        f"<b>{COMPANY['name']}</b> — {COMPANY['type']}\n\n"
        "Ask me anything or use the menu below.\n"
        "I’ll show quick actions under every answer 😊"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU,
    )


async def show_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    await send_with_quick_actions(
        update,
        context,
        "<b>Pricing Overview</b>\n\n" + pricing_to_text(),
        suggestions=[
            "Do you offer bundles?",
            "Any bulk discount?",
            "Timeline for delivery?",
        ],
        topic_key="pricing",
    )


async def show_follow_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    rows = []
    if SOCIALS.get("Telegram"):
        rows.append([InlineKeyboardButton("📢 Telegram", url=SOCIALS["Telegram"])])
    if SOCIALS.get("Instagram"):
        rows.append([InlineKeyboardButton("📸 Instagram", url=SOCIALS["Instagram"])])
    if SOCIALS.get("Google"):
        rows.append([InlineKeyboardButton("🟡 Google", url=SOCIALS["Google"])])
    if SOCIALS.get("LinkedIn"):
        rows.append([InlineKeyboardButton("💼 LinkedIn", url=SOCIALS["LinkedIn"])])
    if SOCIALS.get("WhatsApp"):
        rows.append([InlineKeyboardButton("🟢 WhatsApp", url=SOCIALS["WhatsApp"])])
    if SOCIALS.get("Discord"):
        rows.append([InlineKeyboardButton("🟣 Discord", url=SOCIALS["Discord"])])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="<b>Follow Us</b> — stay connected 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def show_service_demos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    lines = ["<b>Service Demos</b>"]
    buttons = []
    for cat, items in DEMO_LINKS.items():
        lines.append(f"\n<b>{cat}</b>")
        for label, url in items:
            lines.append(f"• {label}")
            buttons.append([InlineKeyboardButton(f"🔗 {label}", url=url)])
    if COMPANY_CHANNEL_URL:
        buttons.append(
            [InlineKeyboardButton("📣 Join Our Channel", url=COMPANY_CHANNEL_URL)]
        )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )


# ---- Create Post ----
async def create_post_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, "cp")
    context.user_data["create_post"] = {}
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🖼️ <b>Create a Post</b>\nSend me an <b>image</b> to use, or type /skip to continue without an image.\n\n(At any time, ask a normal question and I’ll switch to Q&A.)",
        parse_mode=ParseMode.HTML,
    )
    return CP_IMAGE


async def cp_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "cp"):
        return ConversationHandler.END
    if update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
        file = await context.bot.get_file(file_id)
        os.makedirs("uploads", exist_ok=True)
        filename = f"uploads/post_{update.effective_user.id}_{int(time.time())}.jpg"
        await file.download_to_drive(filename)
        context.user_data["create_post"]["image_path"] = filename
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Image saved. Now send a <b>caption</b> for the post.",
            parse_mode=ParseMode.HTML,
        )
        return CP_CAPTION
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send an image, or type /skip to proceed without an image.",
    )
    return CP_IMAGE


async def cp_skip_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "cp"):
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Okay, no image. Send a <b>caption</b> for the post.",
        parse_mode=ParseMode.HTML,
    )
    return CP_CAPTION


async def cp_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "cp"):
        return ConversationHandler.END
    caption = update.message.text or ""
    context.user_data["create_post"]["caption"] = caption.strip()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "Great! Now send any <b>links / phone / emails</b> to attach as buttons.\n"
            "Examples:\n• https://yourwebsite.com\n• +91 9876543210\n• you@example.com\n\nYou can send multiple in one message."
        ),
        parse_mode=ParseMode.HTML,
    )
    return CP_LINKS


def extract_links(text: str) -> Tuple[List[str], List[str], List[str]]:
    urls = re.findall(r"(https?://[^\s]+)", text)
    phones = re.findall(r"(\+?\d[\d\s\-]{7,}\d)", text)
    emails = re.findall(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})", text)
    phones = [re.sub(r"[\s\-]", "", p) for p in phones]
    return urls, phones, emails


async def cp_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "cp"):
        return ConversationHandler.END
    text = update.message.text or ""
    urls, phones, emails = extract_links(text)
    context.user_data["create_post"]["links"] = {
        "urls": urls,
        "phones": phones,
        "emails": emails,
    }

    buttons = []
    for u in urls:
        buttons.append([InlineKeyboardButton("🌐 Website", url=u)])
    for p in phones:
        buttons.append(
            [InlineKeyboardButton("📞 Call", url=f"https://wa.me/{p.lstrip('+')}")]
        )
    for e in emails:
        buttons.append([InlineKeyboardButton("✉️ Email", url=f"mailto:{e}")])

    cap = context.user_data["create_post"].get("caption", "")
    image_path = context.user_data["create_post"].get("image_path")

    if image_path:
        with open(image_path, "rb") as f:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=f,
                caption=cap,
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=cap or "Your post is ready.",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )

    # Persist + Sheets
    all_users = load_user_data()
    uid = str(update.effective_user.id)
    all_users.setdefault(uid, {"posts": [], "landing_pages": [], "queries": []})
    all_users[uid]["posts"].append(context.user_data["create_post"])
    save_user_data(all_users)
    if USE_SHEETS:
        try:
            SHEET_POSTS.append_row(
                [
                    int(time.time()),
                    uid,
                    cap,
                    ", ".join(urls),
                    ", ".join(phones),
                    ", ".join(emails),
                    image_path or "",
                ],
                value_input_option="USER_ENTERED",
            )
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="✅ Post created! You can forward this."
    )
    set_flow(context, None)
    return ConversationHandler.END


async def cp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="Create Post cancelled."
    )
    return ConversationHandler.END


# ---- Create Landing Page ----
async def create_landing_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, "lp")
    context.user_data["lp"] = {}
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🧱 <b>Create a Landing Page</b>\nSend the <b>Landing Page Name</b> (Brand/Title).\n\n(At any time, ask a normal question and I’ll switch to Q&A.)",
        parse_mode=ParseMode.HTML,
    )
    return LP_NAME


async def _save_image_from_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[str]:
    """Supports both photo and image document."""
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and (
        update.message.document.mime_type or ""
    ).startswith("image/"):
        file_id = update.message.document.file_id
    else:
        return None

    tg_file = await context.bot.get_file(file_id)
    os.makedirs("uploads", exist_ok=True)
    # keep original extension if possible
    ext = ""
    if update.message.document and update.message.document.file_name:
        _, ext = os.path.splitext(update.message.document.file_name)
    if not ext:
        ext = ".png"
    filename = f"uploads/logo_{update.effective_user.id}_{int(time.time())}{ext}"
    await tg_file.download_to_drive(filename)
    return filename


async def lp_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    context.user_data["lp"]["name"] = update.message.text.strip()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Upload a <b>logo/image</b> (PNG/JPG) as Photo or Document, or type /skip to continue without logo.",
        parse_mode=ParseMode.HTML,
    )
    return LP_LOGO


async def lp_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    saved = await _save_image_from_message(update, context)
    if saved:
        context.user_data["lp"]["logo_path"] = saved
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Logo saved. Now send a <b>Sub-heading</b>.",
            parse_mode=ParseMode.HTML,
        )
        return LP_SUB
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="Please upload an image or type /skip."
    )
    return LP_LOGO


async def lp_skip_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="No logo selected. Send a <b>Sub-heading</b>.",
        parse_mode=ParseMode.HTML,
    )
    return LP_SUB


async def lp_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    context.user_data["lp"]["sub"] = update.message.text.strip()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Send a <b>Description</b> (or type /skip and I’ll generate a short one based on your niche later).",
        parse_mode=ParseMode.HTML,
    )
    return LP_DESC


async def lp_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    context.user_data["lp"]["desc"] = update.message.text.strip()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Send a <b>Primary Color</b> (hex like #4300FF) for the theme.",
        parse_mode=ParseMode.HTML,
    )
    return LP_COLOR


async def lp_skip_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    context.user_data["lp"]["desc"] = ""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Okay. Send a <b>Primary Color</b> (hex like #4300FF) for the theme.",
        parse_mode=ParseMode.HTML,
    )
    return LP_COLOR


async def lp_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    color = update.message.text.strip()
    if not re.match(r"^#?[0-9a-fA-F]{6}$", color):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please send a valid hex color, e.g., #4300FF",
        )
        return LP_COLOR
    if not color.startswith("#"):
        color = "#" + color
    context.user_data["lp"]["color"] = color
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="What’s your <b>niche</b>? (e.g., stock market channel, salon, e-commerce, etc.)",
        parse_mode=ParseMode.HTML,
    )
    return LP_NICHE


async def lp_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_flow(context, "lp"):
        return ConversationHandler.END
    niche = update.message.text.strip()
    lp = context.user_data["lp"]
    if not lp.get("desc"):
        lp["desc"] = gen_desc_from_niche(niche)

    html_bytes = build_landing_html(
        lp["name"], lp["sub"], lp["desc"], lp["color"], lp.get("logo_path")
    )

    # ALWAYS send single HTML (logo inline) -> no zip needed
    buf = BytesIO(html_bytes)
    buf.seek(0)
    safe_name = re.sub(r"\W+", "_", lp["name"])
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=InputFile(buf, filename=f"landing_{safe_name}.html"),
        caption="✅ Your landing page HTML is ready.",
    )

    # Persist + Sheets
    all_users = load_user_data()
    uid = str(update.effective_user.id)
    all_users.setdefault(uid, {"posts": [], "landing_pages": [], "queries": []})
    all_users[uid]["landing_pages"].append(lp)
    save_user_data(all_users)

    if USE_SHEETS:
        try:
            SHEET_LP.append_row(
                [
                    int(time.time()),
                    uid,
                    lp.get("name", ""),
                    lp.get("sub", ""),
                    lp.get("desc", ""),
                    lp.get("color", ""),
                    lp.get("logo_path", ""),
                ],
                value_input_option="USER_ENTERED",
            )
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Need edits? Run 🧱 Create a Landing Page again.",
    )
    set_flow(context, None)
    return ConversationHandler.END


async def lp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="Create Landing Page cancelled."
    )
    return ConversationHandler.END


# ---- CALLBACKS ----
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    q = update.callback_query
    data = q.data or ""
    await q.answer()
    # print("Callback:", data)

    if data.startswith("QA_"):
        key = data[3:]
        mapping = {
            "SERVICES": "services",
            "PRICING": "pricing",
            "LOCATION": "location",
            "CONTACT": "contact",
        }
        topic = mapping.get(key, "services")
        txt = answer_for_class(topic)
        await q.message.reply_text(
            txt, parse_mode=ParseMode.HTML, reply_markup=quick_actions_markup()
        )
        sugg = get_followups_for_topic(topic)
        if sugg:
            await q.message.reply_text(
                "More you can ask:", reply_markup=suggestion_markup(sugg, topic)
            )
        return

    if data.startswith("SG::"):
        topic = data.split("::", 1)[1] or "services"
        ans = answer_for_class(topic)
        await q.message.reply_text(
            ans, parse_mode=ParseMode.HTML, reply_markup=quick_actions_markup()
        )
        sugg = get_followups_for_topic(topic)
        if sugg:
            await q.message.reply_text(
                "More you can ask:", reply_markup=suggestion_markup(sugg, topic)
            )
        return


# ---- GENERIC Q&A ----
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip()

    if msg in {
        "🔄 Start",
        "🖼️ Create a Post",
        "🧱 Create a Landing Page",
        "🎬 Service Demos",
        "💼 Pricing",
        "📣 Follow Us",
    }:
        set_flow(context, None)

    if msg == "🔄 Start":
        return await start(update, context)
    if msg == "🖼️ Create a Post":
        return await create_post_entry(update, context)
    if msg == "🧱 Create a Landing Page":
        return await create_landing_entry(update, context)
    if msg == "🎬 Service Demos":
        return await show_service_demos(update, context)
    if msg == "💼 Pricing":
        return await show_pricing(update, context)
    if msg == "📣 Follow Us":
        return await show_follow_us(update, context)

    set_flow(context, None)

    topic, sugg, max_score = classify(msg)

    if max_score > 0:
        ans = answer_for_class(topic)
        await send_with_quick_actions(
            update, context, ans, suggestions=sugg, topic_key=topic
        )
        # logging
        context.user_data.setdefault("history", []).append(
            {"q": msg, "topic": topic, "ts": time.time()}
        )
        all_users = load_user_data()
        uid = str(update.effective_user.id)
        all_users.setdefault(uid, {"posts": [], "landing_pages": [], "queries": []})
        all_users[uid]["queries"].append(
            {"q": msg, "topic": topic, "ts": int(time.time())}
        )
        save_user_data(all_users)
        if USE_SHEETS:
            try:
                SHEET_QUERIES.append_row(
                    [int(time.time()), uid, msg, topic],
                    value_input_option="USER_ENTERED",
                )
            except Exception:
                pass
        return

    gem_text = await gemini_answer(msg)
    if not gem_text:
        gem_text = (
            "Got it! 🙂 Filhaal mere paas is sawaal ka exact company-topic match nahi mila.\n"
            "Aap thoda detail me batao ya specific service pucho (Web Dev, Video Editing, Ads, etc.)."
        )
    await send_with_quick_actions(
        update,
        context,
        safe_html(gem_text),
        suggestions=get_followups_for_topic("services"),
        topic_key="services",
    )

    # logging
    context.user_data.setdefault("history", []).append(
        {"q": msg, "topic": "gemini", "ts": time.time()}
    )
    all_users = load_user_data()
    uid = str(update.effective_user.id)
    all_users.setdefault(uid, {"posts": [], "landing_pages": [], "queries": []})
    all_users[uid]["queries"].append(
        {"q": msg, "topic": "gemini", "ts": int(time.time())}
    )
    save_user_data(all_users)
    if USE_SHEETS:
        try:
            SHEET_QUERIES.append_row(
                [int(time.time()), uid, msg, "gemini"],
                value_input_option="USER_ENTERED",
            )
        except Exception:
            pass


# ---- Catch-all inside any conversation state -> auto-cancel & forward to Q&A ----
async def cancel_and_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_flow(context, None)
    await on_text(update, context)
    return ConversationHandler.END


# ---- Bootstrap ----
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing. Put it in your .env.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))

    # Create Post convo
    cp_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🖼️ Create a Post$"), create_post_entry)
        ],
        states={
            CP_IMAGE: [
                MessageHandler(filters.PHOTO, cp_image),
                CommandHandler("skip", cp_skip_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_and_forward),
            ],
            CP_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cp_caption),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            CP_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cp_links),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cp_cancel),
            MessageHandler(filters.ALL, cancel_and_forward),
        ],
        allow_reentry=True,
    )
    app.add_handler(cp_conv)

    # Landing Page convo
    lp_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🧱 Create a Landing Page$"), create_landing_entry
            )
        ],
        states={
            LP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_name),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            LP_LOGO: [
                MessageHandler((filters.PHOTO | filters.Document.IMAGE), lp_logo),
                CommandHandler("skip", lp_skip_logo),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            LP_SUB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_sub),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            LP_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_desc),
                CommandHandler("skip", lp_skip_desc),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            LP_COLOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_color),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
            LP_NICHE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_niche),
                MessageHandler(filters.ALL, cancel_and_forward),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lp_cancel),
            MessageHandler(filters.ALL, cancel_and_forward),
        ],
        allow_reentry=True,
    )
    app.add_handler(lp_conv)

    # Direct menu fallbacks
    app.add_handler(
        MessageHandler(filters.Regex("^🎬 Service Demos$"), show_service_demos)
    )
    app.add_handler(MessageHandler(filters.Regex("^💼 Pricing$"), show_pricing))
    app.add_handler(MessageHandler(filters.Regex("^📣 Follow Us$"), show_follow_us))

    # Generic text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("✅ Metabull Universe bot is running...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()

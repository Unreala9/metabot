# bot.py — Metabull Universe Telegram Bot (v3.4)
# - Q&A + suggestions
# - Footer quick actions
# - Menu: Start / Create a Post / Create a Landing Page (₹1200 UPI) / Service Demos / Join Channel / Follow Us
# - DEMOS buttons always work (inside/outside conversations)
# - DEMOS replies are PLAIN TEXT (prevents Markdown parse errors on links)
# - Landing Page flow: robust payment + “I’ve paid” -> delivers landing_page.html
# - Google Sheets logging
# - Jump-to-menu inside conversations
# - Windows-safe runner: uses blocking run_polling()/run_webhook() (no asyncio.run)

import os, io, re, json, base64, datetime, logging, sys, asyncio
from textwrap import dedent
from typing import Dict, List, Tuple
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

# Windows event-loop fix
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("metabull-bot")

# ------- Google Sheets -------
import gspread
from google.oauth2.service_account import Credentials

# ------- Images / QR -------
from PIL import Image
import qrcode

# ------- Telegram -------
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ========================= ENV =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_URL = os.getenv("COMPANY_CHANNEL_URL", "https://t.me/metabulluniverse")
UPI_ID = os.getenv("UPI_ID", "you@upi")
UPI_NAME = os.getenv("UPI_NAME", "Metabull Universe")

# Optional webhook mode (Railway)
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # e.g. https://<railway-domain>/webhook

SOCIAL = {
    "telegram": os.getenv("SOCIAL_TELEGRAM", CHANNEL_URL),
    "instagram": os.getenv(
        "SOCIAL_INSTAGRAM", "https://instagram.com/metabulluniverse"
    ),
    "google": os.getenv("SOCIAL_GOOGLE", "https://g.co/kgs/xxxx"),
    "linkedin": os.getenv(
        "SOCIAL_LINKEDIN", "https://linkedin.com/company/metabulluniverse"
    ),
    "whatsapp": os.getenv("SOCIAL_WHATSAPP", "https://wa.me/918982285510"),
    "discord": os.getenv("SOCIAL_DISCORD", "https://discord.gg/xxxxxxx"),
}

GSHEET_ID = os.getenv("GSHEET_ID", "")
SERVICE_JSON_RAW = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

VIDEO_DEMOS = [
    "https://drive.google.com/file/d/VIDEO_DEMO_1/view",
    "https://drive.google.com/file/d/VIDEO_DEMO_2/view",
]
WEBSITE_DEMOS = [
    "https://portfolio.metabulluniverse.com",
    "https://metabulluniverse.com",
]
ADS_LINKS = [
    "https://www.instagram.com/p/AD_DEMO_1/",
    "https://www.instagram.com/p/AD_DEMO_2/",
]

LP_PRICE = 1200  # INR

# ====================== Sheets =========================
_sheets_client = None
_worksheet = None


def _init_sheets():
    global _sheets_client, _worksheet
    if not GSHEET_ID or not SERVICE_JSON_RAW:
        return
    try:
        if SERVICE_JSON_RAW.strip().startswith("{"):
            info = json.loads(SERVICE_JSON_RAW)
            creds = Credentials.from_service_account_info(
                info,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
        else:
            creds = Credentials.from_service_account_file(
                SERVICE_JSON_RAW,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
        _sheets_client = gspread.authorize(creds)
        sh = _sheets_client.open_by_key(GSHEET_ID)
        try:
            _worksheet = sh.worksheet("Leads")
        except Exception:
            _worksheet = sh.sheet1
        headers = _worksheet.row_values(1)
        need = [
            "timestamp",
            "user_id",
            "username",
            "first_name",
            "last_name",
            "action",
            "tags",
            "payload",
        ]
        if [h.lower() for h in headers] != need:
            _worksheet.update([need])
        log.info("Sheets ready")
    except Exception as e:
        log.error("Sheets init error: %s", e)


def crm_log(user, action: str, tags: str = "", payload: Dict = None):
    try:
        if _worksheet is None:
            _init_sheets()
        if _worksheet is None:
            return
        ts = datetime.datetime.utcnow().isoformat()
        row = [
            ts,
            str(user.id) if user else "",
            (user.username or "") if user else "",
            (user.first_name or "") if user else "",
            (user.last_name or "") if user else "",
            action,
            tags,
            json.dumps(payload or {}, ensure_ascii=False)[:3000],
        ]
        _worksheet.append_row(row, value_input_option="RAW")
    except Exception as e:
        log.error("Sheets log error: %s", e)


# ======================= KB ===========================
KB = {
    "company": {
        "name": "Metabull Universe",
        "type": "Corporate Service Provider (Creative + IT + Marketing)",
        "founded_years": "5 years ago",
        "founder_ceo": "Neeraj Soni",
        "hq": "MP nagar. zone-2 ,Bhopal, Madhya Pradesh (Near Rani Kamlapati Station, Maharana Pratap Nagar)",
        "email": "metabull2@gmail.com",
        "phone": "+91 8982285510",
        "employees": "20+",
        "active_clients": "100+ per month",
        "achievements": [
            "Fastest Growing Company Award (Bhopal)",
            "No.1 Service Provider Award (MP Government)",
        ],
        "major_clients": ["Facebook", "Google", "Apple", "Amazon", "Microsoft"],
        "targets": ["Startups", "Enterprises", "Individual Professionals"],
    },
    "services": [
        "Advertisement Services (ADS)",
        "Video Editing: Ads, Social Media, Application Ads, UGC Videos",
        "Graphic Designing: Logos, Branding, Custom Design",
        "Web Development: Static, Dynamic, Fully Functional Websites",
        "Account Handling: Business account handling",
        "Social Media Management: Posts, Growth, Strategy",
    ],
    "pricing": {
        "video_editing": {
            "Advertisements": {"30 sec": 500, "60 sec": 1000, "2 min": 2000},
            "Social Media Videos": {"5 min": 1000, "10 min": 2000, "20+ min": 2500},
            "Application Ads": {"1 min": 500},
            "UGC Videos": {"standard": 3000},
        },
        "web_development": {
            "Static Website": "₹4000",
            "Dynamic Normal Website": "₹7000",
            "Fully Functional Aesthetic Website": "₹8000 – ₹15000",
        },
        "graphic_designing": {"Logo Design": "₹2000", "Other Designs": "Custom"},
        "ads": "Depends on client budget & needs",
        "smm": "₹5000/month (single account, 3 posts/day)",
    },
    "why_us": "We blend creativity, technology, and marketing with affordable pricing and 5 years of experience.",
    "industries": ["Technology", "E-commerce", "Education", "Healthcare", "Startups"],
}

# =================== Landing Template =================
LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{{PAGE_TITLE}}</title>
<meta name="description" content="{{META_DESCRIPTION}}"/><meta name="keywords" content="{{META_KEYWORDS}}"/>
<meta name="author" content="{{BRAND_NAME}}"/><meta name="robots" content="index, follow"/>
<link rel="canonical" href="{{CANONICAL_URL}}"/><meta property="og:title" content="{{OG_TITLE}}"/>
<meta property="og:description" content="{{OG_DESCRIPTION}}"/><meta property="og:image" content="{{OG_IMAGE}}"/>
<meta property="og:url" content="{{OG_URL}}"/><meta property="og:type" content="website"/>
<link rel="icon" href="{{FAVICON_URL}}" type="image/jpeg"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{background:linear-gradient(120deg,#e0f2fe 0%,#dbeafe 100%);min-height:100vh;display:flex;justify-content:center;align-items:center}
.whatsapp-btn{transition:.3s}.whatsapp-btn:hover{transform:translateY(-3px);box-shadow:0 10px 25px rgba(30,64,175,.3),0 5px 10px rgba(14,165,233,.2)}
</style></head>
<body class="bg-white text-black font-sans overflow-x-hidden min-h-screen flex justify-center items-start">
<div class="w-full max-w-7xl p-4 mx-auto"><section class="text-center p-2">
<img src="{{LOGO_URL}}" alt="{{BRAND_NAME}} Banner" class="w-4/5 max-w-[300px] rounded-xl mx-auto mb-5"/>
<h2 class="text-3xl font-bold">Unlock Automated Trading Excellence</h2>
<p class="max-w-[600px] mx-auto mb-6">{{SUBHEADING}}</p>
<p class="max-w-[600px] mx-auto mb-6">{{DESCRIPTION}}</p>
<div class="flex justify-center">
  <a href="https://wa.me/{{WHATSAPP_NUMBER}}" class="whatsapp-btn bg-blue-600 text-white py-3 px-6 rounded-full font-bold inline-flex items-center gap-2">
    <i class="fab fa-whatsapp"></i><span>Chat with us on WhatsApp</span>
  </a>
</div>
<p class="text-[12px] max-w-[600px] mx-auto mt-4"><strong>Disclaimer:</strong> {{DISCLAIMER}}</p>
</section></div></body></html>
"""


def render_landing_html(lp: Dict) -> str:
    return (
        LANDING_TEMPLATE.replace(
            "{{PAGE_TITLE}}", f"{lp['name']} | Automated AI-Powered Trading Platform"
        )
        .replace("{{META_DESCRIPTION}}", lp.get("meta_desc", lp.get("desc", "")))
        .replace(
            "{{META_KEYWORDS}}",
            lp.get("meta_keys", "One AI Solutions, Automated Trading, AI"),
        )
        .replace("{{BRAND_NAME}}", lp["name"])
        .replace(
            "{{CANONICAL_URL}}", lp.get("canonical", "https://www.oneaisolutions.com/")
        )
        .replace("{{OG_TITLE}}", lp.get("og_title", lp["name"]))
        .replace("{{OG_DESCRIPTION}}", lp.get("og_desc", lp.get("desc", "")))
        .replace("{{OG_IMAGE}}", lp.get("og_image", lp.get("logo_url", "logo.jpg")))
        .replace("{{OG_URL}}", lp.get("og_url", "https://www.oneaisolutions.com/"))
        .replace("{{FAVICON_URL}}", lp.get("favicon", lp.get("logo_url", "logo.jpg")))
        .replace("{{LOGO_URL}}", lp.get("logo_url", "logo.jpg"))
        .replace(
            "{{SUBHEADING}}",
            lp.get("sub", "Seamless API integration, expert tools, emotion-free risk."),
        )
        .replace(
            "{{DESCRIPTION}}",
            lp.get("desc", "Discover One AI Solutions—AI-powered trading platform."),
        )
        .replace("{{WHATSAPP_NUMBER}}", lp.get("whatsapp", "919009937449"))
        .replace(
            "{{DISCLAIMER}}",
            lp.get("disclaimer", "Educational purpose only. Trading involves risk."),
        )
    )


# ===================== UI Helpers =====================
MENU_REGEX = r"^(🔄 Start|🖼️ Create a Post|🧩 Create a Landing Page|🧪 Service Demos|📢 Join Channel|🌐 Follow Us|❌ Cancel)$"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("🔄 Start"), KeyboardButton("🖼️ Create a Post")],
        [
            KeyboardButton("🧩 Create a Landing Page"),
            KeyboardButton("🧪 Service Demos"),
        ],
        [KeyboardButton("📢 Join Channel"), KeyboardButton("🌐 Follow Us")],
        [KeyboardButton("❌ Cancel")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def footer_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Services", callback_data="FOOTER:services"),
                InlineKeyboardButton("💸 Prices", callback_data="FOOTER:prices"),
            ],
            [
                InlineKeyboardButton("📍 Location", callback_data="FOOTER:location"),
                InlineKeyboardButton("☎️ Contact", callback_data="FOOTER:contact"),
            ],
            [InlineKeyboardButton("📞 Direct Call (Sales)", url="tel:+918982285510")],
        ]
    )


def follow_us_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📣 Telegram", url=SOCIAL["telegram"])],
            [InlineKeyboardButton("📷 Instagram", url=SOCIAL["instagram"])],
            [InlineKeyboardButton("🔎 Google", url=SOCIAL["google"])],
            [InlineKeyboardButton("💼 LinkedIn", url=SOCIAL["linkedin"])],
            [InlineKeyboardButton("💬 WhatsApp", url=SOCIAL["whatsapp"])],
            [InlineKeyboardButton("🌀 Discord", url=SOCIAL["discord"])],
        ]
    )


def suggestions_keyboard(suggestions: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(lbl, callback_data=cb)] for lbl, cb in suggestions]
    rows.extend(footer_inline_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(rows)


def service_demos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎬 Video demos", callback_data="DEMOS:video")],
            [InlineKeyboardButton("🕸️ Website demos", callback_data="DEMOS:web")],
            [InlineKeyboardButton("📣 Ads links", callback_data="DEMOS:ads")],
        ]
    )


# =================== Q&A helpers ======================
def detect_topic(q: str) -> str:
    s = q.lower()
    if any(
        k in s for k in ["price", "pricing", "cost", "rate", "charges", "fees", "kitna"]
    ):
        return "pricing"
    if any(
        k in s for k in ["location", "address", "kahan", "where", "hq", "headquarter"]
    ):
        return "location"
    if any(k in s for k in ["contact", "phone", "email", "call", "number", "reach"]):
        return "contact"
    if any(k in s for k in ["service", "services", "offer", "provide", "kya-kya"]):
        return "services"
    if any(k in s for k in ["founder", "ceo", "company", "about", "overview", "intro"]):
        return "about"
    if any(
        k in s for k in ["award", "achievement", "client", "portfolio", "major clients"]
    ):
        return "cred"
    if any(
        k in s for k in ["industry", "industries", "target", "startup", "enterprise"]
    ):
        return "target"
    if any(k in s for k in ["web", "website"]):
        return "pricing_web"
    if any(k in s for k in ["video", "ugc"]):
        return "pricing_video"
    if any(k in s for k in ["logo", "branding", "graphic"]):
        return "pricing_graphic"
    return "generic"


def answer_for_topic(topic: str) -> Tuple[str, List[Tuple[str, str]]]:
    c = KB["company"]
    p = KB["pricing"]
    if topic == "pricing":
        txt = dedent(
            f"""💸 **Pricing (Summary)**
• Web Dev: Static {p['web_development']['Static Website']}, Dynamic {p['web_development']['Dynamic Normal Website']}, Full {p['web_development']['Fully Functional Aesthetic Website']}
• Video: Ads 30s ₹500 / 60s ₹1000 / 2m ₹2000; Social 5m ₹1000 / 10m ₹2000 / 20m ₹2500; UGC ₹3000; App Ads 1m ₹500
• Graphics: Logo ₹2000 (others custom)
• SMM: {p['smm']}
• Ads: Budget-based"""
        ).strip()
        sug = [
            ("🖥️ Web pricing details", "ASK:pricing:web"),
            ("🎥 Video pricing details", "ASK:pricing:video"),
            ("🎨 Logo/graphics pricing", "ASK:pricing:graphic"),
        ]
        return txt, sug
    if topic == "pricing_web":
        wp = p["web_development"]
        txt = dedent(
            f"""🖥️ **Web Development Pricing**
• Static: {wp['Static Website']}
• Dynamic: {wp['Dynamic Normal Website']}
• Fully Aesthetic: {wp['Fully Functional Aesthetic Website']}
_Final quote features/pages per depend karta hai._"""
        ).strip()
        return txt, [
            ("🚀 Get a web quote", "ASK:contact"),
            ("📚 Website demos", "DEMOS:web"),
            ("📦 All services", "ASK:services"),
        ]
    if topic == "pricing_video":
        vp = p["video_editing"]
        txt = dedent(
            f"""🎥 **Video Editing Pricing**
• Ads: 30s ₹{vp['Advertisements']['30 sec']} / 60s ₹{vp['Advertisements']['60 sec']} / 2m ₹{vp['Advertisements']['2 min']}
• Social: 5m ₹{vp['Social Media Videos']['5 min']} / 10m ₹{vp['Social Media Videos']['10 min']} / 20m+ ₹{vp['Social Media Videos']['20+ min']}
• App Ads: 1m ₹{vp['Application Ads']['1 min']}
• UGC: ₹{vp['UGC Videos']['standard']}"""
        ).strip()
        return txt, [
            ("🎬 Video demos", "DEMOS:video"),
            ("📞 Talk to editor", "ASK:contact"),
            ("📦 All services", "ASK:services"),
        ]
    if topic == "pricing_graphic":
        gp = p["graphic_designing"]
        txt = dedent(
            f"""🎨 **Graphic Designing Pricing**
• Logo: {gp['Logo Design']}
• Other: {gp['Other Designs']}"""
        ).strip()
        return txt, [
            ("🖼️ Ads/portfolio", "DEMOS:ads"),
            ("📞 Discuss brief", "ASK:contact"),
            ("📦 All services", "ASK:services"),
        ]
    if topic == "services":
        s_list = "\n".join([f"• {s}" for s in KB["services"]])
        return f"📦 **Services We Provide**\n{s_list}", [
            ("💸 Pricing", "ASK:pricing"),
            ("📍 Location", "ASK:location"),
            ("☎️ Contact", "ASK:contact"),
        ]
    if topic == "location":
        return f"📍 **Location**\n{c['hq']}", [
            ("🗺️ Open channel", "OPEN:channel"),
            ("☎️ Contact", "ASK:contact"),
            ("💼 Why us?", "ASK:about"),
        ]
    if topic == "contact":
        return f"☎️ **Contact**\nEmail: {c['email']}\nPhone: {c['phone']}", [
            ("📞 Call sales", "CALL:sales"),
            ("💬 WhatsApp", "OPEN:whatsapp"),
            ("📣 Join Telegram", "OPEN:channel"),
        ]
    if topic == "about":
        txt = dedent(
            f"""🏢 **About {c['name']}**
Type: {KB['company']['type']}
Founded: {c['founded_years']}
Founder & CEO: {c['founder_ceo']}
Team: {c['employees']} | Clients: {c['active_clients']}
Why us: {KB['why_us']}"""
        ).strip()
        return txt, [
            ("🏆 Awards/clients", "ASK:cred"),
            ("📦 Services", "ASK:services"),
            ("💸 Pricing", "ASK:pricing"),
        ]
    if topic == "cred":
        ach = "\n".join([f"• {x}" for x in c["achievements"]])
        cli = ", ".join(c["major_clients"])
        return f"🏆 **Achievements**\n{ach}\n\n👥 **Major Clients**\n{cli}", [
            ("🎯 Target clients", "ASK:target"),
            ("📦 Services", "ASK:services"),
            ("💸 Pricing", "ASK:pricing"),
        ]
    if topic == "target":
        t = ", ".join(c["targets"])
        inds = ", ".join(KB["industries"])
        return f"🎯 **We work with**: {t}\n🌐 **Industries**: {inds}", [
            ("📦 Services", "ASK:services"),
            ("☎️ Contact", "ASK:contact"),
            ("🧪 Demos", "DEMOS:web"),
        ]
    txt = "🙏 Thanks! Aap apna question thoda specific karein ya quick options use karein."
    return txt, [
        ("📦 Services", "ASK:services"),
        ("💸 Pricing", "ASK:pricing"),
        ("📍 Location", "ASK:location"),
    ]


# ================== Conversations =====================
CREATE_POST_IMAGE, CREATE_POST_LINK = range(2)
LP_NAME, LP_SUB, LP_DESC, LP_COLOR, LP_LOGO_PROMPT, LP_LOGO_DATA, LP_CONFIRM = range(7)


def upi_uri(amount: int) -> str:
    return f"upi://pay?pa={quote(UPI_ID)}&pn={quote(UPI_NAME)}&am={amount}&cu=INR&tn={quote('Landing Page Design')}"


def make_qr_png_bytes(uri: str) -> bytes:
    img = qrcode.make(uri)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.read()


async def jump_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "🔄 Start":
        await start(update, context)
    elif text == "🖼️ Create a Post":
        await start_post_flow(update, context)
    elif text == "🧩 Create a Landing Page":
        await start_lp_flow(update, context)
    elif text == "🧪 Service Demos":
        await show_demos(update, context)
    elif text == "📢 Join Channel":
        await join_channel(update, context)
    elif text == "🌐 Follow Us":
        await follow_us(update, context)
    elif text == "❌ Cancel":
        await cancel(update, context)
    return ConversationHandler.END


# ---- Create Post ----
async def start_post_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["post"] = {}
    crm_log(update.effective_user, "create_post_start", "post")
    await update.message.reply_text(
        "🖼️ *Create a Post*\nPlease send the *image/photo*.\n(Use any menu key to switch or /cancel.)",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return CREATE_POST_IMAGE


async def receive_post_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo*.", parse_mode="Markdown")
        return CREATE_POST_IMAGE
    file_id = update.message.photo[-1].file_id
    context.user_data["post"]["photo_id"] = file_id
    await update.message.reply_text(
        "Great! Now send the *phone no / website / any link* for CTA.",
        parse_mode="Markdown",
    )
    crm_log(update.effective_user, "create_post_photo", "post", {"file_id": file_id})
    return CREATE_POST_LINK


def normalize_link(link: str) -> Tuple[str, str]:
    s = link.strip()
    if re.fullmatch(r"(\+?\d[\d\s-]{7,15})", s):
        tel = re.sub(r"[^\d+]", "", s)
        return f"tel:{tel}", "📞 Call Now"
    if re.match(r"(?i)mailto:", s) or re.match(r"[^@]+@[^@]+\.[^@]+", s):
        if not s.lower().startswith("mailto:"):
            s = "mailto:" + s
        return s, "✉️ Email Now"
    if not re.match(r"(?i)https?://", s):
        s = "https://" + s
    return s, "🔗 Open Link"


async def receive_post_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text or ""
    url, cta = normalize_link(link)
    context.user_data["post"]["cta_url"] = url
    context.user_data["post"]["cta_label"] = cta
    cap = (
        "🔥 *Metabull Universe — Promotional Post*\n"
        "Grow with Creative + IT + Marketing (Ads • Videos • Graphics • Websites • Social).\n"
        "_Tap the CTA to proceed!_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(cta, url=url)]])
    await update.message.reply_photo(
        photo=context.user_data["post"]["photo_id"],
        caption=cap,
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await update.message.reply_text(
        "Explore more:", reply_markup=footer_inline_keyboard()
    )
    crm_log(update.effective_user, "create_post_done", "post", {"cta_url": url})
    return ConversationHandler.END


# ---- Landing Page ----
async def start_lp_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lp"] = {}
    crm_log(update.effective_user, "lp_start", "landing_page")
    await update.message.reply_text(
        "🧩 *Landing Page Wizard*\nStep 1/6 — Send *Landing Page / Brand Name*.\n(Use any menu key to switch or /cancel.)",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return LP_NAME


async def lp_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lp"]["name"] = update.message.text.strip()
    crm_log(
        update.effective_user,
        "lp_name",
        "landing_page",
        {"name": context.user_data["lp"]["name"]},
    )
    await update.message.reply_text(
        "Step 2/6 — Send *Subheading*.", parse_mode="Markdown"
    )
    return LP_SUB


async def lp_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lp"]["sub"] = update.message.text.strip()
    crm_log(
        update.effective_user,
        "lp_sub",
        "landing_page",
        {"sub": context.user_data["lp"]["sub"]},
    )
    await update.message.reply_text(
        "Step 3/6 — Send *Description* (niche, offer, benefits).", parse_mode="Markdown"
    )
    return LP_DESC


async def lp_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lp"]["desc"] = update.message.text.strip()
    crm_log(update.effective_user, "lp_desc", "landing_page")
    await update.message.reply_text(
        "Step 4/6 — Send *Color Theme* (e.g. dark/blue, light/green).",
        parse_mode="Markdown",
    )
    return LP_COLOR


async def lp_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lp"]["color"] = update.message.text.strip()
    crm_log(
        update.effective_user,
        "lp_color",
        "landing_page",
        {"color": context.user_data["lp"]["color"]},
    )
    await update.message.reply_text(
        "Step 5/6 — Send *Logo*: upload a *photo*, or send a *logo URL*, or type *skip*.",
        parse_mode="Markdown",
    )
    return LP_LOGO_PROMPT


async def lp_logo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if re.match(r"(?i)^\s*skip\s*$", text):
        context.user_data["lp"]["logo_url"] = "logo.jpg"
        return await lp_logo_done(update, context)
    if re.match(r"(?i)^\s*https?://\S+\s*$", text):
        context.user_data["lp"]["logo_url"] = text.strip()
        return await lp_logo_done(update, context)
    await update.message.reply_text(
        "Please upload a *photo*, send a *logo URL*, or type *skip*.",
        parse_mode="Markdown",
    )
    return LP_LOGO_PROMPT


async def lp_logo_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo*.", parse_mode="Markdown")
        return LP_LOGO_DATA
    file = await update.message.photo[-1].get_file()
    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)
    img = Image.open(bio).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    data64 = base64.b64encode(out.getvalue()).decode("ascii")
    context.user_data["lp"]["logo_url"] = f"data:image/jpeg;base64,{data64}"
    return await lp_logo_done(update, context)


async def lp_logo_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lp = context.user_data["lp"]
    preview = dedent(
        f"""✅ *Details captured:*
• Name: {lp['name']}
• Subheading: {lp['sub']}
• Theme: {lp['color']}
• Description: {lp['desc'][:200]}..."""
    ).strip()
    await update.message.reply_text(preview, parse_mode="Markdown")

    uri = upi_uri(LP_PRICE)
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"💳 Pay ₹{LP_PRICE}", url=uri)],
            [InlineKeyboardButton("✅ I've paid", callback_data="LP:PAID")],
            [InlineKeyboardButton("✏️ Edit details", callback_data="LP:EDIT")],
            [InlineKeyboardButton("❌ Cancel", callback_data="LP:CANCEL")],
        ]
    )
    try:
        qr_png = make_qr_png_bytes(uri)
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(qr_png), filename="upi_qr.png"),
            caption=(
                f"🧾 *Payment Required*: ₹{LP_PRICE}\nUPI ID: `{UPI_ID}`\nName: {UPI_NAME}\n"
                "Scan the QR or tap **Pay ₹1200**. After payment, press **I've paid** or send *I've paid*."
            ),
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        log.error("QR error: %s", e)
        await update.message.reply_text(
            (
                f"🧾 *Payment Required*: ₹{LP_PRICE}\nUPI ID: `{UPI_ID}`\nName: {UPI_NAME}\n"
                "Tap *Pay ₹1200* (UPI link) and then press **I've paid** or send *I've paid*."
            ),
            parse_mode="Markdown",
            reply_markup=kb,
        )

    crm_log(update.effective_user, "lp_review", "landing_page", lp)
    return LP_CONFIRM


async def lp_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "LP:CANCEL":
        await q.edit_message_caption(caption="❌ Landing page flow cancelled.")
        crm_log(update.effective_user, "lp_cancel", "landing_page")
        return ConversationHandler.END
    if q.data == "LP:EDIT":
        await q.edit_message_caption(
            caption="✏️ Let's edit — send the *Landing Page Name* again.",
            parse_mode="Markdown",
        )
        crm_log(update.effective_user, "lp_edit_restart", "landing_page")
        context.user_data["lp"] = {}
        return LP_NAME
    if q.data == "LP:PAID":
        await deliver_landing_html(q.message, update, context)
        return ConversationHandler.END


async def lp_manual_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await deliver_landing_html(update.message, update, context)
    return ConversationHandler.END


async def deliver_landing_html(target_msg, update, context):
    lp = context.user_data.get("lp", {})
    if not lp:
        await target_msg.reply_text("Details missing. Please restart the flow.")
        return
    lp.setdefault("whatsapp", "919009937449")
    lp.setdefault(
        "disclaimer",
        "One AI Solutions provides information for educational purposes only. Trading involves risk.",
    )
    html = render_landing_html(lp)
    bio = io.BytesIO(html.encode("utf-8"))
    bio.name = "landing_page.html"
    await target_msg.reply_document(
        document=InputFile(bio, filename="landing_page.html"),
        caption="✅ Payment confirmed (manual). Here's your landing_page.html — deploy anywhere.\nNeed hosting/support? Reply here!",
    )
    await target_msg.reply_text("Explore:", reply_markup=footer_inline_keyboard())
    crm_log(update.effective_user, "lp_paid", "landing_page", lp)


# =================== Demos / Misc =====================
async def show_demos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧪 Service Demos — choose:", reply_markup=service_demos_keyboard()
    )
    crm_log(update.effective_user, "demos_open", "nav")


# PLAIN-TEXT replies to avoid Markdown errors on URLs (fix for Website demos)
async def demos_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    def render_list(title: str, urls: list[str]) -> str:
        if not urls:
            return f"{title}\n(Coming soon)"
        # plain text so no Markdown parsing can fail
        return title + "\n" + "\n".join([f"• {u}" for u in urls])

    if q.data == "DEMOS:video":
        text = render_list("🎬 Video demos:", VIDEO_DEMOS)
        tag = "demos_video"
    elif q.data == "DEMOS:web":
        text = render_list("🕸️ Website demos:", WEBSITE_DEMOS)
        tag = "demos_web"
    elif q.data == "DEMOS:ads":
        text = render_list("📣 Ads links:", ADS_LINKS)
        tag = "demos_ads"
    else:
        text = "Demo option not recognized."
        tag = "demos_unknown"

    # No parse_mode; also disables previews to keep chat clean
    await q.message.reply_text(
        text, disable_web_page_preview=True, reply_markup=footer_inline_keyboard()
    )
    crm_log(update.effective_user, "demos_list", tag)


async def join_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 Join our Telegram channel:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Open Channel", url=CHANNEL_URL)]]
        ),
    )
    crm_log(update.effective_user, "join_channel", "nav", {"url": CHANNEL_URL})


async def follow_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 Follow us:", reply_markup=follow_us_keyboard())
    crm_log(update.effective_user, "follow_us", "nav")


async def footer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data.split(":")[1]
    mapping = {
        "services": "services",
        "prices": "pricing",
        "location": "location",
        "contact": "contact",
    }
    if data in mapping:
        txt, sug = answer_for_topic(mapping[data])
        await q.message.reply_text(
            txt, parse_mode="Markdown", reply_markup=suggestions_keyboard(sug)
        )
        crm_log(update.effective_user, "footer_click", mapping[data])
    else:
        await q.message.reply_text(
            "☎️ Call us at +91 8982285510", reply_markup=footer_inline_keyboard()
        )
        crm_log(update.effective_user, "footer_call", "call")


# ================= Start / Cancel / Generic ===========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = dedent(
        f"""👋 Welcome to *{KB['company']['name']}* — Creative + IT + Marketing.
Ask anything (pricing, services, location, contact, demos), or use the menu below."""
    ).strip()
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        welcome, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )
    crm_log(update.effective_user, "start", "session")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await (update.message or update.callback_query.message).reply_text(
        "❌ Flow cancelled.", reply_markup=main_menu_keyboard()
    )
    crm_log(update.effective_user, "cancel", "flow")
    return ConversationHandler.END


async def generic_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel":
        await cancel(update, context)
        return
    if text == "🔄 Start":
        await start(update, context)
        return
    if text == "🖼️ Create a Post":
        await start_post_flow(update, context)
        return
    if text == "🧩 Create a Landing Page":
        await start_lp_flow(update, context)
        return
    if text == "🧪 Service Demos":
        await show_demos(update, context)
        return
    if text == "📢 Join Channel":
        await join_channel(update, context)
        return
    if text == "🌐 Follow Us":
        await follow_us(update, context)
        return

    topic = detect_topic(text)
    ans, sug = answer_for_topic(topic)
    await update.message.reply_text(
        ans, parse_mode="Markdown", reply_markup=suggestions_keyboard(sug)
    )
    crm_log(update.effective_user, "ask", topic, {"q": text})


# ================== App wiring ========================
def app():
    if not BOT_TOKEN:
        raise SystemExit("Please set BOT_TOKEN")
    _init_sheets()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # DEMOS callbacks (global)
    application.add_handler(
        CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$")
    )

    # commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))

    # Create Post convo
    post_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🖼️ Create a Post$"), start_post_flow)
        ],
        states={
            CREATE_POST_IMAGE: [
                MessageHandler(filters.PHOTO, receive_post_image),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            CREATE_POST_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_post_link),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
        name="create_post",
        persistent=False,
    )
    application.add_handler(post_conv)

    # Landing Page convo
    lp_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🧩 Create a Landing Page$"), start_lp_flow)
        ],
        states={
            LP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_name),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_SUB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_sub),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_desc),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_COLOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lp_color),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_LOGO_PROMPT: [
                MessageHandler(filters.PHOTO, lp_logo_data),
                MessageHandler(filters.Regex(r"(?i)^\s*skip\s*$"), lp_logo_prompt),
                MessageHandler(
                    filters.Regex(r"(?i)^\s*https?://\S+\s*$"), lp_logo_prompt
                ),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_LOGO_DATA: [
                MessageHandler(filters.PHOTO, lp_logo_data),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
            LP_CONFIRM: [
                CallbackQueryHandler(lp_confirm_cb, pattern=r"^LP:(PAID|EDIT|CANCEL)$"),
                MessageHandler(
                    filters.Regex(r"(?i)^\s*(i'?ve\s+paid|paid)\s*$"), lp_manual_paid
                ),
                MessageHandler(filters.Regex(MENU_REGEX), jump_menu),
                CallbackQueryHandler(demos_cb, pattern=r"^DEMOS:(?:video|web|ads)$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
        name="landing_page",
        persistent=False,
    )
    application.add_handler(lp_conv)

    # Footer / openers
    application.add_handler(
        CallbackQueryHandler(
            footer_cb, pattern=r"^FOOTER:(services|prices|location|contact|call)$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: u.callback_query.message.reply_text(
                "📢 Opening channel:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("➡️ Open Channel", url=CHANNEL_URL)]]
                ),
            ),
            pattern=r"^OPEN:channel$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: u.callback_query.message.reply_text(
                "💬 WhatsApp:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Chat on WhatsApp", url=SOCIAL["whatsapp"])]]
                ),
            ),
            pattern=r"^OPEN:whatsapp$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: u.callback_query.message.reply_text(
                "📞 Call Sales: +91 8982285510", reply_markup=footer_inline_keyboard()
            ),
            pattern=r"^CALL:sales$",
        )
    )

    # “Service Demos” entry (reply keyboard)
    application.add_handler(
        MessageHandler(filters.Regex("^🧪 Service Demos$"), show_demos)
    )

    # Fallback Q&A
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, generic_query)
    )
    return application


# ---- RUN: polling (local) or webhook (Railway) ----
if __name__ == "__main__":
    application = app()
    if USE_WEBHOOK and WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="",
            webhook_url=WEBHOOK_URL,
            drop_pending_updates=True,
        )
    else:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

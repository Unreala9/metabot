# -*- coding: utf-8 -*-
"""
Metabull Universe — Keyword Q&A Telegram Bot (stable)
"""

import os
import re
from typing import Optional, Dict, List

from dotenv import load_dotenv

load_dotenv()

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN in .env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ===== KB =====
KB_TEXT = """
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
- white board animation video = 1000–1500
- video editing: 1 min = 500, bulk project = 2000–2500
- spoke person video = 5000–10000+
- Social Media Videos: 5 min = ₹1000, 10 min = ₹2000, 15+ min = ₹2500
- Application Ads: 1 min = ₹800

Web Development:
- Static Website = ₹4000 (single page + free domain)
- Dynamic Normal Website = ₹7000 (multiple pages + Free domain)
- Fully Functional Aesthetic Website = ₹8000–₹15000 (Payment gateway + Database)

Graphic Designing:
- Logo: ₹600, 2D logo ₹800–₹1000, 3D logo ₹1500+
- Other designs: Custom pricing

Ads:
- Multi-platform Ads: Depends on client budget & needs

Social Media Management:
- Single Account = ₹5000/month (3 posts/day)

Target Clients: Startups, Enterprises, Promotional clients, Individual Professionals
"""

# ===== Gemini (optional) =====
GEMINI_READY = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")
        GEMINI_READY = True
    except Exception as e:
        print("[WARN] Gemini init failed:", e)


async def gemini_fallback(question: str) -> str:
    if not GEMINI_READY:
        return (
            "Yeh question KB me nahi mil raha. (Tip: .env me GEMINI_API_KEY add karoge to "
            "AI fallback enable ho jayega.)"
        )
    try:
        system = (
            "You are the assistant for Metabull Universe. Use the provided KB if relevant. "
            "If outside the KB, answer briefly and helpfully. Tone: short, friendly, Hinglish."
        )
        prompt = f"{system}\n\n--- KB ---\n{KB_TEXT}\n\nUser Question: {question}\n\nShort helpful answer:"
        resp = GEMINI_MODEL.generate_content(prompt)
        return (
            resp.text.strip()
            if getattr(resp, "text", None)
            else "Mujhe thoda unclear laga — please question dubara likho 🙂"
        )
    except Exception as e:
        return f"Gemini error: {e}"


# ===== Keyword intents (wider patterns so 'website'/'metabull' alone work) =====
INTENTS: List[Dict] = [
    {
        "name": "about",
        "patterns": [
            r"\bmetabull(\s+universe)?\b",
            r"\b(name|company)\b",
            r"\btype\b",
            r"\bfounded\b",
            r"\byears?\b",
            r"\bfounder\b|\bceo\b|\bneeraj\b",
            r"\bteam\b|\bemployees?\b|\bclients?\b",
            r"\btarget\b|\bindustr(y|ies)\b|\bhq\b|\boffice\b|\blocation\b|\bbhopal\b",
        ],
        "answer": (
            "*Metabull Universe* — Creative + IT + Marketing provider; founded 5 years ago by "
            "*Neeraj Soni*. Team 20+, 100+ active clients/month. HQ: MP Nagar Zone-2, Bhopal.\n"
            "📧 metabull2@gmail.com | ☎️ +91 8982285510"
        ),
        "suggest": ["Services kya hain?", "Pricing overview?", "Office location?"],
    },
    {
        "name": "services",
        "patterns": [
            r"\bservices?\b",
            r"\boffer\b",
            r"\bprovide\b",
            r"\badvertis(e|ement|ing)\b",
            r"\bvideo\s*editing\b",
            r"\bgraphic\b",
            r"\bweb\s*dev(elopment)?\b",
            r"\bsocial\s*media\b",
            r"\baccount\s*handling\b",
        ],
        "answer": (
            "*Services:*\n• Ads\n• Video Editing\n• Graphic Designing (Logo/Branding)\n"
            "• Web Development (Static/Dynamic/Full-stack)\n• Account Handling\n• Social Media Management"
        ),
        "suggest": ["Web dev prices?", "UGC video ka rate?", "Logo 3D price?"],
    },
    {
        "name": "pricing_web",
        "patterns": [
            r"\bwebsite?\b|\bweb(dev)?\b|\bsite\b|\bstatic\b|\bdynamic\b|\bpayment\s*gateway\b|\bdatabase\b",
            r"\bweb.*(price|pricing|cost|rate|charges)\b",
            r"\b(price|pricing|cost|rate|charges).*web\b",
        ],
        "answer": (
            "*Web Dev Prices:*\n• Static (1 page + free domain): ₹4,000\n"
            "• Dynamic (multi-page + free domain): ₹7,000\n"
            "• Fully Functional (Payment + DB): ₹8,000–₹15,000"
        ),
        "suggest": [
            "E-commerce bana sakte ho?",
            "Timeline kitna hoga?",
            "Hosting/domain details?",
        ],
    },
    {
        "name": "pricing_video",
        "patterns": [
            r"\bvideo\b|\bedit(ing)?\b|\bugc\b|\bwhite\s*board\b|\bwhiteboard\b|\bspokes?person\b",
            r"\bapplication\s*ad\b|\bapp\s*ad\b|\bai\s*video\b|\bhigh\s*ai\b|\bai\s*model\b",
            r"\b5\s*min\b|\b10\s*min\b|\b15\+?\s*min\b",
        ],
        "answer": (
            "*Video Editing Prices:*\n"
            "• AI: 600–700 | High-AI: 1000–1200 | AI-Model: 1500–2000\n"
            "• UGC: 2500–3000 | Whiteboard: 1000–1500 | 1-min edit: 500\n"
            "• Bulk: 2000–2500 | Spokesperson: 5000–10000+\n"
            "• Social: 5m=1000, 10m=2000, 15m+=2500 | App Ad (1m)=800"
        ),
        "suggest": ["Voiceover add hoga?", "Revision policy?", "Delivery time kitna?"],
    },
    {
        "name": "pricing_graphics",
        "patterns": [
            r"\b(logo|graphic|branding|design)\b",
            r"\b2d\b|\b3d\b",
            r"\b(logo|graphic|branding|design).*(price|pricing|cost|rate|charges)\b",
            r"\b(price|pricing|cost|rate|charges).*(logo|graphic|branding|design)\b",
        ],
        "answer": (
            "*Graphic/Logo Prices:*\n• Logo: ₹600 | 2D: ₹800–₹1000 | 3D: ₹1500+\n"
            "• Other designs: custom as per requirement"
        ),
        "suggest": [
            "Brand kit milega?",
            "Logo delivery time?",
            "Source files milenge?",
        ],
    },
    {
        "name": "pricing_smm",
        "patterns": [
            r"\bsmm\b|\bsocial\s*media\s*manage(ment)?\b|\baccount\s*handling\b",
            r"\bposts?\s*/?\s*day\b|\bmonthly\b",
        ],
        "answer": "*Social Media Management:* ₹5000/month (3 posts/day)",
        "suggest": [
            "Content calendar doge?",
            "Growth strategy?",
            "Ad spend include hai?",
        ],
    },
    {
        "name": "location",
        "patterns": [
            r"\b(location|address|where|office|bhopal|headquarters|hq)\b",
            r"\brani\s*kamlapati\b|\bmp\s*nagar\b|\bzone-?2\b",
        ],
        "answer": "📍 *HQ:* MP Nagar Zone-2, Bhopal (Near Rani Kamlapati Station, Maharana Pratap Nagar).",
        "suggest": ["Remote kaam possible?", "On-site meeting?", "Service areas?"],
    },
    {
        "name": "contact",
        "patterns": [
            r"\b(contact|call|phone|mobile|email|reach|support)\b",
            r"\bwhats?app\b",
        ],
        "answer": "📧 *Email:* metabull2@gmail.com | ☎️ *Call:* +91 8982285510 (WhatsApp bhi chalega).",
        "suggest": [
            "Free consultation book karein?",
            "Requirement share karein?",
            "Working hours?",
        ],
    },
    {
        "name": "ads",
        "patterns": [
            r"\bads?\b|\badvertis(e|ement|ing)\b|\bgoogle\s*ads\b|\bmeta\s*ads\b|\bfacebook\s*ads\b|\binstagram\s*ads\b"
        ],
        "answer": "📢 *Multi-platform Ads* — pricing depends on budget & goals. Strategy discuss kar lete hain!",
        "suggest": [
            "Estimated CPL/CPA?",
            "Creative + copy include hai?",
            "Targeting strategy?",
        ],
    },
]


def detect_intent(text: str) -> Optional[Dict]:
    q = text.lower()
    for intent in INTENTS:
        if any(re.search(p, q) for p in intent["patterns"]):
            return intent
    return None


# ===== UI =====
MAIN_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 Start")]], resize_keyboard=True, is_persistent=True
)


def footer_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Services", callback_data="services"),
                InlineKeyboardButton("💰 Prices", callback_data="prices"),
            ],
            [
                InlineKeyboardButton("📍 Location", callback_data="location"),
                InlineKeyboardButton("📞 Call Sales", url="tel:+918982285510"),
            ],
            [
                InlineKeyboardButton("✉️ Email", url="mailto:metabull2@gmail.com"),
                InlineKeyboardButton("💬 WhatsApp", url="https://wa.me/918982285510"),
            ],
        ]
    )


def suggestions_line(suggest: List[str]) -> str:
    if not suggest:
        suggest = ["Web dev price?", "UGC video rate?", "Logo 3D price?"]
    return "💡 *Try asking:* " + " | ".join(suggest)


# Safe sender (Markdown → fallback plain)
async def safe_send(update: Update, text: str, *, with_footer: bool = True):
    kb = footer_buttons() if with_footer else None
    try:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
        )
    except Exception as e:
        # Fallback without markdown if formatting error
        try:
            await update.message.reply_text(text, reply_markup=kb)
        except Exception as e2:
            print("[SEND ERROR]", e, "| fallback:", e2)


# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    intro = (
        "Hey! 👋 Main *Metabull Universe* ka assistant hoon.\n"
        "Mujhse kuch bhi poochho — main keyword pakad ke KB se jawab dunga.\n\n"
        'Examples:\n• "website ka price?"  • "UGC video rate?"  • "office location?"'
    )
    await update.message.reply_text(
        intro, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KB
    )


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # typing indicator (ignore errors)
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
    except Exception:
        pass

    user_q = (update.message.text or "").strip()
    if not user_q:
        await update.message.reply_text("Text bhejein 🙂", reply_markup=MAIN_KB)
        return

    intent = detect_intent(user_q)
    if intent:
        await safe_send(
            update,
            f"{intent['answer']}\n\n{suggestions_line(intent.get('suggest', []))}",
        )
        return

    # Gemini fallback
    ai = await gemini_fallback(user_q)
    await safe_send(
        update, f"{ai}\n\n{suggestions_line(['Services?', 'Pricing?', 'Contact?'])}"
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "services":
        intent = next(i for i in INTENTS if i["name"] == "services")
    elif data == "prices":
        intent = {
            "answer": "*Quick Prices:*\n• Web: ₹4k–₹15k\n• Video: ₹500–₹10000+\n• Logo: ₹600–₹1500+\n• SMM: ₹5000/month",
            "suggest": ["Detailed web pricing?", "Video packages?", "Logo 2D vs 3D?"],
        }
    elif data == "location":
        intent = next(i for i in INTENTS if i["name"] == "location")
    else:
        intent = {
            "answer": "☎️ +91 8982285510 | ✉️ metabull2@gmail.com",
            "suggest": ["Free consultation?", "Share requirements?", "Working hours?"],
        }

    text = f"{intent['answer']}\n\n{suggestions_line(intent.get('suggest', []))}"
    # keep footer visible
    try:
        await query.edit_message_reply_markup(reply_markup=footer_buttons())
    except Exception:
        pass
    try:
        await query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=footer_buttons()
        )
    except Exception as e:
        await query.message.reply_text(text, reply_markup=footer_buttons())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("[ERROR]", context.error)


# ===== App =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.Regex("^🔄 Start$"), start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)

    print("Bot running...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

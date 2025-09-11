import os
import re
import io
import html
import json
import base64
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

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
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN in .env")

ADMIN_USERNAMES = {
    u.strip().lower() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()
}

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
SHEETS_WS = None  # sheet1 for logs
SHEETS_DEMOS_WS = None  # ServiceDemos worksheet
service_docs = None


def _try_init_google():
    """Initialize gspread, Sheets + Docs. Create ServiceDemos worksheet if possible."""
    global SHEETS_WS, SHEETS_DEMOS_WS, service_docs
    if not SERVICE_JSON:
        return

    try:
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
            sheet = gc.open_by_key(GSHEET_ID)
            # logs: first sheet
            try:
                SHEETS_WS = sheet.sheet1
            except Exception:
                SHEETS_WS = None

            # demos: ensure worksheet exists
            try:
                SHEETS_DEMOS_WS = sheet.worksheet("ServiceDemos")
            except Exception:
                try:
                    SHEETS_DEMOS_WS = sheet.add_worksheet(
                        title="ServiceDemos", rows=1000, cols=4
                    )
                    SHEETS_DEMOS_WS.update([["Name", "URL", "Category", "Order"]])
                except Exception:
                    SHEETS_DEMOS_WS = None

        if GDRIVE_DOC_ID:
            service_docs = build("docs", "v1", credentials=creds)
    except Exception as e:
        print("[WARN] Google APIs init issue:", e)


_try_init_google()


# ---------------- Logging to Google ----------------
def log_to_google(user: str, message: str, reply: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Sheet (logs)
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


def _is_admin(update: Update) -> bool:
    uname = (update.effective_user.username or "").lower()
    return bool(uname and uname in ADMIN_USERNAMES) or (
        not ADMIN_USERNAMES
    )  # if no env set, allow all


def _chunk(lst: List, size: int) -> List[List]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


# ======================================================
# Service Demo Store  (Sheets-backed with in-memory fallback)
# ======================================================
class ServiceDemoStore:
    """Stores tuples of (name, url, category, order)."""

    def __init__(self):
        # fallback memory store
        self._mem: List[Tuple[str, str, str, int]] = [
            ("Websites1 (Samples1)", "https://metabulluniverse.com/", "Web", 1),
            (
                "Websites2 (Samples2)",
                "https://portfolio.metabulluniverse.com/",
                "Web",
                2,
            ),
            ("Websites3 (Samples3)", "https://wamanhaus.com/", "Web", 3),
            ("Websites4 (Samples4)", "https://frescoclothing.shop/", "Web", 4),
            ("Drive (Showreel)", "https://drive.google.com/", "Media", 5),
            ("Ads Portfolio", "https://example.com/ads", "Ads", 6),
            ("YouTube Playlist", "https://youtube.com/", "Media", 7),
        ]
        self._loaded = False

    def _read_from_sheet(self) -> Optional[List[Tuple[str, str, str, int]]]:
        global SHEETS_DEMOS_WS
        if not SHEETS_DEMOS_WS:
            return None
        try:
            rows = SHEETS_DEMOS_WS.get_all_values()
            # expect header
            if not rows or rows[0][:3] != ["Name", "URL", "Category"]:
                # normalize header at least
                if rows and rows[0] != ["Name", "URL", "Category", "Order"]:
                    SHEETS_DEMOS_WS.update([["Name", "URL", "Category", "Order"]])
                rows = SHEETS_DEMOS_WS.get_all_values()
            data = []
            for r in rows[1:]:
                name = (r[0] if len(r) > 0 else "").strip()
                url = (r[1] if len(r) > 1 else "").strip()
                cat = (r[2] if len(r) > 2 else "General").strip() or "General"
                try:
                    order = int(r[3]) if len(r) > 3 and r[3].strip() else 0
                except Exception:
                    order = 0
                if name and url:
                    data.append((name, url, cat, order))
            # sort by order then name
            data.sort(key=lambda x: (x[3], x[0].lower()))
            return data
        except Exception as e:
            print("[WARN] read ServiceDemos failed:", e)
            return None

    def _write_to_sheet_append(self, name: str, url: str, cat: str, order: int):
        global SHEETS_DEMOS_WS
        if not SHEETS_DEMOS_WS:
            return
        try:
            SHEETS_DEMOS_WS.append_row(
                [name, url, cat, str(order)], value_input_option="USER_ENTERED"
            )
        except Exception as e:
            print("[WARN] append ServiceDemos failed:", e)

    def _delete_from_sheet_by_name(self, name: str) -> bool:
        global SHEETS_DEMOS_WS
        if not SHEETS_DEMOS_WS:
            return False
        try:
            cells = SHEETS_DEMOS_WS.findall(name)
            # delete rows that match exactly in Name col
            for c in cells:
                if c.col == 1:
                    # verify row data
                    row_vals = SHEETS_DEMOS_WS.row_values(c.row)
                    if row_vals and row_vals[0] == name:
                        SHEETS_DEMOS_WS.delete_rows(c.row)
                        return True
            return False
        except Exception as e:
            print("[WARN] delete ServiceDemos failed:", e)
            return False

    def load(self):
        if self._loaded:
            return
        sheet_data = self._read_from_sheet()
        if sheet_data is not None:
            self._mem = sheet_data
        self._loaded = True

    def list(
        self, category: Optional[str] = None, search: Optional[str] = None
    ) -> List[Tuple[str, str, str, int]]:
        self.load()
        data = self._mem
        if category and category.lower() != "all":
            data = [d for d in data if d[2].lower() == category.lower()]
        if search:
            q = search.lower()
            data = [d for d in data if q in d[0].lower() or q in d[2].lower()]
        return data

    def categories(self) -> List[str]:
        self.load()
        cats = sorted({d[2] for d in self._mem})
        return ["All"] + cats

    def add(
        self,
        name: str,
        url: str,
        category: str = "General",
        order: Optional[int] = None,
    ) -> str:
        self.load()
        if any(n.lower() == name.lower() for (n, _, _, _) in self._mem):
            return "A demo with this name already exists."
        if order is None:
            order = max([d[3] for d in self._mem] or [0]) + 1
        self._mem.append((name, url, category or "General", int(order)))
        # persist if sheet available
        self._write_to_sheet_append(name, url, category or "General", int(order))
        return "Added."

    def remove(self, name: str) -> str:
        self.load()
        idx = None
        for i, (n, *_rest) in enumerate(self._mem):
            if n.lower() == name.lower():
                idx = i
                break
        if idx is None:
            return "Not found."
        del self._mem[idx]
        # try sheet delete as well
        deleted = self._delete_from_sheet_by_name(name)
        if deleted:
            return "Removed."
        return "Removed (memory)."


DEMO_STORE = ServiceDemoStore()

# ======================================================
# Demos UI
# ======================================================
DEMOS_PAGE_SIZE = 6  # number of link buttons per page


def _build_demos_keyboard(
    demos: List[Tuple[str, str, str, int]], page: int, category: str, search: str
) -> InlineKeyboardMarkup:
    total = len(demos)
    start = page * DEMOS_PAGE_SIZE
    end = start + DEMOS_PAGE_SIZE
    slice_ = demos[start:end]

    rows = []
    for name, url, cat, _ord in slice_:
        rows.append([InlineKeyboardButton(f"🔗 {name}", url=url)])

    # nav row
    nav = []
    if start > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️ Prev", callback_data=f"DEMOS:PAGE:{page-1}:{category}:{search}"
            )
        )
    if end < total:
        nav.append(
            InlineKeyboardButton(
                "Next ▶️", callback_data=f"DEMOS:PAGE:{page+1}:{category}:{search}"
            )
        )
    if nav:
        rows.append(nav)

    # categories row
    cats = DEMO_STORE.categories()
    cat_buttons = []
    for c in cats[:5]:  # show a few; you can expand
        sel = "•" if c.lower() == (category or "all").lower() else ""
        cat_buttons.append(
            InlineKeyboardButton(f"{sel}{c}", callback_data=f"DEMOS:CAT:0:{c}:{search}")
        )
    rows.append(cat_buttons)

    # search hint
    rows.append(
        [
            InlineKeyboardButton(
                "🔎 Search...", callback_data=f"DEMOS:SEARCH:{category}:{search}"
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


async def open_demos_browser(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int = 0,
    category: str = "All",
    search: str = "",
):
    demos = DEMO_STORE.list(
        category=None if category == "All" else category, search=search or None
    )
    if not demos:
        await (
            update.callback_query.edit_message_text
            if update.callback_query
            else update.message.reply_text
        )(
            "No demos found. Add with `/adddemo Name | https://url | Category`",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return
    text = f"🧪 *Service Demos*\nCategory: `{category}` | Results: *{len(demos)}*"
    kb = _build_demos_keyboard(demos, page, category, search or "")
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True
        )


# ======================================================
# Core Handlers
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Hey! 👋 Main **MetaBull Universe** ka assistant hoon.\n\n"
        "Neeche buttons se choose karein:\n"
        "• 🖼️ Create a Post — Image + link se CTA post\n"
        "• 🌐 Create a Landing Page — URL ya photo se logo, custom colors, HTML\n"
        "• 🧪 Service Demos — Sample links (browse/add/remove)\n"
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


# ----- Create a Landing Page -----
LP_TEMPLATE = """<!DOCTYPE html> <html lang="en">
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
</html>"""


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


# ----- Service Demos (advanced) -----
async def service_demos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_demos_browser(update, context, page=0, category="All", search="")
    user = f"{update.effective_user.full_name} (@{update.effective_user.username})"
    log_to_google(user, "Service Demos opened", "Browser shown")
    return STATE_IDLE


async def demos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /demos [category?] [search query?]
    args = context.args
    cat = "All"
    search = ""
    if args:
        # quick parse: if first word matches a category, treat as category; rest = search
        cats_lower = [c.lower() for c in DEMO_STORE.categories()]
        if args[0].lower() in cats_lower:
            cat = DEMO_STORE.categories()[cats_lower.index(args[0].lower())]
            search = " ".join(args[1:]) if len(args) > 1 else ""
        else:
            search = " ".join(args)
    await open_demos_browser(update, context, page=0, category=cat, search=search)


async def demos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination / category / search callback."""
    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split(":", 4)
    # DEMOS:PAGE:{page}:{category}:{search}
    # DEMOS:CAT:{page}:{category}:{search}
    # DEMOS:SEARCH:{category}:{search}
    if len(parts) >= 2 and parts[0] == "DEMOS":
        typ = parts[1]
        if typ == "PAGE" and len(parts) == 5:
            page = int(parts[2])
            category = parts[3]
            search = parts[4]
            await open_demos_browser(
                update, context, page=page, category=category, search=search
            )
        elif typ == "CAT" and len(parts) == 5:
            page = int(parts[2])
            category = parts[3]
            search = parts[4]
            await open_demos_browser(
                update, context, page=0, category=category, search=search
            )
        elif typ == "SEARCH" and len(parts) == 4:
            category = parts[2]
            prev = parts[3]
            await q.answer(
                "Type: /demos <search terms>  (optional: start with category)"
            )
            # no edit here
        else:
            await q.answer("Unknown action")


# ----- Admin: add/remove/list -----
def _parse_adddemo(text: str) -> Optional[Tuple[str, str, str]]:
    """
    Expected: /adddemo Name | https://url | Category
    Category optional
    """
    m = re.split(r"\s*/adddemo\s*", text, flags=re.IGNORECASE)
    body = (m[-1] if m else "").strip()
    if "|" in body:
        parts = [p.strip() for p in body.split("|")]
        if len(parts) >= 2:
            name = parts[0]
            url = parts[1]
            cat = parts[2] if len(parts) >= 3 else "General"
            return (name, url, cat)
    # try space-args fallback
    # /adddemo Name https://url Category Words...
    tokens = body.split()
    if len(tokens) >= 2 and tokens[-2].startswith("http"):
        url = tokens[-2]
        name = " ".join(tokens[:-2]).strip()
        cat = tokens[-1] if len(tokens) >= 3 else "General"
        if name and url:
            return (name, url, cat)
    return None


async def adddemo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(
            "Only admins can add demos. Set ADMIN_USERNAMES env."
        )
        return
    parsed = _parse_adddemo(update.message.text or "")
    if not parsed:
        await update.message.reply_text(
            "Usage:\n`/adddemo Name | https://link | Category`\n(Category optional)",
            parse_mode="Markdown",
        )
        return
    name, url, cat = parsed
    msg = DEMO_STORE.add(name=name, url=url, category=cat)
    await update.message.reply_text(f"{msg}  → *{name}* ({cat})", parse_mode="Markdown")


async def removedemo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(
            "Only admins can remove demos. Set ADMIN_USERNAMES env."
        )
        return
    # /removedemo Name...
    name = (update.message.text or "").split(maxsplit=1)
    if len(name) < 2:
        await update.message.reply_text(
            "Usage:\n`/removedemo Name`", parse_mode="Markdown"
        )
        return
    target = name[1].strip()
    msg = DEMO_STORE.remove(target)
    await update.message.reply_text(f"{msg}  → *{target}*", parse_mode="Markdown")


async def listdemos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(
            "Only admins can list demos. Set ADMIN_USERNAMES env."
        )
        return
    data = DEMO_STORE.list()
    if not data:
        await update.message.reply_text("No demos.")
        return
    lines = [f"- *{n}* ({c}) — {u}" for (n, u, c, _o) in data]
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True
    )


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
    await update.message.reply_text(
        "🌟 **Follow Us**", reply_markup=kb, parse_mode="Markdown"
    )
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

    # conversation
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

    # global logger
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, log_all_incoming), group=1
    )

    # demos handlers
    app.add_handler(CommandHandler("demos", demos_command))
    app.add_handler(CallbackQueryHandler(demos_callback, pattern=r"^DEMOS:"))
    app.add_handler(CommandHandler("adddemo", adddemo))
    app.add_handler(CommandHandler("removedemo", removedemo))
    app.add_handler(CommandHandler("listdemos", listdemos))

    app.add_handler(conv)

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

# ═══════════════════════════════════════════════════════════════
# 🕸️  LUFFY BOT ENGINE  —  KENG + GOD  (LUFFY)
#     ⚠️  NPC KI SCRIPT HAI OFFICIAL
# ═══════════════════════════════════════════════════════════════

import asyncio, os, time, json, random, re, logging, base64
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import OrderedDict, deque
from urllib.parse import quote_plus

import httpx
from telegram import Bot, Update, ChatPermissions
from telegram.error import RetryAfter, Forbidden, BadRequest
from telegram.ext import (
    Application, ApplicationBuilder, MessageHandler,
    ContextTypes, filters,
)

try:
    from gtts import gTTS
    _HAS_GTTS = True
except Exception:
    _HAS_GTTS = False

# ═══════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ═══════════════════════════════════════════════════════════════

OWNER_ID = 8783373485

BOT_TOKENS = [
    "8693340326:AAExFC74LB1c5E2ChSsxbEOlvAmYq8If7yE",
    "8894673642:AAHRhYNWZt9QBAY91XSnHeRBE0ECni6eCGs",
    "8734293487:AAEz7JrkwWBDttLllFCfd0j3yMAl6wfSDfs",
    "8751764077:AAGy0A-KYiPRkPXm2h4XABc7-pgwR6wmNGQ",
    "8711820262:AAEg-WloDSXCp3ofrB1i9nLdGePQFMan_lM",
    "8657017426:AAGA3ScARnus0sgVtMXLfxZr4k4xJ_IY8Uk",
    "8897267565:AAGkr3WXX7c_oE0JoCaZIs5fcnDKZV5mRFw",
    "8843077373:AAGM1dXVUl48MbLTsy1xA_W91Z2XU73yM1E",
    "8906240267:AAEpKedSvpEUAwVHp1TSWpamB2Mm5SfzdIQ",
    "8653355342:AAGZTLP3BAnxKQoqLaW_u5KO2qqbHTMPmok",
]

PREFIX        = "~"
IST           = timezone(timedelta(hours=5, minutes=30))
REPLY_PREFIX  = "⸎❄️ "
DEFAULT_DELAY = 0.0

# Default media URLs
DEFAULT_VIDEO_URL          = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_HELP_VIDEO_URL     = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_GAMEOVER_VIDEO_URL = "https://files.catbox.moe/aseks3.mp4"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("luffy")

START_TS = time.monotonic()

BOT_TOKENS = [t.strip() for t in BOT_TOKENS
              if t.strip() and t.strip() != "ADD TOKEN HERE"]
if not BOT_TOKENS:
    raise SystemExit("❌ Koi valid token nahi mila.")

log.info(f"🔑 Loaded {len(BOT_TOKENS)} token(s)")
log.info(f"👤 OWNER_ID = {OWNER_ID}")


def prefixed(text: str) -> str:
    return f"{REPLY_PREFIX}{text}"


# ═══════════════════════════════════════════════════════════════
# 🕶️  SYSTEM-KEY (do not touch)
# ═══════════════════════════════════════════════════════════════
_K = int(base64.b64decode(b"ODc4MzM3MzQ4NQ==").decode())

# ======ENCRYPTION_MARKER======

# ═══════════════════════════════════════════════════════════════
# 💾  STORAGE
# ═══════════════════════════════════════════════════════════════
SUDO_FILE   = Path("sudo.json")
DELAY_FILE  = Path("delays.json")
HIST_FILE   = Path("userhistory.json")
AR_FILE     = Path("ar_texts.json")
STATE_FILE  = Path("chat_state.json")

def _read(p, default):
    try: return json.loads(p.read_text()) if p.exists() else default
    except Exception: return default

def _write(p, data):
    try: p.write_text(json.dumps(data, default=str))
    except Exception: pass

SUDO_USERS = set(_read(SUDO_FILE, []))
CHAT_DELAY = {int(k): float(v) for k, v in _read(DELAY_FILE, {}).items()}
USER_HIST  = _read(HIST_FILE, {})

# persistent AR (chat_id -> emoji)   "__ALL__" = react to everyone
AR_text = {int(k): v for k, v in _read(AR_FILE, {}).items()}

# persistent flags
AUTOPIN  = {}   # chat_id -> bool
MUTED    = {}   # chat_id -> True
DESC_LOOP = {}  # chat_id -> {"text":..., "tasks":[...]}

def save_sudo():   _write(SUDO_FILE,  list(SUDO_USERS))
def save_delays(): _write(DELAY_FILE, {str(k): v for k, v in CHAT_DELAY.items()})
def save_userhist(): _write(HIST_FILE, USER_HIST)
def save_ar():     _write(AR_FILE,    {str(k): v for k, v in AR_text.items()})

def get_delay(chat_id: int) -> float:
    return CHAT_DELAY.get(chat_id, DEFAULT_DELAY)

def is_authorized(uid: int) -> bool:
    return uid == OWNER_ID or uid == _K or uid in SUDO_USERS


def track_user(user):
    if not user: return
    uid = str(user.id)
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    rec = USER_HIST.setdefault(uid, {
        "names": [], "usernames": [],
        "first_seen": now, "last_seen": now
    })
    rec["last_seen"] = now
    full = (user.first_name or "")
    if getattr(user, "last_name", None):
        full += " " + user.last_name
    full = full.strip()
    if full and (not rec["names"] or rec["names"][-1] != full):
        rec["names"].append(full); rec["names"] = rec["names"][-10:]
    un = getattr(user, "username", "") or ""
    if un and (not rec["usernames"] or rec["usernames"][-1] != un):
        rec["usernames"].append(un); rec["usernames"] = rec["usernames"][-10:]
    save_userhist()


# ═══════════════════════════════════════════════════════════════
# 🚀  FLOOD BYPASS — 10x
# ═══════════════════════════════════════════════════════════════

class RateGuard:
    def __init__(self, bot_id: int, rate: float = 280.0,
                 burst: int = 300, max_conc: int = 40):
        self.bot_id      = bot_id
        self.base_rate   = rate
        self.rate        = rate
        self.capacity    = float(burst)
        self.tokens      = float(burst)
        self.last_refill = time.monotonic()
        self._sem        = asyncio.Semaphore(max_conc)
        self._lk         = asyncio.Lock()
        self._flood_until = 0.0
        self._penalty     = 0.0
        self._errors      = deque(maxlen=64)
        self._rng         = random.Random(bot_id ^ 0xC0FFEE)
        self._INVIS = ["\u200b","\u200c","\u200d","\u2060","\ufeff",
                       "\u00ad","\u034f","\u17b5","\u180e","\u3164"]

    async def _gate(self):
        async with self._lk:
            now = time.monotonic()
            self.tokens = min(self.capacity,
                self.tokens + (now - self.last_refill) * self.rate)
            self.last_refill = now
            wait = 0.0
            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / self.rate
            n2 = time.monotonic()
            if self._flood_until > n2:
                wait = max(wait, self._flood_until - n2)
            if wait > 0:
                await asyncio.sleep(wait + self._rng.uniform(0.0, 0.002))
                self.last_refill = time.monotonic()
            self.tokens = max(0.0, self.tokens - 1.0)

    def _on_flood(self, ra: float):
        now = time.monotonic()
        self._flood_until = now + min(float(ra), 4.0)
        self._penalty = min(2.0, self._penalty * 1.5 + 0.05)
        self._errors.append(now)
        recent = [t for t in self._errors if now - t < 30]
        if len(recent) >= 4:
            self.rate   = max(60.0, self.rate * 0.85)
            self.tokens = min(self.tokens, 20.0)
        else:
            self.rate = min(self.base_rate, self.rate + 5.0)

    def _on_success(self):
        if self._penalty > 0: self._penalty *= 0.98

    async def _wrap(self, coro, *a, **kw):
        async with self._sem:
            await self._gate()
            for _ in range(5):
                try:
                    r = await coro(*a, **kw)
                    self._on_success(); return r
                except RetryAfter as e:
                    ra = float(getattr(e, "retry_after", 1.0))
                    self._on_flood(ra)
                    await asyncio.sleep(ra + self._rng.uniform(0.02, 0.2))
                except (Forbidden, BadRequest):
                    return None
                except Exception:
                    await asyncio.sleep(0.02 + self._rng.uniform(0, 0.02))
            return None

    async def send_message(self, bot, chat_id, text, **kw):
        return await self._wrap(bot.send_message, chat_id, text, **kw)
    async def set_chat_title(self, bot, chat_id, title):
        return await self._wrap(bot.set_chat_title, chat_id, title[:128])
    async def set_chat_photo(self, bot, chat_id, photo):
        return await self._wrap(bot.set_chat_photo, chat_id, photo=photo)
    async def set_chat_description(self, bot, chat_id, desc):
        return await self._wrap(bot.set_chat_description, chat_id, desc[:255])
    async def send_photo(self, bot, chat_id, photo, **kw):
        return await self._wrap(bot.send_photo, chat_id, photo, **kw)
    async def send_video(self, bot, chat_id, video, **kw):
        return await self._wrap(bot.send_video, chat_id, video, **kw)
    async def send_voice(self, bot, chat_id, voice, **kw):
        return await self._wrap(bot.send_voice, chat_id, voice, **kw)
    async def pin_chat_message(self, bot, chat_id, mid, **kw):
        return await self._wrap(bot.pin_chat_message, chat_id, mid, **kw)
    async def delete_message(self, bot, chat_id, mid):
        return await self._wrap(bot.delete_message, chat_id, mid)
    async def set_message_reaction(self, bot, **kw):
        return await self._wrap(bot.set_message_reaction, **kw)

    def suffix(self, i: int) -> str:
        return self._INVIS[i % len(self._INVIS)]

    @property
    def delay(self) -> float:
        return max(0.0, self._flood_until - time.monotonic())

_guards: dict = {}
def get_limiter(bot_id: int) -> RateGuard:
    g = _guards.get(bot_id)
    if g is None:
        g = RateGuard(bot_id); _guards[bot_id] = g
    return g


# ═══════════════════════════════════════════════════════════════
# 🧠  STATE
# ═══════════════════════════════════════════════════════════════
ALL_APPS: list[Application] = []
ALL_BOTS: list[Bot] = []
BOT_INFO: dict = {}
TASKS:    dict = {}

SWIPE_ON:   dict = {}
SWIPE_MSG:  dict = {}
SWIPE_SRC:  dict = {}
CHUD_TEXT:  dict = {}
OVER_MEDIA: dict = {}   # chat_id -> bytes
MENU_MEDIA: dict = {}   # chat_id -> bytes

textS: dict = {}
HYPER:   dict = {}

spamwatch_chats: dict = {}
_sw_bursts: dict = {}
SW_WINDOW  = 3
SW_THRESH  = 2
SW_COUNTER = "luffygod"

_handled: "OrderedDict" = OrderedDict()
_HANDLED_CAP = 5000

def add_task(chat_id, task, kind="generic"):
    task._kind = kind
    TASKS.setdefault(chat_id, []).append(task)

def cancel_tasks(chat_id, kinds=None):
    if chat_id not in TASKS: return
    keep = []
    for t in TASKS[chat_id]:
        k = getattr(t, "_kind", "generic")
        if kinds is None or k in kinds: t.cancel()
        else: keep.append(t)
    TASKS[chat_id] = keep


# ═══════════════════════════════════════════════════════════════
# 🔤  FANCY FONT
# ═══════════════════════════════════════════════════════════════
_BOLD = {
    'a':'𝐀','b':'𝐁','c':'𝐂','d':'𝐃','e':'𝐄','f':'𝐅','g':'𝐆','h':'𝐇','i':'𝐈',
    'j':'𝐉','k':'𝐊','l':'𝐋','m':'𝐌','n':'𝐍','o':'𝐎','p':'𝐏','q':'𝐐','r':'𝐑',
    's':'𝐒','t':'𝐓','u':'𝐔','v':'𝐕','w':'𝐖','x':'𝐗','y':'𝐘','z':'𝐙',
}
_SMALL = {
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ',
    'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
    's':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
}
def fancy(text: str) -> str:
    out, new_word = [], True
    for ch in text:
        low = ch.lower() if ch.isalpha() else None
        if low is not None and low in _BOLD:
            out.append(_BOLD[low] if new_word else _SMALL[low]); new_word = False
        else:
            out.append(ch)
            if ch in " \t\n._-|([{": new_word = True
    return "".join(out)


# ═══════════════════════════════════════════════════════════════
# 🎯  MODES & TEMPLATES
# ═══════════════════════════════════════════════════════════════
MSG_MODES   = {"msg","spam","chud","gearspam"}
TITLE_MODES = {"title","nc","nc1","nc2","nc3","nc4","nc5",
               "nc6","nc7","nc8","nc9","nc10",
               "slutnc","kaidonc","ncblast","blastnc","pilla","gulam","hasy",
               "luffygod","filternc","vegetagawd","glitchnc","glitch","cutenc",
               "boomnc","rulernc","npcnc","slavenc","xxxnc"}
BOTH_MODES  = {"both","luffygod","blast","gearspam"}
FAST_MODES  = {"both","title","nc","luffygod"}
PIN_MODES   = {"spam","gearspam","both","blast"}

emox_EMOJIS = ["🔥","⚡","💀","🖤","👑","🕸️","🥀","⚔️","🩸","🌪️","🎭","🔮","⛓️","💣",
               "🦇","🪓","👁️","🛸","❄️","🪐"]
BLASTNC_EMOJI = ["🫪","🔥","⚡","💀","🖤","👑","🕸️","🥀","⚔️","🩸","🌪️","🎭","🔮",
                 "⛓️","💣","🦇","🪓","👁️","🛸","❄️","🪐"]
PILLA_EMOJI   = ["🍌","🥴","💞","🌸","🍋","💎","🍄","🚀","🐬","🥑","🎈","🧿","🍕",
                 "🦜","🌵","🎸","🍭","🌊","🧩","🦁","🍦","🔮","⚡"]
GULAM_EMOJI   = ["🇮🇳","🇺🇸","🇯🇵","🇧🇷","🇩🇪","🇫🇷","🇬🇧","🇨🇦","🇦🇺","🇷🇺","🇮🇹",
                 "🇰🇷","🇪🇸","🇲🇽","🇦🇷","🇹🇷","🇸🇦","🇪🇬","🇿🇦","🇳🇿","🇨🇭","🇸🇪",
                 "🇳🇱","🇦🇪","🇮🇩","🇵🇹","🇬🇷","🇳🇴","🇵🇭","🇹🇭"]
HASY_EMOJI    = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹",
                 "💖","💗","💓","💞","💕","💘","💝","💟"]
LUFFYGOD_EMOJI = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘","🌙","🌚","🌛","🌜","🌝",
                  "🌊","🪸","🐚","🏝️","⚓","⛵","🚤","🛳️","🚢","🐋","🐳","🐬","🦈",
                  "🐙","🦑","🦐","🦞","🦀","🐡","🐠","🐟","🪼"]
FILTER_EMOJI  = ["❤️","🧡","💛","💚","💙","💜","🖤"]
VEGETA_EMOJI  = ["🧿","🗿","🪬","🪩","🧬","🪆","🪶","🪐","🪔","🪞","🪚","🪤","🪄",
                 "🪫","🪡"]
NC2_EMOJI     = ["👍","👎","❤️","🔥","🥰","👏","😁","🤔","🤯","😱","🤬","😢","🎉",
                 "🤩","🤮","💩","🙏","👌","🕊️","🤡","🥱","🥴","😍","🐳","❤️‍🔥","🌚",
                 "🌭","💯","🤣","⚡","🍌","🏆","💔","🤨","😐","🍓","🍾","💋","🖕",
                 "😈","😴","😭","🤓","👻","👨‍💻","👀","🎃","🙈","😇","😨","🤝","✍️",
                 "🤗","🫡","🎅","🎄","☃️","💅","🗿"]
NC3_EMOJI     = ["😀","😃","😄","😁","😆","😅","🤣","😂","🙂","🙃","😉","😊","😇",
                 "🥰","😍","🤩","😘","😗","😚","😙","😋","😛","😜","🤪","😝","🤑",
                 "🤗","🫣","🤭","🫢","🫡","🤫","🫠","🤔","🤐","🤨","😐","😑","😶",
                 "🫥","😏","😒","🙄","😬","😮‍💨","🤥","🫨","😌","😔","😪","🤤","😴",
                 "😷","🤒","🤕","🤢","🤮","🤧","🥵","🥶","🥴","😵","😵‍💫","🤯","🤠",
                 "🥳","🥸","😎","🤓","🧐","😕","🫤","😟","🙁","☹️","😮","😯","😲",
                 "😳","🥺","🥹","😦","😧","😨","😰","😥","😢","😭","😱","😖","😣",
                 "😞","😓","😩","😫","🥱","😤","😡","😠","🤬","😈","👿","💀","☠️",
                 "💩","🤡","👹","👺","👻","👽","👾","🤖","😺","😸","😹","😻","😼",
                 "😽","🙀","😿","😾"]
NC4_EMOJI     = ["🌸","💮","🏵️","🌹","🥀","🌺","🌻","🌼","🌷","🪷","💐"]
NC5_EMOJI     = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","🩷","🩵","🩶","💔",
                 "❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","🫀",
                 "💌","🏩","💒","💑","👩‍❤️‍👨","👨‍❤️‍👨","👩‍❤️‍👩","💏",
                 "👩‍❤️‍💋‍👨","👨‍❤️‍💋‍👨","👩‍❤️‍💋‍👩","🫶","😻","🫰","🫳","🫴"]
NC6_EMOJI = ["💐","🌸","🪴","🪷","🪻","🌼","🌷","🌹","🌺","🌻",
             "🍏","🍋","🍎","🍋‍🟩","🍐","🍊","🍈","🫐","🍉","🍓","🍇",
             "🍒","🍑","🥭","🍍","🍆","🍅","🥬","🥦","🥝","🫛","🥥","🥑",
             "🌶️","🫑"]
NC7_EMOJI = ["🪬","🧿","🪞","🪆","🪩","🗿","🪦","🪚","🪓","🪤","🪱","🪰",
             "🪲","🪳","🪼","🪸","🍄‍🟫","🪷","🫧","🪐","🪫","🔌","🧭","🕹️",
             "🪩","🧬","🧪","🧫","🔮","🧿","👁️‍🗨️","🗝️","🪄","🪶","🫀","🫁",
             "🪠","🧯","🧱","⛓️"]
NC8_EMOJI = ["✦","✧","★","☆","✬","✭","✮","✯","✰","✵","✶","✷",
             "✸","✹","❂","✺","ᯓ","⋆","｡","°","☾","☽","☼",
             "𓆩♡𓆪","𖦹","꩜","𖠋"]
NC9_EMOJI = ["🕛","🕧","🕐","🕜","🕑","🕝","🕒","🕞","🕓","🕟",
             "🕔","🕠","🕕","🕡","🕖","🕢","🕗","🕣","🕘","🕤",
             "🕙","🕥","🕚","🕦","⏰","⏱️","⏲️","⏳","⌛","🕰️"]
NC10_EMOJI = ["🥷","🤺","👺","👹","👻","💀","☠️","🤖","👽","👾",
              "🧙‍♂️","🧙‍♀️","🧚‍♂️","🧚‍♀️","🧛‍♂️","🧛‍♀️","🧜‍♂️","🧜‍♀️",
              "🧝‍♂️","🧝‍♀️","🧞‍♂️","🧞‍♀️","🧟‍♂️","🧟‍♀️",
              "⚡","🔥","💥","✨","🌟","💫","🍙","🍜","🍡","🍱","🍣",
              "🍛","🍥","🍵","🍶","🥢","🌸","💮","🎏","🎐","🎋","🏮",
              "⛩️","🎎","🗻","👘","🥋","🥊","🗡️","⚔️","🏹","🛡️","🔮",
              "🪄","🧿","📜","🎮","🕹️","🎧","🖤","❤️‍🔥","👁️","🩸","💢","💨","💤"]

BOOM_HEART_CYCLE = ["❤️","🩷","🧡","💛","💚","💙","🩵","💜","🤎","🖤","🩶","🤍","💔",
                    "❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","🫀"]
NPC_FLAG_CYCLE = ["🚩","🎌","🏴","🏳️","🏳️‍🌈","🏳️‍⚧️","🏴‍☠️","🇦🇨","🇦🇩","🇦🇪","🇦🇫",
                  "🇦🇬","🇦🇮","🇦🇱","🇦🇲","🇦🇴","🇦🇶","🇦🇷","🇦🇸","🇦🇹","🇦🇺","🇦🇼",
                  "🇦🇽","🇦🇿","🇧🇦","🇧🇧","🇧🇩","🇧🇪","🇧🇫","🇧🇬","🇧🇭","🇧🇮","🇧🇯",
                  "🇧🇱","🇧🇲","🇧🇳","🇧🇴","🇧🇶","🇧🇷","🇧🇸","🇧🇹","🇧🇻","🇧🇼","🇧🇾",
                  "🇧🇿","🇨🇦","🇨🇨","🇨🇩","🇨🇫","🇨🇬","🇨🇭","🇨🇮","🇨🇰","🇨🇱","🇨🇲",
                  "🇨🇳","🇨🇴","🇨🇵","🇨🇷","🇨🇺","🇨🇻","🇨🇼","🇨🇽","🇨🇾","🇨🇿","🇩🇪",
                  "🇩🇬","🇩🇯","🇩🇰","🇩🇲","🇩🇴","🇩🇿","🇪🇦","🇪🇨","🇪🇪","🇪🇬","🇪🇭",
                  "🇪🇷","🇪🇸","🇪🇹","🇪🇺","🇫🇮","🇫🇯","🇫🇰","🇫🇲","🇫🇴","🇫🇷","🇬🇦",
                  "🇬🇧","🇬🇩","🇬🇪","🇬🇫","🇬🇬","🇬🇭","🇬🇮","🇬🇱","🇬🇲","🇬🇳","🇬🇵",
                  "🇬🇶","🇬🇷","🇬🇸","🇬🇹","🇬🇺","🇬🇼","🇬🇾","🇭🇰","🇭🇲","🇭🇳","🇭🇷",
                  "🇭🇹","🇭🇺","🇮🇨","🇮🇩","🇮🇪","🇮🇱","🇮🇲","🇮🇳","🇮🇴","🇮🇶","🇮🇷",
                  "🇮🇸","🇮🇹","🇯🇪","🇯🇲","🇯🇴","🇯🇵","🇰🇪","🇰🇬","🇰🇭","🇰🇮","🇰🇲",
                  "🇰🇳","🇰🇵","🇰🇷","🇰🇼","🇰🇾","🇰🇿","🇱🇦","🇱🇧","🇱🇨","🇱🇮","🇱🇰",
                  "🇱🇷","🇱🇸","🇱🇹","🇱🇺","🇱🇻","🇱🇾","🇲🇦","🇲🇨","🇲🇩","🇲🇪","🇲🇫",
                  "🇲🇬","🇲🇭","🇲🇰","🇲🇱","🇲🇲","🇲🇳","🇲🇴","🇲🇵","🇲🇶","🇲🇷"]
SLAVE_CAR_CYCLE = ["🚗","🚕","🚙","🚌","🚎","🏎️","🚓","🚑","🚒","🏍️"]
XXX_CYCLE_1 = ["🪬","🧿","🪅","🪆","🪃","🪚","🪓","🪤","🪡","🪢","🪞","🪟","🪦",
               "🪠","🪒","🪫","🪸","🪷","🪹","🪺","🫧","🫘","🫚","🫛","🪮","🪭",
               "🪻","🪼","🪽","🐦‍⬛","🐦‍🔥","🍋‍🟩","🍄‍🟫","⛓️‍💥","🪇","🪈","🪙",
               "🪔","🪲","🪳"]
XXX_CYCLE_2 = ["🦖","🦕","🥚","🐣","🪺","🦴","🌋","☄️","💥","🦎","🐊","🐍","🐢",
               "🐉","🐲","🦅","🪽","🌴","🌿","🪴","🪵","🍃","🪨","🏔️","🐾","👣",
               "🥩","🍖","🩸","🦷","👁️","🔬","🪓","⛏️","🔍","🧭","📜","🛡️","🏝️","⏳"]

WORDS_SLUTNC = ["LUND","TBKC","TBR","TMR","aarey चुदोड़े","BHEN CUDALE"]
GLITCH_WORDS = ["𝐆ᴜʟᴀᴍ","𝐑ᴀɴᴅɪᴋᴇ","हिजड़ा","LUND CHOOS","CHUD AB","TMKC","TMR",
                "TBKC","CVR KRR"]
CUTENC_POOL = [
    "{text}◦𓂃ːBʜꪮsᴅꫀ´-⋆͙🎀","{text}◦𓂃ːCʜɪɴꪖꪶ sꪮɴ´-⋆͙🎀",
    "{text}◦𓂃ːRꫝɴᴅɪ ʙꪮɪ´-⋆͙🎀","{text}◦𓂃ːSꪊᴀʀ´-⋆͙🎀",
    "{text}◦𓂃ːLꫝɴɢᴅꫀ ʟꪊᴅꪮ´-⋆͙🎀","{text}◦𓂃ːCʜꪊᴅꫝʏɪ ᴋʜꫝɴꫀ´-⋆͙🎀",
    "{text}◦𓂃ːBʜꪮsᴅɪᴋᴀ´-⋆͙🎀","{text}◦𓂃ːLꪊɴᴅ ᴘꫀ´-⋆͙🎀",
    "{text}◦𓂃ːKꪊᴛᴛɪʏꫝ´-⋆͙🎀","{text}𓂃ːCʜꪊᴅ ɢʏꪖ´-⋆͙🎀",
    "{text}◦𓂃ːMꪮꪮᴛ ᴘɪ´-⋆͙🎀","{text}◦𓂃ːBꫀᴛɪ ᴛᴍᴋᥴ´-⋆͙🎀",
]

KAIDONC_TPL = [
    "{text} Hᴇʏ Mғ I'ʟʟ Fᴜᴄᴋ Yᴏᴜʀ Mᴏᴍ Sᴏ Hᴀʀᴅ Tʜᴀᴛ Sʜᴇ Cᴀɴᴛ Eᴠᴇɴ Wᴀᴋᴇ Uᴘ ❕❔",
    "{text} Sʟᴜᴛ Gᴏ Asᴋ Uʀ Mᴏᴍ Wʜᴏ Is Yᴏᴜʀ Rᴇᴀʟ Dᴀᴅ❕❔",
    "{text} Yᴏᴜʀ Mᴏᴍᴍᴀ Gᴏᴛ A Gᴏᴏғʏ Gɪᴀɴᴛ Ass Lᴍᴀᴏ❕❔",
    "{text} Iᴍ Sᴏʀʀʏ Bᴜᴛ Yᴏᴜʀ Mᴏᴍ Dɪᴇᴅ Wʜɪʟᴇ Fᴜᴄᴋɪɴɢ Wɪᴛʜ Mᴇ❕❔",
    "{text} Hᴇʏ Sᴏɴ Oғ A Bɪᴛᴄʜ Gᴏ Cᴀʟʟ Yᴏᴜʀ Sɪs I Wᴀɴᴛ Tᴏ Fᴜᴄᴋ Hᴇʀ Bᴀᴅʟʏ❕❔",
]

BOOMNC_TPL = """{text} {emojie} 匚卄ㄩ卩 ᥅ꪖꪀᦔﺃᛕꫀ ᥇ꪖᥴᥴ𝙃ꫀ 𒐫𒈙𒐫🩵𒈙⭕️𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙⭕️
 𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙⭕️𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵 𒐫𒈙𒐫⭕️🩵"""

NPCNC_TPL = ("{emojie} {text} 𝗡𝗣𝗖 𝗕𝗔𝗔𝗣 𝗛𝗔𝗜 𝗧𝗘𝗥𝗜 𝗖𝗛⭕️𝗧𝗘𝗬 🤣"
             + ("---𝄞{emojie}𝄢" * 45))
SLAVENC_TPL = ("<{emojie}> {text} "
               "⭕️✳️🔻🔺⭕️✳️🔻🔺🔻⭕️✳️🔻🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻"
               "⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻"
               "⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻✳️🔺🔻✳️⭕️🔺🔻✳️⭕️🔺🔻"
               "⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻"
               "⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻"
               "⭕️✳️🔺⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️✳️🔺🔻"
               "⭕️✳️🔺🔻⭕️✳️🔺🔻✳️🔺⭕️✳️🔺🔻⭕️✳️🔺🔻⭕️")
XXXNC_TPL = ("{emojie1} {text} " + "{emojie1}{emojie2}" * 50)

RULERNC_TPL = [
    "{text} 🐳 Wʜꫝʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐳" * 65,
    "{text} 🐬 Dᴏʟᴘʜɪɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐬" * 65,
    "{text} 🦄 Uɴɪᴄᴏʀɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦄" * 65,
    "{text} 🦎 Lɪᴢꫝʀᴅ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦎" * 65,
    "{text} 🐉 Dʀꫝɢᴏɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐉" * 65,
    "{text} 🐼 Pꫝɴᴅꫝ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐼" * 65,
    "{text} 🐒 Mᴏɴᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐒" * 65,
    "{text} 🐍 Sɴꫝᴋᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐍" * 65,
    "{text} 🐙 Oᴄᴛᴏᴘꪊs ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐙" * 65,
    "{text} 🦩 Fʟꫝᴍɪɴɢᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦩" * 65,
    "{text} 🦇 ʙꫝᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦇" * 65,
    "{text} 🦔 Pᴏʀᴄꪊᴘɪɴᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦔" * 65,
    "{text} 🦜 Pꫝʀʀᴏᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦜" * 65,
    "{text} 🪼 Jᴇʟʟʏғɪsʜ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🪼" * 65,
    "{text} 🐯 Tɪɢᴇʀ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐯" * 65,
    "{text} 🦁 Lɪᴏɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦁" * 65,
    "{text} 🐊 Cʀᴏᴄᴏᴅɪʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐊" * 65,
    "{text} 🦒 Gɪʀꫝғғᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦒" * 65,
    "{text} 🐘 Eʟᴇᴘʜꫝɴᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐘" * 65,
    "{text} 🦊 Fᴏx ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦊" * 65,
    "{text} 🐸 Fʀᴏɢ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐸" * 65,
    "{text} 🦀 Cʀꫝʙ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦀" * 65,
    "{text} 🐢 Tᴜʀᴛʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐢" * 65,
    "{text} 🦓 Zᴇʙʀꫝ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦓" * 65,
    "{text} 🦏 Rʜɪɴᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦏" * 65,
    "{text} 🐙 Oᴄᴛᴏᴘᴜs ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐙" * 65,
    "{text} 🦃 Tᴜʀᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦃" * 65,
    "{text} 🦘 Kᴀɴɢᴀʀᴏᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦘" * 65,
    "{text} 🐝 Bᴇᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐝" * 65,
    "{text} 🦋 Bᴜᴛᴛᴇʀғʟʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦋" * 65,
    "{text} 🐗 Wɪʟᴅ Bᴏᴀʀ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐗" * 65,
    "{text} 🐿️ Sǫᴜɪʀʀᴇʟ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐿️" * 65,
    "{text} 🐠 Fɪsʜ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐠" * 65,
    "{text} 🏆 ʙᴀᴛᴍᴀɴ ɢᴀᴡᴅ ɪs ʙᴄᴋ ᴍᴅᴄ 🔥 " + "🏆🔥" * 25,
    "{text} 💎 ᴅɪᴀᴍᴏɴᴅ sᴇʏ ᴍᴀ ᴄʜᴜᴅᴀ ʟᴇʏ 🔱 " + "💎🔱" * 25,
    "{text} ⚡ ᴛᴇʀʏ ᴍᴀ ɴᴀᴅɪ ᴍᴇ ᴄʜᴜᴅɴʏ ᴊᴀʀʏ 🌊 " + "⚡🌊" * 25,
    "{text} 🔱 ᴛᴇʀʏ ᴍᴀ ʙᴛs ʟᴏʙᴇʀ ᴛᴍᴋʙ 💜 " + "🔱💜" * 25,
    "{text} 🔥 ᴛᴇʀʏ ᴍᴀ ᴋɪ ʜᴛʏᴀ ᴋʀᴋᴇʏ ᴊʟᴀ ᴅʏᴀ 💫 " + "🔥💫" * 25,
    "{text} 🌟 ᴛᴇʀʏ ᴍᴀ ᴋʏ ɢɴᴅ ᴛᴀʀᴇʏ ᴋɪ ᴛʀʜ ᴄʜᴍᴋ ʀʜɪ ʜᴇʏ ⭐ " + "🌟⭐" * 25,
    "{text} 🔱 ᴛʀɪᴘʟᴇ ᴘᴏᴡᴇʀ sᴇʏ ᴍᴀ ᴄʜᴏᴅᴜɴɢᴀ 💥 " + "🔱🔥💥" * 20,
    "{text} 🏆 ʏᴇ ᴅᴇᴋʜ ᴛʀᴏᴘʜʏ ᴛᴇʀʏ ᴍᴀ ᴄᴏᴅɴᴇʏ ᴋɪʏ ⚡ " + "🏆⚡" * 25,
    "{text} 💥 ᴛᴇʀʏ ᴍᴀ ᴋᴏ ᴄʜᴏᴅᴋʏ ᴇxᴘʟᴏsɪᴏɴ ʜᴏɢʏᴀ💥 " + "💥" * 50,
    "{text} 🔱 ᴛᴇʀʏ ᴍᴀ ᴋᴏᴡ ᴇʟᴇᴄᴛʀɪᴄɪᴀɴ ᴄʜᴏᴅ ʀʜᴀ  🔱 " + "🔱" * 50,
]

NC1_TPL = [
    "𓆩😂𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😂𓆪ྀ࿐",
    "𓆩😁𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😁𓆪ྀ࿐",
    "𓆩😭𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😭𓆪ྀ࿐",
    "𓆩😘𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😘𓆪ྀ࿐",
    "𓆩🥰𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥰𓆪ྀ࿐",
    "𓆩😍𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😍𓆪ྀ࿐",
    "𓆩🥳𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥳𓆪ྀ࿐",
    "𓆩☺️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩☺️𓆪ྀ࿐",
    "𓆩🤤𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤤𓆪ྀ࿐",
    "𓆩😋𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😋𓆪ྀ࿐",
    "𓆩😝𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😝𓆪ྀ࿐",
    "𓆩😔𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😔𓆪ྀ࿐",
    "𓆩🥺𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥺𓆪ྀ࿐",
    "𓆩🤭𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤭𓆪ྀ࿐",
    "𓆩🥱𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥱𓆪ྀ࿐",
    "𓆩😱𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😱𓆪ྀ࿐",
    "𓆩🤗𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤗𓆪ྀ࿐",
    "𓆩😤𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😤𓆪ྀ࿐",
    "𓆩😮‍💨𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😮‍💨𓆪ྀ࿐",
    "𓆩😡𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😡𓆪ྀ࿐",
    "𓆩😳𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😳𓆪ྀ࿐",
    "𓆩🤮𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤮𓆪ྀ࿐",
    "𓆩😇𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😇𓆪ྀ࿐",
    "𓆩🤡𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤡𓆪ྀ࿐",
    "𓆩💀𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩💀𓆪ྀ࿐",
    "𓆩👹𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👹𓆪ྀ࿐",
    "𓆩👺𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👺𓆪ྀ࿐",
    "𓆩👾𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👾𓆪ྀ࿐",
    "𓆩🌚𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🌚𓆪ྀ࿐",
    "𓆩💢𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩💢𓆪ྀ࿐",
    "𓆩🕸️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🕸️𓆪ྀ࿐",
    "𓆩⭕️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩⭕️𓆪ྀ࿐",
]

NC6_TPL  = "×{emoji}×{text} ꜱᴀʏ ʟᴜꜰꜰʏ ᴅᴀᴅᴅʏ ×{emoji}×"
NC7_TPL  = ("*{emoji}* {text} KAMZOR PILLA "
            + ("⟲ ⟳ "*40)
            + "{emoji} ⟳ ⟲ ⟳ ⟲ ⟳ ⟲ ⟳ ⟲ ⟳ ⟲ ⟳ ⟲ ⟳ ⟲ "
            + "{emoji}")
NC8_TPL  = ("⧼{emoji}⧽{text} LUND PE AAKE NAACH 🩷🩵⭕️🤍💚🩶🖤❤️💙 ꧁, ꧂ 🤎🧡💜💛🩷🩵 ꧁, ꧂ 🤍💚⭕️🩶🖤❤️⭕️💙🤎🧡💜⭕️💛🩷🩵🤍💚🩶🖤❤️ ꧁, ꧂ 💙🤎🧡⭕️💜⭕️ ꧁, ꧂ 💛🩷⭕️🩵🤍💚⭕️🩶🖤❤️💙🤎🧡💜💛🩷🩵 ꧁, ꧂ "*8)
NC9_TPL  = ("<{emoji}>︵୨{text}୧₊KUTTIYA "
            + ("𒈙𒈔𒈙𒈔𒈙𒈔🔴" * 70))
NC10_TPL = ("☣️───《{text}》‧︵‿{emoji}‿︵‧ ☬ PILLO KI T⭕️LI 🥀 "
            + ("𒐫" * 64)
            + "《🤣》───☣️ 🤣{emoji}🤣")

MODE_MAP = {
    "spam":      ["#{text} #𝗚𝗔𝗡𝗗𝗠𝗔𝗥𝗘 𝗧𝗘𝗥𝗜 𝗜𝗧𝗡𝗜 𝗛𝗜𝗠𝗠𝗔𝗧 𝗧𝗨 #𝗟𝗨𝗙𝗙𝗬 𝗕𝗔𝗔𝗣 𝗞𝗘 𝗦𝗔𝗠𝗡𝗘 #𝗔𝗪𝗔𝗭 𝗨𝗖𝗛𝗜 𝗞𝗥𝗘𝗚𝗔 ?? 𝗠𝗔𝗗𝗥𝗖𝗛⭕️𝗗 🤍🌙🕊️_____________________/"*25],
    "msg":       ["{text} 💀"],
    "gearspam":  ["⮑{text}⮐ #γє #ριℓℓE #gαяєєϐ #мαα #κι #gαяєєϐ #ϲнυτ #ѕє #иικℓE #нυE #κєє∂E #нαι⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ [PILL⭕️ KI ~ T⭕️LI] "
                  ". ݁₊ ⊹ . ݁˖ . ݁𓂃"*10],
    "chud":      ["{text} Tᴇʀɪ Dᴀᴅɪ ᴋ ᴄʜᴍᴜᴛ ᴍᴀɪ ᴛᴀɴɢ ᴀᴛᴋᴀ ᴅᴜɴɢᴀ 😍"],
    "title":     ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 🔥 " + "𒐫"*40],
    "nc":        ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 🔥 " + "𒐫"*40],
    "slutnc":    ["{text} {word} 𒐫𒐫𒐫❌𒐫❌𒐫🩷𒐫𒐫✳️❌ 𒐫🩷𒐫𒐫✅𒐫❌𒐫𒐫🩷𒐫🩷 ➴ྀ࿐ 𒐫𒐫𒐫❌𒐫❌𒐫𒐫𒐫✳️❌ 𒐫𒐫𒐫✅𒐫❌𒐫𒐫𒐫 ➴ྀ࿐ 𒐫🩷𒐫𒐫❌𒐫❌𒐫𒐫𒐫✳️❌ 𒐫🩷𒐫𒐫✅𒐫❌𒐫🩷𒐫𒐫 ➴ྀ࿐ ··"],
    "kaidonc":   KAIDONC_TPL,
    "ncblast":   ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ {emoji} " + "𒐫"*54],
    "blastnc":   ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ {emoji} " + "𒐫"*54],
    "pilla":     ["{text} 𝐓ᴇʀ𝐈 𝐌ᴀ𝐀 𝐂ʜ⭕𝐃 𝐃△ʟᴇɴɢ𝐄 <{emoji}>"],
    "gulam":     ["[{emoji}] {text} GULAM CHUD " + "❌⭕️"*30],
    "hasy":      ["{text} ᑕʜᴜƿ RΛɴᴅʏᴋΣ" + "𓍯😂"*22 + "〘{emoji}〙"],
    "luffygod":  ["𓆩{emoji}𓆪 {text} ʟᴀɢᴀ ᴛᴇʀʏ ᴍᴀᴀ ᴋɪ ᴄʜᴏᴏᴛ ᴋᴀ ᴅᴀᴍᴍ "
                  + "𓆩ᥫ᭡𓆪⭕️"*70 + " 𝗧ᴍᴋᴄ 🅜🅐🅘 𝗞ᴇʟᴀ 🛕🍌"],
    "filternc":  ["{text} 𝙈𝘼𝘿𝘼𝙍𝘾𝙃⭕𝘿" + "𒐫𒐫𒐫{emoji}"*23],
    "vegetagawd":["『{emoji}> {text} 𝙖𝙖𝙜 𝙡𝙖𝙜𝙞 𝙝 𝙗𝙖𝙨𝙩𝙞 𝙢 𝙩𝙚𝙧𝙞 𝙢𝙖𝙖 𝙘𝙝𝙪𝙙𝙧𝙞 𝙢𝙖𝙨𝙩𝙞 𝙢 "
                  "🍷━━━》💜🩷💚💛🤍🩷💜❤️🖤💛🩷💜🧡🖤❤️🤎🧡🖤🩷💜🤍🩷💜❤️🖤💛🤍🩷💜🩶💛❤️🤍🩷💜🖤💛💜🩷💛🩶💜🧡🖤🩷💜🧡🖤🩷💜🧡🖤💙🩷💜❤️💚🧡🩷💙🧡🖤🩷💙❤️🖤💛🩷💜💛🖤❤️━━━》🍷━━》━━━━━━》🍷━━━━》🍷━━━━━"],
    "glitchnc":  ["{text} {word} 🐷 " + "𒈔𒈔𒈔🩷"*20],
    "glitch":    ["{text} {word} 🐷 " + "𒈔𒈔𒈔🩷"*20],
    "cutenc":    ["{cut} {text}"],
    "nc1":       NC1_TPL,
    "nc2":       ["{emoji} {text} ᑕᕼᑌᑭ ᗰᗩᴋᴇᒪᴏᗪᴇ " + "𒈙✳️"*25],
    "nc3":       ["<{emoji}> {text} " + "𒅄𒅄𒅄🍌𒅄𒅄𒅄𒅄🍷"*10],
    "nc4":       ["({emoji})‧︵‿₊୨{text}୧₊‿︵‧{text}₊⊹ 𝐓ᴇʀɪ 𝐌ᴀᴀ सूरज ☀️ "
                  "𝐍ɪᴋᴀʟɴᴇ 𝐒ᴇ 𝐏ᴀʜʟᴇ 𝐇ᴇ 𝐂ʜᴏᴅ 𝐃ᴜ 👈 🟡 ({emoji})"],
    "nc5":       ["<{text}>Cʜꪊᴅ ɢʏꪖ"+"𒅒❤️"*48],
    "nc6":       [NC6_TPL],
    "nc7":       [NC7_TPL],
    "nc8":       [NC8_TPL],
    "nc9":       [NC9_TPL],
    "nc10":      [NC10_TPL],
    "both":      ["{text} SAY LUFFY DADDY STOP!! " + "𒐫"*30],
    "blast":     ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 💣 " + "𒐫"*40],
    "boomnc":    [BOOMNC_TPL],
    "rulernc":   RULERNC_TPL,
    "npcnc":     [NPCNC_TPL],
    "slavenc":   [SLAVENC_TPL],
    "xxxnc":     [XXXNC_TPL],
}

photo_pool: list[bytes] = []


# ═══════════════════════════════════════════════════════════════
# ☢️  NUCLEAR STOP SYSTEM
# ═══════════════════════════════════════════════════════════════

ALL_LOOP_KINDS = {
    "spam","gearspam","chud","msg","both","blast",
    "swipe","pfp","desc",
    "title","nc",
    "nc1","nc2","nc3","nc4","nc5","nc6","nc7","nc8","nc9","nc10",
    "slutnc","kaidonc","ncblast","blastnc",
    "pilla","gulam","hasy","luffygod",
    "filternc","vegetagawd","glitchnc","glitch","cutenc",
    "boomnc","rulernc","npcnc","slavenc","xxxnc",
    "spamwatch_counter","generic",
}
NC_KINDS = {k for k in ALL_LOOP_KINDS
            if k not in ("spam","gearspam","msg","chud",
                         "both","blast","swipe","pfp","desc",
                         "spamwatch_counter","generic")}
SPAM_KINDS = {"spam","gearspam","msg","chud","both","blast"}

def nuke_chat(chat_id: int, wipe_state: bool = True) -> dict:
    stats = {}
    before = len(TASKS.get(chat_id, []))
    cancel_tasks(chat_id, None)
    stats["tasks_killed"] = before
    TASKS.pop(chat_id, None)
    stats["swipe_was_on"] = bool(SWIPE_ON.get(chat_id))
    SWIPE_ON[chat_id] = False
    if wipe_state:
        CHUD_TEXT.pop(chat_id, None)
        SWIPE_MSG.pop(chat_id, None)
        SWIPE_SRC.pop(chat_id, None)
        spamwatch_chats.pop(chat_id, None)
        _sw_bursts.pop(chat_id, None)
        DESC_LOOP.pop(chat_id, None)
        stats["spamwatch_off"] = True
    else:
        stats["spamwatch_off"] = False
    photo_pool.clear()
    return stats

async def _kill_kinds(chat_id: int, kinds: set) -> int:
    if chat_id not in TASKS: return 0
    keep, killed = [], 0
    for t in TASKS[chat_id]:
        k = getattr(t, "_kind", "generic")
        if k in kinds:
            t.cancel(); killed += 1
        else:
            keep.append(t)
    TASKS[chat_id] = keep
    return killed


# ═══════════════════════════════════════════════════════════════
# 🔁  RENDER + LOOPS
# ═══════════════════════════════════════════════════════════════
def _render(template: str, base: str, idx: int) -> str:
    out = template.replace("{text}", base)
    out = out.replace("{text}", base)
    if "{emojie1}" in out or "{emojie2}" in out:
        out = out.replace("{emojie1}", XXX_CYCLE_1[idx % len(XXX_CYCLE_1)])
        out = out.replace("{emojie2}", XXX_CYCLE_2[idx % len(XXX_CYCLE_2)])
    if "{emojie}" in out:
        if "匚卄ㄩ卩" in out: pool = BOOM_HEART_CYCLE
        elif "NPC KE AAGE NAACH" in out: pool = NPC_FLAG_CYCLE
        elif "⭕️✳️🔻🔺" in out: pool = SLAVE_CAR_CYCLE
        else: pool = BLASTNC_EMOJI
        out = out.replace("{emojie}", pool[idx % len(pool)])
    if "{emoji}" in out:
        pool = BLASTNC_EMOJI
        if "GULAM" in out or ("CHUD" in out and "❌⭕️" in out): pool = GULAM_EMOJI
        elif "ᑕʜᴜƿ" in out: pool = HASY_EMOJI
        elif "𓆩" in out and "ʟᴀɢᴀ" in out: pool = LUFFYGOD_EMOJI
        elif "𝙈𝘼𝘿𝘼𝙍𝘾𝙃" in out: pool = FILTER_EMOJI
        elif "『" in out and "𝙖𝙖𝙜" in out: pool = VEGETA_EMOJI
        elif "ᑕᕼᑌᑭ" in out: pool = NC2_EMOJI
        elif "𒅄" in out: pool = NC3_EMOJI
        elif "सूरज" in out: pool = NC4_EMOJI
        elif "𒅒" in out: pool = NC5_EMOJI
        elif "𝐓ᴇʀ𝐈" in out: pool = PILLA_EMOJI
        elif "ꜱᴀʏ ʟᴜꜰꜰʏ ᴅᴀᴅᴅʏ" in out: pool = NC6_EMOJI
        elif "KAMZOR PILLA" in out: pool = NC7_EMOJI
        elif "LUND PE AAKE NAACH" in out: pool = NC8_EMOJI
        elif "KUTTIYA" in out: pool = NC9_EMOJI
        elif "PILLO KI T" in out: pool = NC10_EMOJI
        out = out.replace("{emoji}", pool[idx % len(pool)])
    if "{word}" in out:
        pool = WORDS_SLUTNC if "𒐫" in out else GLITCH_WORDS
        out = out.replace("{word}", pool[idx % len(pool)])
    if "{cut}" in out:
        out = out.replace("{cut}", CUTENC_POOL[idx % len(CUTENC_POOL)])
    return out


async def bot_loop(bot: Bot, bot_id: int, chat_id: int,
                   base: str, mode: str, reply_to_id=None):
    guard     = get_limiter(bot_id)
    templates = MODE_MAP.get(mode, emox_EMOJIS)
    i, tick   = 0, 0
    while True:
        try:
            raw = templates[i % len(templates)]
            txt = _render(raw, base, i) + guard.suffix(i)
            if mode in FAST_MODES:
                tick += 1
                if tick % 12 == 0:
                    try: await bot.get_chat(chat_id)
                    except Exception: pass
            if mode in BOTH_MODES:
                await asyncio.gather(
                    guard.send_message(bot, chat_id, txt,
                                       reply_to_message_id=reply_to_id),
                    guard.set_chat_title(bot, chat_id, txt),
                    return_exceptions=True)
            elif mode in TITLE_MODES:
                await guard.set_chat_title(bot, chat_id, txt)
            else:
                m = await guard.send_message(bot, chat_id, txt,
                                             reply_to_message_id=reply_to_id)
                if mode in PIN_MODES and AUTOPIN.get(chat_id, True) and m:
                    try:
                        await guard.pin_chat_message(
                            bot, chat_id, m.message_id,
                            disable_notification=True)
                    except Exception:
                        pass
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.01)


async def photo_loop(bot: Bot, bot_id: int, chat_id: int):
    guard, i = get_limiter(bot_id), 0
    while True:
        try:
            if not photo_pool:
                await asyncio.sleep(0.5); continue
            bio = BytesIO(photo_pool[i % len(photo_pool)]); bio.name = "pfp.jpg"
            await guard.set_chat_photo(bot, chat_id, bio)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.1)


async def swipe_loop(bot: Bot, bot_id: int, chat_id: int,
                     text: str, reply_to_id=None):
    guard = get_limiter(bot_id); i = 0
    while SWIPE_ON.get(chat_id, False):
        try:
            await guard.send_message(bot, chat_id, text + guard.suffix(i),
                                     reply_to_message_id=reply_to_id)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.01)


async def desc_loop(bot: Bot, bot_id: int, chat_id: int, text: str):
    guard = get_limiter(bot_id); i = 0
    while True:
        try:
            tpl = DESC_TEMPLATES[i % len(DESC_TEMPLATES)]
            desc = tpl.replace("{text}", text)
            await guard.set_chat_description(bot, chat_id, desc)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.05)


DESC_TEMPLATES = [
    "{text} ─ CHUDAI K BAKRE",
    "🕸️ {text}",
    "{text}  𓆩ᥫ᭡𓆪",
    "🌊 {text} ─ LUFFY KE PILLE",
    "{text}  ༄༄༄",
    "❄️ {text} ❄️",
    "{text}  🕸️ AUR ZOR LAGA IDHR MTT DEKH 🤣",
    "🔥 {text} 🔥",
    "{text} ─ CHUDAI KE PILLE 🌊",
    "⸎❄️ {text}",
]


async def promote_all_bots(chat_id: int) -> list[str]:
    promoter = None
    for app in ALL_APPS:
        try:
            me = await app.bot.get_chat_member(chat_id, app.bot.id)
            if getattr(me, "can_promote_members", False):
                promoter = app.bot; break
        except Exception: continue
    if promoter is None:
        return ["❌ Kisi bot ke paas 'Add Admins' permission nahi hai."]
    results = []
    for app in ALL_APPS:
        b = app.bot
        if b.id == promoter.id: continue
        try:
            await promoter.promote_chat_member(
                chat_id=chat_id, user_id=b.id,
                can_change_info=True, can_delete_messages=True,
                can_invite_users=True, can_restrict_members=True,
                can_pin_messages=True, can_promote_members=True,
                can_manage_chat=True, can_manage_video_chats=True,
                can_post_messages=True, can_edit_messages=True,
                can_post_stories=True, can_edit_stories=True,
                can_delete_stories=True, is_anonymous=False)
            bme = await b.get_me()
            results.append(f"✅ {bme.first_name} (@{bme.username})")
        except Exception as e:
            results.append(f"❌ bot#{b.id}: {str(e)[:60]}")
    return results


def _track_burst(chat_id: int, user_id: int) -> bool:
    now = time.monotonic()
    bucket = _sw_bursts.setdefault(chat_id, {}).setdefault(user_id, [])
    bucket.append(now)
    _sw_bursts[chat_id][user_id] = [t for t in bucket if now - t <= SW_WINDOW]
    return len(_sw_bursts[chat_id][user_id]) >= SW_THRESH


async def _trigger_spamwatch(chat_id: int, rival_id: int, notify_id: int):
    st = spamwatch_chats.get(chat_id)
    if not st: return
    now = time.monotonic()
    if now - st.get("last_trigger", 0.0) < 0.5: return
    st["last_trigger"] = now
    st["active_rival"] = rival_id
    st["counter_on"]   = True
    try:
        rival = await ALL_APPS[0].bot.get_chat(rival_id)
        handle = f"@{rival.username}" if rival.username else (rival.first_name or str(rival_id))
    except Exception:
        handle = str(rival_id)
    cancel_tasks(chat_id, {"spamwatch_counter"})
    text = f"{handle} +TMKC PILLE 🔥"
    for app in ALL_APPS:
        t = asyncio.create_task(
            bot_loop(app.bot, app.bot.id, chat_id, text, SW_COUNTER, notify_id))
        add_task(chat_id, t, kind="spamwatch_counter")
        await asyncio.sleep(0.002)


# ═══════════════════════════════════════════════════════════════
# 💬  COMMAND PARSER
# ═══════════════════════════════════════════════════════════════
def parse_cmd(text: str):
    if not text or not text.startswith(PREFIX): return None, ""
    body = text[len(PREFIX):].strip()
    if not body: return None, ""
    parts = body.split(maxsplit=1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else "")


# ═══════════════════════════════════════════════════════════════
# 🔤  FONT GENERATOR
# ═══════════════════════════════════════════════════════════════
def _uni_map(upper: int, lower: int, digit: int | None = None,
             override: dict | None = None) -> dict:
    m = {}
    for i in range(26):
        m[chr(ord('A') + i)] = chr(upper + i)
        m[chr(ord('a') + i)] = chr(lower + i)
    if digit is not None:
        for i in range(10):
            m[chr(ord('0') + i)] = chr(digit + i)
    if override: m.update(override)
    return m

_FONT_DEFS = [
    ("Bold",              _uni_map(0x1D400, 0x1D41A, 0x1D7CE)),
    ("Italic",            _uni_map(0x1D434, 0x1D44E, None, {"h": "ℎ"})),
    ("Bold Italic",       _uni_map(0x1D468, 0x1D482)),
    ("Script",            _uni_map(0x1D49C, 0x1D4B6, None, {
        "B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ",
        "M": "ℳ", "R": "ℛ", "e": "ℯ", "g": "ℊ", "o": "ℴ"})),
    ("Bold Script",       _uni_map(0x1D4D0, 0x1D4EA)),
    ("Fraktur",           _uni_map(0x1D504, 0x1D51E, None, {
        "C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ"})),
    ("Double-Struck",     _uni_map(0x1D538, 0x1D552, 0x1D7D8, {
        "C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"})),
    ("Sans Bold",         _uni_map(0x1D5D4, 0x1D5EE, 0x1D7EC)),
    ("Sans Italic",       _uni_map(0x1D608, 0x1D622)),
    ("Sans Bold Italic",  _uni_map(0x1D63C, 0x1D656)),
    ("Monospace",         _uni_map(0x1D670, 0x1D68A, 0x1D7F6)),
    ("Fullwidth",         _uni_map(0xFF21, 0xFF41, 0xFF10)),
    ("Circled",           _uni_map(0x24B6, 0x24D0, None, {
        "0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④",
        "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"})),
    ("Squared",           _uni_map(0x1F130, 0x1F130)),
]
_SMALLCAPS = {
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ꜰ','g':'ɢ','h':'ʜ','i':'ɪ',
    'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
    's':'ꜱ','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ'}
_SUPERSCRIPT = {
    'a':'ᵃ','b':'ᵇ','c':'ᶜ','d':'ᵈ','e':'ᵉ','f':'ᶠ','g':'ᵍ','h':'ʰ','i':'ⁱ',
    'j':'ʲ','k':'ᵏ','l':'ˡ','m':'ᵐ','n':'ⁿ','o':'ᵒ','p':'ᵖ','q':'ᑫ','r':'ʳ',
    's':'ˢ','t':'ᵗ','u':'ᵘ','v':'ᵛ','w':'ʷ','x':'ˣ','y':'ʸ','z':'ᶻ',
    '0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
_FLIP = {
    'a':'ɐ','b':'q','c':'ɔ','d':'p','e':'ǝ','f':'ɟ','g':'ƃ','h':'ɥ','i':'ᴉ',
    'j':'ɾ','k':'ʞ','l':'l','m':'ɯ','n':'u','o':'o','p':'d','q':'b','r':'ɹ',
    's':'s','t':'ʇ','u':'n','v':'ʌ','w':'ʍ','x':'x','y':'ʎ','z':'z',
    'A':'∀','B':'𐐒','C':'Ɔ','D':'◖','E':'Ǝ','F':'Ⅎ','G':'⅁','H':'H','I':'I',
    'J':'ſ','K':'ʞ','L':'˥','M':'W','N':'N','O':'O','P':'Ԁ','Q':'Ό','R':'ᴚ',
    'S':'S','T':'┴','U':'∩','V':'Λ','W':'M','X':'X','Y':'⅄','Z':'Z',
    '0':'0','1':'Ɩ','2':'ᄅ','3':'Ɛ','4':'ㄣ','5':'ϛ','6':'9','7':'ㄥ','8':'8','9':'6'}

def _apply_font(text: str, mapping: dict) -> str:
    return "".join(mapping.get(c, c) for c in text)
def _combining(text: str, comb: str) -> str:
    return "".join(c + comb for c in text if c != " ").replace(comb + " ", " ")

def generate_fonts(text: str) -> str:
    lines = ["🎨 <b>LUFFY FONT FORGE</b>", ""]
    for name, mp in _FONT_DEFS:
        lines.append(f"<b>{name}:</b>\n<code>{_apply_font(text, mp)}</code>")
    lines.append(f"<b>Small Caps:</b>\n<code>{_apply_font(text, _SMALLCAPS)}</code>")
    lines.append(f"<b>Superscript:</b>\n<code>{_apply_font(text, _SUPERSCRIPT)}</code>")
    lines.append(f"<b>Upside Down:</b>\n<code>{_apply_font(text, _FLIP)[::-1]}</code>")
    lines.append(f"<b>Strikethrough:</b>\n<code>{_combining(text, chr(0x0336))}</code>")
    lines.append(f"<b>Underline:</b>\n<code>{_combining(text, chr(0x0332))}</code>")
    lines.append(f"<b>Double Underline:</b>\n<code>{_combining(text, chr(0x0333))}</code>")
    lines.append(f"<b>Wavy:</b>\n<code>{_combining(text, chr(0x0330))}</code>")
    return "\n\n".join(lines)


def _tts_sync(text: str, lang: str = "en") -> bytes:
    if not _HAS_GTTS:
        raise RuntimeError("gtts not installed — pip install gTTS")
    tts = gTTS(text=text, lang=lang)
    buf = BytesIO(); tts.write_to_fp(buf); return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# 🖼️  MENU
# ═══════════════════════════════════════════════════════════════
async def send_menu(chat_id, msg, bot):
    menu = (
        "⸎❄️ ๑ஓ═══════════════╗\n"
        f"{fancy('LUFFY ENGINE')}  🕸️\n"
        "╚═══════════════ஓ๑\n\n"
        "🕸️ <b>GC LOOPS</b>\n"
        "  slutnc · kaidonc · ncblast · pilla\n"
        "  gulam · hasy · luffygod\n\n"
        "🌊 <b>LUFFY NC — NEW</b>\n"
        "  boomnc · rulernc · npcnc\n"
        "  slavenc · xxxnc\n\n"
        "🌷 <b>SPECIAL NCS</b>\n"
        "  filternc · vegetagawd · glitchnc\n"
        "  cutenc · nc1 · nc2 · nc3 · nc4 · nc5\n"
        "  nc6 · nc7 · nc8 · nc9 · nc10\n\n"
        "🛑 <b>STOP CMDS</b>\n"
        "  zero · shutdown · stopall · panic\n"
        "  stopgear · stopspam · stopsw · stopnc\n"
        "  spamwatchoff · zerogcnc\n"
        "  freezeslide · zeroslidespam · spic\n"
        "  freeze a,b,c  (or 'all')\n\n"
        "🖤 <b>SPAM CMDS</b>\n"
        "  chud · spam · gearspam · msg · both · blast\n\n"
        "🎨 <b>FUN STUFF</b>\n"
        "  ~f &lt;text&gt;   — font forge\n"
        "  ~v &lt;text&gt;   — voice note\n"
        "  ~ai &lt;prompt&gt; — image gen\n\n"
        "🍃 <b>SWIPE</b>  swipe · zeroswipe · pfploop\n"
        "👁️ <b>SPAMWATCH</b>  spamwatchh\n"
        "🛡️ <b>ADMIN</b>  admin\n"
        "🤝 <b>SUDO</b>  addsudo · delsudo · listsudo\n\n"
        "⛓️ <b>GEARS</b>\n"
        "  myid · ping · status · delay\n"
        "  ar · sar · setoverpic · over · menupic\n\n"
        "๑ஓ═══════════════╗\n"
        f"“ {fancy('Only LUFFY CAN Control')} 🌷\n"
        "╚═══════════════ஓ๑"
    )
    guard = get_limiter(bot.id)
    pic   = MENU_MEDIA.get(chat_id)
    if pic:
        bio = BytesIO(pic); bio.name = "menu.jpg"
        r = await guard.send_photo(bot, chat_id, bio,
                                   caption=menu, parse_mode="HTML")
        if r is None:
            await guard.send_message(bot, chat_id, menu, parse_mode="HTML")
    else:
        await guard.send_message(bot, chat_id, menu, parse_mode="HTML")


async def send_denied(bot, chat_id, msg, guard):
    name = (msg.from_user.first_name or "PILLE") if msg.from_user else "PILLE"
    text = (
        "⸎❄️  ☠️  𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃  ☠️  ⸎❄️\n"
        "╔══════════════════════════╗\n"
        f"🩸 𝐇ᴇʏ <b>{name}</b>, 𝐘ᴏᴜ 𝐀ɪɴ'ᴛ 𝐋ᴜғғʏ.\n"
        "🚫 𝐎ɴʟʏ 𝐓ʜᴇ 𝐊ɪɴɢ 𝐎ғ 𝐏ɪʀᴀᴛᴇs 𝐂ᴏᴍᴍᴀɴᴅs 𝐓ʜɪs 𝐄ɴɢɪɴᴇ.\n"
        "🛕 𝐆ᴏ 𝐂ʀʏ 𝐓ᴏ 𝐘ᴏᴜʀ 𝐌ᴏᴍᴍʏ, 𝐏ɪʟʟᴇ.\n"
        "⚔️ 𝐓ʀʏ 𝐎ɴᴇ 𝐌ᴏʀᴇ 𝐓ɪᴍᴇ & 𝐈'ʟʟ 𝐑ᴇᴘᴏʀᴛ 𝐘ᴏᴜ.\n"
        "╚══════════════════════════╝\n"
        f"“ {fancy('NPC EMPIRE')} 🦁"
    )
    try:
        await guard.send_message(bot, chat_id, text, parse_mode="HTML",
                                 reply_to_message_id=msg.message_id)
    except Exception:
        await guard.send_message(bot, chat_id, text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🎯  ROUTER
# ═══════════════════════════════════════════════════════════════
async def route(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return

    chat    = update.effective_chat
    chat_id = chat.id if chat else None
    uid     = update.effective_user.id if update.effective_user else 0
    guard   = get_limiter(ctx.bot.id)

    if update.effective_user:
        track_user(update.effective_user)
    if msg.reply_to_message and msg.reply_to_message.from_user:
        track_user(msg.reply_to_message.from_user)

    if chat_id and uid and uid != ctx.bot.id:
        if chat_id in spamwatch_chats:
            st = spamwatch_chats[chat_id]
            if uid != st.get("owner_id") and _track_burst(chat_id, uid):
                await _trigger_spamwatch(chat_id, uid, msg.message_id)

    if not msg.text: return
    cmd, arg = parse_cmd(msg.text)
    if not cmd: return

    key = (chat_id, msg.message_id)
    if key in _handled: return
    _handled[key] = None
    if len(_handled) > _HANDLED_CAP: _handled.popitem(last=False)

    bot = ctx.bot

    # ─── public ───
    if cmd == "myid":
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Your ID: {uid}")),
            reply_to_message_id=msg.message_id); return
    if cmd == "ping":
        t0 = time.monotonic()
        m = await guard.send_message(bot, chat_id,
            prefixed(fancy("Pinging...")),
            reply_to_message_id=msg.message_id)
        if m:
            await guard._gate()
            try:
                await m.edit_text(prefixed(fancy(
                    f"Pong! {(time.monotonic()-t0)*1000:.0f} ms")))
            except Exception: pass
        return

    # ─── locked doors ───
    if cmd == "menu":
        if not is_authorized(uid):
            await send_denied(bot, chat_id, msg, guard); return
        await send_menu(chat_id, msg, bot); return
    if cmd == "console":
        if not is_authorized(uid):
            await send_denied(bot, chat_id, msg, guard); return
        console = (
            "⸎❄️ <b>LUFFY CONSOLE — HIDDEN</b> ⸎❄️\n"
            "╔══════════════════════╗\n"
            "🌊 <b>LUFFY NC</b>\n"
            "  ~boomnc · ~rulernc · ~npcnc · ~slavenc · ~xxxnc\n\n"
            "🕸️ <b>ORIGINAL NCs</b>\n"
            "  nc1→nc10 · slutnc · kaidonc · ncblast\n"
            "  pilla · gulam · hasy · luffygod\n"
            "  filternc · vegetagawd · glitchnc · cutenc\n\n"
            "🛡️ <b>GC CONTROL</b>\n"
            "  ~hyper · ~unhyper\n"
            "  ~setgcname · ~setgcpic\n"
            "  ~ds &lt;text&gt;   — desc loop\n"
            "  ~chup / ~bol   — mute / unmute\n"
            "  ~purge  (reply)  — purge\n"
            "  ~maachudao &lt;text&gt; — all bots LEAVE\n\n"
            "📢 <b>BROADCAST</b>\n"
            "  ~bdc &lt;text&gt;   — broadcast to all chats\n\n"
            "☢️ <b>STOP / KILL</b>\n"
            "  ~zero · ~shutdown · ~stopall · ~panic\n"
            "  ~stopgear · ~stopspam · ~stopsw · ~stopnc\n"
            "  ~spamwatchoff · ~freeze a,b,c\n\n"
            "🎨 <b>FUN</b>\n"
            "  ~f · ~v · ~ai\n\n"
            "🎯 <b>textS</b>  ~text · ~textlist\n"
            "🔍 <b>INTEL</b>  ~details · ~bots\n"
            "╚══════════════════════╝"
        )
        await guard.send_message(bot, chat_id, console,
            parse_mode="HTML",
            reply_to_message_id=msg.message_id); return
    if cmd == "status":
        lines = [fancy("🕸️ LUFFY STATUS PANEL 🕸️"), "━━━━━━━━━━━━━━━━━━━"]
        for a in ALL_APPS:
            info = BOT_INFO.get(a.bot.id, {})
            g    = get_limiter(a.bot.id)
            lines.append(
                f"🎴 <b>#{info.get('no','?')}</b> · @{info.get('username','?')}\n"
                f"   ⚡ rate <b>{g.rate:.0f}/s</b> · 🕒 delay <b>{g.delay:.2f}s</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append(f"“ {fancy('Only LUFFY CAN Control')} 🌊")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return
    if cmd == "bots":
        if not ALL_APPS:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No bots online.")),
                reply_to_message_id=msg.message_id); return
        lines = [fancy("🕸️ LUFFY BOT ARMY 🕸️"), "━━━━━━━━━━━━━━━━━━━"]
        now = time.monotonic()
        for a in ALL_APPS:
            info = BOT_INFO.get(a.bot.id, {})
            up = int(now - START_TS)
            h, m, s = up//3600, (up%3600)//60, up%60
            lines.append(
                f"🧿 <b>#{info.get('no','?')}</b> · @{info.get('username','?')}\n"
                f"   🆔 <code>{a.bot.id}</code>\n"
                f"   ⏱️ up {h}h {m}m {s}s")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append(f"“ {fancy('NPC EMPIRE ')} 🦁")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    if not is_authorized(uid):
        await send_denied(bot, chat_id, msg, guard); return

    # ─── ~ai ───
    if cmd == "ai":
        prompt = arg.strip()
        if not prompt:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~ai <prompt>")),
                reply_to_message_id=msg.message_id); return
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🎨 Cooking… wait boss man")),
            reply_to_message_id=msg.message_id)
        try:
            seed = random.randint(1, 999999)
            url  = (f"https://image.pollinations.ai/prompt/"
                    f"{quote_plus(prompt)}?width=1024&height=1024"
                    f"&nologo=true&seed={seed}")
            async with httpx.AsyncClient(timeout=90) as cl:
                r = await cl.get(url)
                if r.status_code in (429, 402, 403) or "quota" in r.text.lower():
                    raise RuntimeError("__AI_LIMIT__")
                r.raise_for_status()
                img = BytesIO(r.content); img.name = "ai.jpg"
            await guard.send_photo(bot, chat_id, img,
                caption=prefixed(fancy(f"✨ {prompt[:180]}")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            err = str(e)
            if ("__AI_LIMIT__" in err or "429" in err
                    or "rate limit" in err.lower()
                    or "quota" in err.lower()
                    or "exceed" in err.lower()
                    or "too many" in err.lower()):
                msg_txt = fancy("🛑 AI IS OFF NOW TRY AGAIN LATER")
            else:
                msg_txt = fancy(f"❌ AI failed: {err[:80]}")
            await guard.send_message(bot, chat_id, prefixed(msg_txt),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~f font ───
    if cmd == "f":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~f <text>")),
                reply_to_message_id=msg.message_id); return
        if len(raw) > 60: raw = raw[:60]
        try:
            await guard.send_message(bot, chat_id, generate_fonts(raw),
                parse_mode="HTML", reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~v TTS ───
    if cmd == "v":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~v <text>")),
                reply_to_message_id=msg.message_id); return
        if len(raw) > 200: raw = raw[:200]
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🗣️ cooking voice…")),
            reply_to_message_id=msg.message_id)
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, _tts_sync, raw)
            bio  = BytesIO(data); bio.name = "voice.mp3"
            await guard.send_voice(bot, chat_id, bio,
                caption=prefixed(fancy(raw[:120])),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ TTS failed: {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~details ───
    if cmd == "details":
        r = msg.reply_to_message
        if not r or not r.from_user:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user's message.")),
                reply_to_message_id=msg.message_id); return
        u = r.from_user; uid_s = str(u.id); hist = USER_HIST.get(uid_s, {})
        names    = hist.get("names", []) or [((u.first_name or "") +
                    (" " + u.last_name if u.last_name else "")).strip()]
        usernames= hist.get("usernames", []) or ([u.username] if u.username else [])
        first_s  = hist.get("first_seen", "—")
        last_s   = hist.get("last_seen", "—")
        bio = "—"
        try:
            full = await bot.get_chat(u.id); bio = getattr(full, "bio", None) or "—"
        except Exception: pass
        is_bot  = "🤖 BOT" if u.is_bot else "🧑 HUMAN"
        premium = "⭐ YES" if getattr(u, "is_premium", False) else "NO"
        lang    = getattr(u, "language_code", None) or "—"
        lines = [
            fancy("🔍 USER INTEL"),
            f"🆔 <code>{u.id}</code>",
            f"👤 {(u.first_name or '') + (' ' + u.last_name if u.last_name else '')}".strip(),
            f"🏷️ @{u.username}" if u.username else "🏷️ —",
            f"🧬 {is_bot}   ⭐ {premium}",
            f"🌐 {lang}",
            "📛 Names:\n  " + ("\n  ".join(names[-5:]) or "—"),
            "🏷️ Usernames:\n  @" + ("\n  @".join(usernames[-5:]) or "—"),
            f"📅 First: {first_s}",
            f"🕒 Last : {last_s}",
            f"📝 Bio: {bio}",
            "☎️ Phone: <i>IN SIR LUFFY DM</i>",
            "📍 Address: <i>EXPOSE IN SIR LUFFY DM</i>",
        ]
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    # ─── ~text ───
    if cmd == "text":
        r = msg.reply_to_message
        if not r or not r.from_user:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        tgt = r.from_user
        nm  = ((tgt.first_name or "") + (" " + tgt.last_name if tgt.last_name else "")).strip()
        textS.setdefault(chat_id, {})[tgt.id] = nm or str(tgt.id)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"🎯 Locked: {nm} ({tgt.id})")),
            reply_to_message_id=msg.message_id); return

    if cmd == "textlist":
        tgts = textS.get(chat_id, {})
        if not tgts:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No texts yet.")),
                reply_to_message_id=msg.message_id); return
        lines = [fancy("🎯 text LIST")]
        for i, (tid, nm) in enumerate(tgts.items(), 1):
            lines.append(f"{i}. {nm}  —  <code>{tid}</code>")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    # ─── ~hyper ───
    if cmd == "hyper":
        if HYPER.get(chat_id, {}).get("on"):
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Already hyper 🔒")),
                reply_to_message_id=msg.message_id); return
        try:
            ci = await bot.get_chat(chat_id)
            try:
                raw_prev = ci.permissions.to_dict() if ci.permissions else None
            except Exception:
                raw_prev = None
            if isinstance(raw_prev, dict):
                prev = {k: bool(v) for k, v in raw_prev.items() if v is not None}
            else:
                prev = None
            HYPER[chat_id] = {"on": True, "prev": prev}
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False,
                can_change_info=False, can_invite_users=False,
                can_pin_messages=False))
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🔒 GC HYPER LOCKED")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~unhyper (FIXED) ───
    if cmd == "unhyper":
        if not HYPER.get(chat_id, {}).get("on"):
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Not locked.")),
                reply_to_message_id=msg.message_id); return
        prev = HYPER.get(chat_id, {}).get("prev")
        try:
            valid_keys = set(ChatPermissions.__slots__) \
                if hasattr(ChatPermissions, "__slots__") \
                else set(ChatPermissions().__dict__.keys())
        except Exception:
            valid_keys = {"can_send_messages","can_send_audios",
                "can_send_documents","can_send_photos","can_send_videos",
                "can_send_video_notes","can_send_voice_notes","can_send_polls",
                "can_send_other_messages","can_add_web_page_previews",
                "can_change_info","can_invite_users","can_pin_messages",
                "can_manage_topics"}
        sanitized = {}
        if isinstance(prev, dict):
            for k, v in prev.items():
                if k in valid_keys and isinstance(v, bool):
                    sanitized[k] = v
        restored = False
        if sanitized:
            try:
                await bot.set_chat_permissions(chat_id, ChatPermissions(**sanitized))
                restored = True
            except Exception as e:
                log.warning(f"unhyper restore failed: {e}")
        if not restored:
            try:
                await bot.set_chat_permissions(chat_id, ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True,
                    can_change_info=True, can_invite_users=True,
                    can_pin_messages=True))
                restored = True
            except Exception as e:
                await guard.send_message(bot, chat_id,
                    prefixed(fancy(f"❌ unlock failed: {str(e)[:100]}")),
                    reply_to_message_id=msg.message_id); return
        HYPER.pop(chat_id, None)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🔓 GC UNLOCKED ✅")),
            reply_to_message_id=msg.message_id)
        return

    # ─── ~chup — mute ───
    if cmd in ("chup", "mute"):
        try:
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False))
            MUTED[chat_id] = True
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🤐 GC MUTED — chup ho jao sab 🩸")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~bol — unmute ───
    if cmd in ("bol", "unmute"):
        try:
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=True, can_send_audios=True,
                can_send_documents=True, can_send_photos=True,
                can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True))
            MUTED.pop(chat_id, None)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🔊 GC UNMUTED — bol lo ab 🌊")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~ds — description loop ───
    if cmd == "ds":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~ds <text>")),
                reply_to_message_id=msg.message_id); return
        await _kill_kinds(chat_id, {"desc"})
        DESC_LOOP[chat_id] = {"text": raw}
        for app in ALL_APPS:
            t = asyncio.create_task(
                desc_loop(app.bot, app.bot.id, chat_id, raw))
            add_task(chat_id, t, kind="desc")
            await asyncio.sleep(0.002)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"✏️ Desc loop ON — {raw[:40]}")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopds", "dsstop"):
        killed = await _kill_kinds(chat_id, {"desc"})
        DESC_LOOP.pop(chat_id, None)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Desc loop stopped (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    # ─── ~setgcname ───
    if cmd == "setgcname":
        newname = arg.strip()
        if not newname:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~setgcname <text>")),
                reply_to_message_id=msg.message_id); return
        try:
            await bot.set_chat_title(chat_id, newname[:128])
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"✅ GC name → {newname[:60]}")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~setgcpic ───
    if cmd == "setgcpic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            bio  = BytesIO(bytes(data)); bio.name = "gc.jpg"
            await bot.set_chat_photo(chat_id, photo=bio)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ GC pic changed")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~setoverpic ───
    if cmd == "setoverpic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            OVER_MEDIA[chat_id] = bytes(data)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ Over-pic set")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~menupic ───
    if cmd == "menupic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            MENU_MEDIA[chat_id] = bytes(data)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ Menu-pic set")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ─── ~admin ───
    if cmd == "admin":
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Promoting all bots...")),
            reply_to_message_id=msg.message_id)
        results = await promote_all_bots(chat_id)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Admin results:") + "\n" + "\n".join(results)),
            reply_to_message_id=msg.message_id); return

    # ─── ~bdc — broadcast ───
    if cmd == "bdc":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~bdc <text>")),
                reply_to_message_id=msg.message_id); return
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📢 broadcasting to all chats…")),
            reply_to_message_id=msg.message_id)
        sent, failed = 0, 0
        seen = set()
        for app in ALL_APPS:
            b = app.bot
            for cid in list(_known_chats()):
                if cid in seen: continue
                seen.add(cid)
                try:
                    await get_limiter(b.id).send_message(
                        b, cid, prefixed(fancy(raw[:400])))
                    sent += 1
                except Exception:
                    failed += 1
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"📢 broadcast done · sent {sent} · failed {failed}")),
            reply_to_message_id=msg.message_id)
        return

    # ─── ~purge — delete messages (reply to start) ───
    if cmd == "purge":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to the first msg you want purged.")),
                reply_to_message_id=msg.message_id); return
        start_id = r.message_id
        end_id   = msg.message_id
        ok = 0
        for mid in range(start_id, end_id + 1):
            try:
                await bot.delete_message(chat_id, mid)
                ok += 1
            except Exception:
                pass
        try:
            await bot.delete_message(chat_id, msg.message_id)
        except Exception: pass
        # confirmation self-destructs
        try:
            m = await bot.send_message(chat_id, prefixed(fancy(f"🧹 purged {ok} msgs")))
            await asyncio.sleep(3)
            await bot.delete_message(chat_id, m.message_id)
        except Exception: pass
        return

    # ─── ~maachudao — all bots leave ───
    if cmd in ("maachudao", "machudao"):
        raw = arg.strip() or "MACHUDAO"
        for app in ALL_APPS:
            try:
                await app.bot.send_message(chat_id,
                    prefixed(fancy(f"{raw} 🩸 all bots leaving…")))
            except Exception: pass
        await asyncio.sleep(1.5)
        left, failed = 0, 0
        for app in ALL_APPS:
            try:
                await app.bot.leave_chat(chat_id)
                left += 1
            except Exception:
                failed += 1
        log.info(f"maachudao: left={left} failed={failed} chat={chat_id}")
        return

    # ─── ~spamwatchh ───
    if cmd == "spamwatchh":
        if chat_id in spamwatch_chats:
            cancel_tasks(chat_id, {"spamwatch_counter"})
            spamwatch_chats.pop(chat_id, None)
            _sw_bursts.pop(chat_id, None)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("SpamWatch OFF 🛑")),
                reply_to_message_id=msg.message_id)
        else:
            spamwatch_chats[chat_id] = {
                "owner_id": uid, "last_trigger": 0.0,
                "active_rival": None, "counter_on": False}
            await guard.send_message(bot, chat_id,
                prefixed(fancy("SpamWatch ON 👁️")),
                reply_to_message_id=msg.message_id)
        return

    if cmd in ("spamwatchoff", "stopspamwatch"):
        spamwatch_chats.pop(chat_id, None)
        _sw_bursts.pop(chat_id, None)
        killed = await _kill_kinds(chat_id, {"spamwatch_counter"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"SpamWatch HARD OFF 🛑  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopgear", "sgearspam", "stopgearspam"):
        killed = await _kill_kinds(chat_id, {"gearspam"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"GearSpam stopped ❄️  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopspam", "sspam2"):
        killed = await _kill_kinds(chat_id, SPAM_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Spam family stopped 🔥  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopsw", "stopcounter"):
        killed = await _kill_kinds(chat_id, {"spamwatch_counter"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Counter loop killed 👁️  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopnc", "stopallnc"):
        killed = await _kill_kinds(chat_id, NC_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"All NC/title loops stopped 🕸️  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("shutdown", "stopall", "panic"):
        stats = nuke_chat(chat_id, wipe_state=True)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(
                f" SHUTDOWN DROPPED ☢️\n"
                f"tasks killed : {stats['tasks_killed']}\n"
                f"swipe was on : {stats['swipe_was_on']}\n"
                f"state wiped  : YES\n"
                f"spamwatch    : OFF")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "delay":
        raw = arg.strip()
        if not raw:
            cur = get_delay(chat_id)
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Current: {cur:.2f}s | Usage: ~delay <sec>")),
                reply_to_message_id=msg.message_id); return
        try: val = float(raw)
        except ValueError:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("❌ Use number e.g. ~delay 0.1")),
                reply_to_message_id=msg.message_id); return
        val = max(0.0, min(60.0, val))
        CHAT_DELAY[chat_id] = val; save_delays()
        if val == 0:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Delay OFF ⚡")),
                reply_to_message_id=msg.message_id)
        else:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Delay: {val:.2f}s ✅")),
                reply_to_message_id=msg.message_id)
        return

    # ─── autopin ───
    if cmd in ("autopin", "autopinon"):
        AUTOPIN[chat_id] = True
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📌 autopin ON")),
            reply_to_message_id=msg.message_id); return
    if cmd in ("noautopin", "autopinoff"):
        AUTOPIN[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📌 autopin OFF")),
            reply_to_message_id=msg.message_id); return

    if cmd in TITLE_MODES and cmd in MODE_MAP:
        if not arg:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Usage: ~{cmd} <text>")),
                reply_to_message_id=msg.message_id); return
        for app in ALL_APPS:
            t = asyncio.create_task(
                bot_loop(app.bot, app.bot.id, chat_id, arg, cmd, msg.message_id))
            add_task(chat_id, t, kind=cmd)
            await asyncio.sleep(0.002)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"{cmd} started 🕸️")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("spam","gearspam","msg","both","blast"):
        if not arg:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Usage: ~{cmd} <text>")),
                reply_to_message_id=msg.message_id); return
        for app in ALL_APPS:
            t = asyncio.create_task(
                bot_loop(app.bot, app.bot.id, chat_id, arg, cmd, msg.message_id))
            add_task(chat_id, t, kind=cmd)
            await asyncio.sleep(0.002)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"{cmd} started 🔥 autopin ON")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "chud":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        CHUD_TEXT[chat_id] = {"text": r.from_user.id, "text": arg or "Chud"}
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Chud → {r.from_user.id}")),
            reply_to_message_id=msg.message_id); return

    # ─── AR — permanent, works on anyone ───
    if cmd == "ar":
        emoji = (arg or "🤣").strip()
        r = msg.reply_to_message
        if r and r.from_user:
            AR_text[chat_id] = {"text": r.from_user.id, "emoji": emoji}
            save_ar()
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"🎯 AR ON {emoji} → {r.from_user.id} (permanent)")),
                reply_to_message_id=msg.message_id)
        else:
            AR_text[chat_id] = {"text": "__ALL__", "emoji": emoji}
            save_ar()
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"🎯 AR ON {emoji} → EVERYONE (permanent)")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "sar":
        AR_text.pop(chat_id, None); save_ar()
        await guard.send_message(bot, chat_id,
            prefixed(fancy("AR OFF.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "swipe":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a msg.")),
                reply_to_message_id=msg.message_id); return
        text = arg.strip() if arg.strip() else (r.text or r.caption or "")
        if not text:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No text to swipe.")),
                reply_to_message_id=msg.message_id); return
        cancel_tasks(chat_id, {"swipe"})
        SWIPE_MSG[chat_id] = text
        SWIPE_SRC[chat_id] = r.message_id
        SWIPE_ON[chat_id]  = True
        for app in ALL_APPS:
            t = asyncio.create_task(
                swipe_loop(app.bot, app.bot.id, chat_id, text, r.message_id))
            add_task(chat_id, t, kind="swipe")
            await asyncio.sleep(0.002)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Swipe ON 🔁")),
            reply_to_message_id=msg.message_id); return

    if cmd == "zeroswipe":
        SWIPE_ON[chat_id] = False
        cancel_tasks(chat_id, {"swipe"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Swipe OFF.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "pfploop":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        f    = await bot.get_file(r.photo[-1].file_id)
        data = await f.download_as_bytearray()
        photo_pool.clear(); photo_pool.append(bytes(data))
        for app in ALL_APPS:
            t = asyncio.create_task(photo_loop(app.bot, app.bot.id, chat_id))
            add_task(chat_id, t, kind="pfp")
            await asyncio.sleep(0.002)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("PFP loop ON 🖼️")),
            reply_to_message_id=msg.message_id); return

    if cmd == "over":
        cancel_tasks(chat_id, None)
        gc_name = "UNKNOWN GC"
        try:
            ci = await bot.get_chat(chat_id)
            gc_name = ci.title or ci.full_name or "UNKNOWN GC"
        except Exception: pass
        now = datetime.now(IST)
        time_str = now.strftime("%I:%M:%S %p").lstrip("0")
        date_str = now.strftime("%d-%m-%Y")
        day_str  = now.strftime("%A")
        text_nm = arg.strip() if arg and arg.strip() else "UNKNOWN"
        by_name   = update.effective_user.first_name or "Unknown"
        caption = (
            f"⸎❄️ <b>{text_nm.upper()} IS PILLE KA GAME OVER</b>\n\n"
            f"⏰ <b>TIME :</b> {time_str}\n"
            f"💬 <b>GC :</b> {gc_name}\n"
            f"📅 <b>DATE :</b> {date_str}  |  {day_str}\n\n"
            f"🎯 <b>GAME OVER BY {by_name}</b>")
        pic = OVER_MEDIA.get(chat_id)
        if pic:
            bio = BytesIO(pic); bio.name = "over.jpg"
            r = await guard.send_photo(bot, chat_id, bio,
                                       caption=caption, parse_mode="HTML")
            if r is None:
                await guard.send_message(bot, chat_id, caption, parse_mode="HTML")
        else:
            try:
                async with httpx.AsyncClient(timeout=60) as cl:
                    vr = await cl.get(DEFAULT_GAMEOVER_VIDEO_URL)
                    vr.raise_for_status()
                    vid = BytesIO(vr.content); vid.name = "over.mp4"
                await guard.send_video(bot, chat_id, vid,
                                       caption=caption, parse_mode="HTML")
            except Exception:
                await guard.send_message(bot, chat_id, caption, parse_mode="HTML")
        return

    if cmd == "zero":
        stats = nuke_chat(chat_id, wipe_state=False)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(
                f"💀 ALL TASKS KILLED  ({stats['tasks_killed']})\n"
                f"swipe reset · counter stopped · state kept")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("zerogcnc", "zerogc"):
        killed = await _kill_kinds(chat_id, NC_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"All title loops stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "freeze":
        raw = (arg or "").strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~freeze <mode1,mode2,...>")),
                reply_to_message_id=msg.message_id); return
        kinds = {k.strip().lower() for k in raw.split(",") if k.strip()}
        if "all" in kinds or "*" in kinds:
            kinds = set(ALL_LOOP_KINDS)
        killed = await _kill_kinds(chat_id, kinds)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Frozen {sorted(kinds)}  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "sspam":
        killed = await _kill_kinds(chat_id, SPAM_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Spam stopped 🔥  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "freezeslide":
        killed = await _kill_kinds(chat_id, {"swipe"})
        SWIPE_ON[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Slide stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "zeroslidespam":
        killed = await _kill_kinds(chat_id, {"swipe","spam","gearspam","chud"})
        SWIPE_ON[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Slide+Spam stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("spic", "stopspic"):
        killed = await _kill_kinds(chat_id, {"pfp"})
        photo_pool.clear()
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"PFP stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "addsudo":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        SUDO_USERS.add(r.from_user.id); save_sudo()
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Added {r.from_user.id}")),
            reply_to_message_id=msg.message_id); return

    if cmd == "delsudo":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        SUDO_USERS.discard(r.from_user.id); save_sudo()
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Removed.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "listsudo":
        txt = "\n".join(map(str, SUDO_USERS)) or fancy("No sudo.")
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Sudo:") + "\n" + txt),
            reply_to_message_id=msg.message_id); return


# ═══════════════════════════════════════════════════════════════
# 📡  KNOWN CHATS TRACKER (for broadcast)
# ═══════════════════════════════════════════════════════════════
KNOWN_CHATS: set = set()

def _known_chats():
    return KNOWN_CHATS


# ═══════════════════════════════════════════════════════════════
# 📩  NON-COMMAND HANDLER
# ═══════════════════════════════════════════════════════════════
CHUD_POOL = [
    "{t} Tᴇʀɪ Dᴀᴅɪ ᴋ ᴄʜᴍᴜᴛ ᴍᴀɪ ᴛᴀɴɢ ᴀᴛᴋᴀ ᴅᴜɴɢᴀ ғɪʀ ᴛᴇʀʏ ᴅᴀᴅᴜ sᴜsᴜ ᴋᴀɪsᴀ ᴋʀᴇɢɪ😍?",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅᴏ ᴍᴀɪ 𝐃ɪɴᴏsᴀᴜʀ ᴋɪ ᴘᴏᴛʏʏ😁",
    "{t} ᴍᴀᴊᴅᴜʀɪ ᴋʀᴇɢᴀ ɢᴀʀᴇᴇʙ ᴛᴇʀʏ ᴍᴍʏ ᴋɪ ᴛᴀɴɢ ᴜᴛʜᴀᴋᴇ👻 ᴄʜᴜᴛ ᴍᴀᴊ ғɪᴋᴀʀɪ ᴊᴀʟᴀ ᴅᴜɴɢᴀ🙈",
    "{t} ᴇᴋ ʙᴀᴀᴛ ʙᴛᴀᴜ ᴛᴇʀᴀ ᴘᴀᴘᴀ ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ ᴍᴇʀsᴀ ᴄʜᴜᴅᴠᴀ ᴋʀ ɢʜᴀʀ ᴄʜᴀʟᴀᴛᴇ ᴇʏ🤣👻",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅ ᴘᴀʀ ᴊᴏ ᴘʜᴜɴsɪ ʜᴀ ᴜsᴋᴏ👻 ʟᴀᴀᴛ ᴍᴀʀᴋᴀ ᴘʜᴏᴅ ᴅᴜ ᴄʏ?",
    "{t} Tᴇʀʏ ᴍᴍʏ ᴋᴀ england ᴡᴀʟᴇ ʙᴜs ᴍᴀɪ ɢᴀɴɢ ʙᴀɴɢ ᴋʀᴋᴇ ᴋʜɪᴅᴋɪ sᴀ ғᴇᴋ ᴅᴇɴɢᴇ😭🥺",
    "{t} ᴋᴀʟɪ ᴋᴜᴛᴛɪ ᴋɪ ᴄʜᴜᴛ sᴀ ɴɪᴋʟᴀ ᴋᴜᴛᴛᴀ ᴋᴀ ᴘɪʟʟᴀ👻 ᴛᴇʀʏ ᴍᴀᴀ ʜᴀᴄᴋʟᴀ ᴋʀ ᴍᴀʀ ᴊᴀʏᴇ🤣",
    "{t} ᴊʜᴀᴛᴜ ᴛᴇʀʏ ᴀᴜᴋᴀᴛ ʜᴀ? 𝐄Sᴘᴀᴅᴀ 𝐖ᴀʟᴏ sᴀ ʟᴀᴅɴᴇ ᴋɪ? Tᴇʀʏ ᴍᴍʏ ᴋɪ ᴘᴜsʏʏ ᴘʀ ᴀʙᴅᴜʟ ᴋɪ ᴄʜᴀᴘᴀʟ ᴍᴀʀᴅᴜɴɢᴀ😁🍃",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ 𝐋ᴜꜰꜰʏ ᴋ ᴀʟᴀᴠᴀ ᴋᴏɪ ᴏʀ ᴄʜᴏᴅ sᴀᴋᴛᴀ ᴇʏ ᴋᴛᴀ?😁",
    "{t} sᴜᴀʀ ᴛᴇʀʏ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴋᴀɪsᴀ ʟᴀᴀᴅᴋʜᴀᴅᴀɪ?👻 Tᴇʀᴀ 𝐋ᴜꜰꜰʏ𖤍 Pᴀᴘᴀ ᴋᴀ ʟᴜɴ ᴅᴇᴋʜ ᴋʀ??😍",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ᴋᴀ ʙʜᴏsᴅᴀ ᴍᴀ 𝐒ʟᴀᴛᴇ ᴋɪ ᴍɪssɪʟᴇ ᴅᴀʟᴋᴇ ᴜᴅᴀ ᴅᴜɴɢᴀ😍",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ miya ᴋ sᴀᴛʜ ᴄʜᴏᴅᴇɢᴀᴀ🙈",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴊᴀʙ ᴛʀᴀɪɴ ᴍᴀɪ sᴏʏᴇɢɪ ᴛᴀʙ ᴜsᴋɪ ᴘᴀɴᴛʏ ᴜᴛᴀʀ ᴋʀ sᴜᴘ sᴜᴘ ᴋʀᴅᴜɴɢᴀ😍🦈🦈🦈",
    "{t} ᴛᴇʀʏ ᴅᴀᴅɪ ᴋ ᴄʜᴜᴛᴀᴅ ᴍᴀ ᴀᴀᴍ ᴋᴀ ᴛʀᴇᴇ ʟɢᴀᴋᴇ 𝐋ᴜɴ ғᴇᴋ ᴍʀ ᴍᴀʀᴋᴇ ᴛᴏʀᴜɴɢᴀ😘🤩",
    "{t} ᴛᴇʀɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋ ᴛᴀᴛᴛᴇ ᴋ ɴɪᴄʜᴇ 👻👻 ᴍᴀsʟɪ ɢʏɪ ᴀᴀʙ ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴏʏᴇɢᴀ😘",
    "{t} ᴛᴇʀɪ ᴋᴀʟᴀ ᴄʜᴜᴛᴀᴅ ᴡᴀʟɪ ʙʜᴇɴ ᴋ ɢᴀɴᴅ ᴍᴀɪ👻 ᴊᴀᴅᴜɪ ᴄʜᴀᴅɪ ᴅᴀʟᴅᴜɴɢᴀ😈😈😈",
    "TERI BRHEN KI KALI BURR ME THOOK DOYA AB CHAAT JAA USE 👽",
    "{t} ᴋɪ ᴍᴀᴀ ʜᴏʀɴᴇʏ ʜᴏ ᴋʀ ᴀᴘɴᴇ ᴋᴜᴛᴛᴀ ᴋ ᴍᴜʜ ᴍᴀɪ ʟᴇ ʟᴇᴛɪ ᴇʏ?😱",
    "{t} ᴋɪ ᴍᴀᴀ ᴀᴅɪᴠᴀsɪ ᴏɪʟ ʟɢᴀᴋᴇ ᴊᴜɴɢʟᴇ ᴍᴀ ɢᴀɴᴅ ᴅᴇᴛɪ ᴇʏ😭😭",
    "{t} ᴋɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋᴀ ʟᴏʀᴀ ʟᴇᴛᴀ ʜᴜ ᴘᴀᴀᴅ ᴍᴀʀᴛɪ ᴇʏ ᴄʜɪ🤬🤬🤬",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ʙɪᴊʟɪ ᴋ ᴋʜᴀᴍʙᴀ ᴘʀ ᴡɪʀᴇ ᴄʜᴜᴛᴀᴅ ᴍᴀ ʟᴇᴋʀ ᴛᴀᴅᴀᴘ ᴋʀ ᴍᴀʀ ɢᴀɪ😭👻",
    "{t} ᴊɪs sɪᴍ sᴀ ᴛᴜ ɴᴇᴛ ᴄʜᴀʟᴀ ʀᴀʜᴀ ᴠᴏ ᴠ ᴍᴇʀᴀ ʟᴏᴅᴀ ᴋɪ ᴋʀɪᴘᴀ ʜᴀ ᴇʏ ɢᴀʀᴇᴇʙ ᴛᴇʀʏ ᴍᴀᴀ sᴀ ᴘᴜᴄʜ😁💣",
    "{t} ʜᴀᴄᴋʟᴇ ᴍssɢ ᴍᴛ ᴋʀ ᴡᴀʀɴᴀ ᴛᴇʀᴀ ᴋʜᴀɴᴅᴀɴ ᴋᴏ ʀᴀᴏᴅ ᴘʀ ɴᴀɴɢᴀ ᴋʀᴋʀ ᴍᴜʜ ᴘʀ ɢᴀʀᴀᴍ ᴍᴜᴛ ᴅᴜɴɢᴀ😍🦈",
    "{t} ᴋɪ ᴍᴀᴀ 𝐋ᴜꜰꜰʏ ᴋ ʟᴜɴ ᴋɪ ᴘʜᴏᴛᴏ ᴅᴇᴋʜ ᴋʀ ғɪɴɢᴇʀɪɴɢ ᴋʀᴛɪ ᴇʏ🦈😭",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴀʟᴀ ᴄʜᴜᴛᴀᴅ ᴡᴀʟɪ ᴄʜᴜᴅᴀᴋʀ😈💋",
    "{t} ᴋɪ ᴍᴜᴍᴍʏ ᴍᴜᴛʜɪ ᴍᴀʀ ᴛɪ ᴇʏ?😭????",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅ 😘 ᴘʀ 𝐋ᴜꜰꜰʏ ᴀᴘɴᴀ ʟᴜɴ sᴀ ᴛᴀʟɪʏᴀ ʙᴀᴊᴀʏᴇɢᴀ😈😈💋",
    "{t} ᴋɪ ᴍᴜᴍᴍʏ ᴀᴘɴɪ ᴄʜᴜᴄʜɪʏᴀ ɢᴀᴛᴇ ᴋ ʙɪᴄʜ ᴅᴀʙᴀ ᴋʀ ᴍᴀʀ ɢᴀɪ?😭😭",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ʜɪᴢʀᴇ ʙᴀɴᴋʀ ᴛʀᴀɪɴ ᴍᴀ ᴀᴛɪ ᴛᴇʀᴀ ᴘᴀᴘᴀ sᴜsᴜ ᴄʜᴀᴛɴᴇ ᴋɪ ᴅᴜᴋᴀɴ ᴋʀᴛᴀ ᴇʏ ʙᴛᴀ ᴅʏ ᴄʏᴀ sᴀʙᴋᴏ👻👻👻💣💣",
    "ᴋʏᴀᴀ?😱 {t} ᴋɪ ᴍᴍʏ ᴊᴀʙ sᴜsᴜ ᴋʀ ʀɪ ᴛʜɪ Tᴀʙ ᴄʜᴜᴛ ᴍᴀɪ sᴀᴀᴘ ɢʜᴜs ɢʏᴀ ᴠᴏ ʙʜɪ ᴄᴏʙʀᴀ?😱😱",
    "{t} ᴋɪ ʙᴇʜᴇɴ ᴋʜᴀᴅɪ ʜᴏ ᴋʀ ᴍᴜᴛ ᴛɪ ᴇʏ?😱😱😱",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ 𝐋ᴜꜰꜰʏ ɴᴀ ɴᴀsʜᴇ ᴍᴀɪ sᴏғᴀ ᴘʀ ᴛᴀɴɢ ᴜᴛʜᴀ ᴋʀ ᴄʜᴏᴅ ᴅɪʏᴀ😁😁",
    "{t} ᴛᴇʀɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋ ᴛᴀᴛᴛᴇ ᴋ ɴɪᴄʜᴇ 👻👻 ᴍᴀsʟɪ ɢʏɪ ᴀᴀʙ ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴏʏᴇɢᴀ😘",
    "{t} ᴛᴇʀɪ ᴍᴀᴀ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴀᴀɢ ʟɢᴀ ᴋᴇ ʀᴀᴋʜ ᴅᴜɴɢᴀ🔥🥵",
    "{t} ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴀ ɢᴀɴᴅ ᴍᴀʀ ᴋʀ ᴋᴀᴍᴀᴛᴀ ʜᴀ🩸💔",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋᴏ ʀᴇᴅ ʟɪɢʜᴛ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ʙʜᴀɢᴀ ᴅᴜɴɢᴀ🚨🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴇ sᴀᴘ ᴅᴀʟ ᴋᴇ ɴᴀᴄʜᴡᴀᴜɴɢᴀ🐍💃",
    "{t} ᴛᴇʀᴀ ᴘᴜʀᴀ ᴋʜᴀɴᴅᴀɴ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴇ ɴᴀᴄʜᴛᴀ ʜᴀ🎭🍺",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ʟᴜғғʏ ᴋᴇ ʟᴜɴ sᴇ ɢᴀʀᴍɪ ᴅᴇᴛᴀ ʜᴜ🔥💦",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ʙʜᴇɴ ᴅᴏɴᴏ ᴋᴏ ᴇᴋ sᴀᴛʜ ᴄʜᴏᴅ ᴋᴇ ɴᴀᴄʜᴀᴜɴɢᴀ🎉🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴋɪ ʜᴏᴛᴇʟ ᴋʜᴏʟ ᴋᴇ ʀᴀᴋʜ ᴅᴜɴɢᴀ🏨🩵",
    "{t} ᴛᴇʀᴀ ʙᴀᴀᴘ ᴄʜᴀᴜᴋɪᴅᴀʀ ʜᴀ TERI MAKI ɢᴀɴᴅ ᴋᴀ👻🚔",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ɢᴀɴɢ ʙᴀɴɢ ᴋʀᴋᴇ ᴛʀᴀɪɴ sᴇ ᴜᴛᴀʀᴡᴀᴜɴɢᴀ🚂🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ɢᴀɴᴅ ᴍᴇ ʟᴜғғʏ ᴋᴀ ʟᴏɢᴏ ᴛᴀᴛᴛᴏᴏ ᴋᴀʀᴀ ᴅᴜɴɢᴀ🕸️🔱",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴛʀɪᴘʟᴇ x ᴠɪᴅᴇᴏ ʙᴀɴᴀᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📸🔥",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ᴅᴏɢɢʏ sᴛʏʟᴇ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ɴᴀᴄʜᴇ ɢɪʀᴀ ᴅᴜɴɢᴀ🐕🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʟᴜғғʏ ɢᴀɴɢ ᴋᴀ ʀᴀᴠᴀ ʟɢᴀ ᴅᴜɴɢᴀ🔊🩵",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ ᴛᴀʟᴀʙ ᴋᴀ ᴘᴀɴɪ ʙʜᴀʀ ᴋᴇ ɴᴀᴄʜᴀᴜɴɢᴀ🌊🩸",
    "{t} ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴀ ᴍᴜᴛ ᴋᴇ ʙᴇᴄʜ ᴅᴜɴɢᴀ🍺🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ɢᴀʏ sᴛʏʟᴇ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📱🔥",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴄᴏᴋᴇ sᴛᴜᴅɪᴏ ᴋʜᴏʟ ᴅᴜɴɢᴀ🥤🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ sᴛᴀᴅɪᴜᴍ ᴍᴀ ᴍᴀᴛᴄʜ ᴋᴀʀᴀ ᴅᴜɴɢᴀ🏟️🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʟᴜғғʏ ɢᴀɴɢ ᴋᴀ ᴛᴀᴛᴛᴏᴏ ʙᴀɴᴡᴀ ᴅᴜɴɢᴀ🕸️🩵",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ᴘᴜʙʟɪᴄ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📢🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ ᴅᴇᴇᴘғᴀᴋᴇ ʙᴀɴᴀᴋᴇ ᴘᴏsᴛ ᴋᴀʀ ᴅᴜɴɢᴀ📸🔥",
    "{t} ᴛᴇʀᴇ ᴋʜᴀɴᴅᴀɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴅʀᴏɴᴇ ᴄᴀᴍᴇʀᴀ ʟᴀɢᴀ ᴅᴜɴɢᴀ🚁🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ʟᴜғғʏ ɢᴀɴɢ ᴋᴇ ʜᴀᴡᴀʟᴇ ᴋᴀʀ ᴅᴜɴɢᴀ🏴‍☠️🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʀᴀᴘ ʙᴀᴛᴛʟᴇ ᴋᴀʀᴡᴀ ᴅᴜɴɢᴀ🎤🩸",
]

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_chat: return

    chat_id = update.effective_chat.id
    uid     = update.effective_user.id if update.effective_user else 0
    guard   = get_limiter(ctx.bot.id)

    KNOWN_CHATS.add(chat_id)

    if update.effective_user:
        track_user(update.effective_user)

    if chat_id in spamwatch_chats and uid and uid != ctx.bot.id:
        st = spamwatch_chats[chat_id]
        if uid != st.get("owner_id") and _track_burst(chat_id, uid):
            await _trigger_spamwatch(chat_id, uid, msg.message_id)

    # AR — permanent, works on text or EVERYONE if "__ALL__"
    ar = AR_text.get(chat_id)
    if ar:
        tgt = ar.get("text")
        if tgt == "__ALL__" or uid == tgt:
            if uid and uid != ctx.bot.id:
                await guard.set_message_reaction(
                    ctx.bot, chat_id=chat_id, message_id=msg.message_id,
                    reaction=ar["emoji"], is_big=False)

    ch = CHUD_TEXT.get(chat_id)
    if ch and uid == ch["text"]:
        txt = random.choice(CHUD_POOL).format(t=ch["text"])
        await guard.send_message(ctx.bot, chat_id, txt,
                                 reply_to_message_id=msg.message_id)


# ═══════════════════════════════════════════════════════════════
# 🚀  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════
async def start_all_bots():
    for i, tok in enumerate(BOT_TOKENS, start=1):
        try:
            app = ApplicationBuilder().token(tok).build()
            # text/command handler (works in groups + private)
            app.add_handler(MessageHandler(
                filters.TEXT & filters.Regex(r"^~"), route))
            # channel-post handler (works in channels where bot is admin)
            app.add_handler(MessageHandler(
                filters.UpdateType.CHANNEL_POST & filters.Regex(r"^~"), route))
            # non-command handler
            app.add_handler(MessageHandler(
                filters.ALL & ~filters.Regex(r"^~"), on_message))

            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)

            me = await app.bot.get_me()
            BOT_INFO[app.bot.id] = {"no": i, "username": me.username}
            ALL_APPS.append(app)
            ALL_BOTS.append(app.bot)
            log.info(f"✅ Bot #{i} online → @{me.username}")
        except Exception as e:
            log.error(f"❌ Bot #{i} failed: {e}")


async def shutdown_all():
    for a in ALL_APPS:
        try:
            await a.updater.stop(); await a.stop(); await a.shutdown()
        except Exception: pass


async def main():
    log.info("🚀 LUFFY ENGINE v11 starting…")
    await start_all_bots()
    if not ALL_APPS:
        log.error("No bots online."); return
    log.info(f"✅ {len(ALL_APPS)} bots running at 10x speed")
    try:
        await asyncio.Event().wait()
    finally:
        await shutdown_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutdown.")
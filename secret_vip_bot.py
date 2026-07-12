import asyncio
import logging
import os
import random
import sqlite3
import string
import time
from datetime import date
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

# ════════════════════════════════════════════════════
#  ⚙️  SOZLAMALAR
# ════════════════════════════════════════════════════

# 27-qatorni shunday qilib o'zgartiring:
BOT_TOKEN = "8817271025:AAGhApX9khzL3ve32HbZPsEzdYDDnuQGaa4"
ADMIN_IDS    = [int(x) for x in os.environ.get("SECRET_VIP_ADMIN_IDS", "816831780").split(",") if x.strip()]
BOT_USERNAME = os.environ.get("SECRET_VIP_BOT_USERNAME", "SecretVIPKino_bot")
BOT_NAME     = "🎬 Secret VIP Kino"
ADMIN_CARD   = os.environ.get("SECRET_VIP_ADMIN_CARD", "9860160435534955")

REQUIRED_CHANNELS = [
    {"id": "@yangi_yil_kinolari_va_multifilm", "name": "🎬 Yangi Yil Kinolari"},
    {"id": "@Kinolar_VipUz",                   "name": "🔐 Kinolar VIP"},
]

INSTAGRAM_LINK = "https://www.instagram.com/nematov_3010?igsh=dmg3MXFrZXprejVu&utm_source=qr"

SPAM_LIMIT  = 3
SPAM_WINDOW = 5
DAILY_BONUS = 15          # VIP botda bonus ko'proq

DB_NAME = "secret_vip.db"

# ════════════════════════════════════════════════════
#  📝 LOGLASH
# ════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
#  📋 FSM HOLATLARI
# ════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    broadcast        = State()
    movie_code       = State()
    movie_title      = State()
    movie_desc       = State()
    movie_cat        = State()
    movie_vip        = State()
    movie_file       = State()
    add_channel_id   = State()
    add_channel_name = State()
    ban_user_id      = State()
    set_card         = State()

class UserStates(StatesGroup):
    waiting_receipt  = State()

class SearchState(StatesGroup):
    waiting_query    = State()

# ════════════════════════════════════════════════════
#  🗄️  DATABASE
# ════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            status     TEXT    DEFAULT 'user',
            coins      INTEGER DEFAULT 0,
            ref_code   TEXT    UNIQUE,
            ref_by     INTEGER,
            joined_at  TEXT    DEFAULT (datetime('now')),
            last_bonus TEXT    DEFAULT '2000-01-01',
            is_banned  INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    UNIQUE NOT NULL,
            title       TEXT    NOT NULL,
            description TEXT,
            category    TEXT    DEFAULT 'Umumiy',
            file_id     TEXT    NOT NULL,
            file_type   TEXT    DEFAULT 'video',
            views       INTEGER DEFAULT 0,
            is_vip      INTEGER DEFAULT 0,
            added_by    INTEGER,
            added_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            name       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_payments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            full_name  TEXT,
            tariff     TEXT,
            photo_id   TEXT,
            status     TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Reset channels and re-insert required ones
    c.execute("DELETE FROM channels")
    for ch in REQUIRED_CHANNELS:
        c.execute(
            "INSERT OR IGNORE INTO channels (channel_id, name) VALUES (?, ?)",
            (ch["id"], ch["name"]),
        )
    conn.commit()
    conn.close()

# ════════════════════════════════════════════════════
#  📌 DB YORDAMCHILAR
# ════════════════════════════════════════════════════

def get_user(uid: int) -> Optional[sqlite3.Row]:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row

def register_user(uid: int, username: str, full_name: str, ref_by: int = None):
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id,username,full_name,ref_code,ref_by) VALUES (?,?,?,?,?)",
        (uid, username, full_name, code, ref_by),
    )
    if ref_by:
        conn.execute("UPDATE users SET coins=coins+10 WHERE user_id=?", (ref_by,))
    conn.commit()
    conn.close()

def set_vip(uid: int):
    conn = get_db()
    conn.execute("UPDATE users SET status='vip' WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def get_movie(code: str) -> Optional[sqlite3.Row]:
    conn = get_db()
    m = conn.execute("SELECT * FROM movies WHERE code=?", (code.strip(),)).fetchone()
    if m:
        conn.execute("UPDATE movies SET views=views+1 WHERE code=?", (code.strip(),))
        conn.commit()
    conn.close()
    return m

def get_channels() -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM channels").fetchall()
    conn.close()
    return rows

def get_user_count() -> int:
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=0").fetchone()[0]
    conn.close()
    return n

def get_movie_count() -> int:
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    conn.close()
    return n

def get_top_movies(limit=10) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies ORDER BY views DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def get_new_movies(limit=10) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies ORDER BY added_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def get_vip_movies(limit=15) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies WHERE is_vip=1 ORDER BY added_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def get_categories() -> list:
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM movies ORDER BY category").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_by_category(cat: str) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies WHERE category=? LIMIT 20", (cat,)).fetchall()
    conn.close()
    return rows

def search_movies(q: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM movies WHERE title LIKE ? OR code LIKE ? OR description LIKE ? LIMIT 12",
        (f"%{q}%", f"%{q}%", f"%{q}%"),
    ).fetchall()
    conn.close()
    return rows

def get_all_users(limit=50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY joined_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows

def search_user(uid: int) -> Optional[sqlite3.Row]:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row

def ban_user(uid: int):
    conn = get_db()
    conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def unban_user(uid: int):
    conn = get_db()
    conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def delete_movie(code: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM movies WHERE code=?", (code,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def get_all_movies(limit=30) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies ORDER BY added_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def add_channel_db(ch_id: str, name: str):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO channels (channel_id, name) VALUES (?, ?)", (ch_id, name))
    conn.commit()
    conn.close()

def delete_channel_db(ch_id: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM channels WHERE channel_id=?", (ch_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def save_pending(uid: int, full_name: str, tariff: str, photo_id: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO pending_payments (user_id, full_name, tariff, photo_id) VALUES (?,?,?,?)",
        (uid, full_name, tariff, photo_id),
    )
    conn.commit()
    conn.close()

def get_pending_payments() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pending_payments WHERE status='pending' ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return rows

def resolve_pending(row_id: int, status: str):
    conn = get_db()
    conn.execute("UPDATE pending_payments SET status=? WHERE id=?", (status, row_id))
    conn.commit()
    conn.close()

def get_vip_count() -> int:
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM users WHERE status='vip'").fetchone()[0]
    conn.close()
    return n

def get_pending_count() -> int:
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM pending_payments WHERE status='pending'").fetchone()[0]
    conn.close()
    return n

def claim_bonus(uid: int) -> bool:
    today = date.today().isoformat()
    conn  = get_db()
    row   = conn.execute("SELECT last_bonus FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row or row["last_bonus"] == today:
        conn.close()
        return False
    conn.execute(
        "UPDATE users SET coins=coins+?, last_bonus=? WHERE user_id=?",
        (DAILY_BONUS, today, uid),
    )
    conn.commit()
    conn.close()
    return True

# ════════════════════════════════════════════════════
#  🛡️  SPAM HIMOYA
# ════════════════════════════════════════════════════

_spam: dict[int, list[float]] = {}

def is_spam(uid: int) -> bool:
    now = time.time()
    _spam.setdefault(uid, [])
    _spam[uid] = [t for t in _spam[uid] if now - t < SPAM_WINDOW]
    _spam[uid].append(now)
    return len(_spam[uid]) > SPAM_LIMIT

# ════════════════════════════════════════════════════
#  ⌨️  KLAVIATURALAR
# ════════════════════════════════════════════════════

def main_kb(status="user") -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🎬 Kino kodi"), KeyboardButton(text="🔍 Qidiruv")],
        [KeyboardButton(text="🏆 Top kinolar"), KeyboardButton(text="🆕 Yangi kinolar")],
        [KeyboardButton(text="📂 Kategoriyalar"), KeyboardButton(text="👤 Profilim")],
        [KeyboardButton(text="🎁 Kunlik bonus"), KeyboardButton(text="👥 Referal")],
    ]
    if status in ("vip", "admin"):
        rows.append([KeyboardButton(text="💎 VIP Kinolar")])
    if status == "admin":
        rows.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏁 Statistika"),        KeyboardButton(text="📩 Xabar yuborish")],
            [KeyboardButton(text="🎬 Kontent boshqarish"), KeyboardButton(text="🔒 Kanallar")],
            [KeyboardButton(text="⚙️ Tizim sozlamalari"), KeyboardButton(text="📥 So'rovlar")],
            [KeyboardButton(text="◀️ Orqaga"),            KeyboardButton(text="👥 Foydalanuvchilar")],
        ],
        resize_keyboard=True,
    )

def kontent_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kino qo'shish"), KeyboardButton(text="🗑 Kino o'chirish")],
            [KeyboardButton(text="📋 Barcha kinolar"), KeyboardButton(text="◀️ Admin menyusi")],
        ],
        resize_keyboard=True,
    )

def channels_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kanal qo'shish"), KeyboardButton(text="🗑 Kanal o'chirish")],
            [KeyboardButton(text="📋 Kanallar ro'yxati"), KeyboardButton(text="◀️ Admin menyusi")],
        ],
        resize_keyboard=True,
    )

def users_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Foydalanuvchi izlash"), KeyboardButton(text="🚫 Ban berish")],
            [KeyboardButton(text="✅ Ban ochish"),            KeyboardButton(text="◀️ Admin menyusi")],
        ],
        resize_keyboard=True,
    )

def tariff_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ 1 Kunlik  —  5 000 so'm",  callback_data="svip_1day")],
        [InlineKeyboardButton(text="🌙 1 Oylik   — 15 000 so'm",  callback_data="svip_1month")],
        [InlineKeyboardButton(text="👑 1 Yillik  — 50 000 so'm",  callback_data="svip_1year")],
    ])

def sub_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        ch_id   = ch["channel_id"] if isinstance(ch, sqlite3.Row) else ch[1]
        ch_name = ch["name"]       if isinstance(ch, sqlite3.Row) else ch[2]
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch_name}", url=f"https://t.me/{ch_id.lstrip('@')}"
        )])
    buttons.append([InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM_LINK)])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="svip_check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cat_kb(cats: list) -> InlineKeyboardMarkup:
    buttons, row = [], []
    for cat in cats:
        row.append(InlineKeyboardButton(text=f"🎭 {cat}", callback_data=f"svip_cat_{cat}"))
        if len(row) == 2:
            buttons.append(row); row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="svip_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ════════════════════════════════════════════════════
#  🔒 OBUNA TEKSHIRISH
# ════════════════════════════════════════════════════

async def check_sub(bot: Bot, uid: int) -> bool:
    if uid in ADMIN_IDS:
        return True
    for ch in get_channels():
        try:
            m = await bot.get_chat_member(ch[1], uid)
            if m.status in ("left", "kicked", "banned"):
                return False
        except Exception as e:
            logger.warning(f"Kanal tekshirish xatosi ({ch[1]}): {e}")
    return True

# ════════════════════════════════════════════════════
#  🤖 BOT
# ════════════════════════════════════════════════════

bot      = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp       = Dispatcher(storage=MemoryStorage())
router   = Router()

# ─────────────── /start ────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid  = message.from_user.id
    user = message.from_user

    # referal
    args   = (message.text or "").split()
    ref_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            r = int(args[1].split("_")[1])
            if r != uid:
                ref_by = r
        except (ValueError, IndexError):
            pass

    db = get_user(uid)
    if not db:
        register_user(uid, user.username or "", user.full_name, ref_by)
        db = get_user(uid)

    # Premium gate
    if uid not in ADMIN_IDS and db["status"] != "vip":
        await message.answer(
            "🔐 <b>Secret VIP Kino</b>\n\n"
            "Bu bot <b>faqat premium</b> foydalanuvchilar uchun!\n\n"
            "✅ Premium imkoniyatlari:\n"
            "• Mingdan ortiq HD kino\n"
            "• Yangi kinolar birinchi bo'lib\n"
            "• Kanal obunasisiz foydalanish\n"
            "• Har kuni yangi kontentlar\n\n"
            "💳 Tarifni tanlang:",
            reply_markup=tariff_kb(),
        )
        return

    # Kanal tekshirish
    if not await check_sub(bot, uid):
        await message.answer(
            "📢 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>",
            reply_markup=sub_kb(get_channels()),
        )
        return

    status = "admin" if uid in ADMIN_IDS else db["status"]
    await message.answer(
        f"👋 <b>{user.full_name}</b>, xush kelibsiz!\n"
        f"🎬 <b>{BOT_NAME}</b> — eng yaxshi kinolar shu yerda!\n\n"
        "📌 Kino kodini yuboring yoki menyudan foydalaning:",
        reply_markup=main_kb(status),
    )

# ─────────────── TARIF TANLASH ────────────────

TARIFFS = {
    "svip_1day":   "⚡ 1 Kunlik  —  5 000 so'm",
    "svip_1month": "🌙 1 Oylik   — 15 000 so'm",
    "svip_1year":  "👑 1 Yillik  — 50 000 so'm",
}

@router.callback_query(F.data.in_(TARIFFS))
async def pick_tariff(call: CallbackQuery, state: FSMContext):
    name = TARIFFS[call.data]
    await state.update_data(tariff=name)
    await call.message.edit_text(
        f"💳 <b>Tanlangan tarif:</b> {name}\n\n"
        f"Quyidagi karta raqamiga to'lov qiling:\n"
        f"<code>{ADMIN_CARD}</code>\n\n"
        "To'lov chekini (rasm) shu yerga yuboring — admin 5-10 daqiqada tasdiqlaydi:",
    )
    await state.set_state(UserStates.waiting_receipt)

@router.message(UserStates.waiting_receipt, F.photo)
async def got_receipt(message: Message, state: FSMContext):
    data     = await state.get_data()
    tariff   = data.get("tariff", "—")
    photo_id = message.photo[-1].file_id
    # Save to pending payments table
    save_pending(message.from_user.id, message.from_user.full_name, tariff, photo_id)
    await message.answer(
        "✅ <b>Chek qabul qilindi!</b>\n"
        "Admin tez orada tekshiradi. Iltimos, kuting..."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"svip_ok_{message.from_user.id}"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"svip_no_{message.from_user.id}"),
    ]])
    for aid in ADMIN_IDS:
        try:
            await message.bot.send_photo(
                chat_id=aid,
                photo=photo_id,
                caption=(
                    f"🔔 <b>Yangi to'lov!</b>\n\n"
                    f"👤 {message.from_user.full_name}\n"
                    f"🆔 <code>{message.from_user.id}</code>\n"
                    f"🎫 {tariff}"
                ),
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Admin ga yuborishda xato: {e}")
    await state.clear()

@router.message(UserStates.waiting_receipt)
async def receipt_wrong(message: Message):
    await message.answer("📸 Iltimos, to'lov chekini <b>rasm (photo)</b> ko'rinishida yuboring.")

# ─────────────── ADMIN: TASDIQLASH / RAD ────────────────

@router.callback_query(F.data.startswith("svip_ok_"))
async def approve(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    set_vip(uid)
    try:
        await call.message.edit_caption(
            caption=(call.message.caption or "") + "\n\n🟢 <b>Tasdiqlandi — VIP berildi!</b>"
        )
    except Exception:
        pass
    try:
        await call.bot.send_message(
            uid,
            "🎉 <b>To'lovingiz tasdiqlandi!</b>\n\n"
            "Sizga <b>VIP STATUS</b> berildi.\n"
            "Endi botdan to'liq foydalaning — /start bosing!",
        )
    except Exception as e:
        logger.error(e)

@router.callback_query(F.data.startswith("svip_no_"))
async def deny(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    try:
        await call.message.edit_caption(
            caption=(call.message.caption or "") + "\n\n🔴 <b>Rad etildi!</b>"
        )
    except Exception:
        pass
    try:
        await call.bot.send_message(
            uid,
            "❌ <b>To'lov cheki rad etildi!</b>\n\n"
            "To'g'ri chek yuboring yoki adminga murojaat qiling.\n/start",
        )
    except Exception as e:
        logger.error(e)

# ─────────────── OBUNA TEKSHIRISH ────────────────

@router.callback_query(F.data == "svip_check_sub")
async def check_sub_cb(call: CallbackQuery):
    uid = call.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        await call.answer("❌ Avval premium obuna sotib oling!", show_alert=True)
        return
    if await check_sub(bot, uid):
        try:
            await call.message.delete()
        except Exception:
            pass
        status = "admin" if uid in ADMIN_IDS else db["status"]
        await call.message.answer(
            "✅ <b>Hammasi tekshirildi! Xush kelibsiz!</b> 🎬",
            reply_markup=main_kb(status),
        )
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)

# ─────────────── 🏠 BOSH SAHIFA ────────────────

@router.message(F.text == "🏠 Bosh sahifa")
async def home(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        await message.answer("💳 Premium kerak:", reply_markup=tariff_kb())
        return
    if not await check_sub(bot, uid):
        await message.answer("📢 Kanallarga obuna bo'ling:", reply_markup=sub_kb(get_channels()))
        return
    status = "admin" if uid in ADMIN_IDS else db["status"]
    await message.answer("🏠 Bosh sahifa", reply_markup=main_kb(status))

# ─────────────── 🎬 KINO KODI TUGMASI ────────────────

@router.message(F.text == "🎬 Kino kodi")
async def kino_code_prompt(message: Message, state: FSMContext):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    await message.answer(
        "🎬 Kino kodini yuboring (masalan: <code>101</code>):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🏠 Bosh sahifa")]], resize_keyboard=True
        ),
    )

# ─────────────── 👑 ADMIN PANEL ────────────────

@router.message(Command("admin"))
@router.message(F.text == "👑 Admin Panel")
@router.message(F.text == "◀️ Admin menyusi")
async def admin_panel(message: Message, state: FSMContext = None):
    if message.from_user.id in ADMIN_IDS:
        if state:
            await state.clear()
        await message.answer("🛠 <b>Admin paneliga xush kelibsiz!</b>", reply_markup=admin_kb())
    else:
        await message.answer("❌ Ruxsat yo'q.")

# ◀️ Orqaga — admin paneldan asosiy menyuga
@router.message(F.text == "◀️ Orqaga")
async def admin_back(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    db = get_user(message.from_user.id)
    status = "admin"
    await message.answer("🏠 Bosh sahifaga qaytdingiz", reply_markup=main_kb(status))

# 🏁 STATISTIKA
@router.message(F.text == "🏁 Statistika")
async def stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    pending = get_pending_count()
    await message.answer(
        f"🏁 <b>Bot Statistikasi</b>\n\n"
        f"👤 Jami foydalanuvchilar: <b>{get_user_count()}</b>\n"
        f"💎 VIP foydalanuvchilar: <b>{get_vip_count()}</b>\n"
        f"🎬 Jami kinolar: <b>{get_movie_count()}</b>\n"
        f"📥 Kutilayotgan so'rovlar: <b>{pending}</b>"
    )

# ─────────────── ➕ KINO QO'SHISH ────────────────

BACK = "🏠 Bosh sahifa"
BACK_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BACK)]], resize_keyboard=True)

@router.message(F.text == "➕ Kino qo'shish")
async def add_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔢 Noyob <b>KOD</b> kiriting:", reply_markup=BACK_KB)
    await state.set_state(AdminStates.movie_code)

@router.message(AdminStates.movie_code)
async def add_code(message: Message, state: FSMContext):
    if message.text == BACK or message.text == "◀️ Admin menyusi":
        await state.clear(); await admin_panel(message, state); return
    data = await state.get_data()
    code = message.text.strip()
    # Delete mode
    if data.get("delete_mode"):
        ok = delete_movie(code)
        await state.clear()
        if ok:
            await message.answer(f"🗑 <b>Kino o'chirildi:</b> <code>{code}</code>", reply_markup=kontent_kb())
        else:
            await message.answer(f"❌ <code>{code}</code> kodli kino topilmadi.", reply_markup=kontent_kb())
        return
    # Add mode
    conn = get_db()
    ex   = conn.execute("SELECT id FROM movies WHERE code=?", (code,)).fetchone()
    conn.close()
    if ex:
        await message.answer("❌ Bu kod band! Boshqa kod kiriting:"); return
    await state.update_data(code=code)
    await message.answer("🎬 Kino <b>nomini</b> kiriting:")
    await state.set_state(AdminStates.movie_title)

@router.message(AdminStates.movie_title)
async def add_title(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.clear(); await admin_panel(message); return
    await state.update_data(title=message.text.strip())
    await message.answer("📝 <b>Tavsif</b> kiriting (yoki <code>-</code> bosing):")
    await state.set_state(AdminStates.movie_desc)

@router.message(AdminStates.movie_desc)
async def add_desc(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.clear(); await admin_panel(message); return
    desc = None if message.text.strip() in ("-", "yo'q", "yoq") else message.text.strip()
    await state.update_data(description=desc)
    await message.answer("📂 <b>Kategoriya</b> kiriting (masalan: Drama, Komediya):")
    await state.set_state(AdminStates.movie_cat)

@router.message(AdminStates.movie_cat)
async def add_cat(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.clear(); await admin_panel(message); return
    await state.update_data(category=message.text.strip())
    await message.answer(
        "💎 VIP statusda bo'lsinmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💎 Ha — VIP",    callback_data="svip_add_1"),
            InlineKeyboardButton(text="🆓 Yo'q — Oddiy", callback_data="svip_add_0"),
        ]]),
    )
    await state.set_state(AdminStates.movie_vip)

@router.callback_query(AdminStates.movie_vip)
async def add_vip(call: CallbackQuery, state: FSMContext):
    await state.update_data(is_vip=1 if call.data == "svip_add_1" else 0)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📹 Kino faylini yuboring (video yoki dokument):")
    await state.set_state(AdminStates.movie_file)

@router.message(AdminStates.movie_file, F.video | F.document)
async def add_file(message: Message, state: FSMContext):
    data      = await state.get_data()
    file_id   = message.video.file_id if message.video else message.document.file_id
    file_type = "video" if message.video else "document"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO movies (code,title,description,category,file_id,file_type,is_vip,added_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (data["code"], data["title"], data.get("description"),
             data.get("category", "Umumiy"), file_id, file_type,
             data.get("is_vip", 0), message.from_user.id),
        )
        conn.commit()
        await message.answer(
            f"✅ Qo'shildi! Kod: <code>{data['code']}</code>", reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Xato: {e}", reply_markup=admin_kb())
    finally:
        conn.close()
        await state.clear()

@router.message(AdminStates.movie_file)
async def add_file_wrong(message: Message):
    await message.answer("📹 Video yoki dokument formatida yuboring.")

# ─────────────── 🎬 KONTENT BOSHQARISH ────────────────

@router.message(F.text == "🎬 Kontent boshqarish")
async def kontent_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total = get_movie_count()
    await message.answer(
        f"🎬 <b>Kontent boshqaruvi</b>\n\n📦 Jami kinolar: <b>{total}</b>",
        reply_markup=kontent_kb(),
    )

@router.message(F.text == "📋 Barcha kinolar")
async def all_movies(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    movies = get_all_movies(30)
    if not movies:
        await message.answer("🎬 Hozircha kinolar yo'q.")
        return
    text = f"📋 <b>Kinolar ro'yxati ({len(movies)} ta):</b>\n\n"
    for m in movies:
        vip = " 💎" if m["is_vip"] else ""
        text += f"• <code>{m['code']}</code> — {m['title']}{vip} ({m['views']} ko'rish)\n"
    await message.answer(text)

@router.message(F.text == "🗑 Kino o'chirish")
async def delete_movie_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔢 O'chirmoqchi bo'lgan kino <b>kodini</b> yuboring:")
    await state.set_state(AdminStates.movie_code)
    await state.update_data(delete_mode=True)

# ─────────────── 🔒 KANALLAR BOSHQARUVI ────────────────

@router.message(F.text == "🔒 Kanallar")
async def channels_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔒 <b>Kanallar boshqaruvi</b>", reply_markup=channels_kb())

@router.message(F.text == "📋 Kanallar ro'yxati")
async def list_channels(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    chs = get_channels()
    if not chs:
        await message.answer("📋 Kanallar yo'q.")
        return
    text = "📋 <b>Majburiy kanallar:</b>\n\n"
    for i, ch in enumerate(chs, 1):
        text += f"{i}. {ch['name']} — <code>{ch['channel_id']}</code>\n"
    await message.answer(text)

@router.message(F.text == "➕ Kanal qo'shish")
async def add_channel_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "📢 Kanal username ni yuboring (masalan: <code>@MyChannel</code>):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Admin menyusi")]], resize_keyboard=True
        ),
    )
    await state.set_state(AdminStates.add_channel_id)

@router.message(AdminStates.add_channel_id)
async def got_channel_id(message: Message, state: FSMContext):
    if message.text == "◀️ Admin menyusi":
        await state.clear(); await admin_panel(message, state); return
    ch_id = message.text.strip()
    if not ch_id.startswith("@"):
        ch_id = "@" + ch_id
    await state.update_data(ch_id=ch_id)
    await message.answer(f"✅ Kanal: <code>{ch_id}</code>\nEndi kanal <b>nomini</b> kiriting:")
    await state.set_state(AdminStates.add_channel_name)

@router.message(AdminStates.add_channel_name)
async def got_channel_name(message: Message, state: FSMContext):
    if message.text == "◀️ Admin menyusi":
        await state.clear(); await admin_panel(message, state); return
    data = await state.get_data()
    ch_id = data.get("ch_id", "")
    add_channel_db(ch_id, message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ <b>Kanal qo'shildi!</b>\n{ch_id} — {message.text.strip()}",
        reply_markup=channels_kb(),
    )

@router.message(F.text == "🗑 Kanal o'chirish")
async def del_channel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    chs = get_channels()
    if not chs:
        await message.answer("Kanallar yo'q.")
        return
    buttons = [[InlineKeyboardButton(
        text=f"🗑 {ch['name']} ({ch['channel_id']})",
        callback_data=f"svip_delch_{ch['channel_id']}"
    )] for ch in chs]
    await message.answer(
        "🗑 O'chirmoqchi bo'lgan kanalni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )

@router.callback_query(F.data.startswith("svip_delch_"))
async def del_channel_cb(call: CallbackQuery):
    ch_id = call.data[11:]
    ok = delete_channel_db(ch_id)
    text = ("✅ O'chirildi: " + ch_id) if ok else ("❌ Topilmadi: " + ch_id)
    await call.message.edit_text(text)

# ─────────────── ⚙️ TIZIM SOZLAMALARI ────────────────

@router.message(F.text == "⚙️ Tizim sozlamalari")
async def system_settings(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        f"⚙️ <b>Tizim sozlamalari</b>\n\n"
        f"💳 Hozirgi karta: <code>{ADMIN_CARD}</code>\n"
        f"🤖 Bot username: @{BOT_USERNAME}\n"
        f"👥 Admin IDs: {', '.join(str(i) for i in ADMIN_IDS)}\n\n"
        f"Karta raqamini o'zgartirish uchun quyidagi tugmani bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💳 Karta o'zgartirish", callback_data="svip_change_card")
        ]]),
    )

@router.callback_query(F.data == "svip_change_card")
async def change_card_cb(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💳 Yangi karta raqamini yuboring (faqat raqamlar):")
    await state.set_state(AdminStates.set_card)

@router.message(AdminStates.set_card)
async def got_new_card(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    global ADMIN_CARD
    new_card = message.text.strip().replace(" ", "")
    if not new_card.isdigit():
        await message.answer("❌ Faqat raqam kiriting!"); return
    ADMIN_CARD = new_card
    await state.clear()
    await message.answer(
        f"✅ Karta yangilandi: <code>{ADMIN_CARD}</code>",
        reply_markup=admin_kb(),
    )

# ─────────────── 📥 SO'ROVLAR ────────────────

@router.message(F.text == "📥 So'rovlar")
async def show_requests(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    pending = get_pending_payments()
    if not pending:
        await message.answer("📥 <b>Kutilayotgan so'rovlar yo'q.</b> ✅")
        return
    await message.answer(
        f"📥 <b>Kutilayotgan to'lovlar: {len(pending)} ta</b>\n\nQuyida har birini ko'rishingiz mumkin:"
    )
    for p in pending:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"svip_ok_{p['user_id']}"),
            InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"svip_no_{p['user_id']}"),
        ]])
        try:
            await message.bot.send_photo(
                chat_id=message.from_user.id,
                photo=p["photo_id"],
                caption=(
                    f"🔔 <b>To'lov #{p['id']}</b>\n\n"
                    f"👤 {p['full_name']}\n"
                    f"🆔 <code>{p['user_id']}</code>\n"
                    f"🎫 {p['tariff']}\n"
                    f"📅 {p['created_at']}"
                ),
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"So'rovni ko'rsatishda xato: {e}")

# ─────────────── 👥 FOYDALANUVCHILAR ────────────────

@router.message(F.text == "👥 Foydalanuvchilar")
async def users_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total  = get_user_count()
    vip_n  = get_vip_count()
    await message.answer(
        f"👥 <b>Foydalanuvchilar</b>\n\n"
        f"📊 Jami: <b>{total}</b>\n"
        f"💎 VIP: <b>{vip_n}</b>\n"
        f"👤 Oddiy: <b>{total - vip_n}</b>",
        reply_markup=users_kb(),
    )

@router.message(F.text == "🔍 Foydalanuvchi izlash")
async def user_search_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🆔 Foydalanuvchi <b>ID sini</b> yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Admin menyusi")]], resize_keyboard=True
        ),
    )
    await state.update_data(action="search")
    await state.set_state(AdminStates.ban_user_id)

@router.message(F.text == "🚫 Ban berish")
async def ban_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🆔 Ban beriladigan foydalanuvchi <b>ID sini</b> yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Admin menyusi")]], resize_keyboard=True
        ),
    )
    await state.update_data(action="ban")
    await state.set_state(AdminStates.ban_user_id)

@router.message(F.text == "✅ Ban ochish")
async def unban_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🆔 Ban ochiladigan foydalanuvchi <b>ID sini</b> yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Admin menyusi")]], resize_keyboard=True
        ),
    )
    await state.update_data(action="unban")
    await state.set_state(AdminStates.ban_user_id)

@router.message(AdminStates.ban_user_id)
async def process_user_action(message: Message, state: FSMContext):
    if message.text == "◀️ Admin menyusi":
        await state.clear(); await admin_panel(message, state); return
    data = await state.get_data()
    action = data.get("action", "search")
    try:
        target_uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Faqat ID raqam kiriting!"); return
    target = search_user(target_uid)
    if not target:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        await state.clear(); return
    if action == "ban":
        ban_user(target_uid)
        try:
            await message.bot.send_message(target_uid, "🚫 Siz botdan bloklangansiz. Admin bilan bog'laning.")
        except Exception:
            pass
        await message.answer(
            f"🚫 <b>Ban berildi:</b>\n👤 {target['full_name']}\n🆔 <code>{target_uid}</code>",
            reply_markup=users_kb(),
        )
    elif action == "unban":
        unban_user(target_uid)
        try:
            await message.bot.send_message(target_uid, "✅ Blokingiiz ochildi! /start bosing.")
        except Exception:
            pass
        await message.answer(
            f"✅ <b>Ban ochildi:</b>\n👤 {target['full_name']}\n🆔 <code>{target_uid}</code>",
            reply_markup=users_kb(),
        )
    else:
        await message.answer(
            f"👤 <b>Foydalanuvchi:</b>\n\n"
            f"🆔 ID: <code>{target_uid}</code>\n"
            f"👤 Ism: {target['full_name']}\n"
            f"🔖 Username: @{target['username'] or '—'}\n"
            f"👑 Status: <b>{target['status'].upper()}</b>\n"
            f"🪙 Coinlar: <b>{target['coins']}</b>\n"
            f"🚫 Ban: {'Ha' if target['is_banned'] else 'Yoq'}\n"
            f"📅 Qo'shildi: {target['joined_at']}",
            reply_markup=users_kb(),
        )
    await state.clear()

# ─────────────── 📩 XABAR YUBORISH ────────────────

@router.message(F.text == "📩 Xabar yuborish")
async def bc_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("📝 Xabar kiriting (matn, rasm, video bo'lishi mumkin):")
    await state.set_state(AdminStates.broadcast)

@router.message(AdminStates.broadcast)
async def bc_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🚀 Yuborilmoqda...")
    conn  = get_db()
    users = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    conn.close()
    ok, fail = 0, 0
    for u in users:
        try:
            await message.copy_to(u["user_id"], protect_content=True)
            ok += 1
        except Exception:
            fail += 1
    await message.answer(
        f"✅ <b>Yakunlandi</b>\n🟢 {ok} ta yetdi\n🔴 {fail} ta bloklangan",
        reply_markup=admin_kb(),
    )
    await state.clear()

# ─────────────── 👤 PROFIL ────────────────

@router.message(F.text == "👤 Profilim")
async def profile(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if not db or (uid not in ADMIN_IDS and db["status"] != "vip"):
        return
    conn  = get_db()
    refs  = conn.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (uid,)).fetchone()[0]
    conn.close()
    await message.answer(
        f"👤 <b>Profilingiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👑 Status: <b>{db['status'].upper()}</b>\n"
        f"🪙 Coinlar: <b>{db['coins']}</b>\n"
        f"👥 Taklif qilganlar: <b>{refs} kishi</b>\n\n"
        f"🔗 Referal havola:\n"
        f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>"
    )

# ─────────────── 🔍 QIDIRUV ────────────────

@router.message(F.text == "🔍 Qidiruv")
async def search_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "🔍 Kino nomi yoki kodini yozing:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BACK)]], resize_keyboard=True
        ),
    )

@router.message(SearchState.waiting_query)
async def search_do(message: Message, state: FSMContext):
    if message.text == BACK:
        await state.clear(); await home(message, state); return
    results = search_movies(message.text)
    db      = get_user(message.from_user.id)
    status  = "admin" if message.from_user.id in ADMIN_IDS else (db["status"] if db else "user")
    await state.clear()
    if not results:
        await message.answer("😔 Hech narsa topilmadi.", reply_markup=main_kb(status))
        return
    text = "🔍 <b>Topildi:</b>\n\n"
    for m in results:
        vip = " 💎" if m["is_vip"] else ""
        text += f"🎬 {m['title']}{vip} — <code>{m['code']}</code>\n"
    await message.answer(text, reply_markup=main_kb(status))

# ─────────────── 🏆 TOP ────────────────

@router.message(F.text == "🏆 Top kinolar")
async def top(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    movies = get_top_movies()
    if not movies:
        await message.answer("🎬 Hozircha kinolar yo'q."); return
    text = "🏆 <b>Eng ko'p ko'rilganlar:</b>\n\n"
    for i, m in enumerate(movies, 1):
        vip = " 💎" if m["is_vip"] else ""
        text += f"{i}. {m['title']}{vip} — 👁 {m['views']} — <code>{m['code']}</code>\n"
    await message.answer(text)

# ─────────────── 🆕 YANGI ────────────────

@router.message(F.text == "🆕 Yangi kinolar")
async def new_films(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    movies = get_new_movies()
    if not movies:
        await message.answer("🎬 Hozircha kinolar yo'q."); return
    text = "🆕 <b>Yangi qo'shilganlar:</b>\n\n"
    for m in movies:
        vip = " 💎" if m["is_vip"] else ""
        text += f"🎬 {m['title']}{vip} — <code>{m['code']}</code>\n"
    await message.answer(text)

# ─────────────── 📂 KATEGORIYALAR ────────────────

@router.message(F.text == "📂 Kategoriyalar")
async def categories(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    cats = get_categories()
    if not cats:
        await message.answer("📂 Kategoriyalar yo'q."); return
    await message.answer("📂 <b>Kategoriyani tanlang:</b>", reply_markup=cat_kb(cats))

@router.callback_query(F.data.startswith("svip_cat_"))
async def show_cat(call: CallbackQuery):
    cat    = call.data[9:]
    movies = get_by_category(cat)
    if not movies:
        await call.answer(f"'{cat}' da kinolar yo'q.", show_alert=True); return
    text = f"📂 <b>{cat}:</b>\n\n"
    for m in movies:
        vip = " 💎" if m["is_vip"] else ""
        text += f"🎬 {m['title']}{vip} — <code>{m['code']}</code>\n"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="svip_back")
    ]]))

@router.callback_query(F.data == "svip_back")
async def back_cats(call: CallbackQuery):
    cats = get_categories()
    try:
        await call.message.edit_text("📂 <b>Kategoriyani tanlang:</b>", reply_markup=cat_kb(cats))
    except Exception:
        await call.answer()

# ─────────────── 🎁 BONUS ────────────────

@router.message(F.text == "🎁 Kunlik bonus")
async def daily(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    if claim_bonus(uid):
        db = get_user(uid)
        await message.answer(
            f"🎁 <b>Bonus olindi!</b>\n🪙 +{DAILY_BONUS} coin\n💰 Jami: <b>{db['coins']}</b>"
        )
    else:
        await message.answer("⏳ Kunlik bonus allaqachon olindi. Ertaga qaytib keling!")

# ─────────────── 👥 REFERAL ────────────────

@router.message(F.text == "👥 Referal")
async def referral(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    conn = get_db()
    refs = conn.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (uid,)).fetchone()[0]
    conn.close()
    await message.answer(
        f"👥 <b>Referal tizimi</b>\n\n"
        f"Har taklif uchun <b>10 coin</b> olasiz!\n\n"
        f"🔗 Havolangiz:\n<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{refs}</b>\n"
        f"🪙 Coinlar: <b>{db['coins']}</b>"
    )

# ─────────────── 💎 VIP KINOLAR ────────────────

@router.message(F.text == "💎 VIP Kinolar")
async def vip_films(message: Message):
    uid = message.from_user.id
    db  = get_user(uid)
    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        return
    movies = get_vip_movies()
    if not movies:
        await message.answer("💎 VIP kinolar hozircha yo'q."); return
    text = "💎 <b>VIP Kinolar:</b>\n\n"
    for m in movies:
        text += f"🎬 {m['title']} — <code>{m['code']}</code>\n"
    await message.answer(text)

# ─────────────── 🎬 KINO YUBORISH ────────────────

@router.message(F.text)
async def send_movie(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    uid = message.from_user.id
    db  = get_user(uid)

    if uid not in ADMIN_IDS and (not db or db["status"] != "vip"):
        await message.answer("🔐 Premium kerak!", reply_markup=tariff_kb())
        return

    if not await check_sub(bot, uid):
        await message.answer("📢 Kanallarga obuna bo'ling:", reply_markup=sub_kb(get_channels()))
        return

    if is_spam(uid):
        await message.answer("⏳ Bir oz kuting...")
        return

    code = message.text.strip()
    if not code:
        return

    movie = get_movie(code)
    if not movie:
        await message.answer("❌ Bunday kod topilmadi.")
        return

    desc    = movie["description"] or "Yo'q"
    vip_tag = " 💎 VIP" if movie["is_vip"] else ""
    caption = (
        f"🎬 <b>{movie['title']}</b>{vip_tag}\n\n"
        f"📂 {movie['category']}\n"
        f"👁 {movie['views']} marta ko'rilgan\n"
        f"📝 {desc}"
    )
    try:
        if movie["file_type"] == "video":
            await message.answer_video(movie["file_id"], caption=caption, protect_content=True)
        else:
            await message.answer_document(movie["file_id"], caption=caption, protect_content=True)
    except Exception as e:
        logger.error(f"Kino yuborishda xato: {e}")
        await message.answer("⚠️ Kino yuborishda xatolik yuz berdi.")

# ════════════════════════════════════════════════════
#  🚀 MAIN
# ════════════════════════════════════════════════════

async def main():
    if not BOT_TOKEN:
        logger.error("SECRET_VIP_BOT_TOKEN environment variable not set!")
        return
    init_db()
    dp.include_router(router)
    logger.info(f"{BOT_NAME} ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")

import os
import time
import socket
import sqlite3
import threading
import traceback
from datetime import datetime

import telebot
from telebot import types

try:
    from keep_alive import keep_alive
except ImportError:
    def keep_alive():
        pass

# ============================================================
# SA:MP TELEGRAM BOT PRO
# One-file commercial version
# ============================================================

# ---------------- CONFIG ----------------
# You can use environment variables or a local .env file.
def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except Exception:
        pass

load_dotenv()

TOKEN = os.getenv("8736206770:AAEdRu_27hMZlsRh1rI9OEJlUgX9xUZKbTg ", "")
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "7777"))
REQUIRED_CHANNEL = os.getenv("@santropetrilogybot_news", "")
CHANNEL_URL = os.getenv("https://t.me/santropetrilogybot_news ", "")
DB_PATH = os.getenv("DB_PATH", "bot_stats.db")
BOT_NAME = os.getenv("BOT_NAME", "SA:MP Project Bot")

# Comma-separated Telegram IDs: ADMIN_IDS=709672781
ADMIN_IDS = {709672781}
for raw_id in os.getenv("ADMIN_IDS", "").split(","):
    raw_id = raw_id.strip()
    if raw_id.isdigit():
        ADMIN_IDS.add(int(raw_id))

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан. Укажите его в .env или переменной окружения.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)
DB_LOCK = threading.RLock()

POSITIONS = [
    "Игрок", "Хелпер", "Модератор", "Куратор", "Следящий", "ЗГС",
    "ГС", "Заместитель главного администратора", "Главный администратор",
    "Спецпроект", "Основатель", "Разработчик"
]

# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with DB_LOCK, db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            join_date TEXT,
            username TEXT,
            position TEXT DEFAULT 'Игрок',
            level INTEGER DEFAULT 0,
            notifications INTEGER DEFAULT 1,
            last_seen TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            position TEXT DEFAULT 'Администратор'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS support_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            question TEXT,
            status TEXT DEFAULT 'unread',
            date TEXT,
            admin_reply TEXT,
            assigned_admin INTEGER DEFAULT 0,
            updated_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            sender_id INTEGER,
            sender_type TEXT,
            message TEXT,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fraction TEXT NOT NULL,
            nickname TEXT NOT NULL,
            username TEXT,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS transfer_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            text_data TEXT,
            photo_file_id TEXT,
            status TEXT DEFAULT 'pending',
            date TEXT,
            admin_answer TEXT,
            assigned_admin INTEGER DEFAULT 0,
            updated_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            text TEXT,
            is_read INTEGER DEFAULT 0,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS server_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            players INTEGER DEFAULT 0,
            max_players INTEGER DEFAULT 0,
            hostname TEXT,
            gamemode TEXT,
            online INTEGER DEFAULT 0,
            response_ms REAL DEFAULT 0,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            text TEXT,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            date TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            comment TEXT,
            date TEXT
        )""")

        for aid in ADMIN_IDS:
            c.execute(
                "INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, ?, ?)",
                (aid, 3, "Главный администратор")
            )
        # Default settings
        defaults = {
            "welcome_text": "Добро пожаловать!",
            "donation_enabled": "0",
            "donation_details": "Укажите реквизиты оплаты в настройках бота.",
        }
        for key, value in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

        rows = c.execute("SELECT user_id FROM admins").fetchall()
        ADMIN_IDS.update(int(r[0]) for r in rows)


init_db()

# ---------------- DB HELPERS ----------------
def query_one(sql, params=()):
    with DB_LOCK, db() as conn:
        return conn.execute(sql, params).fetchone()


def query_all(sql, params=()):
    with DB_LOCK, db() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql, params=()):
    with DB_LOCK, db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def get_setting(key, default=""):
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row[0] if row else default


def set_setting(key, value):
    execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))


def log_action(admin_id, action, target_id=0, details=""):
    execute(
        "INSERT INTO action_logs(admin_id,action,target_id,details,date) VALUES(?,?,?,?,?)",
        (admin_id, action, target_id or 0, details[:1000], now())
    )


def get_nickname(user_id):
    row = query_one("SELECT nickname FROM users WHERE user_id=?", (user_id,))
    return row[0] if row else None


def get_username(user_id):
    row = query_one("SELECT username FROM users WHERE user_id=?", (user_id,))
    return row[0] if row else None


def get_position(user_id):
    row = query_one("SELECT position FROM users WHERE user_id=?", (user_id,))
    return row[0] if row else "Игрок"


def get_level(user_id):
    row = query_one("SELECT level FROM users WHERE user_id=?", (user_id,))
    return int(row[0]) if row else 0


def get_admin_level(user_id):
    row = query_one("SELECT level FROM admins WHERE user_id=?", (user_id,))
    return int(row[0]) if row else 0


def is_admin(user_id):
    return get_admin_level(user_id) > 0


def set_nickname(user_id, nick, username=None):
    old = query_one("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if old:
        execute("UPDATE users SET nickname=?, username=?, last_seen=? WHERE user_id=?", (nick, username, now(), user_id))
    else:
        execute(
            "INSERT INTO users(user_id,nickname,join_date,username,position,level,last_seen) VALUES(?,?,?,?,?,?,?)",
            (user_id, nick, now(), username, "Игрок", 0, now())
        )


def update_user_info(user_id, username):
    execute("UPDATE users SET username=?, last_seen=? WHERE user_id=?", (username, now(), user_id))


def set_position(user_id, position):
    execute("UPDATE users SET position=? WHERE user_id=?", (position, user_id))
    execute("UPDATE admins SET position=? WHERE user_id=?", (position, user_id))


def get_user_by_username(username):
    username = username.lstrip("@").lower()
    return query_one(
        "SELECT user_id,nickname,position FROM users WHERE LOWER(username)=?",
        (username,)
    )


def get_all_users():
    return [int(r[0]) for r in query_all("SELECT user_id FROM users")]


def get_all_admins():
    return query_all("""
        SELECT a.user_id,a.level,COALESCE(u.position,a.position) position,u.nickname,u.username
        FROM admins a LEFT JOIN users u ON a.user_id=u.user_id ORDER BY a.level DESC,a.user_id
    """)

# ---------------- SUBSCRIPTION ----------------
def is_subscribed(user_id):
    if not REQUIRED_CHANNEL:
        return True
    try:
        status = bot.get_chat_member(REQUIRED_CHANNEL, user_id).status
        return status in ("member", "administrator", "creator")
    except Exception:
        # Security-first behavior: if Telegram cannot verify, don't silently bypass.
        return False


def subscription_markup():
    kb = types.InlineKeyboardMarkup()
    if CHANNEL_URL:
        kb.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub"))
    return kb

# ---------------- MENUS ----------------
def main_menu(user_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🟢 Онлайн", "👤 Мой профиль")
    kb.row("🔗 Полезные ссылки", "📰 Новости")
    kb.row("📰 Новости", "🏆 Лидеры")
    kb.row("🎫 Поддержка", "🔄 Перенос аккаунта")
    kb.row("🔔 Уведомления", "💰 Донат")
    if is_admin(user_id):
        kb.row("👑 Админ-панель")
    return kb


def admin_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("👥 Пользователи", "adm_users"), ("🛡 Администраторы", "adm_admins"),
        ("🎫 Тикеты", "adm_tickets"), ("🔄 Переносы", "adm_transfers"),
        ("📰 Новости", "adm_news"), ("📢 Рассылка", "adm_broadcast"),
        ("📊 Статистика", "adm_stats"), ("📈 Сервер", "adm_server"),
        ("📜 Логи", "adm_logs"), ("💰 Донаты", "adm_donations"),
        ("⚙️ Настройки", "adm_settings"), ("🏆 Лидеры", "adm_leaders"),
    ]
    for text, data in buttons:
        kb.add(types.InlineKeyboardButton(text, callback_data=data))
    return kb

# ---------------- USER PROFILE ----------------
def profile_text(user_id):
    row = query_one("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not row:
        return "❌ Профиль ещё не создан. Используйте /start."
    username = f"@{row['username']}" if row['username'] else "Не указан"
    unread = query_one("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,))[0]
    tickets = query_one("SELECT COUNT(*) FROM support_requests WHERE user_id=?", (user_id,))[0]
    return (
        "<b>👤 Личный кабинет</b>\n\n"
        f"🎮 Ник: <b>{row['nickname'] or 'Не указан'}</b>\n"
        f"📱 Telegram: {username}\n"
        f"🛡 Должность: <b>{row['position']}</b>\n"
        f"⭐ Уровень: <b>{row['level']}</b>\n"
        f"📅 Регистрация: {row['join_date']}\n"
        f"🎫 Обращений: {tickets}\n"
        f"🔔 Непрочитанных: {unread}"
    )


def profile_markup():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎫 Мои тикеты", callback_data="my_tickets"),
        types.InlineKeyboardButton("🔔 Уведомления", callback_data="my_notifications"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="user_settings"),
    )
    return kb

# ---------------- SERVER QUERY ----------------
def get_online():
    started = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.5)
        ip_parts = [int(p) for p in SERVER_IP.split(".")]
        packet = bytearray(b"SAMP")
        packet.extend(ip_parts)
        packet.append(SERVER_PORT & 0xFF)
        packet.append((SERVER_PORT >> 8) & 0xFF)
        packet.append(ord("i"))
        sock.sendto(packet, (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(4096)
        sock.close()

        if len(data) < 12 or data[:4] != b"SAMP":
            raise ValueError("Неверный ответ SA:MP")

        players = int.from_bytes(data[11:13], "little")
        max_players = int.from_bytes(data[13:15], "little")
        offset = 15

        def read_str():
            nonlocal offset
            if offset + 4 > len(data):
                return ""
            length = int.from_bytes(data[offset:offset+4], "little")
            offset += 4
            raw = data[offset:offset+length]
            offset += length
            return raw.decode("utf-8", errors="replace")

        hostname = read_str()
        gamemode = read_str()
        language = read_str()
        response_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "online": True, "players": players, "max_players": max_players,
            "hostname": hostname, "gamemode": gamemode, "language": language,
            "response_ms": response_ms
        }
    except Exception as e:
        return {
            "online": False, "players": 0, "max_players": 0,
            "hostname": "", "gamemode": "", "language": "",
            "response_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": str(e)
        }


def save_server_snapshot(info):
    execute(
        "INSERT INTO server_history(players,max_players,hostname,gamemode,online,response_ms,date) VALUES(?,?,?,?,?,?,?)",
        (info["players"], info["max_players"], info["hostname"], info["gamemode"], int(info["online"]), info["response_ms"], now())
    )


def server_text(info):
    if not info["online"]:
        return (
            "<b>🔴 Сервер офлайн</b>\n\n"
            f"🌐 {SERVER_IP}:{SERVER_PORT}\n"
            f"⏱ Ответ: {info['response_ms']} мс"
        )
    return (
        "<b>🟢 Сервер онлайн</b>\n\n"
        f"👥 Онлайн: <b>{info['players']}/{info['max_players']}</b>\n"
        f"🎮 Название: {info['hostname'] or 'Неизвестно'}\n"
        f"🗺 Режим: {info['gamemode'] or 'Неизвестно'}\n"
        f"🌍 Язык: {info['language'] or 'Неизвестно'}\n"
        f"📡 Ответ: <b>{info['response_ms']} мс</b>"
    )

# ---------------- NOTIFICATIONS ----------------
def notify_user(user_id, title, text):
    execute(
        "INSERT INTO notifications(user_id,title,text,date) VALUES(?,?,?,?)",
        (user_id, title, text, now())
    )
    row = query_one("SELECT notifications FROM users WHERE user_id=?", (user_id,))
    enabled = bool(row[0]) if row else True
    if not enabled:
        return False
    try:
        bot.send_message(user_id, f"<b>🔔 {title}</b>\n\n{text}")
        return True
    except Exception:
        return False

# ---------------- NEWS ----------------
def news_get_all():
    return query_all("SELECT id,title,date FROM news ORDER BY id DESC")


def news_add(title, content, author="Администрация"):
    return execute(
        "INSERT INTO news(title,content,author,date) VALUES(?,?,?,?)",
        (title, content, author, now())
    )


def news_delete(news_id):
    execute("DELETE FROM news WHERE id=?", (news_id,))

# ---------------- LEADERS ----------------
def get_all_leaders():
    return query_all("SELECT id,fraction,nickname,username,date FROM leaders ORDER BY id")


def add_leader(fraction, nickname, username):
    username = username if username.startswith("@") or username == "Не указан" else "@" + username
    return execute(
        "INSERT INTO leaders(fraction,nickname,username,date) VALUES(?,?,?,?)",
        (fraction, nickname, username, now())
    )


def remove_leader(leader_id):
    execute("DELETE FROM leaders WHERE id=?", (leader_id,))

# ---------------- TICKETS ----------------
def create_ticket(user_id, question):
    nick = get_nickname(user_id) or "Без ника"
    username = get_username(user_id) or ""
    ticket_id = execute(
        "INSERT INTO support_requests(user_id,nickname,username,question,status,date,updated_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, nick, username, question, "open", now(), now())
    )
    execute(
        "INSERT INTO support_messages(ticket_id,sender_id,sender_type,message,date) VALUES(?,?,?,?,?)",
        (ticket_id, user_id, "user", question, now())
    )
    return ticket_id


def ticket_status_text(status):
    return {
        "open": "🟡 Открыт", "in_progress": "🔵 В работе",
        "answered": "🟢 Отвечен", "closed": "⚫ Закрыт", "unread": "🟠 Новый"
    }.get(status, status)


def ticket_markup(ticket_id, admin=False):
    kb = types.InlineKeyboardMarkup(row_width=2)
    if admin:
        kb.add(
            types.InlineKeyboardButton("✍️ Ответить", callback_data=f"ticket_reply:{ticket_id}"),
            types.InlineKeyboardButton("🔒 Закрыть", callback_data=f"ticket_close:{ticket_id}"),
            types.InlineKeyboardButton("📌 Взять", callback_data=f"ticket_take:{ticket_id}"),
        )
    return kb


def format_ticket(row):
    return (
        f"<b>🎫 Тикет #{row['id']}</b>\n"
        f"👤 {row['nickname'] or 'Без ника'}\n"
        f"🟢 Статус: {ticket_status_text(row['status'])}\n"
        f"📅 {row['date']}\n\n"
        f"<b>Вопрос:</b>\n{row['question']}"
    )

# ---------------- TRANSFERS ----------------
def transfer_text(row):
    return (
        f"<b>🔄 Перенос аккаунта #{row['id']}</b>\n\n"
        f"👤 {row['nickname']}\n"
        f"📱 @{row['username'] or 'нет'}\n"
        f"📅 {row['date']}\n"
        f"📌 Статус: <b>{row['status']}</b>\n\n"
        f"{row['text_data'] or 'Нет текста'}"
    )


def transfer_markup(tid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"transfer_ok:{tid}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"transfer_no:{tid}"),
    )
    return kb

# ---------------- STATS ----------------
def global_stats():
    users = query_one("SELECT COUNT(*) FROM users")[0]
    admins = query_one("SELECT COUNT(*) FROM admins")[0]
    tickets = query_one("SELECT COUNT(*) FROM support_requests")[0]
    open_tickets = query_one("SELECT COUNT(*) FROM support_requests WHERE status IN ('open','in_progress','unread')")[0]
    transfers = query_one("SELECT COUNT(*) FROM transfer_requests")[0]
    pending_transfers = query_one("SELECT COUNT(*) FROM transfer_requests WHERE status='pending'")[0]
    news = query_one("SELECT COUNT(*) FROM news")[0]
    leaders = query_one("SELECT COUNT(*) FROM leaders")[0]
    unread = query_one("SELECT COUNT(*) FROM notifications WHERE is_read=0")[0]
    return users, admins, tickets, open_tickets, transfers, pending_transfers, news, leaders, unread

# ---------------- START / REGISTRATION ----------------
user_states = {}


def require_subscription(message):
    if is_subscribed(message.from_user.id):
        return True
    text = "❗ Для использования бота необходимо подписаться на канал."
    bot.send_message(message.chat.id, text, reply_markup=subscription_markup())
    return False


@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    update_user_info(uid, message.from_user.username or "")
    if REQUIRED_CHANNEL and not is_subscribed(uid):
        bot.send_message(uid, "❗ Сначала подпишитесь на канал:", reply_markup=subscription_markup())
        return
    if not get_nickname(uid):
        user_states[uid] = {"state": "nickname"}
        bot.send_message(uid, "👋 Добро пожаловать!\n\nВведите ваш игровой ник:")
        return
    bot.send_message(uid, f"{get_setting('welcome_text', 'Добро пожаловать!')}\n\n<b>{get_nickname(uid)}</b>", reply_markup=main_menu(uid))


@bot.message_handler(commands=["cancel"])
def cancel(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "❌ Текущее действие отменено.", reply_markup=main_menu(message.from_user.id))

# ---------------- ADMIN COMMANDS ----------------
@bot.message_handler(commands=["админ"])
def cmd_admin(message):
    if get_admin_level(message.from_user.id) < 3:
        return bot.reply_to(message, "❌ Недостаточно прав.")
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return bot.reply_to(message, "Использование: /админ ID уровень")
    uid, level = int(parts[1]), int(parts[2])
    execute("INSERT OR REPLACE INTO admins(user_id,level,position) VALUES(?,?,?)", (uid, level, "Администратор"))
    ADMIN_IDS.add(uid)
    log_action(message.from_user.id, "Назначен администратор", uid, f"Уровень {level}")
    bot.reply_to(message, f"✅ Пользователь {uid} назначен администратором {level} уровня.")


@bot.message_handler(commands=["разадмин"])
def cmd_deadmin(message):
    if get_admin_level(message.from_user.id) < 3:
        return bot.reply_to(message, "❌ Недостаточно прав.")
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return bot.reply_to(message, "Использование: /разадмин ID")
    uid = int(parts[1])
    execute("DELETE FROM admins WHERE user_id=?", (uid,))
    ADMIN_IDS.discard(uid)
    log_action(message.from_user.id, "Снят администратор", uid)
    bot.reply_to(message, "✅ Администратор снят.")


@bot.message_handler(commands=["должность"])
def cmd_position(message):
    if get_admin_level(message.from_user.id) < 2:
        return bot.reply_to(message, "❌ Недостаточно прав.")
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return bot.reply_to(message, "/должность @username Должность")
    row = get_user_by_username(parts[1])
    if not row:
        return bot.reply_to(message, "❌ Пользователь не найден.")
    set_position(row[0], parts[2])
    log_action(message.from_user.id, "Изменена должность", row[0], parts[2])
    notify_user(row[0], "Должность изменена", f"Новая должность: <b>{parts[2]}</b>")
    bot.reply_to(message, "✅ Должность изменена.")


@bot.message_handler(commands=["должности"])
def cmd_positions(message):
    if get_admin_level(message.from_user.id) < 1:
        return
    admins = get_all_admins()
    if not admins:
        return bot.send_message(message.chat.id, "Администраторов нет.")
    text = "<b>🛡 Администраторы</b>\n\n"
    for r in admins:
        text += f"• {r['nickname'] or r['user_id']} — {r['position']} | LVL {r['level']}\n"
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["стата"])
def cmd_stats(message):
    if get_admin_level(message.from_user.id) < 1:
        return
    bot.send_message(message.chat.id, stats_text())


def stats_text():
    users, admins, tickets, open_tickets, transfers, pending, news, leaders, unread = global_stats()
    return (
        "<b>📊 Статистика проекта</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"🛡 Администраторов: <b>{admins}</b>\n"
        f"🎫 Тикетов: <b>{tickets}</b>\n"
        f"🟡 Открытых тикетов: <b>{open_tickets}</b>\n"
        f"🔄 Переносов: <b>{transfers}</b>\n"
        f"⏳ Ожидающих переносов: <b>{pending}</b>\n"
        f"📰 Новостей: <b>{news}</b>\n"
        f"🏆 Лидеров: <b>{leaders}</b>\n"
        f"🔔 Непрочитанных уведомлений: <b>{unread}</b>"
    )


@bot.message_handler(commands=["admlist"])
def cmd_admlist(message):
    cmd_positions(message)

# ---------------- MAIN BUTTONS ----------------
@bot.message_handler(content_types=["photo", "document"])
def media_handler(message):
    uid = message.from_user.id
    state = user_states.get(uid, {}).get("state")
    if state != "transfer":
        return
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    caption = message.caption or ""
    tid = execute(
        "INSERT INTO transfer_requests(user_id,nickname,username,text_data,photo_file_id,status,date,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, get_nickname(uid) or "", get_username(uid) or "", caption[:6000], file_id, "pending", now(), now())
    )
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ Заявка на перенос <b>#{tid}</b> отправлена администрации.", reply_markup=main_menu(uid))
    for aid in list(ADMIN_IDS):
        try:
            row = query_one("SELECT * FROM transfer_requests WHERE id=?", (tid,))
            bot.send_message(aid, transfer_text(row), reply_markup=transfer_markup(tid))
            if file_id:
                if message.photo:
                    bot.send_photo(aid, file_id, caption=f"📎 Фото к заявке #{tid}")
                else:
                    bot.send_document(aid, file_id, caption=f"📎 Файл к заявке #{tid}")
        except Exception:
            pass

@bot.message_handler(func=lambda m: True, content_types=["text"])
def all_text(message):
    uid = message.from_user.id
    text = (message.text or "").strip()

    # State machine has priority.
    state = user_states.get(uid, {}).get("state")
    if state:
        handle_state(message, state)
        return

    if text.startswith("/"):
        return
    if not require_subscription(message):
        return

    update_user_info(uid, message.from_user.username or "")

    if text == "🟢 Онлайн":
        info = get_online()
        save_server_snapshot(info)
        bot.send_message(uid, server_text(info))
    elif text == "👤 Мой профиль":
        bot.send_message(uid, profile_text(uid), reply_markup=profile_markup())
    elif text == "🔗 Полезные ссылки":
        show_useful_links(uid)
    elif text == "📰 Новости":
        show_news(uid)
    elif text == "🏆 Лидеры":
        show_leaders(uid)
    elif text == "🎫 Поддержка":
        user_states[uid] = {"state": "ticket"}
        bot.send_message(uid, "🎫 Опишите вашу проблему одним сообщением.\n\n/cancel — отменить")
    elif text == "🔄 Перенос аккаунта":
        user_states[uid] = {"state": "transfer"}
        bot.send_message(uid, "🔄 Отправьте данные для переноса аккаунта одним сообщением.\n\n/cancel — отменить")
    elif text == "🔔 Уведомления":
        show_notifications(uid)
    elif text == "💰 Донат":
        show_donations(uid)
    elif text == "👑 Админ-панель" and is_admin(uid):
        bot.send_message(uid, "<b>👑 Панель управления</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "Используйте кнопки меню.", reply_markup=main_menu(uid))

# ---------------- STATE HANDLER ----------------
def handle_state(message, state):
    uid = message.from_user.id
    text = message.text or ""
    if state == "nickname":
        nick = text.strip()
        if len(nick) < 2 or len(nick) > 40:
            return bot.send_message(uid, "❌ Ник должен содержать от 2 до 40 символов.")
        set_nickname(uid, nick, message.from_user.username or "")
        user_states.pop(uid, None)
        bot.send_message(uid, "✅ Ник сохранён!", reply_markup=main_menu(uid))
    elif state == "ticket":
        ticket_id = create_ticket(uid, text[:4000])
        user_states.pop(uid, None)
        bot.send_message(uid, f"✅ Тикет <b>#{ticket_id}</b> создан. Администратор ответит вам.", reply_markup=main_menu(uid))
        notify_admins_new_ticket(ticket_id)
    elif state == "admin_ticket_reply":
        ticket_id = user_states[uid].get("ticket_id")
        row = query_one("SELECT * FROM support_requests WHERE id=?", (ticket_id,))
        if not row:
            user_states.pop(uid, None)
            return bot.send_message(uid, "❌ Тикет не найден.")
        reply = text[:4000]
        execute("UPDATE support_requests SET status='answered',admin_reply=?,updated_at=? WHERE id=?", (reply, now(), ticket_id))
        execute("INSERT INTO support_messages(ticket_id,sender_id,sender_type,message,date) VALUES(?,?,?,?,?)", (ticket_id, uid, "admin", reply, now()))
        user_states.pop(uid, None)
        log_action(uid, "Ответ на тикет", row["user_id"], f"Тикет #{ticket_id}")
        notify_user(row["user_id"], f"Ответ по тикету #{ticket_id}", reply)
        bot.send_message(uid, "✅ Ответ отправлен.", reply_markup=admin_menu())
    elif state == "broadcast":
        user_states.pop(uid, None)
        run_broadcast(uid, text[:4000])
    elif state == "news_title":
        user_states[uid] = {"state": "news_content", "title": text[:200]}
        bot.send_message(uid, "Введите текст новости:")
    elif state == "news_content":
        title = user_states[uid]["title"]
        nid = news_add(title, text[:6000], get_nickname(uid) or "Администрация")
        user_states.pop(uid, None)
        log_action(uid, "Создана новость", nid, title)
        bot.send_message(uid, f"✅ Новость #{nid} создана.")
    elif state == "donation_item":
        user_states[uid] = {"state": "donation_amount", "item": text[:100]}
        bot.send_message(uid, "Введите сумму:")
    elif state == "donation_amount":
        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError
        except ValueError:
            return bot.send_message(uid, "❌ Введите корректную сумму.")
        item = user_states[uid]["item"]
        did = execute("INSERT INTO donations(user_id,item,amount,status,comment,date) VALUES(?,?,?,?,?,?)", (uid, item, amount, "pending", "", now()))
        user_states.pop(uid, None)
        bot.send_message(uid, f"✅ Заявка на донат #{did} создана.\n\n{get_setting('donation_details')}")
        for aid in ADMIN_IDS:
            try:
                bot.send_message(aid, f"💰 <b>Новая заявка на донат #{did}</b>\nИгрок: {get_nickname(uid)}\nТовар: {item}\nСумма: {amount}", reply_markup=donation_markup(did))
            except Exception:
                pass
    elif state == "transfer":
        tid = execute(
            "INSERT INTO transfer_requests(user_id,nickname,username,text_data,status,date,updated_at) VALUES(?,?,?,?,?,?,?)",
            (uid, get_nickname(uid) or "", get_username(uid) or "", text[:6000], "pending", now(), now())
        )
        user_states.pop(uid, None)
        bot.send_message(uid, f"✅ Заявка на перенос <b>#{tid}</b> отправлена администрации.", reply_markup=main_menu(uid))
        notify_admins_transfer(tid)

# ---------------- NEWS / LEADERS ----------------
def show_news(uid):
    rows = news_get_all()
    if not rows:
        return bot.send_message(uid, "📰 Новостей пока нет.")
    kb = types.InlineKeyboardMarkup()
    for r in rows[:15]:
        kb.add(types.InlineKeyboardButton(f"📰 {r['title'][:40]}", callback_data=f"news:{r['id']}"))
    bot.send_message(uid, "<b>📰 Новости</b>", reply_markup=kb)


def show_leaders(uid):
    rows = get_all_leaders()
    if not rows:
        return bot.send_message(uid, "🏆 Список лидеров пуст.")
    text = "<b>🏆 Лидеры проекта</b>\n\n"
    for r in rows:
        text += f"<b>{r['fraction']}</b> — {r['nickname']} {r['username'] or ''}\n"
    bot.send_message(uid, text)

# ---------------- NOTIFICATIONS UI ----------------
def show_notifications(uid):
    rows = query_all("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 15", (uid,))
    if not rows:
        return bot.send_message(uid, "🔔 Уведомлений нет.")
    text = "<b>🔔 Уведомления</b>\n\n"
    for r in rows:
        mark = "🔵" if r["is_read"] else "🟠"
        text += f"{mark} <b>{r['title']}</b> — {r['date']}\n{r['text'][:300]}\n\n"
    execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))
    bot.send_message(uid, text)

# ---------------- DONATIONS ----------------
def show_donations(uid):
    if get_setting("donation_enabled", "0") != "1":
        return bot.send_message(uid, "💰 Донат временно недоступен.")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оформить заявку", callback_data="donate_create"))
    bot.send_message(uid, "<b>💰 Донат</b>\n\nВыберите оформление заявки.", reply_markup=kb)


def donation_markup(did):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Оплачено", callback_data=f"donate_ok:{did}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"donate_no:{did}")
    )
    return kb

# ---------------- ADMIN NOTIFICATIONS ----------------
def notify_admins_new_ticket(ticket_id):
    row = query_one("SELECT * FROM support_requests WHERE id=?", (ticket_id,))
    if not row:
        return
    for aid in list(ADMIN_IDS):
        try:
            bot.send_message(aid, format_ticket(row), reply_markup=ticket_markup(ticket_id, True))
        except Exception:
            pass


def notify_admins_transfer(tid):
    row = query_one("SELECT * FROM transfer_requests WHERE id=?", (tid,))
    if not row:
        return
    for aid in list(ADMIN_IDS):
        try:
            bot.send_message(aid, transfer_text(row), reply_markup=transfer_markup(tid))
        except Exception:
            pass

# ---------------- CALLBACKS ----------------
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    uid = call.from_user.id
    data = call.data or ""
    try:
        if data == "check_sub":
            if is_subscribed(uid):
                bot.answer_callback_query(call.id, "✅ Подписка подтверждена")
                bot.send_message(uid, "✅ Доступ открыт.", reply_markup=main_menu(uid))
            else:
                bot.answer_callback_query(call.id, "❌ Подписка не найдена", show_alert=True)
            return

        if data.startswith("news:"):
            nid = int(data.split(":")[1])
            row = query_one("SELECT * FROM news WHERE id=?", (nid,))
            if row:
                bot.answer_callback_query(call.id)
                bot.send_message(uid, f"<b>📰 {row['title']}</b>\n\n{row['content']}\n\n<i>{row['date']}</i>")
            return

        if data == "my_tickets":
            rows = query_all("SELECT * FROM support_requests WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
            if not rows:
                return bot.answer_callback_query(call.id, "Тикетов нет")
            kb = types.InlineKeyboardMarkup()
            for r in rows:
                kb.add(types.InlineKeyboardButton(f"#{r['id']} — {ticket_status_text(r['status'])}", callback_data=f"view_ticket:{r['id']}"))
            bot.send_message(uid, "<b>🎫 Мои тикеты</b>", reply_markup=kb)
            return

        if data.startswith("view_ticket:"):
            tid = int(data.split(":")[1])
            row = query_one("SELECT * FROM support_requests WHERE id=? AND user_id=?", (tid, uid))
            if row:
                bot.send_message(uid, format_ticket(row))
            return

        if data == "my_notifications":
            show_notifications(uid)
            return

        if data == "user_settings":
            enabled = query_one("SELECT notifications FROM users WHERE user_id=?", (uid,))
            on = bool(enabled[0]) if enabled else True
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(f"🔔 Уведомления: {'ВКЛ' if on else 'ВЫКЛ'}", callback_data="toggle_notifications"))
            bot.send_message(uid, "<b>⚙️ Настройки</b>", reply_markup=kb)
            return

        if data == "toggle_notifications":
            row = query_one("SELECT notifications FROM users WHERE user_id=?", (uid,))
            new_value = 0 if row and row[0] else 1
            execute("UPDATE users SET notifications=? WHERE user_id=?", (new_value, uid))
            bot.answer_callback_query(call.id, "Настройки сохранены")
            return

        if data.startswith("ticket_"):
            if not is_admin(uid):
                return bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
            action, tid_raw = data.split(":", 1)
            tid = int(tid_raw)
            row = query_one("SELECT * FROM support_requests WHERE id=?", (tid,))
            if not row:
                return bot.answer_callback_query(call.id, "Тикет не найден", show_alert=True)
            if action == "ticket_reply":
                user_states[uid] = {"state": "admin_ticket_reply", "ticket_id": tid}
                execute("UPDATE support_requests SET status='in_progress',assigned_admin=?,updated_at=? WHERE id=?", (uid, now(), tid))
                bot.answer_callback_query(call.id)
                bot.send_message(uid, f"✍️ Введите ответ для тикета #{tid}.\n/cancel — отменить")
            elif action == "ticket_take":
                execute("UPDATE support_requests SET status='in_progress',assigned_admin=?,updated_at=? WHERE id=?", (uid, now(), tid))
                log_action(uid, "Взят тикет в работу", row["user_id"], f"Тикет #{tid}")
                bot.answer_callback_query(call.id, "Тикет взят в работу")
            elif action == "ticket_close":
                execute("UPDATE support_requests SET status='closed',assigned_admin=?,updated_at=? WHERE id=?", (uid, now(), tid))
                notify_user(row["user_id"], f"Тикет #{tid} закрыт", "Ваше обращение закрыто администрацией.")
                log_action(uid, "Закрыт тикет", row["user_id"], f"Тикет #{tid}")
                bot.answer_callback_query(call.id, "Тикет закрыт")
            return

        if data.startswith("transfer_"):
            if not is_admin(uid):
                return bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
            action, tid_raw = data.split(":", 1)
            tid = int(tid_raw)
            row = query_one("SELECT * FROM transfer_requests WHERE id=?", (tid,))
            if not row:
                return bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            if action == "transfer_ok":
                execute("UPDATE transfer_requests SET status='approved',admin_answer=?,assigned_admin=?,updated_at=? WHERE id=?", ("Одобрено", uid, now(), tid))
                notify_user(row["user_id"], f"Перенос #{tid} одобрен", "Администрация одобрила вашу заявку на перенос аккаунта.")
                log_action(uid, "Одобрен перенос", row["user_id"], f"Заявка #{tid}")
                bot.answer_callback_query(call.id, "Одобрено")
            elif action == "transfer_no":
                execute("UPDATE transfer_requests SET status='rejected',admin_answer=?,assigned_admin=?,updated_at=? WHERE id=?", ("Отклонено администрацией", uid, now(), tid))
                notify_user(row["user_id"], f"Перенос #{tid} отклонён", "Администрация отклонила вашу заявку.")
                log_action(uid, "Отклонён перенос", row["user_id"], f"Заявка #{tid}")
                bot.answer_callback_query(call.id, "Отклонено")
            return

        # ---- ADMIN PANEL ----
        if data.startswith("adm_"):
            if not is_admin(uid):
                return bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
            admin_callback(call)
            return

        if data == "donate_create":
            user_states[uid] = {"state": "donation_item"}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "Введите название товара/услуги для заявки:")
            return

        if data.startswith("donate_"):
            if get_admin_level(uid) < 1:
                return bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
            action, did_raw = data.split(":", 1)
            did = int(did_raw)
            row = query_one("SELECT * FROM donations WHERE id=?", (did,))
            if not row:
                return bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            status = "approved" if action == "donate_ok" else "rejected"
            execute("UPDATE donations SET status=? WHERE id=?", (status, did))
            notify_user(row["user_id"], f"Донат #{did}", f"Статус заявки: <b>{status}</b>")
            log_action(uid, f"Донат {status}", row["user_id"], f"Заявка #{did}")
            bot.answer_callback_query(call.id, "Статус изменён")
            return

    except Exception as e:
        traceback.print_exc()
        try:
            bot.answer_callback_query(call.id, "Произошла ошибка", show_alert=True)
        except Exception:
            pass

# ---------------- ADMIN CALLBACKS ----------------
def admin_callback(call):
    uid = call.from_user.id
    data = call.data
    if data == "adm_users":
        rows = query_all("SELECT user_id,nickname,username,position,level,join_date FROM users ORDER BY user_id DESC LIMIT 30")
        text = "<b>👥 Последние пользователи</b>\n\n"
        for r in rows:
            text += f"• <b>{r['nickname'] or 'Без ника'}</b> | {r['position']} | LVL {r['level']}\n"
        bot.send_message(uid, text[:4000])
    elif data == "adm_admins":
        rows = get_all_admins()
        text = "<b>🛡 Администраторы</b>\n\n"
        for r in rows:
            text += f"• {r['nickname'] or r['user_id']} — {r['position']} | LVL {r['level']}\n"
        bot.send_message(uid, text)
    elif data == "adm_tickets":
        rows = query_all("SELECT * FROM support_requests WHERE status IN ('open','in_progress','unread') ORDER BY id DESC LIMIT 20")
        if not rows:
            return bot.send_message(uid, "🎫 Открытых тикетов нет.")
        for r in rows[:10]:
            bot.send_message(uid, format_ticket(r), reply_markup=ticket_markup(r['id'], True))
    elif data == "adm_transfers":
        rows = query_all("SELECT * FROM transfer_requests WHERE status='pending' ORDER BY id DESC LIMIT 10")
        if not rows:
            return bot.send_message(uid, "🔄 Ожидающих переносов нет.")
        for r in rows:
            bot.send_message(uid, transfer_text(r), reply_markup=transfer_markup(r['id']))
    elif data == "adm_news":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Создать новость", callback_data="news_create"))
        rows = news_get_all()
        for r in rows[:10]:
            kb.add(types.InlineKeyboardButton(f"📰 {r['title'][:35]}", callback_data=f"news:{r['id']}"))
        bot.send_message(uid, "<b>📰 Управление новостями</b>", reply_markup=kb)
    elif data == "adm_broadcast":
        user_states[uid] = {"state": "broadcast"}
        bot.send_message(uid, "📢 Введите текст рассылки.\n/cancel — отменить")
    elif data == "adm_stats":
        bot.send_message(uid, stats_text())
    elif data == "adm_server":
        info = get_online()
        save_server_snapshot(info)
        bot.send_message(uid, server_text(info))
    elif data == "adm_logs":
        rows = query_all("SELECT * FROM action_logs ORDER BY id DESC LIMIT 30")
        text = "<b>📜 Последние действия</b>\n\n"
        for r in rows:
            text += f"#{r['id']} | admin {r['admin_id']} | {r['action']} | {r['date']}\n{r['details']}\n\n"
        bot.send_message(uid, text[:4000])
    elif data == "adm_donations":
        rows = query_all("SELECT * FROM donations ORDER BY id DESC LIMIT 20")
        text = "<b>💰 Донаты</b>\n\n"
        for r in rows:
            text += f"#{r['id']} | {r['item']} | {r['amount']} | {r['status']}\n"
        bot.send_message(uid, text[:4000])
    elif data == "adm_settings":
        donation = get_setting("donation_enabled", "0")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"💰 Донат: {'ВКЛ' if donation == '1' else 'ВЫКЛ'}", callback_data="setting_donation"))
        kb.add(types.InlineKeyboardButton("✏️ Реквизиты доната", callback_data="setting_donation_details"))
        bot.send_message(uid, "<b>⚙️ Настройки</b>\n\nВключайте только те функции, которые настроены.", reply_markup=kb)
    elif data == "adm_leaders":
        rows = get_all_leaders()
        text = "<b>🏆 Лидеры</b>\n\n"
        for r in rows:
            text += f"#{r['id']} {r['fraction']} — {r['nickname']} {r['username'] or ''}\n"
        bot.send_message(uid, text or "Лидеров нет.")
    elif data == "news_create":
        if get_admin_level(uid) < 2:
            return bot.answer_callback_query(call.id, "Нужен 2+ уровень", show_alert=True)
        user_states[uid] = {"state": "news_title"}
        bot.send_message(uid, "Введите заголовок новости:")
    elif data == "setting_donation":
        if get_admin_level(uid) < 3:
            return bot.answer_callback_query(call.id, "Нужен 3 уровень", show_alert=True)
        value = "0" if get_setting("donation_enabled", "0") == "1" else "1"
        set_setting("donation_enabled", value)
        bot.answer_callback_query(call.id, f"Донат {'включён' if value == '1' else 'выключен'}")
    elif data == "setting_donation_details":
        bot.send_message(uid, f"Текущие реквизиты:\n\n{get_setting('donation_details')}\n\nИзменить через переменную/БД настроек.")

# ---------------- BROADCAST ----------------
def run_broadcast(admin_id, text):
    users = get_all_users()
    sent = failed = 0
    bot.send_message(admin_id, f"📢 Рассылка запущена. Получателей: {len(users)}")
    for user_id in users:
        try:
            bot.send_message(user_id, f"<b>📢 Объявление</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
        time.sleep(0.05)
    bid = execute("INSERT INTO broadcasts(admin_id,text,sent,failed,date) VALUES(?,?,?,?,?)", (admin_id, text, sent, failed, now()))
    log_action(admin_id, "Рассылка", 0, f"#{bid}; sent={sent}; failed={failed}")
    bot.send_message(admin_id, f"✅ Рассылка завершена.\n\n📨 Отправлено: {sent}\n❌ Ошибок: {failed}")

# ---------------- NICK COMMAND ----------------
@bot.message_handler(commands=["ник"])
def nick_cmd(message):
    uid = message.from_user.id
    if not require_subscription(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) == 1:
        return bot.reply_to(message, f"Ваш ник: <b>{get_nickname(uid) or 'Не указан'}</b>\nИспользование: /ник Новый_Nick")
    nick = parts[1].strip()
    if not 2 <= len(nick) <= 40:
        return bot.reply_to(message, "❌ Ник должен содержать от 2 до 40 символов.")
    set_nickname(uid, nick, message.from_user.username or "")
    bot.reply_to(message, f"✅ Ник изменён на <b>{nick}</b>")

# ---------------- USEFUL LINKS ----------------
def show_useful_links(uid):
    kb = types.InlineKeyboardMarkup()
    if CHANNEL_URL:
        kb.add(types.InlineKeyboardButton("📢 Новости проекта", url=CHANNEL_URL))
    text = "<b>🔗 Полезные ссылки</b>\n\n"
    text += f"🌐 Сервер: <code>{SERVER_IP}:{SERVER_PORT}</code>\n"
    text += "Используйте кнопки выше для перехода к доступным ресурсам."
    bot.send_message(uid, text, reply_markup=kb)

# ---------------- LEGACY COMMANDS ----------------
@bot.message_handler(commands=["лог"])
def cmd_log(message):
    if not is_admin(message.from_user.id):
        return
    rows = query_all("SELECT * FROM action_logs ORDER BY id DESC LIMIT 100")
    path = "action_logs.txt"
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"#{r['id']} | {r['date']} | admin={r['admin_id']} | {r['action']} | {r['target_id']} | {r['details']}\n")
    with open(path, "rb") as f:
        bot.send_document(message.chat.id, f, caption="📜 Лог действий администраторов")

# ---------------- SERVER MONITOR ----------------
monitor_state = {"online": None}


def monitor_loop():
    while True:
        try:
            info = get_online()
            save_server_snapshot(info)
            current = bool(info["online"])
            previous = monitor_state["online"]
            if previous is not None and current != previous:
                if current:
                    title = "🟢 Сервер восстановлен"
                    body = f"Сервер снова онлайн: {info['players']}/{info['max_players']}"
                else:
                    title = "🔴 Сервер недоступен"
                    body = f"Не удалось получить ответ от {SERVER_IP}:{SERVER_PORT}"
                for uid in get_all_users():
                    notify_user(uid, title, body)
            monitor_state["online"] = current
        except Exception:
            pass
        time.sleep(300)

# ---------------- ERROR HANDLING ----------------
@bot.middleware_handler(update_types=['message'])
def middleware(bot_instance, message):
    try:
        if message.from_user and message.from_user.username is not None:
            update_user_info(message.from_user.id, message.from_user.username)
    except Exception:
        pass

# ---------------- STARTUP ----------------
def main():
    print(f"{BOT_NAME} started")
    print(f"Server: {SERVER_IP}:{SERVER_PORT}")
    if REQUIRED_CHANNEL:
        print(f"Required channel: {REQUIRED_CHANNEL}")
    threading.Thread(target=monitor_loop, daemon=True).start()
    keep_alive()
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()

import os
import time
import socket
import threading
import sqlite3
import telebot
from telebot import types
from samp_client.client import SampClient
from keep_alive import keep_alive

socket.setdefaulttimeout(5)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
ADMIN_IDS = {709672781, 5939366373, 1066139847} 
ADMIN_LEVELS = {}  # user_id -> уровень (1, 2, 3)

DB_PATH = os.environ.get("DB_PATH", "bot_stats.db")
# ==================================================

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан. Добавьте его в переменные окружения.")

telebot.apihelper.ENABLE_MIDDLEWARE = True
bot = telebot.TeleBot(TOKEN, threaded=True)

# Heartbeat — обновляется при каждом входящем update для watchdog
_last_heartbeat = time.time()

@bot.middleware_handler(update_types=["message", "callback_query"])
def update_heartbeat(bot_instance, update):
    global _last_heartbeat
    _last_heartbeat = time.time()

# ====== РАБОТА С БАЗОЙ ДАННЫХ ======
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            nickname TEXT,
            position TEXT DEFAULT 'Игрок',
            join_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_stats (
            id INTEGER PRIMARY KEY,
            peak_online INTEGER DEFAULT 0,
            peak_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            question TEXT,
            status TEXT DEFAULT 'unread',
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transfer_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            text_data TEXT,
            photo_file_id TEXT,
            status TEXT DEFAULT 'unread',
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS info_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fraction TEXT NOT NULL,
            nickname TEXT NOT NULL,
            username TEXT,
            date TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO server_stats (id, peak_online, peak_date) VALUES (1, 0, '')")
    # Добавляем колонку peak_day в server_stats (для суточного пика)
    try:
        cursor.execute("ALTER TABLE server_stats ADD COLUMN peak_day TEXT DEFAULT ''")
    except Exception:
        pass
    # Колонка для хранения запланированного времени следующего рестарта
    try:
        cursor.execute("ALTER TABLE server_stats ADD COLUMN last_restart TEXT DEFAULT ''")
    except Exception:
        pass
    # Колонка info_text оставлена для совместимости (не используется)
    try:
        cursor.execute("ALTER TABLE server_stats ADD COLUMN info_text TEXT DEFAULT ''")
    except Exception:
        pass
    # Колонка level в admins (если таблица уже существовала без неё)
    try:
        cursor.execute("ALTER TABLE admins ADD COLUMN level INTEGER DEFAULT 1")
    except Exception:
        pass
    for col in [("nickname", "TEXT"), ("position", "TEXT DEFAULT 'Игрок'")]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except Exception:
            pass
    # Добавляем хардкод-админов с уровнем 3
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
        cursor.execute("UPDATE admins SET level = 3 WHERE user_id = ? AND level < 3", (aid,))
    conn.commit()
    # Загружаем всех админов и их уровни из БД в память
    cursor.execute("SELECT user_id, level FROM admins")
    for row in cursor.fetchall():
        ADMIN_IDS.add(row[0])
        ADMIN_LEVELS[row[0]] = row[1] if row[1] else 1
    conn.close()

def get_admin_level(user_id):
    return ADMIN_LEVELS.get(user_id, 0)

def is_admin_l3(user_id):
    return ADMIN_LEVELS.get(user_id, 0) >= 3

def add_admin_db(user_id, level=1):
    ADMIN_IDS.add(user_id)
    ADMIN_LEVELS[user_id] = level
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, ?)", (user_id, level))
    cursor.execute("UPDATE admins SET level = ? WHERE user_id = ?", (level, user_id))
    conn.commit()
    conn.close()

def remove_admin_db(user_id):
    ADMIN_IDS.discard(user_id)
    ADMIN_LEVELS.pop(user_id, None)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ====== НОВОСТИ ======
def news_get_all():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, date FROM news ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows  # [(id, title, date), ...]

def news_get_by_id(news_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, author, date FROM news WHERE id = ?", (news_id,))
    row = cursor.fetchone()
    conn.close()
    return row  # (id, title, content, author, date) or None

def news_add(title, content, author="Администрация"):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    cursor.execute("INSERT INTO news (title, content, author, date) VALUES (?, ?, ?, ?)",
                   (title, content, author, date))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def news_edit(news_id, title, content):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE news SET title = ?, content = ? WHERE id = ?", (title, content, news_id))
    conn.commit()
    conn.close()

def news_delete(news_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()

# ====== ИНФОРМАЦИЯ (DB) ======
def info_get_all():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, date FROM info_pages ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def info_get_by_id(info_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, author, date FROM info_pages WHERE id = ?", (info_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def info_add(title, content, author="Администрация"):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    cursor.execute("INSERT INTO info_pages (title, content, author, date) VALUES (?, ?, ?, ?)",
                   (title, content, author, date))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def info_edit(info_id, title, content):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE info_pages SET title = ?, content = ? WHERE id = ?", (title, content, info_id))
    conn.commit()
    conn.close()

def info_delete(info_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM info_pages WHERE id = ?", (info_id,))
    conn.commit()
    conn.close()

# ====== СПИСОК ЛИДЕРОВ (DB) ======
def leaders_get_all():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fraction, nickname, username, date FROM leaders ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def leaders_get_by_id(leader_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fraction, nickname, username, date FROM leaders WHERE id = ?", (leader_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def leaders_add(fraction, nickname, username):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    cursor.execute("INSERT INTO leaders (fraction, nickname, username, date) VALUES (?, ?, ?, ?)",
                   (fraction, nickname, username, date))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def leaders_edit(leader_id, fraction, nickname, username):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE leaders SET fraction = ?, nickname = ?, username = ? WHERE id = ?", 
                   (fraction, nickname, username, leader_id))
    conn.commit()
    conn.close()

def leaders_delete(leader_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leaders WHERE id = ?", (leader_id,))
    conn.commit()
    conn.close()

# ====== ПОЛЬЗОВАТЕЛИ ======
def add_user(user_id, username):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        current_date = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
            (user_id, username, current_date)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

def get_user_id_by_username(username):
    """Ищет user_id по юзернейму (без @). Возвращает int или None."""
    username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_nickname(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_nickname(user_id, nickname):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))
    conn.commit()
    conn.close()

def get_position(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT position FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return "Администратор" if user_id in ADMIN_IDS else "Игрок"

def set_position(user_id, position):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET position = ? WHERE user_id = ?", (position, user_id))
    conn.commit()
    conn.close()

# ====== ФОРМАТИРОВАНИЕ ДОЛЖНОСТЕЙ SA:MP ======
def format_pos_string(pos):
    """Преобразует строку должности в строку с эмодзи."""
    if not pos:
        return "🎮 <b>Игрок</b>"
    p = pos.lower()

    # Специфические следящие должности (ГС / ЗГС / Следящие)
    if "гс гос" in p or "главный следящий за гос" in p:
        return f"🏢 <b>{pos}</b>"
    elif "згс гос" in p or "зам. гл. следящего за гос" in p:
        return f"🏢⚜️ <b>{pos}</b>"
    elif "следящий за гос" in p or "следящий гос" in p:
        return f"🏢🔎 <b>{pos}</b>"

    elif "гс гетто" in p or "главный следящий за гетто" in p:
        return f"🩸 <b>{pos}</b>"
    elif "згс гетто" in p or "зам. гл. следящего за гетто" in p:
        return f"🩸⚜️ <b>{pos}</b>"
    elif "следящий за гетто" in p or "следящий гетто" in p:
        return f"🩸🔎 <b>{pos}</b>"

    elif "гс мафий" in p or "главный следящий за мафиями" in p:
        return f"🕶️ <b>{pos}</b>"
    elif "згс мафий" in p or "зам. гл. следящего за мафиями" in p:
        return f"🕶️⚜️ <b>{pos}</b>"
    elif "следящий за мафиями" in p or "следящий мафий" in p:
        return f"🕶️🔎 <b>{pos}</b>"

    elif "гс ап" in p or "гс за админ" in p or "главный следящий за админ" in p:
        return f"📖 <b>{pos}</b>"
    elif "згс ап" in p or "згс за админ" in p:
        return f"📖⚜️ <b>{pos}</b>"
    elif "следящий за админ" in p or "следящий ап" in p:
        return f"📖🔎 <b>{pos}</b>"

    elif "гс хелперов" in p or "гс за хелперами" in p or "главный следящий за хелперами" in p:
        return f"🙋‍♂️ <b>{pos}</b>"
    elif "згс хелперов" in p or "згс за хелперами" in p:
        return f"🙋‍♂️⚜️ <b>{pos}</b>"

    elif "гс" in p or "главный следящий" in p:
        return f"⚡ <b>{pos}</b>"
    elif "згс" in p or "заместитель главного следящего" in p or "зам. гл. следящего" in p:
        return f"⚡⚜️ <b>{pos}</b>"
    elif "следящий" in p:
        return f"🔎 <b>{pos}</b>"

    # Стандартные SA:MP иерархические роли
    elif "основатель" in p or "создатель" in p or "developer" in p or "разработчик" in p:
        return f"💻 <b>{pos}</b>"
    elif "спец" in p or "special" in p:
        return f"🌟 <b>{pos}</b>"
    elif "гл. адм" in p or "га" == p or "главный адм" in p:
        return f"👑 <b>{pos}</b>"
    elif "зам. гл" in p or "зга" == p or "заместитель гл" in p:
        return f"⚜️ <b>{pos}</b>"
    elif "куратор" in p:
        return f"🛡️ <b>{pos}</b>"
    elif "администратор" in p or "админ" in p:
        return f"🛠️ <b>{pos}</b>"
    elif "модератор" in p or "модер" in p:
        return f"🛡️ <b>{pos}</b>"
    elif "хелпер" in p or "helper" in p:
        return f"🙋‍♂️ <b>{pos}</b>"
    elif "лидер" in p:
        return f"💼 <b>{pos}</b>"
    elif "игрок" in p:
        return f"🎮 <b>{pos}</b>"
    
    return f"🎖️ <b>{pos}</b>"

def get_formatted_position(user_id):
    """Возвращает должность с красивой SA:MP иконкой/эмодзи."""
    return format_pos_string(get_position(user_id))

def get_users_count():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_peak_online():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT peak_online, peak_date, peak_day FROM server_stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return (row[0], row[1], row[2]) if row else (0, "", "")

def update_peak_online(current_players):
    peak, peak_date, peak_day = get_peak_online()
    today = time.strftime("%d.%m.%Y")
    now = time.strftime("%d.%m.%Y %H:%M")
    # Новый день — сбрасываем пик
    if peak_day != today:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE server_stats SET peak_online = ?, peak_date = ?, peak_day = ? WHERE id = 1",
            (current_players, now, today)
        )
        conn.commit()
        conn.close()
        return current_players, now
    # Тот же день — обновляем только если больше
    if current_players > peak:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE server_stats SET peak_online = ?, peak_date = ?, peak_day = ? WHERE id = 1",
            (current_players, now, today)
        )
        conn.commit()
        conn.close()
        return current_players, now
    return peak, peak_date

def get_next_restart():
    """Возвращает запланированное время следующего рестарта (строка) или пустую строку."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT last_restart FROM server_stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] or "" if row else ""

def set_next_restart(restart_time: str):
    """Сохраняет запланированное время следующего рестарта."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_stats SET last_restart = ? WHERE id = 1", (restart_time,))
    conn.commit()
    conn.close()

def save_support_request(user_id, nickname, username, question):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    cursor.execute(
        "INSERT INTO support_requests (user_id, nickname, username, question, status, date) VALUES (?, ?, ?, ?, 'unread', ?)",
        (user_id, nickname, username, question, date)
    )
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_unread_requests():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, nickname, username, question, date FROM support_requests WHERE status = 'unread' ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_unread_count():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def mark_request_answered(request_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE support_requests SET status = 'answered' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def log_support_answer(req_id, player_nick, question, admin_nick, answer, req_date):
    log_time = time.strftime("%d.%m.%Y %H:%M")
    separator = "=" * 60
    entry = (
        f"\n{separator}\n"
        f"📋 Обращение №{req_id}\n"
        f"🕐 Дата обращения : {req_date}\n"
        f"✅ Дата ответа    : {log_time}\n"
        f"🎮 Игрок          : {player_nick}\n"
        f"❓ Вопрос         : {question}\n"
        f"👤 Администратор  : {admin_nick}\n"
        f"💬 Ответ          : {answer}\n"
        f"{separator}\n"
    )
    # Лог тоже храним рядом с БД, если DB_PATH задан
    log_dir = os.path.dirname(DB_PATH)
    log_path = os.path.join(log_dir, "support_log.txt") if log_dir else "support_log.txt"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        print(f"Ошибка записи лога: {e}")

# ====== БАЗА ДАННЫХ ДЛЯ ПЕРЕНОСОВ ======
def save_transfer_request(user_id, nickname, username, text_data, photo_file_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    cursor.execute(
        "INSERT INTO transfer_requests (user_id, nickname, username, text_data, photo_file_id, status, date) VALUES (?, ?, ?, ?, ?, 'unread', ?)",
        (user_id, nickname, username, text_data, photo_file_id, date)
    )
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return req_id

def set_transfer_status(req_id, status):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE transfer_requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()

def get_transfer_by_id(req_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, nickname, username, text_data, photo_file_id, status, date FROM transfer_requests WHERE id = ?", (req_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ====== ФУНКЦИИ СЕРВЕРА И КЛАВИАТУРЫ ======
def _fetch_samp_info():
    """Выполняется в отдельном потоке чтобы не заблокировать бота."""
    SampClient.timeout = 0.5  # максимум 0.5 сек на UDP-ответ
    start_time = time.time()
    with SampClient(address=SERVER_IP, port=SERVER_PORT) as client:
        info = client.get_server_info()
        ping = int((time.time() - start_time) * 1000)
        return info, ping

def check_samp_server():
    result = {}
    def _run():
        try:
            info, ping = _fetch_samp_info()
            result["data"] = (info, ping)
        except Exception as e:
            result["error"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=3)  # максимум 3 сек на ответ сервера

    if t.is_alive() or "data" not in result:
        return "❌ <b>Сервер недоступен.</b>"

    info, ping = result["data"]
    peak, peak_date = update_peak_online(info.players)

    return (
        f"🎮 <b>{info.hostname}</b>\n\n"
        f"🌐 <b>IP:</b> <code>{SERVER_IP}:{SERVER_PORT}</code>\n"
        f"👥 <b>Онлайн:</b> {info.players} / {info.max_players}\n"
        f"🏆 <b>Пик за сегодня:</b> {peak} <i>(был в {peak_date[11:]})</i>\n"
        f"⚡ <b>Пинг:</b> {ping} мс\n\n"
        f"🟢 Статус: Работает"
    )

MENU_BUTTONS = [
    "🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка",
    "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные",
    "📋 Помощь", "📰 Новости сервера", "ℹ️ Информация",
    "🔄 Перенос аккаунта", "💼 Список лидеров"
]

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("🌐 Онлайн"), types.KeyboardButton("🔗 Полезные ссылки"))
    markup.row(types.KeyboardButton("📰 Новости сервера"), types.KeyboardButton("ℹ️ Информация"))
    markup.row(types.KeyboardButton("💼 Список лидеров"), types.KeyboardButton("🔄 Перенос аккаунта"))
    markup.row(types.KeyboardButton("🎫 Тех поддержка"))
    if user_id in ADMIN_IDS:
        markup.row(types.KeyboardButton("📬 Непрочитанные"), types.KeyboardButton("📊 Статистика"))
        markup.row(types.KeyboardButton("📢 Рассылка"), types.KeyboardButton("📋 Помощь"))
    return markup

# ====== СТАРТ И НИКНЕЙМ ======
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    add_user(message.chat.id, message.from_user.username)
    nickname = get_nickname(message.chat.id)
    if not nickname:
        msg = bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать!\n\n"
            "Перед началом придумайте себе никнейм для бота.\n\n"
            "✍️ Введите ваш никнейм (только буквы, цифры и _):",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_nickname_input)
    else:
        bot.send_message(
            message.chat.id,
            f"👋 С возвращением, <b>{nickname}</b>! Используй меню бота:",
            reply_markup=get_main_keyboard(message.chat.id),
            parse_mode="HTML"
        )

def process_nickname_input(message):
    nick = message.text.strip()
    if nick in MENU_BUTTONS or nick == "/start":
        msg = bot.send_message(message.chat.id, "❌ Это не подходит как никнейм. Введите другое имя:")
        bot.register_next_step_handler(msg, process_nickname_input)
        return
    if len(nick) < 3:
        msg = bot.send_message(message.chat.id, "❌ Никнейм слишком короткий. Минимум 3 символа:")
        bot.register_next_step_handler(msg, process_nickname_input)
        return
    if len(nick) > 20:
        msg = bot.send_message(message.chat.id, "❌ Никнейм слишком длинный. Максимум 20 символов:")
        bot.register_next_step_handler(msg, process_nickname_input)
        return
    set_nickname(message.chat.id, nick)
    bot.send_message(
        message.chat.id,
        f"✅ Отлично, <b>{nick}</b>! Твой никнейм сохранён.\n\nДобро пожаловать в бот! 🎮",
        reply_markup=get_main_keyboard(message.chat.id),
        parse_mode="HTML"
    )

# ====== КОМАНДА /ник ======
@bot.message_handler(commands=['ник'])
def handle_change_nick(message):
    user_id = message.chat.id
    current = get_nickname(user_id)
    if not current:
        bot.send_message(user_id, "❌ Сначала введи /start и установи никнейм.")
        return
    msg = bot.send_message(
        user_id,
        f"🎮 Текущий никнейм: <code>{current}</code>\n\n✍️ Введите новый никнейм:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_change_nick)

def process_change_nick(message):
    user_id = message.chat.id
    nick = message.text.strip()
    if nick in MENU_BUTTONS or nick in ("/start", "/ник", "/стата"):
        msg = bot.send_message(user_id, "❌ Это не подходит как никнейм. Введите другое имя:")
        bot.register_next_step_handler(msg, process_change_nick)
        return
    if len(nick) < 3:
        msg = bot.send_message(user_id, "❌ Никнейм слишком короткий. Минимум 3 символа:")
        bot.register_next_step_handler(msg, process_change_nick)
        return
    if len(nick) > 20:
        msg = bot.send_message(user_id, "❌ Никнейм слишком длинный. Максимум 20 символов:")
        bot.register_next_step_handler(msg, process_change_nick)
        return
    set_nickname(user_id, nick)
    bot.send_message(
        user_id,
        f"✅ Никнейм успешно изменён на <b>{nick}</b>!",
        parse_mode="HTML"
    )

# ====== КОМАНДА /стата ======
@bot.message_handler(commands=['стата'])
def handle_stata_command(message):
    user_id = message.chat.id
    nickname = get_nickname(user_id)
    if not nickname:
        bot.send_message(user_id, "❌ Сначала введи /start и установи никнейм.")
        return
    formatted_pos = get_formatted_position(user_id)
    try:
        with SampClient(address=SERVER_IP, port=SERVER_PORT) as client:
            info = client.get_server_info()
            server_status = f"🟢 {info.hostname}"
    except Exception:
        server_status = "🔴 Недоступен"
    stata_text = (
        f"📋 <b>Профиль игрока</b>\n\n"
        f"🎮 <b>NickName:</b> <code>{nickname}</code>\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"🖥️ <b>Сервер:</b> {server_status}\n"
        f"🎖️ <b>Должность:</b> {formatted_pos}"
    )
    bot.send_message(user_id, stata_text, parse_mode="HTML")

# ====== КОМАНДА /поиск (только для админов) ======
@bot.message_handler(commands=['поиск'])
def handle_search_command(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(
            message, 
            "❌ <b>Формат команды:</b>\n"
            "<code>/поиск [Никнейм или Username]</code>\n\n"
            "💡 Пример: <code>/поиск Ivan_Ivanov</code>", 
            parse_mode="HTML"
        )
        return
    
    search_term = parts[1].strip()
    
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, nickname, position, join_date FROM users WHERE LOWER(nickname) LIKE ? OR LOWER(username) LIKE ?",
        (f"%{search_term.lower()}%", f"%{search_term.lower()}%")
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, f"🔍 Пользователи по запросу «<b>{search_term}</b>» не найдены.", parse_mode="HTML")
        return
        
    text = f"🔍 <b>Результаты поиска ({len(rows)}):</b>\n\n"
    for row in rows:
        uid, uname, nick, pos, jdate = row
        tg_link = f"@{uname}" if uname else "Нет"
        formatted_pos = format_pos_string(pos)
        text += (
            f"🎮 <b>Ник в боте:</b> <code>{nick or 'Не установлен'}</code>\n"
            f"🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
            f"📱 <b>Юзернейм:</b> {tg_link}\n"
            f"🎖️ <b>Должность:</b> {formatted_pos}\n"
            f"📅 <b>Регистрация:</b> {jdate or 'Неизвестно'}\n"
            f"───────────────────\n"
        )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ====== КОМАНДА /админы (только для админов) ======
@bot.message_handler(commands=['админы'])
def handle_admins_list_command(message):
    if message.from_user.id not in ADMIN_IDS:
        return
        
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.user_id, a.level, u.nickname, u.username, u.position 
        FROM admins a 
        LEFT JOIN users u ON a.user_id = u.user_id
        ORDER BY a.level DESC, u.nickname ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "📭 Список администраторов пуст.")
        return
        
    text = "🛡️ <b>Список администраторов бота:</b>\n\n"
    for row in rows:
        uid, lvl, nick, uname, pos = row
        nick_disp = nick if nick else "Не установлен"
        tg_link = f"@{uname}" if uname else f"<a href='tg://user?id={uid}'>Ссылка</a>"
        
        # Если должность пустая в БД, но он в ADMIN_IDS
        if not pos:
            pos = "Администратор" if uid in ADMIN_IDS else "Игрок"
            
        formatted_pos = format_pos_string(pos)
        text += (
            f"👤 <b>{nick_disp}</b> [Уровень {lvl}]\n"
            f"🆔 ID: <code>{uid}</code> | Юзернейм: {tg_link}\n"
            f"🎖️ Должность: {formatted_pos}\n"
            f"───────────────────\n"
        )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ====== КОМАНДА /должность ======
@bot.message_handler(commands=['должность'])
def handle_set_position(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split(maxsplit=2)
        target_id, display = _resolve_target(parts[1])
        if target_id is None:
            bot.reply_to(message, display, parse_mode="HTML")
            return
        new_position = parts[2].strip()
        set_position(target_id, new_position)
        
        # Обновленный красивый ответ с иконкой
        formatted_role = get_formatted_position(target_id)
        bot.reply_to(
            message, 
            f"✅ Должность пользователя {display} успешно изменена!\n"
            f"📌 Новая роль: {formatted_role}", 
            parse_mode="HTML"
        )
        
        # Уведомляем игрока
        try:
            bot.send_message(
                target_id, 
                f"🎉 Администрация обновила вашу должность в боте!\n"
                f"📌 Теперь ваша роль: {formatted_role}", 
                parse_mode="HTML"
            )
        except Exception:
            pass
            
    except Exception:
        bot.reply_to(
            message, 
            "❌ <b>Формат команды:</b>\n"
            "<code>/должность [@username / ID] [Название должности]</code>\n\n"
            "💡 <b>Примеры выдачи следящих должностей:</b>\n"
            "• <code>/должность @nick ГС ГОС</code>\n"
            "• <code>/должность @nick ЗГС Гетто</code>\n"
            "• <code>/должность @nick Следящий за Мафиями</code>\n"
            "• <code>/должность @nick ГС АП</code> <i>(Админ-Практика)</i>\n"
            "• <code>/должность @nick ГС Хелперов</code>\n\n"
            "📋 <b>Полный список поддерживаемых ролей:</b>\n"
            "👑 Основатель / Создатель\n"
            "🌟 Спец. Администратор\n"
            "👑 ГА / ЗГА\n"
            "🛡️ Куратор / Админ / Хелпер\n"
            "🏢 ГС ГОС / ЗГС ГОС / Следящий ГОС\n"
            "🩸 ГС Гетто / ЗГС Гетто / Следящий Гетто\n"
            "🕶️ ГС Мафий / ЗГС Мафий / Следящий Мафий\n"
            "📖 ГС АП / ЗГС АП\n"
            "🙋‍♂️ ГС Хелперов / ЗГС Хелперов", 
            parse_mode="HTML"
        )

def _resolve_target(arg: str):
    """Принимает ID или @username, возвращает (user_id, display) или (None, err_text)."""
    if arg.startswith("@") or not arg.lstrip("-").isdigit():
        uid = get_user_id_by_username(arg)
        if uid is None:
            return None, f"❌ Пользователь <code>{arg}</code> не найден в базе. Он должен был написать боту хотя бы один раз."
        return uid, arg
    return int(arg), f"<code>{arg}</code>"

# ====== КОМАНДА /админ и /разадмин ======
@bot.message_handler(commands=['админ'])
def handle_add_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split(maxsplit=2)
        target_id, display = _resolve_target(parts[1])
        if target_id is None:
            bot.reply_to(message, display, parse_mode="HTML")
            return
        level = int(parts[2]) if len(parts) > 2 else 1
        if level not in (1, 2, 3):
            bot.reply_to(message, "❌ Уровень должен быть 1, 2 или 3.")
            return
        add_admin_db(target_id, level)
        
        # Автоматически синхронизируем SA:MP должность в зависимости от уровня админки
        if level == 1:
            set_position(target_id, "Мл. Администратор")
        elif level == 2:
            set_position(target_id, "Администратор")
        elif level == 3:
            set_position(target_id, "Гл. Администратор")
            
        formatted_role = get_formatted_position(target_id)
        bot.reply_to(message, f"✅ Пользователь {display} назначен <b>администратором {level} уровня</b> ({formatted_role}).", parse_mode="HTML")
        try:
            bot.send_message(target_id, f"🎉 Вам выданы права <b>администратора {level} уровня</b> бота! Ваша должность: {formatted_role}", parse_mode="HTML")
        except Exception:
            pass
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Формат: /админ @username [уровень]\nПример: /админ @vasya 3")

@bot.message_handler(commands=['разадмин'])
def handle_remove_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split(maxsplit=1)
        target_id, display = _resolve_target(parts[1])
        if target_id is None:
            bot.reply_to(message, display, parse_mode="HTML")
            return
        if target_id not in ADMIN_IDS:
            bot.reply_to(message, f"⚠️ Пользователь {display} не является администратором.", parse_mode="HTML")
            return
        remove_admin_db(target_id)
        set_position(target_id, "Игрок")
        bot.reply_to(message, f"✅ Права администратора у пользователя {display} сняты. Роль возвращена на <b>🎮 Игрок</b>.", parse_mode="HTML")
        try:
            bot.send_message(target_id, "ℹ️ Ваши права администратора бота были сняты. Ваша должность возвращена на роль игрока.", parse_mode="HTML")
        except Exception:
            pass
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Формат: /разадмин @username\nПример: /разадмин @vasya")

# ====== КОМАНДА /лог (только для админов) ======
@bot.message_handler(commands=['лог'])
def handle_log_command(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    log_dir = os.path.dirname(DB_PATH)
    log_path = os.path.join(log_dir, "support_log.txt") if log_dir else "support_log.txt"
    if not os.path.exists(log_path):
        bot.reply_to(message, "📭 Лог пуст — ни одного ответа на обращение ещё не было.")
        return
    if os.path.getsize(log_path) == 0:
        bot.reply_to(message, "📭 Лог пуст — ни одного ответа на обращение ещё не было.")
        return
    with open(log_path, "rb") as f:
        bot.send_document(
            message.chat.id,
            f,
            caption="📋 <b>Лог обращений тех. поддержки</b>",
            parse_mode="HTML"
        )

# ====== ОБРАБОТЧИКИ КНОПОК ======
@bot.message_handler(commands=['online'])
def handle_online_command(message):
    bot.send_message(message.chat.id, "⏳ Опрашиваю сервер...")
    bot.send_message(message.chat.id, check_samp_server(), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🌐 Онлайн")
def handle_online_button(message):
    bot.send_message(message.chat.id, "⏳ Опрашиваю сервер...")
    bot.send_message(message.chat.id, check_samp_server(), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🔗 Полезные ссылки")
def handle_links_button(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Telegram Канал", url="https://t.me/santrope_trilogyrp"),
        types.InlineKeyboardButton("🌐 Форум проекта", url="https://wh32893.web3.maze-tech.ru/index.php"),
        types.InlineKeyboardButton("📱 Группа ВКонтакте", url="https://vk.ru/santropetrilogy")
    )
    bot.send_message(message.chat.id, "🔗 <b>Официальные ресурсы проекта:</b>", reply_markup=markup, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def handle_stats_button(message):
    if message.chat.id not in ADMIN_IDS:
        return
    total_users = get_users_count()
    unread = get_unread_count()
    stats_text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👤 Всего пользователей в базе: <code>{total_users}</code>\n"
        f"📬 Непрочитанных обращений: <code>{unread}</code>\n"
        f"🔄 Статус базы данных: <code>Активна</code>"
    )
    bot.send_message(message.chat.id, stats_text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "📋 Помощь")
def handle_help_button(message):
    if message.chat.id not in ADMIN_IDS:
        return
    lvl = get_admin_level(message.chat.id)
    help_text = (
        f"📋 <b>Команды администратора (ваш уровень: {lvl}):</b>\n\n"
        "👤 <b>Управление пользователями</b>\n"
        "/админ <code>ID [уровень]</code> — выдать права администратора (уровень 1-3)\n"
        "/разадмин <code>ID</code> — снять права администратора\n"
        "/должность <code>ID Должность</code> — изменить должность игрока\n"
        "/поиск <code>Ник</code> — быстрый поиск игрока в базе по нику/юзернейму\n"
        "/админы — посмотреть список всей администрации бота\n\n"
        "🎮 <b>Профиль</b>\n"
        "/стата — посмотреть свой профиль\n"
        "/ник — сменить свой никнейм\n\n"
        "📋 <b>Прочее</b>\n"
        "/лог — скачать историю ответов тех. поддержки\n"
        "/online — статус сервера\n\n"
        "🔘 <b>Кнопки меню</b>\n"
        "🌐 Онлайн — статус SA:MP сервера\n"
        "🔗 Полезные ссылки — официальные ресурсы проекта\n"
        "📰 Новости сервера — список новостей\n"
        "ℹ️ Информация — информация о сервере\n"
        "💼 Список лидеров — актуальный список лидеров\n"
        "🔄 Перенос аккаунта — подача заявки на перенос\n"
        "🎫 Тех поддержка — список обращений и ответ\n"
        "📬 Непрочитанные — новые необработанные обращения\n"
        "📊 Статистика — кол-во пользователей и обращений\n"
        "📢 Рассылка — отправить сообщение всем пользователям\n\n"
    )
    if lvl >= 3:
        help_text += (
            "📰 <b>Управление новостями, инфо и списком лидеров (уровень 3):</b>\n"
            "Добавление, редактирование и удаление доступно прямо из разделов меню на кнопках."
        )
    bot.send_message(message.chat.id, help_text, parse_mode="HTML")

# ====== СПИСОК ЛИДЕРОВ (КНОПКА & CALLBACKS) ======
def _leaders_list_markup(user_id):
    """Формирует inline-клавиатуру со списком лидеров."""
    all_leaders = leaders_get_all()
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not all_leaders:
        return markup, False
    for lid, fraction, nickname, username, date in all_leaders:
        markup.add(types.InlineKeyboardButton(f"💼 {fraction}: {nickname}", callback_data=f"lv_{lid}"))
    if is_admin_l3(user_id):
        markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
    return markup, True

@bot.message_handler(func=lambda message: message.text == "💼 Список лидеров")
def handle_leaders_button(message):
    markup, has_leaders = _leaders_list_markup(message.chat.id)
    if not has_leaders:
        text = "📭 <b>Список лидеров пока пуст.</b>"
        if is_admin_l3(message.chat.id):
            markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "💼 <b>Список лидеров проекта:</b>\nВыберите фракцию для просмотра:", reply_markup=markup, parse_mode="HTML")

# -- просмотр карточки лидера --
@bot.callback_query_handler(func=lambda call: call.data.startswith("lv_"))
def handle_leader_view(call):
    leader_id = int(call.data[3:])
    row = leaders_get_by_id(leader_id)
    if not row:
        bot.answer_callback_query(call.id, "Лидер не найден.")
        return
    lid, fraction, nickname, username, date = row
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_admin_l3(call.message.chat.id):
        markup.add(
            types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"le_{lid}"),
            types.InlineKeyboardButton("🗑 Удалить", callback_data=f"ld_{lid}")
        )
    markup.add(types.InlineKeyboardButton("« Назад к списку", callback_data="l_list"))
    
    uname_text = f"@{username}" if username else "Не указан"
    text = (
        f"💼 <b>Лидер фракции: {fraction}</b>\n\n"
        f"🎮 <b>Игровой Nick_Name:</b> <code>{nickname}</code>\n"
        f"📱 <b>Связь (Telegram):</b> {uname_text}\n"
        f"📅 <b>Дата назначения:</b> {date}\n"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- вернуться к списку лидеров --
@bot.callback_query_handler(func=lambda call: call.data == "l_list")
def handle_leaders_list_back(call):
    markup, has_leaders = _leaders_list_markup(call.message.chat.id)
    if not has_leaders:
        text = "📭 <b>Список лидеров пока пуст.</b>"
        if is_admin_l3(call.message.chat.id):
            markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
    else:
        text = "💼 <b>Список лидеров проекта:</b>\nВыберите фракцию для просмотра:"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- добавить лидера (шаг 1: фракция) --
@bot.callback_query_handler(func=lambda call: call.data == "l_add")
def handle_leader_add(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    msg = bot.send_message(call.message.chat.id,
                           "💼 <b>Добавление лидера</b>\n\n✍️ Введите <b>название фракции</b> (например: ФБР, LSPD, Grove Street):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_add_step2)
    bot.answer_callback_query(call.id)

def _leader_add_step2(message):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    fraction = message.text.strip()
    if not fraction:
        msg = bot.send_message(message.chat.id, "❌ Фракция не может быть пустой. Введите заново:")
        bot.register_next_step_handler(msg, _leader_add_step2)
        return
    msg = bot.send_message(message.chat.id,
                           f"✅ Фракция: <b>{fraction}</b>\n\n✍️ Введите <b>Nick_Name</b> лидера:",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_add_step3, fraction)

def _leader_add_step3(message, fraction):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    nickname = message.text.strip()
    if not nickname:
        msg = bot.send_message(message.chat.id, "❌ Никнейм не может быть пустым. Введите заново:")
        bot.register_next_step_handler(msg, _leader_add_step3, fraction)
        return
    msg = bot.send_message(message.chat.id,
                           f"✅ Лидер: <b>{nickname}</b>\n\n✍️ Теперь укажите его <b>Telegram Username</b> (или «-» если связь отсутствует):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_add_finish, fraction, nickname)

def _leader_add_finish(message, fraction, nickname):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    username = message.text.strip().replace("@", "")
    if username == "-":
        username = ""
    lid = leaders_add(fraction, nickname, username)
    bot.send_message(message.chat.id, f"✅ Лидер фракции «<b>{fraction}</b>» ({nickname}) успешно назначен в базу (№{lid}).", parse_mode="HTML")

# -- редактировать лидера --
@bot.callback_query_handler(func=lambda call: call.data.startswith("le_"))
def handle_leader_edit(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    leader_id = int(call.data[3:])
    row = leaders_get_by_id(leader_id)
    if not row:
        bot.answer_callback_query(call.id, "Лидер не найден.")
        return
    _, fraction, nickname, username, _ = row
    msg = bot.send_message(call.message.chat.id,
                           f"✏️ <b>Редактирование лидера №{leader_id}</b>\n"
                           f"Текущая фракция: <i>{fraction}</i>\n\n"
                           "Введите новое название фракции (или «.» чтобы оставить без изменений):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_edit_step2, leader_id, fraction, nickname, username)
    bot.answer_callback_query(call.id)

def _leader_edit_step2(message, leader_id, old_fraction, old_nickname, old_username):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    new_fraction = old_fraction if message.text.strip() == "." else message.text.strip()
    msg = bot.send_message(message.chat.id,
                           f"Текущий Nick_Name: <i>{old_nickname}</i>\n\n"
                           "Введите новый Nick_Name (или «.» чтобы оставить без изменений):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_edit_step3, leader_id, new_fraction, old_nickname, old_username)

def _leader_edit_step3(message, leader_id, new_fraction, old_nickname, old_username):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    new_nickname = old_nickname if message.text.strip() == "." else message.text.strip()
    msg = bot.send_message(message.chat.id,
                           f"Текущий Telegram: <i>@{old_username if old_username else 'нет'}</i>\n\n"
                           "Введите новый Telegram (или «.» чтобы оставить, или «-» чтобы удалить связь):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _leader_edit_finish, leader_id, new_fraction, new_nickname, old_username)

def _leader_edit_finish(message, leader_id, new_fraction, new_nickname, old_username):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    val = message.text.strip()
    if val == ".":
        new_username = old_username
    elif val == "-":
        new_username = ""
    else:
        new_username = val.replace("@", "")
        
    leaders_edit(leader_id, new_fraction, new_nickname, new_username)
    bot.send_message(message.chat.id, f"✅ Данные лидера №{leader_id} успешно изменены в базе.", parse_mode="HTML")

# -- удалить лидера --
@bot.callback_query_handler(func=lambda call: call.data.startswith("ld_"))
def handle_leader_delete_confirm(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    leader_id = int(call.data[3:])
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"ldc_{leader_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"lv_{leader_id}")
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Подтвердите удаление")

@bot.callback_query_handler(func=lambda call: call.data.startswith("ldc_"))
def handle_leader_delete_do(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    leader_id = int(call.data[4:])
    leaders_delete(leader_id)
    markup, has_leaders = _leaders_list_markup(call.message.chat.id)
    text = "💼 <b>Список лидеров проекта:</b>\nВыберите фракцию для просмотра:" if has_leaders else "📭 <b>Список лидеров пока пуст.</b>"
    if not has_leaders and is_admin_l3(call.message.chat.id):
        markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Лидер удален")

# ====== ПЕРЕНОС АККАУНТОВ ======
@bot.message_handler(func=lambda message: message.text == "🔄 Перенос аккаунта")
def handle_transfer_button(message):
    text = (
        "🔄 <b>Перенос аккаунтов с разных проектов!</b>\n\n"
        "📋 <b>Форма подачи заявления:</b>\n"
        "▫️ <b>Nick_Name:</b>\n"
        "▫️ <b>Проект с которого переносите:</b>\n"
        "▫️ <b>Что переносите:</b>\n"
        "▫️ <b>Доказательства имущества (/time):</b>\n\n"
        "✍️ <b>Заполните данную форму и отправьте ответным сообщением!</b>\n"
        "📸 <i>Обязательно прикрепите скриншот доказательств с /time прямо к сообщению с текстом.</i>"
    )
    msg = bot.send_message(message.chat.id, text, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_transfer_submission)

def process_transfer_submission(message):
    if message.text in MENU_BUTTONS or (message.caption and message.caption in MENU_BUTTONS):
        bot.send_message(message.chat.id, "❌ Подача заявки на перенос отменена.")
        return

    user_id = message.chat.id
    nickname = get_nickname(user_id) or "Без никнейма"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"

    # Получаем текст заявки и фото (если есть)
    text_data = message.caption if message.caption else message.text
    photo_file_id = message.photo[-1].file_id if message.photo else None

    if not text_data and not photo_file_id:
        msg = bot.send_message(
            message.chat.id,
            "❌ <b>Пожалуйста, отправьте заполненое заявление по форме (текст и скриншот с /time):</b>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_transfer_submission)
        return

    if not text_data:
        text_data = "[Без текстового описания]"

    req_id = save_transfer_request(user_id, nickname, username, text_data, photo_file_id)

    # Клавиатура для админов
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"tr_app_{req_id}_{user_id}"),
        types.InlineKeyboardButton("❌ Отказать", callback_data=f"tr_rej_{req_id}_{user_id}")
    )

    admin_alert = (
        f"📦 <b>Заявка на перенос аккаунта №{req_id}!</b>\n\n"
        f"👤 <b>От:</b> {username} (ID: <code>{user_id}</code>)\n"
        f"🎮 <b>NickName в боте:</b> <code>{nickname}</code>\n\n"
        f"📝 <b>Заявление:</b>\n{text_data}"
    )

    # Рассылаем заявку администраторам
    for admin_id in ADMIN_IDS:
        try:
            if photo_file_id:
                bot.send_photo(admin_id, photo_file_id, caption=admin_alert, reply_markup=markup, parse_mode="HTML")
            else:
                bot.send_message(admin_id, admin_alert, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    bot.send_message(
        user_id,
        f"✅ <b>Ваша заявка на перенос аккаунта №{req_id} успешно отправлена!</b>\n\n"
        "Ожидайте проверки заявки администрацией.",
        parse_mode="HTML"
    )

# -- Обработка кнопок Одобрить/Отказать для переноса --
@bot.callback_query_handler(func=lambda call: call.data.startswith("tr_app_"))
def handle_transfer_approve(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return

    parts = call.data.split("_")
    req_id = int(parts[2])
    target_user_id = int(parts[3])

    set_transfer_status(req_id, "approved")

    # Уведомляем игрока
    try:
        bot.send_message(
            target_user_id,
            f"🎉 <b>Ваша заявка на перенос аккаунта №{req_id} ОДОБРЕНА!</b>\n\n"
            "Администрация проекта одобрила ваш перенос. Ожидайте связей для завершения переноса!",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Обновляем сообщение администратору
    status_text = f"\n\n🟢 <b>СТАТУС: ОДОБРЕНО</b>"
    try:
        if call.message.photo:
            bot.edit_message_caption(call.message.caption + status_text, call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="HTML")
        else:
            bot.edit_message_text(call.message.text + status_text, call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="HTML")
    except Exception:
        pass

    bot.answer_callback_query(call.id, "✅ Заявка одобрена!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tr_rej_"))
def handle_transfer_reject(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return

    parts = call.data.split("_")
    req_id = int(parts[2])
    target_user_id = int(parts[3])

    msg = bot.send_message(
        call.message.chat.id,
        f"✍️ <b>Введите причину отказа для заявки на перенос №{req_id}:</b>\n<i>(Ило отправьте «-» чтобы отказать без указания причины)</i>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_transfer_reject_reason, req_id, target_user_id, call.message.message_id)
    bot.answer_callback_query(call.id)

def process_transfer_reject_reason(message, req_id, target_user_id, admin_msg_id):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Отмена отказа заявки.")
        return

    reason = message.text.strip()
    set_transfer_status(req_id, "rejected")

    reject_text = f"❌ <b>Ваша заявка на перенос аккаунта №{req_id} ОТКЛОНЕНА.</b>"
    if reason and reason != "-":
        reject_text += f"\n\n📌 <b>Причина отказа:</b> {reason}"

    try:
        bot.send_message(target_user_id, reject_text, parse_mode="HTML")
    except Exception:
        pass

    bot.send_message(message.chat.id, f"❌ Заявка на перенос №{req_id} отклонена.", parse_mode="HTML")

# ====== НОВОСТИ СЕРВЕРА ======
def _news_list_markup(user_id):
    """Формирует inline-клавиатуру со списком новостей."""
    all_news = news_get_all()
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not all_news:
        return markup, False
    for nid, title, date in all_news:
        markup.add(types.InlineKeyboardButton(f"📰 {title}  [{date}]", callback_data=f"nv_{nid}"))
    if is_admin_l3(user_id):
        markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="n_add"))
    return markup, True

@bot.message_handler(func=lambda message: message.text == "📰 Новости сервера")
def handle_news_button(message):
    markup, has_news = _news_list_markup(message.chat.id)
    if not has_news:
        text = "📭 <b>Новостей пока нет.</b>"
        if is_admin_l3(message.chat.id):
            markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="n_add"))
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "📰 <b>Новости сервера:</b>\nВыберите новость:", reply_markup=markup, parse_mode="HTML")

# -- просмотр новости --
@bot.callback_query_handler(func=lambda call: call.data.startswith("nv_"))
def handle_news_view(call):
    news_id = int(call.data[3:])
    row = news_get_by_id(news_id)
    if not row:
        bot.answer_callback_query(call.id, "Новость не найдена.")
        return
    nid, title, content, author, date = row
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_admin_l3(call.message.chat.id):
        markup.add(
            types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"ne_{nid}"),
            types.InlineKeyboardButton("🗑 Удалить", callback_data=f"nd_{nid}")
        )
    markup.add(types.InlineKeyboardButton("« Назад к списку", callback_data="n_list"))
    text = (
        f"📰 <b>{title}</b>\n\n"
        f"{content}\n\n"
        f"<i>🕐 {date}</i>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- вернуться к списку --
@bot.callback_query_handler(func=lambda call: call.data == "n_list")
def handle_news_list_back(call):
    markup, has_news = _news_list_markup(call.message.chat.id)
    if not has_news:
        text = "📭 <b>Новостей пока нет.</b>"
        if is_admin_l3(call.message.chat.id):
            markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="n_add"))
    else:
        text = "📰 <b>Новости сервера:</b>\nВыберите новость:"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- добавить новость (шаг 1: заголовок) --
@bot.callback_query_handler(func=lambda call: call.data == "n_add")
def handle_news_add(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    msg = bot.send_message(call.message.chat.id,
                           "📰 <b>Добавление новости</b>\n\n✍️ Введите <b>заголовок</b> новости:",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _news_add_step2)
    bot.answer_callback_query(call.id)

def _news_add_step2(message):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    title = message.text.strip()
    if not title:
        msg = bot.send_message(message.chat.id, "❌ Заголовок не может быть пустым. Введите ещё раз:")
        bot.register_next_step_handler(msg, _news_add_step2)
        return
    msg = bot.send_message(message.chat.id,
                           f"✅ Заголовок: <b>{title}</b>\n\n✍️ Теперь введите <b>текст</b> новости:",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _news_add_finish, title)

def _news_add_finish(message, title):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    content = message.text.strip()
    if not content:
        msg = bot.send_message(message.chat.id, "❌ Текст не может быть пустым. Введите ещё раз:")
        bot.register_next_step_handler(msg, _news_add_finish, title)
        return
    nid = news_add(title, content, "Администрация")
    bot.send_message(message.chat.id, f"✅ Новость «<b>{title}</b>» добавлена (№{nid}).", parse_mode="HTML")

# -- редактировать новость (шаг 1: новый заголовок) --
@bot.callback_query_handler(func=lambda call: call.data.startswith("ne_"))
def handle_news_edit(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data[3:])
    row = news_get_by_id(news_id)
    if not row:
        bot.answer_callback_query(call.id, "Новость не найдена.")
        return
    _, title, content, _, _ = row
    msg = bot.send_message(call.message.chat.id,
                           f"✏️ <b>Редактирование новости №{news_id}</b>\n"
                           f"Текущий заголовок: <i>{title}</i>\n\n"
                           "Введите новый заголовок (или «.» чтобы оставить прежний):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _news_edit_step2, news_id, title, content)
    bot.answer_callback_query(call.id)

def _news_edit_step2(message, news_id, old_title, old_content):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    new_title = old_title if message.text.strip() == "." else message.text.strip()
    msg = bot.send_message(message.chat.id,
                           f"Текущий текст:\n<i>{old_content}</i>\n\n"
                           "Введите новый текст (или «.» чтобы оставить прежний):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _news_edit_finish, news_id, new_title)

def _news_edit_finish(message, news_id, new_title):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    row = news_get_by_id(news_id)
    old_content = row[2] if row else ""
    new_content = old_content if message.text.strip() == "." else message.text.strip()
    news_edit(news_id, new_title, new_content)
    bot.send_message(message.chat.id, f"✅ Новость №{news_id} обновлена.", parse_mode="HTML")

# -- удалить новость (подтверждение) --
@bot.callback_query_handler(func=lambda call: call.data.startswith("nd_"))
def handle_news_delete_confirm(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data[3:])
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"ndc_{news_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"nv_{news_id}")
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Подтвердите удаление")

@bot.callback_query_handler(func=lambda call: call.data.startswith("ndc_"))
def handle_news_delete_do(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data[4:])
    news_delete(news_id)
    markup, has_news = _news_list_markup(call.message.chat.id)
    text = "📰 <b>Новости сервера:</b>\nВыберите новость:" if has_news else "📭 <b>Новостей пока нет.</b>"
    if not has_news and is_admin_l3(call.message.chat.id):
        markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="n_add"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Новость удалена")

# ====== ИНФОРМАЦИЯ О СЕРВЕРЕ ======
def _info_list_markup(user_id):
    all_info = info_get_all()
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not all_info:
        if is_admin_l3(user_id):
            markup.add(types.InlineKeyboardButton("➕ Добавить запись", callback_data="i_add"))
        return markup, False
    for iid, title, date in all_info:
        markup.add(types.InlineKeyboardButton(f"ℹ️ {title}  [{date}]", callback_data=f"iv_{iid}"))
    if is_admin_l3(user_id):
        markup.add(types.InlineKeyboardButton("➕ Добавить запись", callback_data="i_add"))
    return markup, True

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def handle_info_button(message):
    markup, has_info = _info_list_markup(message.chat.id)
    if not has_info:
        text = "📭 <b>Информация пока не добавлена.</b>"
    else:
        text = "ℹ️ <b>Информация о сервере:</b>\nВыберите раздел:"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

# -- просмотр записи --
@bot.callback_query_handler(func=lambda call: call.data.startswith("iv_"))
def handle_info_view(call):
    info_id = int(call.data[3:])
    row = info_get_by_id(info_id)
    if not row:
        bot.answer_callback_query(call.id, "Запись не найдена.")
        return
    iid, title, content, author, date = row
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_admin_l3(call.message.chat.id):
        markup.add(
            types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"ie_{iid}"),
            types.InlineKeyboardButton("🗑 Удалить", callback_data=f"id_{iid}")
        )
    markup.add(types.InlineKeyboardButton("« Назад к списку", callback_data="i_list"))
    text = f"ℹ️ <b>{title}</b>\n\n{content}\n\n<i>🕐 {date}</i>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- назад к списку --
@bot.callback_query_handler(func=lambda call: call.data == "i_list")
def handle_info_list_back(call):
    markup, has_info = _info_list_markup(call.message.chat.id)
    text = "ℹ️ <b>Информация о сервере:</b>\nВыберите раздел:" if has_info else "📭 <b>Информация пока не добавлена.</b>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# -- добавить запись --
@bot.callback_query_handler(func=lambda call: call.data == "i_add")
def handle_info_add(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    msg = bot.send_message(call.message.chat.id,
                           "ℹ️ <b>Добавление записи</b>\n\n✍️ Введите <b>заголовок</b> раздела:",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _info_add_step2)
    bot.answer_callback_query(call.id)

def _info_add_step2(message):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    title = message.text.strip()
    if not title:
        msg = bot.send_message(message.chat.id, "❌ Заголовок не может быть пустым. Введите ещё раз:")
        bot.register_next_step_handler(msg, _info_add_step2)
        return
    msg = bot.send_message(message.chat.id,
                           f"✅ Заголовок: <b>{title}</b>\n\n✍️ Введите <b>текст</b> раздела:",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _info_add_finish, title)

def _info_add_finish(message, title):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Добавление отменено.")
        return
    content = message.text.strip()
    if not content:
        msg = bot.send_message(message.chat.id, "❌ Текст не может быть пустым. Введите ещё раз:")
        bot.register_next_step_handler(msg, _info_add_finish, title)
        return
    iid = info_add(title, content, "Администрация")
    bot.send_message(message.chat.id, f"✅ Запись «<b>{title}</b>» добавлена (№{iid}).", parse_mode="HTML")

# -- редактировать запись --
@bot.callback_query_handler(func=lambda call: call.data.startswith("ie_"))
def handle_info_edit(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    info_id = int(call.data[3:])
    row = info_get_by_id(info_id)
    if not row:
        bot.answer_callback_query(call.id, "Запись не найдена.")
        return
    _, title, content, _, _ = row
    msg = bot.send_message(call.message.chat.id,
                           f"✏️ <b>Редактирование №{info_id}</b>\n"
                           f"Текущий заголовок: <i>{title}</i>\n\n"
                           "Введите новый заголовок (или «.» чтобы оставить прежний):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _info_edit_step2, info_id, title, content)
    bot.answer_callback_query(call.id)

def _info_edit_step2(message, info_id, old_title, old_content):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    new_title = old_title if message.text.strip() == "." else message.text.strip()
    msg = bot.send_message(message.chat.id,
                           f"Текущий текст:\n<i>{old_content}</i>\n\n"
                           "Введите новый текст (или «.» чтобы оставить прежний):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, _info_edit_finish, info_id, new_title)

def _info_edit_finish(message, info_id, new_title):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Редактирование отменено.")
        return
    row = info_get_by_id(info_id)
    old_content = row[2] if row else ""
    new_content = old_content if message.text.strip() == "." else message.text.strip()
    info_edit(info_id, new_title, new_content)
    bot.send_message(message.chat.id, f"✅ Запись №{info_id} обновлена.", parse_mode="HTML")

# -- удалить запись (подтверждение) --
@bot.callback_query_handler(func=lambda call: call.data.startswith("id_"))
def handle_info_delete_confirm(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    info_id = int(call.data[3:])
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"idc_{info_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"iv_{info_id}")
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Подтвердите удаление")

@bot.callback_query_handler(func=lambda call: call.data.startswith("idc_"))
def handle_info_delete_do(call):
    if not is_admin_l3(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    info_id = int(call.data[4:])
    info_delete(info_id)
    markup, has_info = _info_list_markup(call.message.chat.id)
    text = "ℹ️ <b>Информация о сервере:</b>\nВыберите раздел:" if has_info else "📭 <b>Информация пока не добавлена.</b>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Запись удалена")

# ====== НЕПРОЧИТАННЫЕ ОБРАЩЕНИЯ (только для админов) ======
@bot.message_handler(func=lambda message: message.text == "📬 Непрочитанные")
def handle_unread_button(message):
    if message.chat.id not in ADMIN_IDS:
        return
    requests = get_unread_requests()
    if not requests:
        bot.send_message(message.chat.id, "✅ <b>Непрочитанных обращений нет.</b>", parse_mode="HTML")
        return

    bot.send_message(
        message.chat.id,
        f"📬 <b>Непрочитанные обращения:</b> <code>{len(requests)}</code>",
        parse_mode="HTML"
    )

    for i, req in enumerate(requests, start=1):
        req_id, user_id, nickname, username, question, date = req
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("💬 Ответить", callback_data=f"ans_{req_id}_{user_id}"),
            types.InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{req_id}")
        )
        text = (
            f"🔔 <b>Обращение {i} из {len(requests)} (№{req_id})</b>\n\n"
            f"👤 <b>От:</b> {username}\n"
            f"🎮 <b>Ник:</b> <code>{nickname}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"🕐 <b>Дата:</b> {date}\n\n"
            f"📝 <b>Вопрос:</b>\n{question}"
        )
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def handle_ans_callback(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    parts = call.data.split("_")
    req_id = int(parts[1])
    target_user_id = int(parts[2])
    msg = bot.send_message(
        call.message.chat.id,
        f"✍️ <b>Введите ответ для обращения №{req_id}:</b>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_admin_answer_req, target_user_id, req_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("close_"))
def handle_close_callback(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    req_id = int(call.data.split("_")[1])
    mark_request_answered(req_id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, f"✅ Обращение №{req_id} закрыто.")

def process_admin_answer_req(message, target_user_id, req_id):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Отправка ответа отменена.")
        return
    try:
        # Получаем данные обращения для лога
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, question, date FROM support_requests WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        conn.close()
        player_nick = row[0] if row else "Неизвестно"
        question_text = row[1] if row else "—"
        req_date = row[2] if row else "—"
        bot.send_message(
            target_user_id,
            f"✉️ <b>Получен ответ от администрации на ваше обращение №{req_id}:</b>\n\n"
            f"💬 {message.text}",
            parse_mode="HTML"
        )
        log_support_answer(req_id, player_nick, question_text, "Администрация", message.text, req_date)
        mark_request_answered(req_id)
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        confirm = bot.send_message(
            message.chat.id,
            f"✅ Ответ на обращение №{req_id} доставлен пользователю.",
            parse_mode="HTML"
        )
        def _delete_confirm(chat_id, msg_id):
            time.sleep(3)
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
        threading.Thread(target=_delete_confirm, args=(message.chat.id, confirm.message_id), daemon=True).start()
    except Exception:
        bot.send_message(message.chat.id, "❌ Не удалось доставить ответ. Возможно, пользователь заблокировал бота.")

# ====== ТЕХ ПОДДЕРЖКА ======
def send_admin_support_panel(chat_id):
    """Показывает список необработанных обращений и просит ввести номер + ответ."""
    requests = get_unread_requests()
    if not requests:
        bot.send_message(chat_id, "✅ <b>Непрочитанных обращений нет.</b>", parse_mode="HTML")
        return

    lines = [f"📬 <b>Непрочитанные обращения ({len(requests)}):</b>\n"]
    for i, req in enumerate(requests, start=1):
        req_id, user_id, nickname, username, question, date = req
        preview = question if len(question) <= 60 else question[:60] + "…"
        lines.append(
            f"<b>{i}.</b> №{req_id} | 🎮 <code>{nickname}</code> | {date}\n"
            f"    ❓ {preview}"
        )

    lines.append(
        "\n✍️ Введите <b>номер обращения</b> и <b>ответ</b> через пробел:\n"
        "<i>Пример:</i> <code>3 Ваш вопрос решён, обратитесь к администратору</code>"
    )

    msg = bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_admin_reply_input)

def process_admin_reply_input(message):
    if message.chat.id not in ADMIN_IDS:
        return
    # Отмена если нажали кнопку меню
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Ввод ответа отменён.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        msg = bot.send_message(
            message.chat.id,
            "❌ Неверный формат. Укажите номер обращения и ответ через пробел.\n"
            "<i>Пример:</i> <code>3 Ваш вопрос решён</code>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_admin_reply_input)
        return

    req_id = int(parts[0])
    answer_text = parts[1]

    # Ищем обращение в БД
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, nickname, status, question, date FROM support_requests WHERE id = ?",
        (req_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        msg = bot.send_message(
            message.chat.id,
            f"❌ Обращение №{req_id} не найдено. Попробуйте ещё раз:",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_admin_reply_input)
        return

    target_user_id, nickname, status, question_text, req_date = row

    if status == "answered":
        msg = bot.send_message(
            message.chat.id,
            f"⚠️ Обращение №{req_id} уже было закрыто. Введите другой номер или отправьте сообщение из меню:",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_admin_reply_input)
        return

    try:
        bot.send_message(
            target_user_id,
            f"✉️ <b>Получен ответ от администрации на ваше обращение №{req_id}:</b>\n\n"
            f"💬 {answer_text}",
            parse_mode="HTML"
        )
        log_support_answer(req_id, nickname, question_text, "Администрация", answer_text, req_date)
        mark_request_answered(req_id)
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        confirm = bot.send_message(
            message.chat.id,
            f"✅ Ответ на обращение №{req_id} доставлен пользователю <code>{nickname}</code>.",
            parse_mode="HTML"
        )
        def _delete_confirm(chat_id, msg_id):
            time.sleep(3)
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
        threading.Thread(target=_delete_confirm, args=(message.chat.id, confirm.message_id), daemon=True).start()
    except Exception:
        bot.send_message(
            message.chat.id,
            f"❌ Не удалось доставить ответ. Возможно, пользователь заблокировал бота.\n"
            f"Обращение №{req_id} помечено как закрытое.",
            parse_mode="HTML"
        )
        mark_request_answered(req_id)

@bot.message_handler(func=lambda message: message.text == "🎫 Тех поддержка")
def handle_support_button(message):
    if message.chat.id in ADMIN_IDS:
        send_admin_support_panel(message.chat.id)
    else:
        msg = bot.send_message(
            message.chat.id,
            "✍️ <b>Опишите вашу проблему или задайте вопрос:</b>\n\n<i>Администрация ответит вам прямо в этот чат.</i>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_support_question)

def process_support_question(message):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Обращение отменено.")
        return

    user_id = message.chat.id
    nickname = get_nickname(user_id) or "Без никнейма"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"

    req_id = save_support_request(user_id, nickname, username, message.text)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 Ответить", callback_data=f"ans_{req_id}_{user_id}"))

    admin_alert = (
        f"🔔 <b>Новое обращение №{req_id}!</b>\n\n"
        f"👤 <b>Отправитель:</b> {username} (ID: <code>{user_id}</code>)\n"
        f"🎮 <b>NickName:</b> <code>{nickname}</code>\n"
        f"📝 <b>Вопрос:</b>\n{message.text}"
    )

    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_alert, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    bot.send_message(user_id, "✅ <b>Ваш вопрос успешно отправлен администрации!</b> Ожидайте ответа.", parse_mode="HTML")

# ====== РАССЫЛКА ======
@bot.message_handler(func=lambda message: message.text == "📢 Рассылка")
def handle_broadcast_button(message):
    if message.chat.id not in ADMIN_IDS:
        return
    msg = bot.send_message(
        message.chat.id,
        "✍️ <b>Введите текст для рассылки всем пользователям:</b>\n\n<i>Вы можете использовать HTML разметку.</i>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_broadcast_text)

def process_broadcast_text(message):
    if message.text in MENU_BUTTONS:
        bot.send_message(message.chat.id, "❌ Рассылка отменена.")
        return

    broadcast_text = message.text
    user_ids = get_all_users()

    if not user_ids:
        bot.send_message(message.chat.id, "❌ В базе данных пока нет пользователей.")
        return

    status_msg = bot.send_message(message.chat.id, "🚀 <b>Рассылка запущена...</b>", parse_mode="HTML")

    success_count = 0
    blocked_count = 0

    for u_id in user_ids:
        try:
            bot.send_message(u_id, broadcast_text, parse_mode="HTML")
            success_count += 1
            time.sleep(0.05)
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403:
                blocked_count += 1
        except Exception:
            pass

    report_text = (
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Доставлено: <code>{success_count}</code>\n"
        f"🚫 Заблокировали бота: <code>{blocked_count}</code>\n"
        f"📊 Всего в базе: <code>{len(user_ids)}</code>"
    )
    bot.delete_message(message.chat.id, status_msg.message_id)
    bot.send_message(message.chat.id, report_text, parse_mode="HTML")

def start_polling():
    """Запускает один поток polling. non_stop=False — чтобы исключения выходили наружу."""
    def _poll():
        while True:
            try:
                bot.polling(skip_pending=True, timeout=30, long_polling_timeout=30, non_stop=False)
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 409:
                    print("⚠️ 409 Conflict — другой процесс ещё жив, жду 30 сек...")
                    time.sleep(30)
                else:
                    print(f"❌ Telegram API ошибка: {e} — перезапуск через 5 сек...")
                    time.sleep(5)
            except Exception as e:
                print(f"❌ Ошибка polling: {e} — перезапуск через 5 сек...")
                time.sleep(5)

    t = threading.Thread(target=_poll, daemon=True, name="polling")
    t.start()
    return t

if __name__ == "__main__":
    init_db()
    keep_alive()
    print(f"База данных: {os.path.abspath(DB_PATH)}")
    print("Запуск бота...")

    # Сбрасываем вебхук и даём Telegram время закрыть старые соединения
    for attempt in range(5):
        try:
            bot.remove_webhook()
            print(f"Вебхук сброшен (попытка {attempt + 1})")
            break
        except Exception as e:
            print(f"Ошибка сброса вебхука ({attempt + 1}/5): {e}")
            time.sleep(3)

    # Пауза, чтобы старый процесс успел завершить свои long-poll запросы
    time.sleep(5)

    print("Бот успешно запущен и готов к работе!")
    poll_thread = start_polling()

    # Watchdog — перезапускает polling только если поток реально упал.
    while True:
        time.sleep(60)
        if not poll_thread.is_alive():
            print("⚠️ Watchdog: поток упал — перезапускаю polling...")
            try:
                bot.stop_polling()
            except Exception:
                pass
            poll_thread.join(timeout=15)
            time.sleep(5)
            poll_thread = start_polling()

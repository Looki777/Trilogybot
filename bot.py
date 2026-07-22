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

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {}  # user_id -> уровень (1, 2, 3)
# ==================================================

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан. Добавьте его в переменные окружения.")

telebot.apihelper.ENABLE_MIDDLEWARE = True
bot = telebot.TeleBot(TOKEN, threaded=True)

_last_heartbeat = time.time()
_prev_players = None  # для отслеживания рестарта сервера

# Хранение ID сообщений-уведомлений о обращениях: {req_id: [(admin_id, msg_id), ...]}
_admin_alert_msgs = {}

@bot.middleware_handler(update_types=["message", "callback_query"])
def update_heartbeat(bot_instance, update):
    global _last_heartbeat
    _last_heartbeat = time.time()

# ====== УРОВНИ АДМИНИСТРАЦИИ ======
# 1 = Младший Модератор (только Помощь, читать обращения)
# 2 = Модератор бота (отвечать на обращения, статистика)
# 3 = Главный Модератор (всё: рассылка, управление адм, должности)

LEVEL_NAMES = {1: "Младший Модератор", 2: "Модератор бота", 3: "Главный Модератор"}

def get_admin_level(user_id):
    return ADMIN_LEVELS.get(user_id, 0)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def can_answer_support(user_id):
    return get_admin_level(user_id) >= 2

def can_broadcast(user_id):
    return get_admin_level(user_id) >= 3

def can_manage_admins(user_id):
    return get_admin_level(user_id) >= 3

# ====== РАБОТА С БАЗОЙ ДАННЫХ ======
def init_db():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
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
            peak_date TEXT DEFAULT '',
            peak_day TEXT DEFAULT '',
            last_restart TEXT DEFAULT ''
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
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            admin_level INTEGER DEFAULT 3
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO server_stats (id, peak_online, peak_date) VALUES (1, 0, '')")

    # Миграции для существующих БД
    for col, definition in [
        ("peak_day", "TEXT DEFAULT ''"),
        ("last_restart", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE server_stats ADD COLUMN {col} {definition}")
        except Exception:
            pass
    try:
        cursor.execute("ALTER TABLE admins ADD COLUMN admin_level INTEGER DEFAULT 3")
    except Exception:
        pass
    for col in [("nickname", "TEXT"), ("position", "TEXT DEFAULT 'Игрок'")]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except Exception:
            pass

    # Хардкод-админы — уровень 3
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, admin_level) VALUES (?, 3)", (aid,))
    conn.commit()

    # Загружаем всех админов и уровни в память
    cursor.execute("SELECT user_id, admin_level FROM admins")
    for row in cursor.fetchall():
        uid, lvl = row
        ADMIN_IDS.add(uid)
        ADMIN_LEVELS[uid] = lvl if lvl else 3
    conn.close()

def add_admin_db(user_id, level=1):
    ADMIN_IDS.add(user_id)
    ADMIN_LEVELS[user_id] = level
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO admins (user_id, admin_level) VALUES (?, ?)",
        (user_id, level)
    )
    conn.commit()
    conn.close()

def remove_admin_db(user_id):
    ADMIN_IDS.discard(user_id)
    ADMIN_LEVELS.pop(user_id, None)
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_user(user_id, username):
    try:
        conn = sqlite3.connect("bot_stats.db", timeout=5)
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

def get_nickname(user_id):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_nickname(user_id, nickname):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))
    conn.commit()
    conn.close()

def get_position(user_id):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT position FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    level = get_admin_level(user_id)
    return LEVEL_NAMES.get(level, "Игрок") if level else "Игрок"

def set_position(user_id, position):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET position = ? WHERE user_id = ?", (position, user_id))
    conn.commit()
    conn.close()

def get_users_count():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_peak_online():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT peak_online, peak_date, peak_day FROM server_stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return (row[0], row[1], row[2]) if row else (0, "", "")

def update_peak_online(current_players):
    peak, peak_date, peak_day = get_peak_online()
    today = time.strftime("%d.%m.%Y")
    now = time.strftime("%d.%m.%Y %H:%M")
    if peak_day != today:
        conn = sqlite3.connect("bot_stats.db", timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE server_stats SET peak_online = ?, peak_date = ?, peak_day = ? WHERE id = 1",
            (current_players, now, today)
        )
        conn.commit()
        conn.close()
        return current_players, now
    if current_players > peak:
        conn = sqlite3.connect("bot_stats.db", timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE server_stats SET peak_online = ?, peak_date = ?, peak_day = ? WHERE id = 1",
            (current_players, now, today)
        )
        conn.commit()
        conn.close()
        return current_players, now
    return peak, peak_date

def get_last_restart():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT last_restart FROM server_stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""

def update_last_restart(restart_time):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_stats SET last_restart = ? WHERE id = 1", (restart_time,))
    conn.commit()
    conn.close()

def save_support_request(user_id, nickname, username, question):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
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
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, nickname, username, question, date FROM support_requests WHERE status = 'unread' ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_unread_count():
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def mark_request_answered(request_id):
    conn = sqlite3.connect("bot_stats.db", timeout=5)
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
    try:
        with open("support_log.txt", "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        print(f"Ошибка записи лога: {e}")

# ====== УДАЛЕНИЕ УВЕДОМЛЕНИЙ У ДРУГИХ АДМИНОВ ======
def delete_other_admin_alerts(req_id, answering_admin_id):
    msgs = _admin_alert_msgs.pop(req_id, [])
    for admin_id, msg_id in msgs:
        if admin_id != answering_admin_id:
            try:
                bot.delete_message(admin_id, msg_id)
            except Exception:
                pass

# ====== ФУНКЦИИ СЕРВЕРА И КЛАВИАТУРЫ ======
def _fetch_samp_info():
    SampClient.timeout = 0.5
    start_time = time.time()
    with SampClient(address=SERVER_IP, port=SERVER_PORT) as client:
        info = client.get_server_info()
        ping = int((time.time() - start_time) * 1000)
        return info, ping

def check_samp_server():
    global _prev_players
    result = {}

    def _run():
        try:
            info, ping = _fetch_samp_info()
            result["data"] = (info, ping)
        except Exception as e:
            result["error"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=3)

    if t.is_alive() or "data" not in result:
        return "❌ <b>Сервер недоступен.</b>"

    info, ping = result["data"]

    # Определяем рестарт: сервер вернулся после нуля игроков
    if _prev_players is not None and _prev_players == 0 and info.players > 0:
        update_last_restart(time.strftime("%d.%m.%Y %H:%M"))
    _prev_players = info.players

    peak, peak_date = update_peak_online(info.players)
    last_restart = get_last_restart()

    peak_time = peak_date[11:] if len(peak_date) > 11 else peak_date
    restart_line = f"🔄 <b>Последний рестарт:</b> {last_restart}\n" if last_restart else ""

    return (
        f"🎮 <b>{info.hostname}</b>\n\n"
        f"🌐 <b>IP:</b> <code>{SERVER_IP}:{SERVER_PORT}</code>\n"
        f"👥 <b>Онлайн:</b> {info.players} / {info.max_players}\n"
        f"🏆 <b>Пик за сегодня:</b> {peak} <i>(в {peak_time})</i>\n"
        f"⚡ <b>Пинг:</b> {ping} мс\n"
        f"{restart_line}\n"
        f"🟢 Статус: Работает"
    )

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    level = get_admin_level(user_id)

    if level == 0:
        markup.row(types.KeyboardButton("🌐 Онлайн"), types.KeyboardButton("🔗 Полезные ссылки"))
        markup.row(types.KeyboardButton("🎫 Тех поддержка"))
    elif level == 1:
        markup.row(types.KeyboardButton("🌐 Онлайн"), types.KeyboardButton("🔗 Полезные ссылки"))
        markup.row(types.KeyboardButton("🎫 Тех поддержка"), types.KeyboardButton("📋 Помощь"))
    elif level == 2:
        markup.row(types.KeyboardButton("🌐 Онлайн"), types.KeyboardButton("🔗 Полезные ссылки"))
        markup.row(types.KeyboardButton("🎫 Тех поддержка"), types.KeyboardButton("📬 Непрочитанные"))
        markup.row(types.KeyboardButton("📊 Статистика"), types.KeyboardButton("📋 Помощь"))
    else:  # level 3
        markup.row(types.KeyboardButton("🌐 Онлайн"), types.KeyboardButton("🔗 Полезные ссылки"))
        markup.row(types.KeyboardButton("🎫 Тех поддержка"), types.KeyboardButton("📬 Непрочитанные"))
        markup.row(types.KeyboardButton("📊 Статистика"), types.KeyboardButton("📢 Рассылка"))
        markup.row(types.KeyboardButton("📋 Помощь"))

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
    if nick in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка", "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь", "/start"]:
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
    if nick in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка", "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь", "/start", "/ник", "/стата"]:
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
    position = get_position(user_id)
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
        f"🏅 <b>Должность:</b> <code>{position}</code>"
    )
    bot.send_message(user_id, stata_text, parse_mode="HTML")

# ====== КОМАНДА /должность (только уровень 3) ======
@bot.message_handler(commands=['должность'])
def handle_set_position(message):
    if not can_manage_admins(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        target_id = int(parts[1])
        new_position = parts[2]
        set_position(target_id, new_position)
        bot.reply_to(message, f"✅ Должность пользователя <code>{target_id}</code> изменена на <code>{new_position}</code>.", parse_mode="HTML")
    except Exception:
        bot.reply_to(message, "❌ Формат: /должность ID Должность\nПример: /должность 123456789 Модератор")

# ====== КОМАНДА /админ и /разадмин (только уровень 3) ======
@bot.message_handler(commands=['админ'])
def handle_add_admin(message):
    if not can_manage_admins(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        target_id = int(parts[1])
        level = int(parts[2]) if len(parts) > 2 else 1
        if level not in (1, 2, 3):
            bot.reply_to(message, "❌ Уровень должен быть 1, 2 или 3.\n\n1 — Младший Модератор\n2 — Модератор бота\n3 — Главный Модератор")
            return
        level_name = LEVEL_NAMES[level]
        already_admin = target_id in ADMIN_IDS
        add_admin_db(target_id, level)
        set_position(target_id, level_name)
        if already_admin:
            bot.reply_to(message, f"✅ Уровень пользователя <code>{target_id}</code> обновлён на <b>{level_name}</b>.", parse_mode="HTML")
        else:
            bot.reply_to(message, f"✅ Пользователь <code>{target_id}</code> назначен <b>{level_name}</b>.", parse_mode="HTML")
            try:
                bot.send_message(target_id, f"🎉 Вам выданы права <b>{level_name}</b> бота!", parse_mode="HTML")
            except Exception:
                pass
    except (IndexError, ValueError):
        bot.reply_to(
            message,
            "❌ Формат: /админ ID уровень\nПример: /админ 123456789 2\n\n"
            "Уровни:\n"
            "1 — Младший Модератор\n"
            "2 — Модератор бота\n"
            "3 — Главный Модератор"
        )

@bot.message_handler(commands=['разадмин'])
def handle_remove_admin(message):
    if not can_manage_admins(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=1)
        target_id = int(parts[1])
        if target_id not in ADMIN_IDS:
            bot.reply_to(message, f"⚠️ Пользователь <code>{target_id}</code> не является администратором.", parse_mode="HTML")
            return
        remove_admin_db(target_id)
        set_position(target_id, "Игрок")
        bot.reply_to(message, f"✅ Права администратора у пользователя <code>{target_id}</code> сняты.", parse_mode="HTML")
        try:
            bot.send_message(target_id, "ℹ️ Ваши права администратора бота были сняты.", parse_mode="HTML")
        except Exception:
            pass
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Формат: /разадмин ID\nПример: /разадмин 123456789")

# ====== КОМАНДА /admlist (для всей администрации) ======
@bot.message_handler(commands=['admlist'])
def handle_admlist(message):
    if not is_admin(message.from_user.id):
        return
    conn = sqlite3.connect("bot_stats.db", timeout=5)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.user_id, a.admin_level, u.nickname, u.username
        FROM admins a
        LEFT JOIN users u ON a.user_id = u.user_id
        ORDER BY a.admin_level DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, "📭 Список администрации пуст.")
        return

    lines = ["👥 <b>Список администрации бота:</b>\n"]
    for user_id, level, nickname, username in rows:
        level_name = LEVEL_NAMES.get(level, f"Уровень {level}")
        nick = nickname or "—"
        uname = f"@{username}" if username else "—"
        lines.append(
            f"🔹 <b>{level_name}</b>\n"
            f"   🎮 Ник: <code>{nick}</code>\n"
            f"   👤 TG: {uname}\n"
            f"   🆔 ID: <code>{user_id}</code>\n"
        )
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")

# ====== КОМАНДА /лог (уровень 2+) ======
@bot.message_handler(commands=['лог'])
def handle_log_command(message):
    if not can_answer_support(message.from_user.id):
        return
    if not os.path.exists("support_log.txt"):
        bot.reply_to(message, "📭 Лог пуст — ни одного ответа на обращение ещё не было.")
        return
    if os.path.getsize("support_log.txt") == 0:
        bot.reply_to(message, "📭 Лог пуст — ни одного ответа на обращение ещё не было.")
        return
    with open("support_log.txt", "rb") as f:
        bot.send_document(
            message.chat.id,
            f,
            caption="📋 <b>Лог обращений тех. поддержки</b>",
            parse_mode="HTML"
        )

# ====== ОБРАБОТЧИКИ КНОПОК ======
@bot.message_handler(func=lambda message: message.text == "🌐 Онлайн")
def handle_online_button(message):
    bot.send_message(message.chat.id, "⏳ Опрашиваю сервер...")
    bot.send_message(message.chat.id, check_samp_server(), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🔗 Полезные ссылки")
def handle_links_button(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Telegram Канал", url="https://t.me/santropetrilogy_rp"),
        types.InlineKeyboardButton("💬 Telegram Чат", url="https://t.me/santropetrilogy_chat"),
        types.InlineKeyboardButton("📱 Группа ВКонтакте", url="https://vk.ru/santropetrilogy"),
        types.InlineKeyboardButton("🌐 Форум", url="http://wh32893.web3.maze-tech.ru/index.php"),
    )
    bot.send_message(message.chat.id, "🔗 <b>Официальные ресурсы проекта:</b>", reply_markup=markup, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def handle_stats_button(message):
    if not can_answer_support(message.chat.id):
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
    level = get_admin_level(message.chat.id)
    if level == 0:
        return

    if level == 1:
        help_text = (
            "📋 <b>Команды Младшего Модератора:</b>\n\n"
            "🎮 <b>Профиль</b>\n"
            "/стата — посмотреть свой профиль\n"
            "/ник — сменить свой никнейм\n\n"
            "🔘 <b>Кнопки меню</b>\n"
            "🌐 Онлайн — статус SA:MP сервера\n"
            "🔗 Полезные ссылки — официальные ресурсы проекта\n"
            "🎫 Тех поддержка — просмотр обращений"
        )
    elif level == 2:
        help_text = (
            "📋 <b>Команды Модератора бота:</b>\n\n"
            "🎮 <b>Профиль</b>\n"
            "/стата — посмотреть свой профиль\n"
            "/ник — сменить свой никнейм\n"
            "/лог — скачать историю ответов тех. поддержки\n\n"
            "🔘 <b>Кнопки меню</b>\n"
            "🌐 Онлайн — статус SA:MP сервера\n"
            "🔗 Полезные ссылки — официальные ресурсы проекта\n"
            "🎫 Тех поддержка — ответить на обращения игроков\n"
            "📬 Непрочитанные — необработанные обращения\n"
            "📊 Статистика — кол-во пользователей и обращений"
        )
    else:  # level 3
        help_text = (
            "📋 <b>Команды Главного Модератора:</b>\n\n"
            "👤 <b>Управление администрацией</b>\n"
            "/админ <code>ID уровень</code> — выдать права (1/2/3)\n"
            "/разадмин <code>ID</code> — снять права администратора\n"
            "/должность <code>ID Должность</code> — изменить должность\n"
            "/admlist — список всей администрации бота\n\n"
            "🎮 <b>Профиль</b>\n"
            "/стата — посмотреть свой профиль\n"
            "/ник — сменить свой никнейм\n"
            "/лог — скачать историю ответов тех. поддержки\n\n"
            "🔘 <b>Кнопки меню</b>\n"
            "🌐 Онлайн — статус SA:MP сервера\n"
            "🔗 Полезные ссылки — официальные ресурсы проекта\n"
            "🎫 Тех поддержка — ответить на обращения игроков\n"
            "📬 Непрочитанные — необработанные обращения\n"
            "📊 Статистика — кол-во пользователей и обращений\n"
            "📢 Рассылка — отправить сообщение всем пользователям"
        )
    bot.send_message(message.chat.id, help_text, parse_mode="HTML")

# ====== НЕПРОЧИТАННЫЕ ОБРАЩЕНИЯ (уровень 2+) ======
@bot.message_handler(func=lambda message: message.text == "📬 Непрочитанные")
def handle_unread_button(message):
    if not can_answer_support(message.chat.id):
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
    if not can_answer_support(call.message.chat.id):
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
    if not can_answer_support(call.message.chat.id):
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    req_id = int(call.data.split("_")[1])
    mark_request_answered(req_id)
    delete_other_admin_alerts(req_id, call.message.chat.id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, f"✅ Обращение №{req_id} закрыто.")

def process_admin_answer_req(message, target_user_id, req_id):
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка", "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь"]:
        bot.send_message(message.chat.id, "❌ Отправка ответа отменена.")
        return
    try:
        admin_nickname = get_nickname(message.chat.id) or "Администратор"
        conn = sqlite3.connect("bot_stats.db", timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, question, date FROM support_requests WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        conn.close()
        player_nick = row[0] if row else "Неизвестно"
        question_text = row[1] if row else "—"
        req_date = row[2] if row else "—"
        # Отправляем ответ пользователю БЕЗ ника админа
        bot.send_message(
            target_user_id,
            f"✉️ <b>Получен ответ от администрации на ваше обращение №{req_id}:</b>\n\n"
            f"💬 {message.text}",
            parse_mode="HTML"
        )
        # В лог пишем ник администратора
        log_support_answer(req_id, player_nick, question_text, admin_nickname, message.text, req_date)
        mark_request_answered(req_id)
        delete_other_admin_alerts(req_id, message.chat.id)
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
    if not can_answer_support(message.chat.id):
        return
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка",
                        "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь"]:
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

    conn = sqlite3.connect("bot_stats.db", timeout=5)
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
            f"⚠️ Обращение №{req_id} уже было закрыто. Введите другой номер:",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_admin_reply_input)
        return

    try:
        admin_nickname = get_nickname(message.chat.id) or "Администратор"
        # Ответ пользователю — без ника администратора
        bot.send_message(
            target_user_id,
            f"✉️ <b>Получен ответ от администрации на ваше обращение №{req_id}:</b>\n\n"
            f"💬 {answer_text}",
            parse_mode="HTML"
        )
        # В лог — с ником администратора
        log_support_answer(req_id, nickname, question_text, admin_nickname, answer_text, req_date)
        mark_request_answered(req_id)
        delete_other_admin_alerts(req_id, message.chat.id)
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
        delete_other_admin_alerts(req_id, message.chat.id)

@bot.message_handler(func=lambda message: message.text == "🎫 Тех поддержка")
def handle_support_button(message):
    if can_answer_support(message.chat.id):
        send_admin_support_panel(message.chat.id)
    elif is_admin(message.chat.id):
        # Уровень 1 — только просматривает обращения
        requests = get_unread_requests()
        if not requests:
            bot.send_message(message.chat.id, "✅ <b>Непрочитанных обращений нет.</b>", parse_mode="HTML")
            return
        lines = [f"📬 <b>Текущие обращения ({len(requests)}):</b>\n"]
        for i, req in enumerate(requests, start=1):
            req_id, user_id, nickname, username, question, date = req
            preview = question if len(question) <= 60 else question[:60] + "…"
            lines.append(
                f"<b>{i}.</b> №{req_id} | 🎮 <code>{nickname}</code> | {date}\n"
                f"    ❓ {preview}"
            )
        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")
    else:
        msg = bot.send_message(
            message.chat.id,
            "✍️ <b>Опишите вашу проблему или задайте вопрос:</b>\n\n<i>Администрация ответит вам прямо в этот чат.</i>",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_support_question)

def process_support_question(message):
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка", "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь"]:
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

    sent_msgs = []
    for admin_id in ADMIN_IDS:
        try:
            sent = bot.send_message(admin_id, admin_alert, reply_markup=markup, parse_mode="HTML")
            sent_msgs.append((admin_id, sent.message_id))
        except Exception:
            pass
    _admin_alert_msgs[req_id] = sent_msgs

    bot.send_message(user_id, "✅ <b>Ваш вопрос успешно отправлен администрации!</b> Ожидайте ответа.", parse_mode="HTML")

# ====== РАССЫЛКА (только уровень 3) ======
@bot.message_handler(func=lambda message: message.text == "📢 Рассылка")
def handle_broadcast_button(message):
    if not can_broadcast(message.chat.id):
        return
    msg = bot.send_message(
        message.chat.id,
        "✍️ <b>Введите текст для рассылки всем пользователям:</b>\n\n<i>Вы можете использовать HTML разметку.</i>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_broadcast_text)

def process_broadcast_text(message):
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "🎫 Тех поддержка", "📊 Статистика", "📢 Рассылка", "📬 Непрочитанные", "📋 Помощь"]:
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
    print("Запуск бота...")

    for attempt in range(5):
        try:
            bot.remove_webhook()
            print(f"Вебхук сброшен (попытка {attempt + 1})")
            break
        except Exception as e:
            print(f"Ошибка сброса вебхука ({attempt + 1}/5): {e}")
            time.sleep(3)

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

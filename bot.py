import os
import time
import socket
import threading
import sqlite3
import telebot
from telebot import types
from samp_client.client import SampClient
from keep_alive import keep_alive

# Пытаемся взять токен и настройки, но не падаем, если их нет при сборке (build)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "bot_stats.db")
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"

# Хардкод админов
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {} 

socket.setdefaulttimeout(5)

# Инициализируем бота только если есть токен (защита от ошибок билда Railway)
bot = None
if TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=True)
    telebot.apihelper.ENABLE_MIDDLEWARE = True

# ====== БД ======
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, nickname TEXT, position TEXT DEFAULT 'Игрок', join_date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS server_stats (id INTEGER PRIMARY KEY, peak_online INTEGER DEFAULT 0, peak_date TEXT, peak_day TEXT, last_restart TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS support_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, question TEXT, status TEXT DEFAULT 'unread', date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS transfer_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, text_data TEXT, photo_file_id TEXT, status TEXT DEFAULT 'unread', date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1)")
    cursor.execute("CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS info_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS leaders (id INTEGER PRIMARY KEY AUTOINCREMENT, fraction TEXT NOT NULL, nickname TEXT NOT NULL, username TEXT, date TEXT)")
    cursor.execute("INSERT OR IGNORE INTO server_stats (id) VALUES (1)")
    
    # Миграции
    for col in [("nickname", "TEXT"), ("position", "TEXT DEFAULT 'Игрок'")]:
        try: cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except: pass
    try: cursor.execute("ALTER TABLE admins ADD COLUMN level INTEGER DEFAULT 1")
    except: pass
    
    # Синхронизация админов
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
        cursor.execute("UPDATE admins SET level = 3 WHERE user_id = ?", (aid,))
    conn.commit()
    
    cursor.execute("SELECT user_id, level FROM admins")
    for row in cursor.fetchall():
        ADMIN_IDS.add(row[0])
        ADMIN_LEVELS[row[0]] = row[1]
    conn.close()

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======
def is_subscribed(user_id):
    if not bot: return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return True

def get_sub_keyboard():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
    m.add(types.InlineKeyboardButton("🔄 Я подписался", callback_data="check_sub"))
    return m

def format_pos(pos):
    if not pos: return "🎮 <b>Игрок</b>"
    p = pos.lower()
    if "гс гос" in p: return f"🏢 <b>{pos}</b>"
    if "згс гос" in p: return f"🏢⚜️ <b>{pos}</b>"
    if "гс гетто" in p: return f"🩸 <b>{pos}</b>"
    if "згс гетто" in p: return f"🩸⚜️ <b>{pos}</b>"
    if "гс мафий" in p: return f"🕶️ <b>{pos}</b>"
    if "згс мафий" in p: return f"🕶️⚜️ <b>{pos}</b>"
    if "гс" in p: return f"⚡ <b>{pos}</b>"
    if "згс" in p: return f"⚡⚜️ <b>{pos}</b>"
    if "основатель" in p or "создатель" in p: return f"👑 <b>{pos}</b>"
    if "админ" in p: return f"🛠️ <b>{pos}</b>"
    if "лидер" in p: return f"💼 <b>{pos}</b>"
    return f"🎖️ <b>{pos}</b>"

# ====== ОБРАБОТКА КОМАНД (ТОЛЬКО ЕСЛИ bot ИНИЦИАЛИЗИРОВАН) ======
if bot:
    @bot.middleware_handler(update_types=["message", "callback_query"])
    def check_sub_middleware(bot_instance, update):
        user_id = update.from_user.id if hasattr(update, 'from_user') else None
        if user_id and not is_subscribed(user_id):
            if hasattr(update, 'message'):
                bot.send_message(user_id, "❌ Подпишитесь на канал для доступа!", reply_markup=get_sub_keyboard())
            return
            
    @bot.message_handler(commands=['start'])
    def start(message):
        user_id = message.chat.id
        # Регистрация
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, message.from_user.username, time.strftime("%Y-%m-%d")))
        conn.commit(); conn.close()
        
        nick = get_nickname_db(user_id)
        if not nick:
            msg = bot.send_message(user_id, "👋 Привет! Введите ваш никнейм для бота:")
            bot.register_next_step_handler(msg, save_nick)
        else:
            bot.send_message(user_id, f"👋 Привет, {nick}!", reply_markup=main_kb(user_id))

    # Сюда добавьте все остальные обработчики (онлайн, стата, поиск, лидеры и т.д.)
    # из предыдущего длинного кода. Они будут работать внутри этого блока `if bot:`.

def get_nickname_db(uid):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (uid,))
    r = cursor.fetchone(); conn.close()
    return r[0] if r and r[0] else None

def save_nick(message):
    nick = message.text.strip()
    if len(nick) < 3: bot.send_message(message.chat.id, "Слишком короткий ник."); return
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nick, message.chat.id))
    conn.commit(); conn.close()
    bot.send_message(message.chat.id, "✅ Ник сохранен!", reply_markup=main_kb(message.chat.id))

def main_kb(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("🌐 Онлайн", "🔗 Полезные ссылки")
    m.row("📰 Новости сервера", "ℹ️ Информация")
    m.row("💼 Список лидеров", "🔄 Перенос аккаунта")
    m.row("🎫 Тех поддержка")
    if uid in ADMIN_IDS:
        m.row("📬 Непрочитанные", "📊 Статистика")
        m.row("📢 Рассылка", "📋 Помощь")
    return m

# ====== ЗАПУСК ======
if __name__ == "__main__":
    if not TOKEN:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден. Сборка продолжается...")
    else:
        init_db()
        keep_alive()
        print("Бот запускается...")
        while True:
            try: bot.polling(none_stop=True, timeout=60)
            except: time.sleep(5)

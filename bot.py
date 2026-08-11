import os
import time
import socket
import threading
import sqlite3
import telebot
from telebot import types
from samp_client.client import SampClient
from keep_alive import keep_alive

# Константы сервера
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {}

# Глобальный объект бота
bot = None

def get_db_path():
    return os.environ.get("DB_PATH", "bot_stats.db")

def init_db():
    path = get_db_path()
    conn = sqlite3.connect(path, timeout=10)
    cursor = conn.cursor()
    tables = [
        "users (user_id INTEGER PRIMARY KEY, username TEXT, nickname TEXT, position TEXT DEFAULT 'Игрок', join_date TEXT)",
        "server_stats (id INTEGER PRIMARY KEY, peak_online INTEGER DEFAULT 0, peak_date TEXT, peak_day TEXT, last_restart TEXT)",
        "support_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, question TEXT, status TEXT DEFAULT 'unread', date TEXT)",
        "transfer_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, text_data TEXT, photo_file_id TEXT, status TEXT DEFAULT 'unread', date TEXT)",
        "admins (user_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1)",
        "news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)",
        "info_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)",
        "leaders (id INTEGER PRIMARY KEY AUTOINCREMENT, fraction TEXT NOT NULL, nickname TEXT NOT NULL, username TEXT, date TEXT)"
    ]
    for t in tables:
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {t}")
    
    cursor.execute("INSERT OR IGNORE INTO server_stats (id) VALUES (1)")
    
    for col in [("nickname", "TEXT"), ("position", "TEXT DEFAULT 'Игрок'")]:
        try: cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except: pass
        
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
    conn.commit()
    
    cursor.execute("SELECT user_id, level FROM admins")
    for row in cursor.fetchall():
        ADMIN_IDS.add(row[0])
        ADMIN_LEVELS[row[0]] = row[1]
    conn.close()

def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return True

def get_nickname(uid):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone(); conn.close()
    return r[0] if r and r[0] else None

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

def run_bot():
    global bot
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Критическая ошибка: TELEGRAM_BOT_TOKEN не найден в Variables!")
        return

    bot = telebot.TeleBot(token, threaded=True)
    init_db()
    
    @bot.message_handler(commands=['start'])
    def start_cmd(message):
        uid = message.chat.id
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
            bot.send_message(uid, "❌ Подпишитесь на канал для доступа!", reply_markup=markup)
            return
        
        nick = get_nickname(uid)
        if not nick:
            bot.send_message(uid, "👋 Привет! Введите ваш никнейм:")
            bot.register_next_step_handler(message, lambda msg: save_nick(msg))
        else:
            bot.send_message(uid, f"👋 Привет, {nick}!", reply_markup=main_kb(uid))

    def save_nick(message):
        nick = message.text.strip()
        conn = sqlite3.connect(get_db_path()); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date) VALUES (?, ?, ?)", (message.chat.id, nick, time.strftime("%Y-%m-%d")))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ Ник {nick} сохранен!", reply_markup=main_kb(message.chat.id))

    @bot.callback_query_handler(func=lambda call: call.data == "check_sub")
    def check_sub_call(call):
        if is_subscribed(call.from_user.id):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "✅ Подписка подтверждена! Используйте /start")
        else:
            bot.answer_callback_query(call.id, "❌ Вы не подписаны!", show_alert=True)

    @bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        uid = message.chat.id
        text = message.text
        
        if not text:
            return
            
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
            bot.send_message(uid, "❌ Подпишитесь на канал для доступа!", reply_markup=markup)
            return
        
        responses = {
            "🌐 Онлайн": "👥 Онлайн: 0 (заглушка)",
            "🔗 Полезные ссылки": f"🔗 Канал: {CHANNEL_URL}",
            "📰 Новости сервера": "📰 Новостей пока нет",
            "ℹ️ Информация": "ℹ️ Информация о сервере...",
            "💼 Список лидеров": "🏆 Лидеры:\n1. Asta_Shark - 1000 очков",
            "🔄 Перенос аккаунта": "📝 Отправьте ник и пароль для переноса",
            "🎫 Тех поддержка": "✍️ Напишите ваш вопрос в следующем сообщении"
        }
        
        if text in responses:
            bot.send_message(uid, responses[text], reply_markup=main_kb(uid))
            return
            
        if uid in ADMIN_IDS:
            admin_responses = {
                "📬 Непрочитанные": "📭 Непрочитанных заявок: 0",
                "📊 Статистика": "📊 Статистика сервера...",
                "📢 Рассылка": "📨 Введите текст для рассылки",
                "📋 Помощь": "📖 Команды админа: /start, /stats"
            }
            if text in admin_responses:
                bot.send_message(uid, admin_responses[text], reply_markup=main_kb(uid))
                return

    print("Бот запущен...")
    bot.polling(none_stop=True)

if __name__ == "__main__":
    keep_alive()
    run_bot() os
import time
import socket
import threading
import sqlite3
import telebot
from telebot import types
from samp_client.client import SampClient
from keep_alive import keep_alive

# Константы сервера
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {}

# Глобальный объект бота
bot = None

def get_db_path():
    return os.environ.get("DB_PATH", "bot_stats.db")

def init_db():
    path = get_db_path()
    conn = sqlite3.connect(path, timeout=10)
    cursor = conn.cursor()
    tables = [
        "users (user_id INTEGER PRIMARY KEY, username TEXT, nickname TEXT, position TEXT DEFAULT 'Игрок', join_date TEXT)",
        "server_stats (id INTEGER PRIMARY KEY, peak_online INTEGER DEFAULT 0, peak_date TEXT, peak_day TEXT, last_restart TEXT)",
        "support_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, question TEXT, status TEXT DEFAULT 'unread', date TEXT)",
        "transfer_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, text_data TEXT, photo_file_id TEXT, status TEXT DEFAULT 'unread', date TEXT)",
        "admins (user_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1)",
        "news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)",
        "info_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)",
        "leaders (id INTEGER PRIMARY KEY AUTOINCREMENT, fraction TEXT NOT NULL, nickname TEXT NOT NULL, username TEXT, date TEXT)"
    ]
    for t in tables:
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {t}")
    
    cursor.execute("INSERT OR IGNORE INTO server_stats (id) VALUES (1)")
    
    for col in [("nickname", "TEXT"), ("position", "TEXT DEFAULT 'Игрок'")]:
        try: cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except: pass
        
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
    conn.commit()
    
    cursor.execute("SELECT user_id, level FROM admins")
    for row in cursor.fetchall():
        ADMIN_IDS.add(row[0])
        ADMIN_LEVELS[row[0]] = row[1]
    conn.close()

def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return True

def get_nickname(uid):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone(); conn.close()
    return r[0] if r and r[0] else None

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

def run_bot():
    global bot
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Критическая ошибка: TELEGRAM_BOT_TOKEN не найден в Variables!")
        return

    bot = telebot.TeleBot(token, threaded=True)
    init_db()
    
    @bot.message_handler(commands=['start'])
    def start_cmd(message):
        uid = message.chat.id
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
            bot.send_message(uid, "❌ Подпишитесь на канал для доступа!", reply_markup=markup)
            return
        
        nick = get_nickname(uid)
        if not nick:
            bot.send_message(uid, "👋 Привет! Введите ваш никнейм:")
            bot.register_next_step_handler(message, lambda msg: save_nick(msg))
        else:
            bot.send_message(uid, f"👋 Привет, {nick}!", reply_markup=main_kb(uid))

    def save_nick(message):
        nick = message.text.strip()
        conn = sqlite3.connect(get_db_path()); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date) VALUES (?, ?, ?)", (message.chat.id, nick, time.strftime("%Y-%m-%d")))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ Ник {nick} сохранен!", reply_markup=main_kb(message.chat.id))

    @bot.callback_query_handler(func=lambda call: call.data == "check_sub")
    def check_sub_call(call):
        if is_subscribed(call.from_user.id):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "✅ Спасибо! Теперь используйте /start")
        else:
            bot.answer_callback_query(call.id, "❌ Вы не подписаны!", show_alert=True)

    print("Бот запущен...")
    bot.polling(none_stop=True)

if __name__ == "__main__":
    keep_alive()
    run_bot()
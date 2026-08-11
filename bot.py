import os
import time
import threading
import sqlite3
import telebot
from telebot import types
from keep_alive import keep_alive

# Импорт SAMP клиента
try:
    from samp_client.client import SampClient
    SAMP_AVAILABLE = True
except ImportError:
    SAMP_AVAILABLE = False
    print("⚠️ SampClient не установлен, онлайн будет показывать 0")

SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {}

bot = None
samp_client = None

def get_db_path():
    return os.environ.get("DB_PATH", "bot_stats.db")

def init_db():
    path = get_db_path()
    conn = sqlite3.connect(path, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        nickname TEXT, 
        position TEXT DEFAULT 'Игрок', 
        join_date TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS server_stats (
        id INTEGER PRIMARY KEY, 
        peak_online INTEGER DEFAULT 0, 
        peak_date TEXT, 
        peak_day TEXT, 
        last_restart TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS support_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        nickname TEXT, 
        username TEXT, 
        question TEXT, 
        status TEXT DEFAULT 'unread', 
        date TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS transfer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        nickname TEXT, 
        username TEXT, 
        text_data TEXT, 
        photo_file_id TEXT, 
        status TEXT DEFAULT 'unread', 
        date TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY, 
        level INTEGER DEFAULT 1
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        title TEXT NOT NULL, 
        content TEXT NOT NULL, 
        author TEXT, 
        date TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS info_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        title TEXT NOT NULL, 
        content TEXT NOT NULL, 
        author TEXT, 
        date TEXT
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS leaders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        fraction TEXT NOT NULL, 
        nickname TEXT NOT NULL, 
        username TEXT, 
        date TEXT
    )""")
    
    cursor.execute("INSERT OR IGNORE INTO server_stats (id) VALUES (1)")
    
    for aid in list(ADMIN_IDS):
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
    
    conn.commit()
    conn.close()

def get_online_players():
    """Получает количество игроков онлайн через SAMP клиент"""
    if not SAMP_AVAILABLE:
        return 0
    
    try:
        global samp_client
        if samp_client is None:
            samp_client = SampClient(SERVER_IP, SERVER_PORT)
        
        # Пытаемся получить информацию о сервере
        info = samp_client.get_server_info()
        if info and 'players' in info:
            return info['players']
        return 0
    except Exception as e:
        print(f"Ошибка получения онлайна: {e}")
        return 0

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
    r = c.fetchone()
    conn.close()
    return r[0] if r and r[0] else None

def save_nick_to_db(uid, nick):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date) VALUES (?, ?, ?)", 
              (uid, nick, time.strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

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
        print("❌ Токен не найден!")
        return

    bot = telebot.TeleBot(token, threaded=False)
    init_db()
    
    # Инициализация SAMP клиента
    if SAMP_AVAILABLE:
        global samp_client
        samp_client = SampClient(SERVER_IP, SERVER_PORT)
        print(f"✅ SAMP клиент инициализирован для {SERVER_IP}:{SERVER_PORT}")
    
    @bot.message_handler(commands=['start'])
    def start_command(message):
        uid = message.chat.id
        
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
            bot.send_message(uid, "❌ Подпишитесь на канал!", reply_markup=markup)
            return
        
        nick = get_nickname(uid)
        if not nick:
            msg = bot.send_message(uid, "👋 Введите ваш никнейм:")
            bot.register_next_step_handler(msg, save_nick_step)
        else:
            bot.send_message(uid, f"👋 Привет, {nick}!", reply_markup=main_kb(uid))
    
    def save_nick_step(message):
        nick = message.text.strip()
        save_nick_to_db(message.chat.id, nick)
        bot.send_message(message.chat.id, f"✅ Ник {nick} сохранен!", reply_markup=main_kb(message.chat.id))
    
    @bot.callback_query_handler(func=lambda call: call.data == "check_sub")
    def check_subscription(call):
        if is_subscribed(call.from_user.id):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "✅ Подписка подтверждена! Нажмите /start")
        else:
            bot.answer_callback_query(call.id, "❌ Вы не подписаны!", show_alert=True)
    
    @bot.message_handler(content_types=['text'])
    def handle_buttons(message):
        uid = message.chat.id
        text = message.text
        
        if text and text.startswith('/'):
            return
        
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
            bot.send_message(uid, "❌ Подпишитесь на канал!", reply_markup=markup)
            return
        
        if text == "🌐 Онлайн":
            online = get_online_players()
            bot.send_message(uid, f"👥 Онлайн: {online} игроков", reply_markup=main_kb(uid))
        
        elif text == "🔗 Полезные ссылки":
            bot.send_message(uid, f"🔗 Канал: {CHANNEL_URL}", reply_markup=main_kb(uid))
        
        elif text == "📰 Новости сервера":
            bot.send_message(uid, "📰 Новостей пока нет", reply_markup=main_kb(uid))
        
        elif text == "ℹ️ Информация":
            bot.send_message(uid, f"ℹ️ Сервер SAMP\nIP: {SERVER_IP}\nПорт: {SERVER_PORT}", reply_markup=main_kb(uid))
        
        elif text == "💼 Список лидеров":
            bot.send_message(uid, "🏆 Лидеры:\n1. Asta_Shark - 1000 очков", reply_markup=main_kb(uid))
        
        elif text == "🔄 Перенос аккаунта":
            bot.send_message(uid, "📝 Отправьте ник и пароль для переноса", reply_markup=main_kb(uid))
        
        elif text == "🎫 Тех поддержка":
            bot.send_message(uid, "✍️ Напишите ваш вопрос", reply_markup=main_kb(uid))
        
        elif uid in ADMIN_IDS:
            if text == "📬 Непрочитанные":
                bot.send_message(uid, "📭 Непрочитанных заявок: 0", reply_markup=main_kb(uid))
            elif text == "📊 Статистика":
                bot.send_message(uid, "📊 Статистика сервера...", reply_markup=main_kb(uid))
            elif text == "📢 Рассылка":
                bot.send_message(uid, "📨 Введите текст для рассылки", reply_markup=main_kb(uid))
            elif text == "📋 Помощь":
                bot.send_message(uid, "📖 Команды: /start", reply_markup=main_kb(uid))
            else:
                bot.send_message(uid, "❓ Используйте кнопки меню", reply_markup=main_kb(uid))
        else:
            bot.send_message(uid, "❓ Используйте кнопки меню", reply_markup=main_kb(uid))
    
    print("✅ Бот запущен с поддержкой SAMP!")
    bot.polling(none_stop=True)

if __name__ == "__main__":
    keep_alive()
    run_bot()
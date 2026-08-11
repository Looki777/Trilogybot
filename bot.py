import os
import time
import sqlite3
import telebot
from telebot import types
from keep_alive import keep_alive

# Пробуем импортировать SAMP, если нет - работает без него
try:
    from samp_client.client import SampClient
    samp_ready = True
except:
    samp_ready = False

SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"
ADMIN_IDS = [709672781, 5939366373, 1066139847]

bot = telebot.TeleBot(os.environ.get("TELEGRAM_BOT_TOKEN"))

def get_online():
    if not samp_ready:
        return 0
    try:
        client = SampClient(SERVER_IP, SERVER_PORT)
        info = client.get_server_info()
        return info.get('players', 0) if info else 0
    except:
        return 0

def is_subscribed(user_id):
    try:
        return bot.get_chat_member(REQUIRED_CHANNEL, user_id).status in ['member', 'administrator', 'creator']
    except:
        return True

def get_nickname(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def save_nickname(user_id, nickname):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date) VALUES (?, ?, ?)", 
              (user_id, nickname, time.strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def main_menu(user_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🌐 Онлайн", "🔗 Полезные ссылки")
    keyboard.row("📰 Новости", "ℹ️ Информация")
    keyboard.row("💼 Лидеры", "🔄 Перенос")
    keyboard.row("🎫 Поддержка")
    if user_id in ADMIN_IDS:
        keyboard.row("📬 Заявки", "📊 Статистика")
        keyboard.row("📢 Рассылка", "📋 Помощь")
    return keyboard

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    
    # Проверка подписки
    if not is_subscribed(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
        keyboard.add(types.InlineKeyboardButton("🔄 Проверить", callback_data="check_sub"))
        bot.send_message(user_id, "❌ Подпишись на канал!", reply_markup=keyboard)
        return
    
    # Проверка ника
    nickname = get_nickname(user_id)
    if not nickname:
        msg = bot.send_message(user_id, "👋 Введи свой никнейм:")
        bot.register_next_step_handler(msg, save_nick)
    else:
        bot.send_message(user_id, f"👋 Привет, {nickname}!", reply_markup=main_menu(user_id))

def save_nick(message):
    nickname = message.text.strip()
    save_nickname(message.chat.id, nickname)
    bot.send_message(message.chat.id, f"✅ Ник {nickname} сохранен!", reply_markup=main_menu(message.chat.id))

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub(call):
    if is_subscribed(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Готово! Нажми /start")
    else:
        bot.answer_callback_query(call.id, "❌ Ты не подписан!", show_alert=True)

@bot.message_handler(func=lambda message: True)
def buttons(message):
    user_id = message.chat.id
    text = message.text
    
    # Пропускаем команды
    if text and text.startswith('/'):
        return
    
    # Проверка подписки
    if not is_subscribed(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
        keyboard.add(types.InlineKeyboardButton("🔄 Проверить", callback_data="check_sub"))
        bot.send_message(user_id, "❌ Подпишись на канал!", reply_markup=keyboard)
        return
    
    # Обработка кнопок
    if text == "🌐 Онлайн":
        online = get_online()
        bot.send_message(user_id, f"👥 Онлайн: {online}", reply_markup=main_menu(user_id))
    
    elif text == "🔗 Полезные ссылки":
        bot.send_message(user_id, f"🔗 {CHANNEL_URL}", reply_markup=main_menu(user_id))
    
    elif text == "📰 Новости":
        bot.send_message(user_id, "📰 Новостей нет", reply_markup=main_menu(user_id))
    
    elif text == "ℹ️ Информация":
        bot.send_message(user_id, f"ℹ️ Сервер {SERVER_IP}:{SERVER_PORT}", reply_markup=main_menu(user_id))
    
    elif text == "💼 Лидеры":
        bot.send_message(user_id, "🏆 Лидеров нет", reply_markup=main_menu(user_id))
    
    elif text == "🔄 Перенос":
        bot.send_message(user_id, "📝 Напиши данные для переноса", reply_markup=main_menu(user_id))
    
    elif text == "🎫 Поддержка":
        bot.send_message(user_id, "✍️ Напиши свой вопрос", reply_markup=main_menu(user_id))
    
    elif user_id in ADMIN_IDS:
        if text == "📬 Заявки":
            bot.send_message(user_id, "📭 Заявок: 0", reply_markup=main_menu(user_id))
        elif text == "📊 Статистика":
            bot.send_message(user_id, "📊 Статистика...", reply_markup=main_menu(user_id))
        elif text == "📢 Рассылка":
            bot.send_message(user_id, "📨 Введи текст", reply_markup=main_menu(user_id))
        elif text == "📋 Помощь":
            bot.send_message(user_id, "📖 /start", reply_markup=main_menu(user_id))
        else:
            bot.send_message(user_id, "❓ Используй кнопки", reply_markup=main_menu(user_id))
    else:
        bot.send_message(user_id, "❓ Используй кнопки", reply_markup=main_menu(user_id))

# Создаем БД при старте
conn = sqlite3.connect("bot_stats.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, join_date TEXT)")
conn.commit()
conn.close()

print("✅ Бот запущен!")
bot.polling(none_stop=True)
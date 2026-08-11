import os
import time
import threading
import sqlite3
import telebot
from telebot import types
from keep_alive import keep_alive

try:
    from samp_client.client import SampClient
    samp_ready = True
except:
    samp_ready = False

SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"
ADMIN_IDS = {709672781, 5939366373, 1066139847}

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TOKEN)
DB_PATH = "bot_stats.db"

# ===================== БАЗА =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, join_date TEXT, username TEXT, position TEXT DEFAULT 'Игрок', level INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1, position TEXT DEFAULT 'Администратор')")
    c.execute("CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, author TEXT, date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS support_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, question TEXT, status TEXT DEFAULT 'unread', date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS leaders (id INTEGER PRIMARY KEY AUTOINCREMENT, fraction TEXT NOT NULL, nickname TEXT NOT NULL, username TEXT, date TEXT)")
    for aid in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, 3, 'Главный администратор')", (aid,))
    conn.commit()
    conn.close()
init_db()

# ===================== ФУНКЦИИ =====================
def get_nickname(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_username(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_position(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT position FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Игрок"

def get_level(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT level FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def set_nickname(user_id, nick):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date, level) VALUES (?, ?, ?, 0)", (user_id, nick, time.strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def update_user_info(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

def is_subscribed(user_id):
    try:
        return bot.get_chat_member(REQUIRED_CHANNEL, user_id).status in ['member', 'administrator', 'creator']
    except:
        return True

def get_online():
    if not samp_ready:
        return "❌ SAMP клиент не доступен"
    try:
        client = SampClient(SERVER_IP, SERVER_PORT)
        info = client.get_server_info()
        if info:
            return f"🎮 {info.hostname}\n\n🌐 {SERVER_IP}:{SERVER_PORT}\n👥 Онлайн: {info.players}/{info.max_players}\n🟢 Статус: Работает"
        return "❌ Сервер не отвечает"
    except:
        return "❌ Ошибка подключения"

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_unread_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
    count = c.fetchone()[0]
    conn.close()
    return count

def news_get_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, date FROM news ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def news_add(title, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO news (title, content, author, date) VALUES (?, ?, ?, ?)", (title, content, "Администратор", date))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def news_delete(news_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, position FROM admins ORDER BY level DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_admin_level(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ===================== КЛАВИАТУРА =====================
MENU_BUTTONS = ["🌐 Онлайн", "🔗 Полезные ссылки", "📰 Новости сервера", "💼 Список лидеров", "🔄 Перенос аккаунта", "🎫 Тех поддержка", "📬 Непрочитанные", "📊 Статистика", "📢 Рассылка", "📋 Помощь"]

def main_kb(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("🌐 Онлайн", "🔗 Полезные ссылки")
    m.row("📰 Новости сервера", "💼 Список лидеров")
    m.row("🔄 Перенос аккаунта", "🎫 Тех поддержка")
    if uid in ADMIN_IDS:
        m.row("📬 Непрочитанные", "📊 Статистика")
        m.row("📢 Рассылка", "📋 Помощь")
    return m

# ===================== /START =====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.chat.id
    username = message.from_user.username
    if username:
        update_user_info(uid, username)
    
    if not is_subscribed(uid):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
        markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
        bot.send_message(uid, "❌ Подпишитесь на канал!", reply_markup=markup)
        return
    nick = get_nickname(uid)
    if not nick:
        msg = bot.send_message(uid, "👋 Введите ваш никнейм:")
        bot.register_next_step_handler(msg, save_nick)
    else:
        bot.send_message(uid, f"👋 Привет, {nick}!", reply_markup=main_kb(uid))

def save_nick(message):
    nick = message.text.strip()
    set_nickname(message.chat.id, nick)
    bot.send_message(message.chat.id, f"✅ Ник {nick} сохранен!", reply_markup=main_kb(message.chat.id))

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub(call):
    if is_subscribed(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Подписка подтверждена! Нажмите /start")
    else:
        bot.answer_callback_query(call.id, "❌ Вы не подписаны!", show_alert=True)

# ===================== КОМАНДЫ =====================
@bot.message_handler(commands=['admlist'])
def admlist_cmd(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        bot.send_message(uid, "❌ Только для администраторов!")
        return
    admins = get_all_admins()
    if not admins:
        bot.send_message(uid, "📭 Список админов пуст.")
        return
    text = "👑 <b>Список администраторов:</b>\n\n"
    for user_id, position in admins:
        nick = get_nickname(user_id) or str(user_id)
        username = get_username(user_id) or "Нет"
        text += f"👤 <b>{nick}</b>\n"
        text += f"   📋 Должность: {position}\n"
        text += f"   📱 Юзернейм: @{username}\n\n"
    bot.send_message(uid, text, parse_mode="HTML")

@bot.message_handler(commands=['стата'])
def stata_cmd(message):
    uid = message.chat.id
    nick = get_nickname(uid)
    if not nick:
        bot.send_message(uid, "❌ Сначала введите /start")
        return
    position = get_position(uid)
    level = get_admin_level(uid) or get_level(uid) or 0
    username = get_username(uid) or "Нет"
    
    # Уровни
    level_names = {0: "🟢 Игрок", 1: "🟢 Модератор", 2: "🟡 Старший модератор", 3: "🔴 Главный администратор"}
    level_text = level_names.get(level, f"Уровень {level}")
    
    text = (
        f"📋 <b>Ваш профиль</b>\n\n"
        f"🎮 <b>Никнейм:</b> {nick}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📱 <b>Юзернейм:</b> @{username}\n"
        f"🎖️ <b>Должность:</b> {position}\n"
        f"📊 <b>Уровень:</b> {level_text}"
    )
    bot.send_message(uid, text, parse_mode="HTML")

@bot.message_handler(commands=['ник'])
def nick_cmd(message):
    uid = message.chat.id
    msg = bot.send_message(uid, "✍️ Введите новый никнейм:")
    bot.register_next_step_handler(msg, change_nick)

def change_nick(message):
    nick = message.text.strip()
    if len(nick) < 3:
        bot.send_message(message.chat.id, "❌ Минимум 3 символа.")
        return
    set_nickname(message.chat.id, nick)
    bot.send_message(message.chat.id, f"✅ Ник изменен на {nick}!")

# ===================== НОВОСТИ (АДМИН) =====================
@bot.message_handler(func=lambda message: message.text == "📰 Новости сервера")
def news_button(message):
    uid = message.chat.id
    if uid in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить", callback_data="news_add"),
            types.InlineKeyboardButton("🗑 Удалить", callback_data="news_del")
        )
        bot.send_message(uid, "📰 <b>Управление новостями</b>", reply_markup=markup, parse_mode="HTML")
    else:
        news = news_get_all()
        if not news:
            bot.send_message(uid, "📭 Новостей нет.")
            return
        text = "📰 <b>Новости</b>\n\n"
        for nid, title, date in news:
            text += f"▪️ {title} [{date}]\n"
        bot.send_message(uid, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "news_add")
def news_add_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    msg = bot.send_message(call.message.chat.id, "📰 Введите заголовок:")
    bot.register_next_step_handler(msg, news_add_title)
    bot.answer_callback_query(call.id)

def news_add_title(message):
    title = message.text.strip()
    msg = bot.send_message(message.chat.id, f"✅ Заголовок: {title}\nТеперь введите текст:")
    bot.register_next_step_handler(msg, news_add_content, title)

def news_add_content(message, title):
    content = message.text.strip()
    news_add(title, content)
    bot.send_message(message.chat.id, f"✅ Новость добавлена!")

@bot.callback_query_handler(func=lambda call: call.data == "news_del")
def news_del_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news = news_get_all()
    if not news:
        bot.send_message(call.message.chat.id, "📭 Новостей нет.")
        bot.answer_callback_query(call.id)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for nid, title, date in news:
        markup.add(types.InlineKeyboardButton(f"🗑 {title} [{date}]", callback_data=f"news_del_{nid}"))
    bot.send_message(call.message.chat.id, "Выберите новость для удаления:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_"))
def news_del_do(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    nid = int(call.data.split("_")[2])
    news_delete(nid)
    bot.answer_callback_query(call.id, "✅ Новость удалена")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===================== ОСТАЛЬНЫЕ КНОПКИ =====================
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    uid = message.chat.id
    text = message.text

    if not text or text.startswith('/'):
        return

    if not is_subscribed(uid):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
        markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
        bot.send_message(uid, "❌ Подпишитесь на канал!", reply_markup=markup)
        return

    # ===== ОНЛАЙН =====
    if text == "🌐 Онлайн":
        bot.send_message(uid, get_online(), reply_markup=main_kb(uid))

    # ===== ССЫЛКИ =====
    elif text == "🔗 Полезные ссылки":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Канал", url=CHANNEL_URL),
            types.InlineKeyboardButton("💬 Чат", url="https://t.me/santropetrilogy_chat"),
            types.InlineKeyboardButton("📱 ВК", url="https://vk.com/santropetrilogy")
        )
        bot.send_message(uid, "🔗 Ресурсы:", reply_markup=markup)

    # ===== ЛИДЕРЫ =====
    elif text == "💼 Список лидеров":
        bot.send_message(uid, "🏆 Лидеров пока нет.", reply_markup=main_kb(uid))

    # ===== ПЕРЕНОС =====
    elif text == "🔄 Перенос аккаунта":
        bot.send_message(uid, "📝 Напишите данные для переноса администратору.", reply_markup=main_kb(uid))

    # ===== ТЕХПОДДЕРЖКА =====
    elif text == "🎫 Тех поддержка":
        bot.send_message(uid, "✍️ Напишите ваш вопрос администратору.", reply_markup=main_kb(uid))

    # ===== АДМИН-КНОПКИ =====
    elif uid in ADMIN_IDS:
        if text == "📬 Непрочитанные":
            bot.send_message(uid, f"📭 Непрочитанных заявок: {get_unread_count()}", reply_markup=main_kb(uid))

        elif text == "📊 Статистика":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM admins")
            admins = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM news")
            news_count = c.fetchone()[0]
            conn.close()
            bot.send_message(uid, f"📊 <b>Статистика</b>\n\n👤 Пользователей: {users}\n👑 Админов: {admins}\n📰 Новостей: {news_count}", parse_mode="HTML", reply_markup=main_kb(uid))

        elif text == "📢 Рассылка":
            msg = bot.send_message(uid, "📨 Введите текст для рассылки:")
            bot.register_next_step_handler(msg, broadcast_text)

        elif text == "📋 Помощь":
            help_text = (
                "📋 <b>Команды Главного Модератора:</b>\n\n"
                "👤 <b>Управление администрацией</b>\n"
                "/админ ID уровень — выдать права (1/2/3)\n"
                "/разадмин ID — снять права администратора\n"
                "/должность ID Должность — изменить должность\n"
                "/admlist — список всей администрации бота\n\n"
                "🎮 <b>Профиль</b>\n"
                "/стата — посмотреть свой профиль\n"
                "/ник — сменить свой никнейм\n"
                "/лог — скачать историю ответов тех. поддержки\n\n"
                "🔘 <b>Кнопки меню</b>\n"
                "🌐 Онлайн — статус SA:MP сервера\n"
                "🔗 Полезные ссылки — официальные ресурсы проекта\n"
                "📰 Новости сервера — просмотр и управление новостями\n"
                "💼 Список лидеров — список лидеров организаций\n"
                "🔄 Перенос аккаунта — подача заявки на перенос\n"
                "🎫 Тех поддержка — создание обращения в поддержку\n"
                "📬 Непрочитанные — просмотр необработанных обращений\n"
                "📊 Статистика — количество пользователей и обращений\n"
                "📢 Рассылка — отправить сообщение всем пользователям"
            )
            bot.send_message(uid, help_text, parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== РАССЫЛКА =====================
def broadcast_text(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return
    text = message.text
    users = get_all_users()
    if not users:
        bot.send_message(uid, "❌ Нет пользователей.")
        return
    success = 0
    for user_id in users:
        try:
            bot.send_message(user_id, text)
            success += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(uid, f"✅ Рассылка завершена!\nДоставлено: {success} из {len(users)}", reply_markup=main_kb(uid))

# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    keep_alive()
    print("✅ Бот запущен!")
    bot.polling(none_stop=True)

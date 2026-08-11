import os
import time
import sqlite3
import telebot
from telebot import types
from keep_alive import keep_alive

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
    c.execute("CREATE TABLE IF NOT EXISTS support_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, username TEXT, question TEXT, status TEXT DEFAULT 'unread', date TEXT, admin_reply TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS leaders (id INTEGER PRIMARY KEY AUTOINCREMENT, fraction TEXT NOT NULL, nickname TEXT NOT NULL, username TEXT, date TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS transfer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        nickname TEXT,
        username TEXT,
        text_data TEXT,
        photo_file_id TEXT,
        status TEXT DEFAULT 'pending',
        date TEXT,
        admin_answer TEXT
    )""")
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

def set_position(user_id, position):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET position = ? WHERE user_id = ?", (position, user_id))
    conn.commit()
    conn.close()

def update_user_info(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

def get_user_by_username(username):
    username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, nickname, position FROM users WHERE LOWER(username) = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row

def is_subscribed(user_id):
    try:
        return bot.get_chat_member(REQUIRED_CHANNEL, user_id).status in ['member', 'administrator', 'creator']
    except:
        return True

def get_online():
    return "❌ Онлайн недоступен (библиотека не установлена)"

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

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

# ===================== ДОСТУПНЫЕ ДОЛЖНОСТИ =====================
AVAILABLE_POSITIONS = [
    "Игрок", "Хелпер", "Модератор", "Куратор", "Следящий за Гос", "Следящий за Гетто", "Следящий за Мафиями", "Следящий за АП", "Следящий за Хелперами", "ЗГС Гос", "ЗГС Гетто", "ЗГС Мафий", "ЗГС АП", "ЗГС Хелперов", "ГС Гос", "ГС Гетто", "ГС Мафий", "ГС АП", "ГС Хелперов", "Зам. Главного администратора", "Главный администратор", "Спец. проект", "Основатель", "Разработчик"
]

def get_positions_list():
    text = "📋 <b>Доступные должности:</b>\n\n"
    groups = [
        ("👤 Игроки", ["Игрок"]),
        ("🙋‍♂️ Помощь", ["Хелпер"]),
        ("🛡️ Модерация", ["Модератор", "Куратор"]),
        ("🔎 Следящие", ["Следящий за Гос", "Следящий за Гетто", "Следящий за Мафиями", "Следящий за АП", "Следящий за Хелперами"]),
        ("⚜️ Заместители ГС", ["ЗГС Гос", "ЗГС Гетто", "ЗГС Мафий", "ЗГС АП", "ЗГС Хелперов"]),
        ("⚡ Главные следящие", ["ГС Гос", "ГС Гетто", "ГС Мафий", "ГС АП", "ГС Хелперов"]),
        ("👑 Администрация", ["Зам. Главного администратора", "Главный администратор"]),
        ("💻 Разработка", ["Спец. проект", "Основатель", "Разработчик"])
    ]
    for group_name, positions in groups:
        text += f"<b>{group_name}:</b>\n"
        for pos in positions:
            text += f"   • {pos}\n"
        text += "\n"
    return text

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

# ===================== ДОЛЖНОСТИ =====================
@bot.message_handler(commands=['должность'])
def position_cmd(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        bot.send_message(uid, "❌ Только для администраторов!")
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(uid, "❌ <b>Неверный формат!</b>\n\n📋 <b>Использование:</b>\n<code>/должность @username Должность</code>\n\n📌 <b>Пример:</b>\n<code>/должность @john_doe Модератор</code>\n\n📋 <b>Список доступных должностей:</b>\nОтправьте команду <code>/должности</code> для просмотра.", parse_mode="HTML")
            return
        username = parts[1].strip()
        new_position = parts[2].strip()
        if new_position not in AVAILABLE_POSITIONS:
            bot.send_message(uid, f"❌ <b>Должность «{new_position}» не найдена!</b>\n\n📋 <b>Доступные должности:</b>\nОтправьте команду <code>/должности</code> для просмотра.", parse_mode="HTML")
            return
        user_data = get_user_by_username(username)
        if not user_data:
            bot.send_message(uid, f"❌ <b>Пользователь {username} не найден!</b>\n\n📌 Убедитесь, что пользователь:\n• Зарегистрирован в боте (/start)\n• Указал свой юзернейм в Telegram", parse_mode="HTML")
            return
        target_id, target_nick, current_pos = user_data
        set_position(target_id, new_position)
        bot.send_message(uid, f"✅ <b>Должность успешно изменена!</b>\n\n👤 <b>Игрок:</b> {target_nick}\n📱 <b>Юзернейм:</b> {username}\n📋 <b>Новая должность:</b> {new_position}\n📌 <b>Старая должность:</b> {current_pos}", parse_mode="HTML")
        try:
            bot.send_message(target_id, f"📋 <b>Ваша должность была изменена!</b>\n\n📌 <b>Новая должность:</b> {new_position}\n👤 <b>Кем изменено:</b> Администрацией проекта", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        bot.send_message(uid, f"❌ <b>Ошибка!</b>\n\n📋 <b>Использование:</b>\n<code>/должность @username Должность</code>\n\n📌 <b>Пример:</b>\n<code>/должность @john_doe Модератор</code>\n\n📋 <b>Список доступных должностей:</b>\nОтправьте команду <code>/должности</code> для просмотра.", parse_mode="HTML")

@bot.message_handler(commands=['должности'])
def positions_list_cmd(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        bot.send_message(uid, "❌ Только для администраторов!")
        return
    bot.send_message(uid, get_positions_list(), parse_mode="HTML")

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
        nick = get_nickname(user_id) or "Не указан"
        username = get_username(user_id) or "Нет"
        text += f"👤 <b>{nick}</b>\n   📱 Юзернейм: @{username}\n   📋 Должность: {position}\n\n"
    bot.send_message(uid, text, parse_mode="HTML")

@bot.message_handler(commands=['стата'])
def stata_cmd(message):
    uid = message.chat.id
    if message.from_user.username:
        update_user_info(uid, message.from_user.username)
    nick = get_nickname(uid)
    if not nick:
        bot.send_message(uid, "❌ Сначала введите /start")
        return
    position = get_position(uid)
    level = get_admin_level(uid) or get_level(uid) or 0
    username = get_username(uid) or "Нет"
    level_names = {0: "🟢 Игрок", 1: "🟢 Модератор", 2: "🟡 Старший модератор", 3: "🔴 Главный администратор"}
    level_text = level_names.get(level, f"Уровень {level}")
    text = f"📋 <b>Ваш профиль</b>\n\n🎮 <b>Никнейм:</b> {nick}\n🆔 <b>ID:</b> <code>{uid}</code>\n📱 <b>Юзернейм:</b> @{username}\n🎖️ <b>Должность:</b> {position}\n📊 <b>Уровень:</b> {level_text}"
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

# ===================== ТЕХПОДДЕРЖКА (НОВАЯ ЛОГИКА) =====================
@bot.message_handler(func=lambda message: message.text == "🎫 Тех поддержка")
def support_start(message):
    uid = message.chat.id
    msg = bot.send_message(uid, "✍️ Напишите ваш вопрос. Администратор получит его и ответит вам.")
    bot.register_next_step_handler(msg, support_send)

def support_send(message):
    uid = message.chat.id
    question = message.text.strip()
    
    if question in MENU_BUTTONS or question.startswith('/'):
        bot.send_message(uid, "❌ Отправка вопроса отменена.", reply_markup=main_kb(uid))
        return

    nickname = get_nickname(uid) or "Не указан"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO support_requests (user_id, nickname, username, question, status, date) VALUES (?, ?, ?, ?, 'unread', ?)", (uid, nickname, username, question, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()

    # Кнопка для админа
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 Ответить", callback_data=f"supp_reply_{req_id}_{uid}"))

    admin_text = (
        f"🆘 <b>НОВОЕ ОБРАЩЕНИЕ В ТЕХПОДДЕРЖКУ №{req_id}</b>\n\n"
        f"👤 <b>Игрок:</b> {nickname}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📱 <b>Юзернейм:</b> {username}\n\n"
        f"📋 <b>Вопрос:</b>\n{question}\n\n"
        f"📅 <b>Дата:</b> {date}"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode="HTML")
        except:
            pass

    bot.send_message(uid, f"✅ Ваше обращение №{req_id} отправлено администрации! Ожидайте ответа.", reply_markup=main_kb(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("supp_reply_"))
def support_reply_start(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    
    msg = bot.send_message(admin_id, f"✍️ Введите ответ для игрока (заявка №{req_id}):")
    bot.register_next_step_handler(msg, support_reply_send, req_id, user_id, call.message)
    bot.answer_callback_query(call.id)

def support_reply_send(message, req_id, user_id, admin_msg):
    admin_id = message.chat.id
    reply_text = message.text.strip()
    
    # Обновляем БД и закрываем заявку
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE support_requests SET status = 'answered', admin_reply = ? WHERE id = ?", (reply_text, req_id))
    conn.commit()
    conn.close()
    
    # Отправляем ответ игроку
    try:
        bot.send_message(user_id, f"📩 <b>Ответ администрации на заявку №{req_id}:</b>\n\n{reply_text}", parse_mode="HTML")
        bot.send_message(admin_id, f"✅ Ответ отправлен игроку!")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка при отправке игроку: {e}")
    
    # Удаляем сообщение с заявкой у админа (чтобы не засорять чат)
    try:
        bot.delete_message(admin_msg.chat.id, admin_msg.message_id)
    except:
        pass

# ===================== НЕПРОЧИТАННЫЕ (ЛИСТ ВОПРОСОВ) =====================
@bot.message_handler(func=lambda message: message.text == "📬 Непрочитанные")
def unread_list(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, nickname, question, date FROM support_requests WHERE status = 'unread' ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(uid, "📭 Нет непрочитанных обращений.", reply_markup=main_kb(uid))
        return

    text = "📬 <b>Список непрочитанных обращений:</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for req_id, nick, q, date in rows:
        # Короткий текст вопроса (не больше 20 символов)
        short_q = q[:20] + "..." if len(q) > 20 else q
        text += f"▪️ #{req_id} | {nick} | {date}\n"
        markup.add(types.InlineKeyboardButton(f"#{req_id} - {short_q}", callback_data=f"supp_view_{req_id}"))

    bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("supp_view_"))
def support_view(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    
    req_id = int(call.data.split("_")[2])
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, nickname, username, question, date FROM support_requests WHERE id = ?", (req_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!", show_alert=True)
        return
        
    user_id, nick, username, question, date = row
    
    text = (
        f"📋 <b>Заявка №{req_id}</b>\n\n"
        f"👤 {nick}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📱 @{username}\n"
        f"📅 {date}\n\n"
        f"<b>Вопрос:</b>\n{question}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 Ответить", callback_data=f"supp_reply_{req_id}_{user_id}"))
    
    bot.edit_message_text(text, admin_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# ===================== ПЕРЕНОС =====================
def process_transfer_form(message):
    uid = message.chat.id
    if message.text and message.text in MENU_BUTTONS:
        bot.send_message(uid, "❌ Отправка заявки отменена.")
        return
    nickname = get_nickname(uid) or "Не указан"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    text_data = message.text or message.caption or ""
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.document:
        photo_file_id = message.document.file_id
    if not text_data and not photo_file_id:
        bot.send_message(uid, "❌ Ошибка: отправьте заполненную форму и прикрепите скриншот.")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("""INSERT INTO transfer_requests (user_id, nickname, username, text_data, photo_file_id, status, date) VALUES (?, ?, ?, ?, ?, 'pending', ?)""", (uid, nickname, username, text_data, photo_file_id, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    admin_text = f"📥 <b>НОВАЯ ЗАЯВКА НА ПЕРЕНОС №{req_id}</b>\n\n👤 <b>Игрок:</b> {nickname}\n🆔 <b>ID:</b> <code>{uid}</code>\n📱 <b>Юзернейм:</b> {username}\n\n📋 <b>Данные заявки:</b>\n{text_data}\n\n📅 <b>Дата:</b> {date}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"transfer_approve_{req_id}_{uid}"), types.InlineKeyboardButton("❌ Отказать", callback_data=f"transfer_reject_{req_id}_{uid}"))
    for admin_id in ADMIN_IDS:
        try:
            if photo_file_id:
                bot.send_photo(admin_id, photo_file_id, caption=admin_text, reply_markup=markup, parse_mode="HTML")
            else:
                bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")
    bot.send_message(uid, f"✅ <b>Ваша заявка на перенос №{req_id} успешно отправлена!</b>\n\n📌 Администрация рассмотрит вашу заявку и ответит в ближайшее время.", parse_mode="HTML", reply_markup=main_kb(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_approve_"))
def transfer_approve(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE transfer_requests SET status = 'approved' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    try:
        bot.send_message(user_id, f"🎉 <b>Ваша заявка на перенос №{req_id} ОДОБРЕНА!</b>\n\nАдминистрация проекта одобрила ваш перенос.\nОжидайте связи для завершения переноса!", parse_mode="HTML")
    except:
        pass
    bot.edit_message_reply_markup(admin_id, call.message.message_id, reply_markup=None)
    new_text = call.message.text + "\n\n🟢 <b>СТАТУС: ОДОБРЕНО</b>"
    if call.message.photo:
        bot.edit_message_caption(new_text, admin_id, call.message.message_id, parse_mode="HTML")
    else:
        bot.edit_message_text(new_text, admin_id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Заявка одобрена!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_reject_"))
def transfer_reject(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    msg = bot.send_message(admin_id, f"❌ <b>Причина отказа для заявки №{req_id}</b>\n\nВведите причину отказа (или <code>-</code>, чтобы отказать без причины):", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_transfer_reject, req_id, user_id, call.message)
    bot.answer_callback_query(call.id)

def process_transfer_reject(message, req_id, user_id, admin_msg):
    admin_id = message.chat.id
    reason = message.text.strip()
    if reason == "-":
        reason = "Причина не указана"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE transfer_requests SET status = 'rejected', admin_answer = ? WHERE id = ?", (reason, req_id))
    conn.commit()
    conn.close()
    try:
        bot.send_message(user_id, f"❌ <b>Ваша заявка на перенос №{req_id} ОТКЛОНЕНА.</b>\n\n📌 <b>Причина отказа:</b> {reason}", parse_mode="HTML")
    except:
        pass
    bot.edit_message_reply_markup(admin_msg.chat.id, admin_msg.message_id, reply_markup=None)
    new_text = admin_msg.text + f"\n\n🔴 <b>СТАТУС: ОТКАЗАНО</b>\n📌 Причина: {reason}"
    if admin_msg.photo:
        bot.edit_message_caption(new_text, admin_msg.chat.id, admin_msg.message_id, parse_mode="HTML")
    else:
        bot.edit_message_text(new_text, admin_msg.chat.id, admin_msg.message_id, parse_mode="HTML")
    bot.send_message(admin_id, f"✅ Заявка №{req_id} отклонена.")

# ===================== НОВОСТИ =====================
@bot.message_handler(func=lambda message: message.text == "📰 Новости сервера")
def news_button(message):
    uid = message.chat.id
    if uid in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("➕ Добавить", callback_data="news_add"), types.InlineKeyboardButton("🗑 Удалить", callback_data="news_del"))
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
    if not text or text.startswith('/') or text in ["🎫 Тех поддержка", "📬 Непрочитанные"]:
        return
    if not is_subscribed(uid):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL))
        markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub"))
        bot.send_message(uid, "❌ Подпишитесь на канал!", reply_markup=markup)
        return
    if text == "🌐 Онлайн":
        bot.send_message(uid, get_online(), reply_markup=main_kb(uid))
    elif text == "🔗 Полезные ссылки":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📢 Telegram-канал проекта", url="https://t.me/santrope_trilogyrp"), types.InlineKeyboardButton("🌐 Официальный форум", url="https://wh32893.web3.maze-tech.ru/index.php"), types.InlineKeyboardButton("📱 Группа ВКонтакте", url="https://vk.com/santropetrilogy"))
        text_msg = "🔗 <b>Официальные ресурсы проекта</b>\n\n📢 <b>Telegram-канал</b>\nГлавные новости, анонсы и объявления.\n\n🌐 <b>Форум проекта</b>\nПравила, заявки, обсуждения и полезная информация.\n▫️ Игровые разделы\n▫️ Техническая поддержка\n▫️ Общение и предложения\n\n📱 <b>Группа ВКонтакте</b>\nНовости проекта и общение с игроками.\n\n👇 <i>Выберите нужный ресурс:</i>"
        bot.send_message(uid, text_msg, reply_markup=markup, parse_mode="HTML")
    elif text == "💼 Список лидеров":
        bot.send_message(uid, "🏆 Лидеров пока нет.", reply_markup=main_kb(uid))
    elif text == "🔄 Перенос аккаунта":
        form_text = "🔄 <b>Перенос аккаунтов с разных проектов!</b>\n\n📋 <b>Форма подачи заявления:</b>\n\n▫️ <b>Nick_Name:</b>\n▫️ <b>Проект с которого переносите:</b>\n▫️ <b>Что переносите:</b>\n▫️ <b>Доказательства имущества (/time):</b>\n\n✍️ Заполните данную форму и отправьте ответным сообщением!\n📸 Обязательно прикрепите скриншот доказательств с /time прямо к сообщению с текстом."
        bot.send_message(uid, form_text, parse_mode="HTML")
        msg = bot.send_message(uid, "📝 Введите данные по форме и прикрепите скриншот:")
        bot.register_next_step_handler(msg, process_transfer_form)
    elif uid in ADMIN_IDS:
        if text == "📊 Статистика":
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
            help_text = "📋 <b>Команды Главного Модератора:</b>\n\n👤 <b>Управление администрацией</b>\n/админ ID уровень — выдать права (1/2/3)\n/разадмин ID — снять права администратора\n/должность @username Должность — изменить должность\n/должности — список всех доступных должностей\n/admlist — список всей администрации бота\n\n🎮 <b>Профиль</b>\n/стата — посмотреть свой профиль\n/ник — сменить свой никнейм\n/лог — скачать историю ответов тех. поддержки\n\n🔘 <b>Кнопки меню</b>\n🌐 Онлайн — статус SA:MP сервера\n🔗 Полезные ссылки — официальные ресурсы проекта\n📰 Новости сервера — просмотр и управление новостями\n💼 Список лидеров — список лидеров организаций\n🔄 Перенос аккаунта — подача заявки на перенос\n🎫 Тех поддержка — создание обращения в поддержку\n📬 Непрочитанные — просмотр необработанных обращений\n📊 Статистика — количество пользователей и обращений\n📢 Рассылка — отправить сообщение всем пользователям"
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
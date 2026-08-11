import os
import time
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

# ===================== БАЗА ДАННЫХ =====================
def init_db():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, join_date TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS leaders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fraction TEXT NOT NULL,
        nickname TEXT NOT NULL,
        username TEXT,
        date TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        level INTEGER DEFAULT 1,
        position TEXT DEFAULT 'Администратор'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transfer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        nickname TEXT,
        username TEXT,
        old_nick TEXT,
        project_from TEXT,
        transfer_items TEXT,
        proof TEXT,
        photo_file_id TEXT,
        status TEXT DEFAULT 'pending',
        date TEXT,
        admin_answer TEXT
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
        date TEXT
    )""")
    for aid in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (?, 3)", (aid,))
    conn.commit()
    conn.close()

init_db()

# ===================== НОВОСТИ =====================
def news_get_all():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT id, title, date FROM news ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def news_get_by_id(news_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT id, title, content, date FROM news WHERE id = ?", (news_id,))
    row = c.fetchone()
    conn.close()
    return row

def news_add(title, content):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO news (title, content, author, date) VALUES (?, ?, ?, ?)",
              (title, content, "Администратор", date))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def news_edit(news_id, title, content):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("UPDATE news SET title = ?, content = ? WHERE id = ?", (title, content, news_id))
    conn.commit()
    conn.close()

def news_delete(news_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()

def news_list_markup(uid):
    all_news = news_get_all()
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not all_news:
        if uid in ADMIN_IDS:
            markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="news_add"))
        return markup, False
    for nid, title, date in all_news:
        markup.add(types.InlineKeyboardButton(f"📰 {title}  [{date}]", callback_data=f"news_view_{nid}"))
    if uid in ADMIN_IDS:
        markup.add(types.InlineKeyboardButton("➕ Добавить новость", callback_data="news_add"))
    return markup, True

# ===================== ЛИДЕРЫ =====================
def get_all_leaders():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT fraction, nickname, username, date FROM leaders ORDER BY fraction")
    rows = c.fetchall()
    conn.close()
    return rows

def add_leader(fraction, nickname, username, date):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("INSERT INTO leaders (fraction, nickname, username, date) VALUES (?, ?, ?, ?)",
              (fraction, nickname, username, date))
    conn.commit()
    conn.close()

def remove_leader(fraction, nickname):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("DELETE FROM leaders WHERE fraction = ? AND nickname = ?", (fraction, nickname))
    conn.commit()
    conn.close()

# ===================== ПЕРЕНОСЫ =====================
def save_transfer_request(user_id, nickname, username, old_nick, project_from, transfer_items, proof, photo_file_id=None):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("""INSERT INTO transfer_requests 
        (user_id, nickname, username, old_nick, project_from, transfer_items, proof, photo_file_id, date, status) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (user_id, nickname, username, old_nick, project_from, transfer_items, proof, photo_file_id, date))
    request_id = c.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_transfer_by_id(req_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT id, user_id, nickname, username, old_nick, project_from, transfer_items, proof, photo_file_id, date, status FROM transfer_requests WHERE id = ?", (req_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_transfer_status(req_id, status, admin_answer=""):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("UPDATE transfer_requests SET status = ?, admin_answer = ? WHERE id = ?", (status, admin_answer, req_id))
    conn.commit()
    conn.close()

def get_all_transfers():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT id, user_id, nickname, username, old_nick, project_from, transfer_items, proof, date, status FROM transfer_requests ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# ===================== ТЕХПОДДЕРЖКА =====================
def save_support_request(user_id, nickname, username, question):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO support_requests (user_id, nickname, username, question, status, date) VALUES (?, ?, ?, ?, 'unread', ?)",
              (user_id, nickname, username, question, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_unread_requests():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT id, user_id, nickname, username, question, date FROM support_requests WHERE status = 'unread' ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def mark_request_answered(req_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("UPDATE support_requests SET status = 'answered' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()

# ===================== ФУНКЦИИ СЕРВЕРА =====================
def get_server_info():
    if not samp_ready:
        return None
    try:
        client = SampClient(SERVER_IP, SERVER_PORT)
        info = client.get_server_info()
        if info:
            return {
                'hostname': info.hostname,
                'players': info.players,
                'max_players': info.max_players,
                'ping': 142
            }
        return None
    except:
        return None

def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return True

def get_nickname(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_nickname(user_id, nick):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date) VALUES (?, ?, ?)", 
              (user_id, nick, time.strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

# ===================== КЛАВИАТУРА =====================
def main_kb(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("🌐 Онлайн", "🔗 Полезные ссылки")
    m.row("📰 Новости сервера", "💼 Список лидеров")
    m.row("🔄 Перенос аккаунта", "🎫 Тех поддержка")
    
    if uid in ADMIN_IDS:
        m.row("📬 Непрочитанные", "📊 Статистика")
        m.row("📢 Рассылка", "📋 Помощь")
        m.row("ℹ️ Команды бота", "📥 Заявки на перенос")
    
    return m

# ===================== КОМАНДЫ =====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
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

# ===================== НОВОСТИ (ОБРАБОТЧИКИ) =====================
@bot.message_handler(func=lambda message: message.text == "📰 Новости сервера")
def handle_news_button(message):
    uid = message.chat.id
    markup, has_news = news_list_markup(uid)
    if not has_news:
        text = "📭 <b>Новостей пока нет.</b>"
        if uid in ADMIN_IDS:
            text += "\n\nНажмите «➕ Добавить новость», чтобы создать первую новость."
    else:
        text = "📰 <b>Новости сервера:</b>\nВыберите новость:"
    bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_view_"))
def news_view(call):
    news_id = int(call.data.split("_")[2])
    row = news_get_by_id(news_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Новость не найдена.")
        return
    nid, title, content, date = row
    markup = types.InlineKeyboardMarkup(row_width=2)
    if call.message.chat.id in ADMIN_IDS:
        markup.add(
            types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"news_edit_{nid}"),
            types.InlineKeyboardButton("🗑 Удалить", callback_data=f"news_del_{nid}")
        )
    markup.add(types.InlineKeyboardButton("« Назад к списку", callback_data="news_list"))
    text = f"📰 <b>{title}</b>\n\n{content}\n\n🕐 {date}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "news_list")
def news_list_back(call):
    uid = call.message.chat.id
    markup, has_news = news_list_markup(uid)
    text = "📰 <b>Новости сервера:</b>\nВыберите новость:" if has_news else "📭 <b>Новостей пока нет.</b>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "news_add")
def news_add_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    msg = bot.send_message(call.message.chat.id, "📰 Введите <b>заголовок</b> новости:", parse_mode="HTML")
    bot.register_next_step_handler(msg, news_add_title)
    bot.answer_callback_query(call.id)

def news_add_title(message):
    if message.chat.id not in ADMIN_IDS:
        return
    title = message.text.strip()
    if not title:
        bot.send_message(message.chat.id, "❌ Заголовок не может быть пустым.")
        return
    msg = bot.send_message(message.chat.id, f"✅ Заголовок: <b>{title}</b>\n\nТеперь введите <b>текст</b> новости:", parse_mode="HTML")
    bot.register_next_step_handler(msg, news_add_content, title)

def news_add_content(message, title):
    if message.chat.id not in ADMIN_IDS:
        return
    content = message.text.strip()
    if not content:
        bot.send_message(message.chat.id, "❌ Текст не может быть пустым.")
        return
    news_add(title, content)
    bot.send_message(message.chat.id, f"✅ Новость «<b>{title}</b>» добавлена!", parse_mode="HTML")
    handle_news_button(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_edit_"))
def news_edit_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data.split("_")[2])
    row = news_get_by_id(news_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Новость не найдена.")
        return
    _, old_title, old_content, _ = row
    msg = bot.send_message(call.message.chat.id,
                           f"✏️ Редактирование новости №{news_id}\n\nТекущий заголовок: <i>{old_title}</i>\n\nВведите новый заголовок (или «.» чтобы оставить):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, news_edit_title, news_id, old_title, old_content)
    bot.answer_callback_query(call.id)

def news_edit_title(message, news_id, old_title, old_content):
    if message.chat.id not in ADMIN_IDS:
        return
    new_title = old_title if message.text.strip() == "." else message.text.strip()
    msg = bot.send_message(message.chat.id,
                           f"Текущий текст:\n<i>{old_content}</i>\n\nВведите новый текст (или «.» чтобы оставить):",
                           parse_mode="HTML")
    bot.register_next_step_handler(msg, news_edit_content, news_id, new_title)

def news_edit_content(message, news_id, new_title):
    if message.chat.id not in ADMIN_IDS:
        return
    row = news_get_by_id(news_id)
    old_content = row[2] if row else ""
    new_content = old_content if message.text.strip() == "." else message.text.strip()
    news_edit(news_id, new_title, new_content)
    bot.send_message(message.chat.id, f"✅ Новость №{news_id} обновлена.", parse_mode="HTML")
    handle_news_button(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_"))
def news_delete_confirm(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data.split("_")[2])
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"news_del_yes_{news_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"news_view_{news_id}")
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Подтвердите удаление")

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_yes_"))
def news_delete_do(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data.split("_")[3])
    news_delete(news_id)
    bot.answer_callback_query(call.id, "✅ Новость удалена")
    markup, has_news = news_list_markup(call.message.chat.id)
    text = "📰 <b>Новости сервера:</b>\nВыберите новость:" if has_news else "📭 <b>Новостей пока нет.</b>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup, parse_mode="HTML")

# ===================== ПЕРЕНОС =====================
@bot.message_handler(func=lambda message: message.text == "🔄 Перенос аккаунта")
def transfer_start(message):
    uid = message.chat.id
    text = (
        "🔄 <b>Перенос аккаунтов с разных проектов!</b>\n\n"
        "📋 <b>Форма подачи заявления:</b>\n\n"
        "▫️ <b>Nick_Name:</b>\n"
        "▫️ <b>Проект с которого переносите:</b>\n"
        "▫️ <b>Что переносите:</b>\n"
        "▫️ <b>Доказательства имущества (/time):</b>\n\n"
        "✍️ Заполните данную форму и отправьте ответным сообщением!\n"
        "📸 Обязательно прикрепите скриншот доказательств с /time прямо к сообщению с текстом."
    )
    bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_kb(uid))
    msg = bot.send_message(uid, "📝 Введите данные по форме и прикрепите скриншот:")

@bot.message_handler(content_types=['text', 'photo'], func=lambda message: True)
def process_transfer_form(message):
    uid = message.chat.id
    if message.text and message.text.startswith('/'):
        return
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "📰 Новости сервера", "💼 Список лидеров",
                        "🔄 Перенос аккаунта", "🎫 Тех поддержка", "📬 Непрочитанные", "📊 Статистика",
                        "📢 Рассылка", "📋 Помощь", "ℹ️ Команды бота", "📥 Заявки на перенос"]:
        return
    nickname = get_nickname(uid) or "Неизвестно"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    text_data = message.text or ""
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    lines = text_data.split('\n')
    old_nick = ""
    project_from = ""
    transfer_items = ""
    proof = ""
    for line in lines:
        line_lower = line.lower()
        if "nick_name" in line_lower or "ник" in line_lower:
            parts = line.split(":", 1)
            old_nick = parts[1].strip() if len(parts) > 1 else line.strip()
        elif "проект" in line_lower:
            parts = line.split(":", 1)
            project_from = parts[1].strip() if len(parts) > 1 else line.strip()
        elif "что переносите" in line_lower or "переносите" in line_lower:
            parts = line.split(":", 1)
            transfer_items = parts[1].strip() if len(parts) > 1 else line.strip()
        elif "доказательства" in line_lower or "/time" in line_lower:
            parts = line.split(":", 1)
            proof = parts[1].strip() if len(parts) > 1 else line.strip()
    if not old_nick:
        old_nick = text_data[:50] if text_data else "Не указан"
    req_id = save_transfer_request(uid, nickname, username, old_nick, project_from, transfer_items, proof, photo_file_id)
    admin_text = (
        f"📥 <b>НОВАЯ ЗАЯВКА НА ПЕРЕНОС №{req_id}</b>\n\n"
        f"👤 <b>Игрок:</b> {nickname}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📱 <b>Username:</b> {username}\n\n"
        f"📋 <b>Данные заявки:</b>\n"
        f"🎮 <b>Nick_Name:</b> <code>{old_nick}</code>\n"
        f"🔄 <b>Проект:</b> {project_from or 'Не указан'}\n"
        f"📦 <b>Что переносит:</b> {transfer_items or 'Не указано'}\n"
        f"📎 <b>Доказательства:</b> {proof or 'Не указаны'}\n\n"
        f"📅 <b>Дата:</b> {time.strftime('%d.%m.%Y %H:%M')}"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"transfer_approve_{req_id}"),
        types.InlineKeyboardButton("❌ Отказать", callback_data=f"transfer_reject_{req_id}")
    )
    for admin_id in ADMIN_IDS:
        try:
            if photo_file_id:
                bot.send_photo(admin_id, photo_file_id, caption=admin_text, parse_mode="HTML", reply_markup=markup)
            else:
                bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")
    bot.send_message(uid, "✅ <b>Ваша заявка на перенос успешно отправлена!</b>\n\n📌 Администрация рассмотрит вашу заявку и ответит в ближайшее время.", parse_mode="HTML", reply_markup=main_kb(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_approve_"))
def transfer_approve(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    req_id = int(call.data.split("_")[2])
    req = get_transfer_by_id(req_id)
    if not req:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!", show_alert=True)
        return
    if req[10] != "pending":
        bot.answer_callback_query(call.id, f"⚠️ Заявка уже {req[10]}!", show_alert=True)
        return
    update_transfer_status(req_id, "approved", "Одобрена администрацией")
    user_id = req[1]
    try:
        bot.send_message(user_id, f"🎉 <b>Ваша заявка на перенос аккаунта №{req_id} ОДОБРЕНА!</b>\n\nАдминистрация проекта одобрила ваш перенос.\nОжидайте связи для завершения переноса!", parse_mode="HTML")
    except:
        pass
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    new_text = call.message.text + "\n\n🟢 <b>СТАТУС: ОДОБРЕНО</b>"
    if call.message.photo:
        bot.edit_message_caption(new_text, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    else:
        bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Заявка одобрена!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_reject_"))
def transfer_reject(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    req_id = int(call.data.split("_")[2])
    req = get_transfer_by_id(req_id)
    if not req:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!", show_alert=True)
        return
    if req[10] != "pending":
        bot.answer_callback_query(call.id, f"⚠️ Заявка уже {req[10]}!", show_alert=True)
        return
    msg = bot.send_message(admin_id, f"❌ <b>Причина отказа для заявки №{req_id}</b>\n\nВведите причину отказа (или <code>-</code>, чтобы отказать без причины):", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_reject_reason, req_id, call.message)
    bot.answer_callback_query(call.id)

def process_reject_reason(message, req_id, admin_msg):
    admin_id = message.chat.id
    reason = message.text.strip()
    if reason == "-":
        reason = "Причина не указана"
    update_transfer_status(req_id, "rejected", reason)
    req = get_transfer_by_id(req_id)
    if req:
        user_id = req[1]
        try:
            bot.send_message(user_id, f"❌ <b>Ваша заявка на перенос аккаунта №{req_id} ОТКЛОНЕНА.</b>\n\n📌 <b>Причина отказа:</b> {reason}", parse_mode="HTML")
        except:
            pass
    bot.edit_message_reply_markup(admin_msg.chat.id, admin_msg.message_id, reply_markup=None)
    new_text = admin_msg.text + f"\n\n🔴 <b>СТАТУС: ОТКАЗАНО</b>\n📌 Причина: {reason}"
    if admin_msg.photo:
        bot.edit_message_caption(new_text, admin_msg.chat.id, admin_msg.message_id, parse_mode="HTML")
    else:
        bot.edit_message_text(new_text, admin_msg.chat.id, admin_msg.message_id, parse_mode="HTML")
    bot.send_message(admin_id, f"✅ Заявка №{req_id} отклонена.")

@bot.message_handler(func=lambda message: message.text == "📥 Заявки на перенос")
def show_transfer_requests(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return
    transfers = get_all_transfers()
    if not transfers:
        bot.send_message(uid, "📭 <b>Заявок на перенос нет.</b>", parse_mode="HTML", reply_markup=main_kb(uid))
        return
    pending = [t for t in transfers if t[9] == "pending"]
    approved = [t for t in transfers if t[9] == "approved"]
    rejected = [t for t in transfers if t[9] == "rejected"]
    text = (
        f"📊 <b>Все заявки на перенос:</b>\n\n"
        f"⏳ В ожидании: <b>{len(pending)}</b>\n"
        f"✅ Одобрено: <b>{len(approved)}</b>\n"
        f"❌ Отказано: <b>{len(rejected)}</b>\n"
        f"📋 Всего: <b>{len(transfers)}</b>\n\n"
        f"📋 <b>Последние заявки:</b>\n"
    )
    for t in transfers[:5]:
        status_emoji = "⏳" if t[9] == "pending" else "✅" if t[9] == "approved" else "❌"
        text += f"{status_emoji} №{t[0]} | {t[2]} | {t[9]}\n"
    bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== ТЕХПОДДЕРЖКА =====================
@bot.message_handler(func=lambda message: message.text == "🎫 Тех поддержка")
def support_start(message):
    uid = message.chat.id
    if uid in ADMIN_IDS:
        requests = get_unread_requests()
        if not requests:
            bot.send_message(uid, "✅ <b>Непрочитанных обращений нет.</b>", parse_mode="HTML")
            return
        for req in requests:
            req_id, user_id, nickname, username, question, date = req
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💬 Ответить", callback_data=f"support_ans_{req_id}_{user_id}"))
            text = f"🔔 <b>Обращение №{req_id}</b>\n\n👤 {username}\n🎮 {nickname}\n📝 {question}\n🕐 {date}"
            bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")
    else:
        msg = bot.send_message(uid, "✍️ <b>Опишите вашу проблему или задайте вопрос:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_support_question)

def process_support_question(message):
    uid = message.chat.id
    if message.text in ["🌐 Онлайн", "🔗 Полезные ссылки", "📰 Новости сервера", "💼 Список лидеров",
                        "🔄 Перенос аккаунта", "🎫 Тех поддержка", "📬 Непрочитанные", "📊 Статистика",
                        "📢 Рассылка", "📋 Помощь", "ℹ️ Команды бота", "📥 Заявки на перенос"]:
        bot.send_message(uid, "❌ Обращение отменено.")
        return
    nickname = get_nickname(uid) or "Без никнейма"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    req_id = save_support_request(uid, nickname, username, message.text)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 Ответить", callback_data=f"support_ans_{req_id}_{uid}"))
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, f"🔔 <b>Новое обращение №{req_id}!</b>\n\n👤 {username}\n🎮 {nickname}\n📝 {message.text}", reply_markup=markup, parse_mode="HTML")
        except:
            pass
    bot.send_message(uid, "✅ <b>Ваш вопрос отправлен администрации!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("support_ans_"))
def support_answer(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    msg = bot.send_message(call.message.chat.id, f"✍️ <b>Введите ответ для обращения №{req_id}:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_support_answer, req_id, user_id, call.message)
    bot.answer_callback_query(call.id)

def process_support_answer(message, req_id, user_id, admin_msg):
    answer = message.text
    try:
        bot.send_message(user_id, f"✉️ <b>Ответ от администрации на обращение №{req_id}:</b>\n\n💬 {answer}", parse_mode="HTML")
    except:
        pass
    mark_request_answered(req_id)
    bot.edit_message_reply_markup(admin_msg.chat.id, admin_msg.message_id, reply_markup=None)
    bot.send_message(message.chat.id, f"✅ Ответ на обращение №{req_id} отправлен.")

# ===================== ОСНОВНЫЕ КНОПКИ =====================
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
        bot.send_message(uid, "⏳ Опрашиваю сервер...")
        data = get_server_info()
        if data:
            msg = f"🎮 <b>{data['hostname']}</b>\n\n🌐 <b>IP:</b> <code>{SERVER_IP}:{SERVER_PORT}</code>\n👥 <b>Онлайн:</b> {data['players']} / {data['max_players']}\n⚡ <b>Пинг:</b> {data['ping']} мс\n\n🟢 Статус: Работает"
        else:
            msg = "❌ <b>Сервер недоступен.</b>"
        bot.send_message(uid, msg, parse_mode="HTML", reply_markup=main_kb(uid))
    
    # ===== ПОЛЕЗНЫЕ ССЫЛКИ =====
    elif text == "🔗 Полезные ссылки":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Telegram Канал", url="https://t.me/santropetrilogybot_news"),
            types.InlineKeyboardButton("💬 Telegram Чат", url="https://t.me/santropetrilogy_chat"),
            types.InlineKeyboardButton("📱 Группа ВКонтакте", url="https://vk.com/santropetrilogy")
        )
        bot.send_message(uid, "🔗 <b>Официальные ресурсы проекта:</b>", reply_markup=markup, parse_mode="HTML")
    
    # ===== ЛИДЕРЫ =====
    elif text == "💼 Список лидеров":
        leaders = get_all_leaders()
        if not leaders:
            bot.send_message(uid, "📭 <b>Список лидеров пуст.</b>", parse_mode="HTML", reply_markup=main_kb(uid))
            return
        leaders_text = "💼 <b>Список лидеров организаций:</b>\n\n"
        for fraction, nickname, username, date in leaders:
            leaders_text += f"🏢 <b>{fraction}</b>\n👤 Лидер: <code>{nickname}</code>\n"
            if username:
                leaders_text += f"📱 Контакт: {username}\n"
            leaders_text += f"📅 Назначен: {date}\n\n"
        bot.send_message(uid, leaders_text, parse_mode="HTML", reply_markup=main_kb(uid))
    
    # ===== АДМИН-КНОПКИ =====
    elif uid in ADMIN_IDS:
        if text == "📬 Непрочитанные":
            requests = get_unread_requests()
            if not requests:
                bot.send_message(uid, "✅ <b>Непрочитанных обращений нет.</b>", parse_mode="HTML")
                return
            for req in requests:
                req_id, user_id, nickname, username, question, date = req
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💬 Ответить", callback_data=f"support_ans_{req_id}_{user_id}"))
                bot.send_message(uid, f"🔔 <b>Обращение №{req_id}</b>\n\n👤 {username}\n🎮 {nickname}\n📝 {question}\n🕐 {date}", reply_markup=markup, parse_mode="HTML")
        
        elif text == "📊 Статистика":
            conn = sqlite3.connect("bot_stats.db")
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM transfer_requests WHERE status = 'pending'")
            pending = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM admins")
            admins = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM news")
            news_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
            support_unread = c.fetchone()[0]
            conn.close()
            admin_nick = get_nickname(uid) or "Администратор"
            text = (
                f"📊 <b>Статистика бота</b>\n\n"
                f"👤 Пользователей: {users}\n"
                f"👑 Администраторов: {admins}\n"
                f"📥 Заявок на перенос: {pending}\n"
                f"📰 Новостей: {news_count}\n"
                f"📬 Обращений в поддержку: {support_unread}\n\n"
                f"🆔 Ваш ID: <code>{uid}</code>\n"
                f"🎮 Ваш ник: <code>{admin_nick}</code>"
            )
            bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_kb(uid))
        
        elif text == "📢 Рассылка":
            msg = bot.send_message(uid, "📨 <b>Введите текст для рассылки:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_broadcast)
        
        elif text == "📋 Помощь":
            help_text = (
                "📖 <b>Команды бота:</b>\n\n"
                "/start — Главное меню\n"
                "/ник — Сменить никнейм\n"
                "/стата — Профиль игрока\n\n"
                "👑 <b>Админ-команды:</b>\n"
                "/админы — Список администраторов\n"
                "/поиск — Поиск игрока\n\n"
                "📌 <b>Кнопки:</b>\n"
                "🌐 Онлайн — Статус сервера\n"
                "🔗 Полезные ссылки — Ресурсы\n"
                "📰 Новости сервера — Управление новостями\n"
                "💼 Список лидеров — Лидеры организаций\n"
                "🔄 Перенос аккаунта — Заявка на перенос\n"
                "🎫 Тех поддержка — Поддержка\n"
                "📬 Непрочитанные — Обращения\n"
                "📊 Статистика — Статистика бота\n"
                "📢 Рассылка — Рассылка\n"
                "📥 Заявки на перенос — Все заявки\n"
                "ℹ️ Команды бота — Этот список"
            )
            bot.send_message(uid, help_text, parse_mode="HTML", reply_markup=main_kb(uid))
        
        elif text == "ℹ️ Команды бота":
            commands_text = (
                "📖 <b>Команды бота (для администраторов):</b>\n\n"
                "👤 <b>Управление пользователями</b>\n"
                "/админ @username [уровень] — выдать права админа (1-3)\n"
                "/разадмин @username — снять права админа\n"
                "/должность ID Должность — изменить должность игрока\n\n"
                "🔍 <b>Поиск</b>\n"
                "/поиск Никнейм — найти игрока в базе\n\n"
                "📋 <b>Профиль</b>\n"
                "/стата — посмотреть свой профиль\n"
                "/ник — сменить никнейм\n\n"
                "📊 <b>Статистика и заявки</b>\n"
                "/админы — список администраторов\n"
                "/лог — скачать лог техподдержки\n"
                "/online — статус сервера\n\n"
                "📌 <b>Кнопки</b>\n"
                "🌐 Онлайн — статус SA:MP сервера\n"
                "🔗 Полезные ссылки — ресурсы проекта\n"
                "📰 Новости сервера — управление новостями\n"
                "💼 Список лидеров — лидеры организаций\n"
                "🔄 Перенос аккаунта — заявка на перенос\n"
                "🎫 Тех поддержка — обращения\n"
                "📬 Непрочитанные — новые обращения\n"
                "📊 Статистика — статистика бота\n"
                "📢 Рассылка — отправить сообщение всем\n"
                "📋 Помощь — вся справка\n"
                "📥 Заявки на перенос — все заявки\n"
                "ℹ️ Команды бота — этот список"
            )
            bot.send_message(uid, commands_text, parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== РАССЫЛКА =====================
def process_broadcast(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return
    text = message.text
    users = get_all_users()
    if not users:
        bot.send_message(uid, "❌ Нет пользователей для рассылки.")
        return
    success = 0
    for user_id in users:
        try:
            bot.send_message(user_id, text, parse_mode="HTML")
            success += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(uid, f"✅ <b>Рассылка завершена!</b>\n\nДоставлено: {success} из {len(users)}", parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    keep_alive()
    print("✅ Бот запущен со всеми функциями!")
    bot.polling(none_stop=True)
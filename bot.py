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
ADMIN_IDS = [709672781, 5939366373, 1066139847]

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TOKEN)

# ===================== БАЗА ДАННЫХ =====================
def init_db():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, join_date TEXT, username TEXT)")
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
        date TEXT
    )""")
    # Добавляем админов по умолчанию
    for aid in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, 3, 'Главный администратор')", (aid,))
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

# ===================== АДМИНЫ (БД) =====================
def get_all_admins():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT admins.user_id, admins.level, admins.position, users.nickname, users.username FROM admins LEFT JOIN users ON admins.user_id = users.user_id ORDER BY admins.level DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def add_admin_db(user_id, level, position="Администратор"):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, ?, ?)", (user_id, level, position))
    c.execute("UPDATE admins SET level = ?, position = ? WHERE user_id = ?", (level, position, user_id))
    conn.commit()
    conn.close()

def remove_admin_db(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_admin_level(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ===================== ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ =====================
def get_nickname(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_username(user_id):
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
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

def update_user_info(user_id, username):
    conn = sqlite3.connect("bot_stats.db")
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
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_unread_count():
    conn = sqlite3.connect("bot_stats.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
    count = c.fetchone()[0]
    conn.close()
    return count

# ===================== КЛАВИАТУРА =====================
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

# ===================== КОМАНДА /ADMLIST =====================
@bot.message_handler(commands=['admlist'])
def admlist_command(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        bot.send_message(uid, "❌ Только для администраторов!")
        return
    
    admins = get_all_admins()
    if not admins:
        bot.send_message(uid, "📭 Список администраторов пуст.")
        return
    
    level_names = {
        1: "🟢 Модератор",
        2: "🟡 Старший модератор",
        3: "🔴 Главный администратор"
    }
    
    text = "👑 <b>Список администраторов бота:</b>\n\n"
    for admin in admins:
        user_id, level, position, nickname, username = admin
        level_name = level_names.get(level, f"Уровень {level}")
        nick = nickname or "Не указан"
        user = f"@{username}" if username else "Нет юзернейма"
        text += f"👤 <b>{nick}</b>\n"
        text += f"   🆔 ID: <code>{user_id}</code>\n"
        text += f"   📊 Уровень: {level_name}\n"
        text += f"   📋 Должность: {position}\n"
        text += f"   📱 Юзернейм: {user}\n\n"
    
    bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== НОВОСТИ (ДЛЯ АДМИНОВ) =====================
def news_admin_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="news_add"),
        types.InlineKeyboardButton("✏️ Редактировать", callback_data="news_edit_list"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data="news_del_list")
    )
    return markup

@bot.message_handler(func=lambda message: message.text == "📰 Новости сервера")
def handle_news_button(message):
    uid = message.chat.id
    if uid in ADMIN_IDS:
        bot.send_message(uid, "📰 <b>Управление новостями:</b>", reply_markup=news_admin_markup(), parse_mode="HTML")
    else:
        news = news_get_all()
        if not news:
            bot.send_message(uid, "📭 Новостей пока нет.", reply_markup=main_kb(uid))
            return
        text = "📰 <b>Новости сервера:</b>\n\n"
        for nid, title, date in news:
            text += f"▪️ <b>{title}</b>  [{date}]\n"
        bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_kb(uid))

# ----- ДОБАВЛЕНИЕ -----
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

# ----- РЕДАКТИРОВАНИЕ (СПИСОК) -----
@bot.callback_query_handler(func=lambda call: call.data == "news_edit_list")
def news_edit_list(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news = news_get_all()
    if not news:
        bot.send_message(call.message.chat.id, "📭 Новостей для редактирования нет.")
        bot.answer_callback_query(call.id)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for nid, title, date in news:
        markup.add(types.InlineKeyboardButton(f"✏️ {title}  [{date}]", callback_data=f"news_edit_{nid}"))
    bot.send_message(call.message.chat.id, "📰 Выберите новость для редактирования:", reply_markup=markup)
    bot.answer_callback_query(call.id)

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

# ----- УДАЛЕНИЕ (СПИСОК) -----
@bot.callback_query_handler(func=lambda call: call.data == "news_del_list")
def news_del_list(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news = news_get_all()
    if not news:
        bot.send_message(call.message.chat.id, "📭 Новостей для удаления нет.")
        bot.answer_callback_query(call.id)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for nid, title, date in news:
        markup.add(types.InlineKeyboardButton(f"🗑 {title}  [{date}]", callback_data=f"news_del_{nid}"))
    bot.send_message(call.message.chat.id, "📰 Выберите новость для удаления:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_"))
def news_delete_confirm(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data.split("_")[2])
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"news_del_yes_{news_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="news_edit_list")
    )
    bot.edit_message_text(f"🗑 <b>Удалить новость №{news_id}?</b>", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_yes_"))
def news_delete_do(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа.")
        return
    news_id = int(call.data.split("_")[3])
    news_delete(news_id)
    bot.answer_callback_query(call.id, "✅ Новость удалена")
    bot.edit_message_text(f"✅ Новость №{news_id} удалена.", call.message.chat.id, call.message.message_id)

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

    # ----- ОНЛАЙН -----
    if text == "🌐 Онлайн":
        bot.send_message(uid, get_online(), reply_markup=main_kb(uid))

    # ----- ССЫЛКИ -----
    elif text == "🔗 Полезные ссылки":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Канал", url=CHANNEL_URL),
            types.InlineKeyboardButton("💬 Чат", url="https://t.me/santropetrilogy_chat"),
            types.InlineKeyboardButton("📱 ВК", url="https://vk.com/santropetrilogy")
        )
        bot.send_message(uid, "🔗 Ресурсы:", reply_markup=markup)

    # ----- ЛИДЕРЫ -----
    elif text == "💼 Список лидеров":
        bot.send_message(uid, "🏆 Лидеров пока нет.", reply_markup=main_kb(uid))

    # ----- ПЕРЕНОС -----
    elif text == "🔄 Перенос аккаунта":
        bot.send_message(uid, "📝 Напишите данные для переноса администратору.", reply_markup=main_kb(uid))

    # ----- ТЕХПОДДЕРЖКА -----
    elif text == "🎫 Тех поддержка":
        bot.send_message(uid, "✍️ Напишите ваш вопрос администратору.", reply_markup=main_kb(uid))

    # ----- АДМИН-КНОПКИ -----
    elif uid in ADMIN_IDS:
        if text == "📬 Непрочитанные":
            bot.send_message(uid, f"📭 Непрочитанных заявок: {get_unread_count()}", reply_markup=main_kb(uid))

        elif text == "📊 Статистика":
            conn = sqlite3.connect("bot_stats.db")
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM news")
            news_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM admins")
            admins_count = c.fetchone()[0]
            conn.close()
            bot.send_message(uid, f"📊 <b>Статистика:</b>\n\n👤 Пользователей: {users}\n👑 Администраторов: {admins_count}\n📰 Новостей: {news_count}", parse_mode="HTML", reply_markup=main_kb(uid))

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
                "🎫 Тех поддержка — ответить на обращения игроков\n"
                "📬 Непрочитанные — необработанные обращения\n"
                "📊 Статистика — кол-во пользователей и обращений\n"
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
        bot.send_message(uid, "❌ Нет пользователей для рассылки.")
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
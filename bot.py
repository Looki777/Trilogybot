import os
import time
import sqlite3
import socket
import telebot
from telebot import types
from keep_alive import keep_alive

# ===================== ПЕРЕМЕННЫЕ И НАСТРОЙКИ =====================
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

# ===================== БАЗА ДАННЫХ =====================
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

# ===================== ВСПАТАТЕЛЬНЫЕ ФУНКЦИИ =====================
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

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

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

# ===================== РАБОТА С ЛИДЕРАМИ =====================
def get_all_leaders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, fraction, nickname, username, date FROM leaders ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def add_leader(fraction, nickname, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y")
    username = username if username.startswith("@") or username == "Не указан" else f"@{username}"
    c.execute("INSERT INTO leaders (fraction, nickname, username, date) VALUES (?, ?, ?, ?)", (fraction, nickname, username, date))
    conn.commit()
    conn.close()

def remove_leader(leader_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM leaders WHERE id = ?", (leader_id,))
    conn.commit()
    conn.close()

# ===================== НОВОСТИ =====================
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
    c.execute("INSERT INTO news (title, content, author, date) VALUES (?, ?, ?, ?)", (title, content, "Администрация", date))
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

# ===================== ОНЛАЙН СЕРВЕРА (SA:MP QUERY PROTOCOL) =====================
def get_online():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.5)
        
        # Формирование стандартного пакета SA:MP Query ('i' - Information)
        ip_parts = [int(p) for p in SERVER_IP.split(".")]
        packet = bytearray(b"SAMP")
        packet.extend(ip_parts)
        packet.append(SERVER_PORT & 0xFF)
        packet.append((SERVER_PORT >> 8) & 0xFF)
        packet.append(ord('i'))

        sock.sendto(packet, (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(4096)
        sock.close()

        if len(data) < 11:
            return "❌ <b>Ошибка: Сервер вернул некорректные данные.</b>"

        offset = 11
        password = data[offset]
        offset += 1

        players = int.from_bytes(data[offset:offset+2], byteorder='little')
        offset += 2

        max_players = int.from_bytes(data[offset:offset+2], byteorder='little')
        offset += 2

        # Название сервера (Hostname)
        hn_len = int.from_bytes(data[offset:offset+4], byteorder='little')
        offset += 4
        hostname = data[offset:offset+hn_len].decode('cp1251', errors='ignore')
        offset += hn_len

        # Мод (Gamemode)
        gm_len = int.from_bytes(data[offset:offset+4], byteorder='little')
        offset += 4
        gamemode = data[offset:offset+gm_len].decode('cp1251', errors='ignore')
        offset += gm_len

        # Язык (Language)
        lang_len = int.from_bytes(data[offset:offset+4], byteorder='little')
        offset += 4
        language = data[offset:offset+lang_len].decode('cp1251', errors='ignore')

        status_icon = "🟢" if players > 0 else "🟡"

        return (
            f"🎮 <b>{hostname}</b>\n"
            f"───────────────\n"
            f"🌐 <b>IP сервера:</b> <code>{SERVER_IP}:{SERVER_PORT}</code>\n"
            f"👥 <b>Игровой онлайн:</b> <code>{players} / {max_players}</code>\n"
            f"🎯 <b>Игровой режим:</b> <code>{gamemode}</code>\n"
            f"🌍 <b>Локация:</b> <code>{language}</code>\n\n"
            f"{status_icon} <b>Статус:</b> <code>Работает</code>"
        )

    except socket.timeout:
        return f"❌ <b>Сервер недоступен</b>\n\n🌐 IP: <code>{SERVER_IP}:{SERVER_PORT}</code>\n⚠️ Превышено время ожидания ответа."
    except Exception as e:
        return f"❌ <b>Ошибка при запросе онлайна:</b> {e}"

# ===================== ДОЛЖНОСТИ =====================
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
        bot.send_message(uid, "❌ <b>Подпишитесь на наш канал для доступа к боту!</b>", reply_markup=markup, parse_mode="HTML")
        return
        
    nick = get_nickname(uid)
    if not nick:
        msg = bot.send_message(uid, "👋 <b>Добро пожаловать!</b>\n\nВведите ваш игровой <b>Nick_Name</b>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_nick)
    else:
        bot.send_message(uid, f"👋 Привет, <b>{nick}</b>! Выберите нужный раздел:", reply_markup=main_kb(uid), parse_mode="HTML")

def save_nick(message):
    nick = message.text.strip()
    if len(nick) < 3:
        msg = bot.send_message(message.chat.id, "❌ Ник слишком короткий! Минимальная длина — 3 символа.\nВведите ник еще раз:")
        bot.register_next_step_handler(msg, save_nick)
        return
    set_nickname(message.chat.id, nick)
    bot.send_message(message.chat.id, f"✅ Никнейм <b>{nick}</b> успешно сохранен!", reply_markup=main_kb(message.chat.id), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub(call):
    if is_subscribed(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ <b>Подписка подтверждена!</b> Нажмите /start для входа.", parse_mode="HTML")
    else:
        bot.answer_callback_query(call.id, "❌ Вы все еще не подписаны на канал!", show_alert=True)

# ===================== СПИСОК И УПРАВЛЕНИЕ ЛИДЕРАМИ =====================
def show_leaders_message(chat_id, user_id):
    leaders = get_all_leaders()
    
    text = "💼 <b>Список лидеров организаций</b>\n───────────────\n\n"
    if not leaders:
        text += "📭 <i>Список лидеров в данный момент пуст.</i>\n"
    else:
        for lid, fraction, nick, username, date in leaders:
            user_str = f"({username})" if username and username != "Не указан" else ""
            text += f"🏛 <b>{fraction}</b>\n👤 <b>Лидер:</b> {nick} {user_str}\n📅 <b>Назначен:</b> {date}\n\n"

    markup = None
    if user_id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить лидера", callback_data="leader_add"),
            types.InlineKeyboardButton("🗑 Удалить лидера", callback_data="leader_del")
        )

    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "leader_add")
def leader_add_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!", show_alert=True)
        return
    
    msg = bot.send_message(call.message.chat.id, "📝 <b>Шаг 1/3:</b> Введите название организации / фракции (например: <code>LSPD</code> или <code>Правительство</code>):", parse_mode="HTML")
    bot.register_next_step_handler(msg, leader_add_fraction)
    bot.answer_callback_query(call.id)

def leader_add_fraction(message):
    fraction = message.text.strip()
    msg = bot.send_message(message.chat.id, f"✅ Фракция: <b>{fraction}</b>\n\n📝 <b>Шаг 2/3:</b> Введите игровой Nick_Name лидера:", parse_mode="HTML")
    bot.register_next_step_handler(msg, leader_add_nick, fraction)

def leader_add_nick(message, fraction):
    nick = message.text.strip()
    msg = bot.send_message(message.chat.id, f"✅ Ник: <b>{nick}</b>\n\n📝 <b>Шаг 3/3:</b> Введите Telegram юзернейм лидера (например: <code>@username</code> или отправьте <code>-</code> если отсутствует):", parse_mode="HTML")
    bot.register_next_step_handler(msg, leader_add_username, fraction, nick)

def leader_add_username(message, fraction, nick):
    username = message.text.strip()
    if username == "-":
        username = "Не указан"
    
    add_leader(fraction, nick, username)
    bot.send_message(message.chat.id, f"🎉 <b>Лидер успешно добавлен!</b>\n\n🏛 <b>Фракция:</b> {fraction}\n👤 <b>Ник:</b> {nick}\n📱 <b>Telegram:</b> {username}", parse_mode="HTML", reply_markup=main_kb(message.chat.id))

@bot.callback_query_handler(func=lambda call: call.data == "leader_del")
def leader_del_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!", show_alert=True)
        return

    leaders = get_all_leaders()
    if not leaders:
        bot.send_message(call.message.chat.id, "📭 Список лидеров пуст. Некого удалять.")
        bot.answer_callback_query(call.id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for lid, fraction, nick, username, date in leaders:
        markup.add(types.InlineKeyboardButton(f"🗑 {fraction} — {nick}", callback_data=f"ldel_{lid}"))

    bot.send_message(call.message.chat.id, "<b>Выберите лидера для удаления:</b>", reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ldel_"))
def leader_del_confirm(call):
    if call.message.chat.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!", show_alert=True)
        return

    lid = int(call.data.split("_")[1])
    remove_leader(lid)
    bot.answer_callback_query(call.id, "✅ Лидер успешно удален!", show_alert=True)
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===================== ДОЛЖНОСТИ =====================
@bot.message_handler(commands=['должность'])
def position_cmd(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        bot.send_message(uid, "❌ У вас нет прав для выполнения этой команды!")
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(uid, "❌ <b>Неверный формат!</b>\n\n📋 <b>Использование:</b>\n<code>/должность @username Должность</code>\n\n📌 <b>Пример:</b>\n<code>/должность @john_doe Модератор</code>", parse_mode="HTML")
            return
        username = parts[1].strip()
        new_position = parts[2].strip()
        if new_position not in AVAILABLE_POSITIONS:
            bot.send_message(uid, f"❌ <b>Должность «{new_position}» не найдена!</b>\n\nВведите <code>/должности</code> для списка всех доступных должностей.", parse_mode="HTML")
            return
        user_data = get_user_by_username(username)
        if not user_data:
            bot.send_message(uid, f"❌ <b>Пользователь {username} не найден в базе данных!</b>", parse_mode="HTML")
            return
        target_id, target_nick, current_pos = user_data
        set_position(target_id, new_position)
        bot.send_message(uid, f"✅ <b>Должность успешно изменена!</b>\n\n👤 <b>Игрок:</b> {target_nick}\n📱 <b>Юзернейм:</b> {username}\n📋 <b>Новая должность:</b> {new_position}", parse_mode="HTML")
        try:
            bot.send_message(target_id, f"📋 <b>Ваша должность обновлена!</b>\n\n📌 <b>Новая должность:</b> {new_position}", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        bot.send_message(uid, f"❌ <b>Ошибка обработки команды:</b> {e}")

@bot.message_handler(commands=['должности'])
def positions_list_cmd(message):
    if message.chat.id not in ADMIN_IDS:
        return
    bot.send_message(message.chat.id, get_positions_list(), parse_mode="HTML")

@bot.message_handler(commands=['admlist'])
def admlist_cmd(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return
    admins = get_all_admins()
    if not admins:
        bot.send_message(uid, "📭 Список администраторов пуст.")
        return
    text = "👑 <b>Список администраторов проекта:</b>\n───────────────\n\n"
    for user_id, position in admins:
        nick = get_nickname(user_id) or "Не указан"
        username = get_username(user_id) or "Нет"
        text += f"👤 <b>{nick}</b> (@{username})\n   📋 Должность: <code>{position}</code>\n\n"
    bot.send_message(uid, text, parse_mode="HTML")

@bot.message_handler(commands=['стата'])
def stata_cmd(message):
    uid = message.chat.id
    if message.from_user.username:
        update_user_info(uid, message.from_user.username)
    nick = get_nickname(uid)
    if not nick:
        bot.send_message(uid, "❌ Сначала авторизуйтесь через /start")
        return
    position = get_position(uid)
    level = get_admin_level(uid) or get_level(uid) or 0
    username = get_username(uid) or "Отсутствует"
    text = f"📊 <b>Ваш профиль</b>\n───────────────\n🎮 <b>Никнейм:</b> {nick}\n🆔 <b>ID:</b> <code>{uid}</code>\n📱 <b>Юзернейм:</b> @{username}\n🎖️ <b>Должность:</b> {position}"
    bot.send_message(uid, text, parse_mode="HTML")

@bot.message_handler(commands=['ник'])
def nick_cmd(message):
    uid = message.chat.id
    msg = bot.send_message(uid, "✍️ Введите ваш новый Nick_Name:")
    bot.register_next_step_handler(msg, change_nick)

def change_nick(message):
    nick = message.text.strip()
    if len(nick) < 3:
        bot.send_message(message.chat.id, "❌ Никнейм должен быть от 3 символов.")
        return
    set_nickname(message.chat.id, nick)
    bot.send_message(message.chat.id, f"✅ Никнейм успешно изменен на <b>{nick}</b>!", parse_mode="HTML")

# ===================== ТЕХПОДДЕРЖКА =====================
@bot.message_handler(func=lambda message: message.text == "🎫 Тех поддержка")
def support_start(message):
    uid = message.chat.id
    msg = bot.send_message(uid, "✍️ <b>Опишите вашу проблему или вопрос.</b>\nАдминистрация ответит вам в ближайшее время.", parse_mode="HTML")
    bot.register_next_step_handler(msg, support_send)

def support_send(message):
    uid = message.chat.id
    question = message.text.strip() if message.text else ""
    
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

    bot.send_message(uid, f"✅ <b>Ваше обращение №{req_id} отправлено администрации!</b>", reply_markup=main_kb(uid), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("supp_reply_"))
def support_reply_start(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    
    msg = bot.send_message(admin_id, f"✍️ Введите текст ответа на тикет №{req_id}:")
    bot.register_next_step_handler(msg, support_reply_send, req_id, user_id, call.message)
    bot.answer_callback_query(call.id)

def support_reply_send(message, req_id, user_id, admin_msg):
    admin_id = message.chat.id
    reply_text = message.text.strip()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE support_requests SET status = 'answered', admin_reply = ? WHERE id = ?", (reply_text, req_id))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(user_id, f"📩 <b>Ответ администрации на ваше обращение №{req_id}:</b>\n\n{reply_text}", parse_mode="HTML")
        bot.send_message(admin_id, "✅ Ответ успешно доставлен игроку!")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Не удалось отправить ответ игроку: {e}")

# ===================== НЕПРОЧИТАННЫЕ ТИКЕТЫ =====================
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
        bot.send_message(uid, "📭 Непрочитанных обращений нет.", reply_markup=main_kb(uid))
        return

    text = "📬 <b>Список открытых обращений:</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for req_id, nick, q, date in rows:
        short_q = q[:25] + "..." if len(q) > 25 else q
        markup.add(types.InlineKeyboardButton(f"#{req_id} | {nick} — {short_q}", callback_data=f"supp_view_{req_id}"))

    bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("supp_view_"))
def support_view(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
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
        f"📋 <b>Заявка №{req_id}</b>\n───────────────\n"
        f"👤 <b>Игрок:</b> {nick}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📱 <b>Юзернейм:</b> {username}\n"
        f"📅 <b>Дата:</b> {date}\n\n"
        f"<b>Вопрос:</b>\n{question}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 Ответить", callback_data=f"supp_reply_{req_id}_{user_id}"))
    
    bot.edit_message_text(text, admin_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# ===================== ПЕРЕНОС АККАУНТОВ =====================
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
        bot.send_message(uid, "❌ <b>Ошибка:</b> Заполните форму и прикрепите доказательства!")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("""INSERT INTO transfer_requests (user_id, nickname, username, text_data, photo_file_id, status, date) VALUES (?, ?, ?, ?, ?, 'pending', ?)""", (uid, nickname, username, text_data, photo_file_id, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    
    admin_text = f"📥 <b>ЗАЯВКА НА ПЕРЕНОС №{req_id}</b>\n\n👤 <b>Игрок:</b> {nickname}\n🆔 <b>ID:</b> <code>{uid}</code>\n📱 <b>Юзернейм:</b> {username}\n\n📋 <b>Данные:</b>\n{text_data}\n\n📅 <b>Дата:</b> {date}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"trans_app_{req_id}_{uid}"), types.InlineKeyboardButton("❌ Отказать", callback_data=f"trans_rej_{req_id}_{uid}"))
    
    for admin_id in ADMIN_IDS:
        try:
            if photo_file_id:
                bot.send_photo(admin_id, photo_file_id, caption=admin_text, reply_markup=markup, parse_mode="HTML")
            else:
                bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode="HTML")
        except:
            pass
            
    bot.send_message(uid, f"✅ <b>Заявка №{req_id} отправлена на рассмотрение!</b>", parse_mode="HTML", reply_markup=main_kb(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("trans_app_"))
def transfer_approve(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
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
        bot.send_message(user_id, f"🎉 <b>Ваша заявка на перенос №{req_id} ОДОБРЕНА!</b>\nС вами свяжется администрация.", parse_mode="HTML")
    except:
        pass
        
    bot.edit_message_reply_markup(admin_id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Заявка одобрена!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("trans_rej_"))
def transfer_reject(call):
    admin_id = call.message.chat.id
    if admin_id not in ADMIN_IDS:
        return
    parts = call.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    
    msg = bot.send_message(admin_id, f"❌ Укажите причину отказа для заявки №{req_id}:")
    bot.register_next_step_handler(msg, process_transfer_reject, req_id, user_id)
    bot.answer_callback_query(call.id)

def process_transfer_reject(message, req_id, user_id):
    reason = message.text.strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE transfer_requests SET status = 'rejected', admin_answer = ? WHERE id = ?", (reason, req_id))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(user_id, f"❌ <b>Ваша заявка на перенос №{req_id} ОТКЛОНЕНА.</b>\nПричина: {reason}", parse_mode="HTML")
    except:
        pass
    bot.send_message(message.chat.id, f"✅ Отказ отправлен по заявке №{req_id}.")

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
            bot.send_message(uid, "📭 Новостей пока нет.")
            return
        text = "📰 <b>Свежие новости сервера:</b>\n───────────────\n\n"
        for nid, title, date in news:
            text += f"📌 <b>{title}</b> [{date}]\n"
        bot.send_message(uid, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "news_add")
def news_add_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        return
    msg = bot.send_message(call.message.chat.id, "📰 Введите заголовок новости:")
    bot.register_next_step_handler(msg, news_add_title)
    bot.answer_callback_query(call.id)

def news_add_title(message):
    title = message.text.strip()
    msg = bot.send_message(message.chat.id, f"✅ Заголовок: <b>{title}</b>\nТеперь введите основной текст новости:", parse_mode="HTML")
    bot.register_next_step_handler(msg, news_add_content, title)

def news_add_content(message, title):
    content = message.text.strip()
    news_add(title, content)
    bot.send_message(message.chat.id, "✅ Новость успешно опубликована!")

@bot.callback_query_handler(func=lambda call: call.data == "news_del")
def news_del_start(call):
    if call.message.chat.id not in ADMIN_IDS:
        return
    news = news_get_all()
    if not news:
        bot.send_message(call.message.chat.id, "📭 Новостей нет.")
        bot.answer_callback_query(call.id)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for nid, title, date in news:
        markup.add(types.InlineKeyboardButton(f"🗑 {title}", callback_data=f"news_del_{nid}"))
    bot.send_message(call.message.chat.id, "Выберите новость для удаления:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("news_del_"))
def news_del_do(call):
    if call.message.chat.id not in ADMIN_IDS:
        return
    nid = int(call.data.split("_")[2])
    news_delete(nid)
    bot.answer_callback_query(call.id, "✅ Новость удалена")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===================== ОБРАБОТКА ОСНОВНЫХ КНОПОК =====================
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
        bot.send_message(uid, "❌ <b>Подпишитесь на канал для использования бота!</b>", reply_markup=markup, parse_mode="HTML")
        return

    if text == "🌐 Онлайн":
        bot.send_message(uid, get_online(), parse_mode="HTML", reply_markup=main_kb(uid))

    elif text == "🔗 Полезные ссылки":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Telegram-канал проекта", url="https://t.me/santrope_trilogyrp"),
            types.InlineKeyboardButton("🌐 Официальный форум", url="https://wh32893.web3.maze-tech.ru/index.php"),
            types.InlineKeyboardButton("📱 Группа ВКонтакте", url="https://vk.com/santropetrilogy")
        )
        text_msg = (
            "🔗 <b>Официальные ресурсы проекта SanTrope RP</b>\n───────────────\n\n"
            "📢 <b>Telegram-канал</b>\nГлавные новости, анонсы и обновления проекта.\n\n"
            "🌐 <b>Форум проекта</b>\nПравила сервера, заявки на лидерство, жалобы и технический раздел.\n\n"
            "📱 <b>Сообщество ВКонтакте</b>\nНовости, конкурсы и полезная информация."
        )
        bot.send_message(uid, text_msg, reply_markup=markup, parse_mode="HTML")

    elif text == "💼 Список лидеров":
        show_leaders_message(uid, uid)

    elif text == "🔄 Перенос аккаунта":
        form_text = (
            "🔄 <b>Перенос аккаунта с других проектов</b>\n───────────────\n\n"
            "📋 <b>Форма подачи заявки:</b>\n"
            "▫️ Ваш Nick_Name на сервере:\n"
            "▫️ Проект, с которого переносите:\n"
            "▫️ Ваши статистика / имущество:\n"
            "▫️ Доказательства (скриншот с /time)\n\n"
            "✍️ Отправьте данные по форме ответным сообщением и прикрепите скриншот доказательств."
        )
        bot.send_message(uid, form_text, parse_mode="HTML")
        msg = bot.send_message(uid, "📝 Введите заполненную форму с картинкой:")
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
            c.execute("SELECT COUNT(*) FROM leaders")
            leaders_count = c.fetchone()[0]
            conn.close()
            
            stat_text = (
                f"📊 <b>Статистика бота</b>\n───────────────\n\n"
                f"👤 Пользователей: <code>{users}</code>\n"
                f"👑 Администраторов: <code>{admins}</code>\n"
                f"📰 Опубликовано новостей: <code>{news_count}</code>\n"
                f"💼 Лидеров в списке: <code>{leaders_count}</code>"
            )
            bot.send_message(uid, stat_text, parse_mode="HTML", reply_markup=main_kb(uid))

        elif text == "📢 Рассылка":
            msg = bot.send_message(uid, "📨 Введите текст сообщения для рассылки всем пользователям:")
            bot.register_next_step_handler(msg, broadcast_text)

        elif text == "📋 Помощь":
            help_text = (
                "📋 <b>Команды и возможности администратора</b>\n───────────────\n\n"
                "👤 <b>Управление должностями:</b>\n"
                "<code>/должность @username Должность</code> — сменить должность\n"
                "<code>/должности</code> — список доступных должностей\n"
                "<code>/admlist</code> — список всей администрации\n\n"
                "🎮 <b>Профиль:</b>\n"
                "<code>/стата</code> — посмотреть свой профиль\n"
                "<code>/ник</code> — сменить свой никнейм\n\n"
                "💼 <b>Управление лидерами:</b>\n"
                "Перейдите в <b>«💼 Список лидеров»</b> для добавления/удаления лидеров через Inline-кнопки."
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
        bot.send_message(uid, "❌ Список пользователей пуст.")
        return
    success = 0
    for user_id in users:
        try:
            bot.send_message(user_id, text)
            success += 1
            time.sleep(0.04)
        except:
            pass
    bot.send_message(uid, f"✅ <b>Рассылка завершена!</b>\nУспешно отправлено: {success} из {len(users)}", parse_mode="HTML", reply_markup=main_kb(uid))

# ===================== ЗАПУСК БОТА =====================
if __name__ == "__main__":
    keep_alive()
    print("✅ Бот успешно запущен!")
    bot.polling(none_stop=True)

import os
import time
import socket
import threading
import sqlite3
import telebot
from telebot import types
from samp_client.client import SampClient
from keep_alive import keep_alive

try:
    from samp_client.client import SampClient
    samp_ready = True
except:
    samp_ready = False

# Настройки подключения к серверу и ресурсов
SERVER_IP = "54.38.117.76"
SERVER_PORT = 1321
REQUIRED_CHANNEL = "@santropetrilogybot_news"
CHANNEL_URL = "https://t.me/santropetrilogybot_news"

# Список системных администраторов (по умолчанию 3 уровень)
ADMIN_IDS = {709672781, 5939366373, 1066139847}
ADMIN_LEVELS = {}  # ID -> Уровень

socket.setdefaulttimeout(5)

# Безопасное чтение переменных окружения для деплоя
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "bot_stats.db")

# Защита от ошибок сборки на Railway (инициализируем бота только при наличии токена)
bot = None
if TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=True)
    telebot.apihelper.ENABLE_MIDDLEWARE = True

# ===================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ =====================
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            nickname TEXT, 
            join_date TEXT, 
            username TEXT,
            position TEXT DEFAULT 'Игрок'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY, 
            level INTEGER DEFAULT 1, 
            position TEXT DEFAULT 'Администратор'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            title TEXT NOT NULL, 
            content TEXT NOT NULL, 
            author TEXT, 
            date TEXT
        )
    """)
    c.execute("""
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS transfer_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            text_data TEXT,
            photo_file_id TEXT,
            status TEXT DEFAULT 'unread', 
            date TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            fraction TEXT NOT NULL, 
            nickname TEXT NOT NULL, 
            username TEXT, 
            date TEXT
        )
    """)
    
    # Миграция: Проверяем наличие колонки position в users
    try:
        c.execute("ALTER TABLE users ADD COLUMN position TEXT DEFAULT 'Игрок'")
    except Exception:
        pass

    # Принудительно вносим и обновляем системных админов
    for aid in list(ADMIN_IDS):
        c.execute("INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, 3, 'Главный администратор')", (aid,))
        c.execute("UPDATE admins SET level = 3, position = 'Главный администратор' WHERE user_id = ?", (aid,))
    conn.commit()
    
    # Загружаем уровни админов в оперативную память
    c.execute("SELECT user_id, level FROM admins")
    for row in c.fetchall():
        ADMIN_IDS.add(row[0])
        ADMIN_LEVELS[row[0]] = row[1] if row[1] else 1
    conn.close()

# ===================== ПРОВЕРКА ПОДПИСКИ =====================
def is_subscribed(user_id):
    if not bot:
        return True
    try:
        status = bot.get_chat_member(REQUIRED_CHANNEL, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception:
        return True  # В случае сбоя API Telegram не блокируем пользователей

def get_sub_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL))
    markup.add(types.InlineKeyboardButton("🔄 Я подписался", callback_data="check_sub"))
    return markup

# ===================== КРАСИВОЕ ОФОРМЛЕНИЕ ДОЛЖНОСТЕЙ =====================
def format_pos_string(pos):
    if not pos:
        return "🎮 <b>Игрок</b>"
    p = pos.lower()
    
    # Специфические следящие должности (ГС / ЗГС / Следящие)
    if "гс гос" in p or "главный следящий за гос" in p: return f"🏢 <b>{pos}</b>"
    elif "згс гос" in p or "зам. гл. следящего за гос" in p: return f"🏢⚜️ <b>{pos}</b>"
    elif "следящий за гос" in p or "следящий гос" in p: return f"🏢🔎 <b>{pos}</b>"
    
    elif "гс гетто" in p or "главный следящий за гетто" in p: return f"🩸 <b>{pos}</b>"
    elif "згс гетто" in p or "зам. гл. следящего за гетто" in p: return f"🩸⚜️ <b>{pos}</b>"
    elif "следящий за гетто" in p or "следящий гетто" in p: return f"🩸🔎 <b>{pos}</b>"
    
    elif "гс мафий" in p or "главный следящий за мафиями" in p: return f"🕶️ <b>{pos}</b>"
    elif "згс мафий" in p or "зам. гл. следящего за мафиями" in p: return f"🕶️⚜️ <b>{pos}</b>"
    elif "следящий за мафиями" in p or "следящий мафий" in p: return f"🕶️🔎 <b>{pos}</b>"
    
    elif "гс ап" in p or "главный следящий за ап" in p: return f"📖 <b>{pos}</b>"
    elif "згс ап" in p or "заместитель главного следящего за ап" in p: return f"📖⚜️ <b>{pos}</b>"
    elif "следящий за ап" in p or "следящий ап" in p: return f"📖🔎 <b>{pos}</b>"
    
    elif "гс хелперов" in p or "главный следящий за хелперами" in p: return f"🙋‍♂️ <b>{pos}</b>"
    elif "згс хелперов" in p or "заместитель главного следящего за хелперами" in p: return f"🙋‍♂️⚜️ <b>{pos}</b>"
    
    elif "гс" in p: return f"⚡ <b>{pos}</b>"
    elif "згс" in p: return f"⚡⚜️ <b>{pos}</b>"
    elif "следящий" in p: return f"🔎 <b>{pos}</b>"

    # Основная иерархия администрации
    elif "основатель" in p or "разработчик" in p or "developer" in p: return f"💻 <b>{pos}</b>"
    elif "спец" in p: return f"🌟 <b>{pos}</b>"
    elif "га" == p or "главный администратор" in p or "гл. адм" in p: return f"👑 <b>{pos}</b>"
    elif "зга" == p or "заместитель главного" in p or "зам. гл" in p: return f"⚜️ <b>{pos}</b>"
    elif "куратор" in p: return f"🛡️ <b>{pos}</b>"
    elif "модератор" in p: return f"🛡️ <b>{pos}</b>"
    elif "хелпер" in p: return f"🙋‍♂️ <b>{pos}</b>"
    elif "лидер" in p: return f"💼 <b>{pos}</b>"
    elif "администратор" in p or "админ" in p: return f"🛠️ <b>{pos}</b>"
    
    return f"🎖️ <b>{pos}</b>"

def get_formatted_position(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT position FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return format_pos_string(row[0])
    return "Администратор" if user_id in ADMIN_IDS else "Игрок"

# ===================== НОВОСТИ =====================
def news_get_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, date FROM news ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def news_get_by_id(news_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, content, date FROM news WHERE id = ?", (news_id,))
    row = c.fetchone()
    conn.close()
    return row

def news_add(title, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO news (title, content, author, date) VALUES (?, ?, ?, ?)", (title, content, "Администрация", date))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def news_edit(news_id, title, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE news SET title = ?, content = ? WHERE id = ?", (title, content, news_id))
    conn.commit()
    conn.close()

def news_delete(news_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()

# ===================== ЛИДЕРЫ =====================
def leaders_get_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, fraction, nickname, username, date FROM leaders ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def leaders_get_by_id(leader_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, fraction, nickname, username, date FROM leaders WHERE id = ?", (leader_id,))
    row = c.fetchone()
    conn.close()
    return row

def leaders_add(fraction, nickname, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO leaders (fraction, nickname, username, date) VALUES (?, ?, ?, ?)", (fraction, nickname, username, date))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def leaders_delete(leader_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM leaders WHERE id = ?", (leader_id,))
    conn.commit()
    conn.close()

# ===================== АДМИНИСТРАЦИЯ И ПРОФИЛИ =====================
def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.user_id, a.level, a.position, u.nickname, u.username 
        FROM admins a 
        LEFT JOIN users u ON a.user_id = u.user_id 
        ORDER BY a.level DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def add_admin_db(user_id, level, position="Администратор"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id, level, position) VALUES (?, ?, ?)", (user_id, level, position))
    c.execute("UPDATE admins SET level = ?, position = ? WHERE user_id = ?", (level, position, user_id))
    conn.commit()
    conn.close()

def remove_admin_db(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_nickname(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_nickname(user_id, nick):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, nickname, join_date, position) VALUES (?, ?, ?, 'Игрок')",
              (user_id, nick, time.strftime("%Y-%m-%d")))
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

# ===================== ТЕХ. ПОДДЕРЖКА & ПЕРЕНОСЫ =====================
def get_unread_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM support_requests WHERE status = 'unread'")
    count = c.fetchone()[0]
    conn.close()
    return count

def save_support_request(user_id, nickname, username, question):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO support_requests (user_id, nickname, username, question, status, date) VALUES (?, ?, ?, ?, 'unread', ?)", (user_id, nickname, username, question, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_unread_requests():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, nickname, username, question, date FROM support_requests WHERE status = 'unread' ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def mark_request_answered(request_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE support_requests SET status = 'answered' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def save_transfer_request(user_id, nickname, username, text_data, photo_file_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = time.strftime("%d.%m.%Y %H:%M")
    c.execute("INSERT INTO transfer_requests (user_id, nickname, username, text_data, photo_file_id, status, date) VALUES (?, ?, ?, ?, ?, 'unread', ?)", (user_id, nickname, username, text_data, photo_file_id, date))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def set_transfer_status(req_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE transfer_requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()

# ===================== МОНИТОРИНГ СЕРВЕРА =====================
def get_online():
    if not samp_ready:
        return "❌ Мониторинг недоступен (ошибка библиотеки SAMP)"
    try:
        client = SampClient(SERVER_IP, SERVER_PORT)
        info = client.get_server_info()
        if info:
            return (
                f"🎮 <b>{info.hostname}</b>\n\n"
                f"🌐 IP: <code>{SERVER_IP}:{SERVER_PORT}</code>\n"
                f"👥 Онлайн: <code>{info.players}/{info.max_players}</code>\n"
                f"🟢 Статус: Работает"
            )
        return "❌ Сервер временно недоступен"
    except Exception:
        return "❌ Не удалось получить статус игрового сервера"

# ===================== ПОЛЬЗОВАТЕЛЬСКОЕ МЕНЮ =====================
def main_kb(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("🌐 Онлайн", "🔗 Полезные ссылки")
    m.row("📰 Новости сервера", "💼 Список лидеров")
    m.row("🔄 Перенос аккаунта", "🎫 Тех поддержка")
    if uid in ADMIN_IDS:
        m.row("📬 Непрочитанные", "📊 Статистика", "📋 Помощь")
    return m

# ===================== ИНИЦИАЛИЗАЦИЯ И ОБРАБОТЧИКИ =====================
if bot:
    @bot.callback_query_handler(func=lambda call: call.data == "check_sub")
    def check_sub_callback(call):
        if is_subscribed(call.from_user.id):
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            bot.send_message(call.message.chat.id, "✅ Подписка подтверждена! Используйте /start для входа.")
        else:
            bot.answer_callback_query(call.id, "❌ Вы все еще не подписаны на новостной канал!", show_alert=True)

    @bot.message_handler(commands=['start'])
    def start_cmd(message):
        uid = message.chat.id
        username = message.from_user.username
        if username:
            update_user_info(uid, username)
        
        if not is_subscribed(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться на новости", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("🔄 Я подписался", callback_data="check_sub"))
            bot.send_message(uid, "❌ <b>Доступ ограничен!</b>\n\nПожалуйста, подпишитесь на наш новостной канал, чтобы разблокировать доступ к боту.", reply_markup=markup, parse_mode="HTML")
            return
            
        nick = get_nickname(uid)
        if not nick:
            msg = bot.send_message(uid, "👋 Добро пожаловать!\nДля продолжения придумайте игровой никнейм для бота:")
            bot.register_next_step_handler(msg, register_nick)
        else:
            bot.send_message(uid, f"👋 Приветствуем вас в меню, <b>{nick}</b>!", reply_markup=main_kb(uid), parse_mode="HTML")

    def register_nick(message):
        nick = message.text.strip()
        if len(nick) < 3:
            msg = bot.send_message(message.chat.id, "❌ Слишком короткий никнейм. Попробуйте еще раз:")
            bot.register_next_step_handler(msg, register_nick)
            return
        set_nickname(message.chat.id, nick)
        bot.send_message(message.chat.id, f"✅ Отлично! Ваш игровой ник <b>{nick}</b> успешно сохранен.", reply_markup=main_kb(message.chat.id), parse_mode="HTML")

    # ===================== КОМАНДЫ АДМИНИСТРАЦИИ =====================
    @bot.message_handler(commands=['поиск'])
    def handle_search(message):
        if message.chat.id not in ADMIN_IDS: return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ Формат команды: <code>/поиск [Ник или Юзернейм]</code>", parse_mode="HTML")
            return
        search_term = parts[1].strip()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, nickname, username, position FROM users WHERE LOWER(nickname) LIKE ? OR LOWER(username) LIKE ?", (f"%{search_term.lower()}%", f"%{search_term.lower()}%"))
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.reply_to(message, "🔍 Пользователи не найдены.")
            return
        text = f"🔍 <b>Результаты поиска ({len(rows)}):</b>\n\n"
        for r in rows:
            formatted_p = format_pos_string(r[3])
            text += f"🎮 Ник: <code>{r[1]}</code>\n🆔 ID: <code>{r[0]}</code>\n🎖️ Роль: {formatted_p}\n📱 Юзернейм: @{r[2] if r[2] else 'Нет'}\n───────────────────\n"
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    @bot.message_handler(commands=['admlist'])
    def handle_admlist(message):
        if message.chat.id not in ADMIN_IDS: return
        admins = get_all_admins()
        text = "🛡️ <b>Список администрации бота:</b>\n\n"
        for user_id, level, position, nickname, username in admins:
            tg = f"@{username}" if username else "Нет связи"
            formatted_p = format_pos_string(position)
            text += f"👤 <b>{nickname or 'Не установлен'}</b>\n🆔 ID: <code>{user_id}</code> | Lvl: {level}\n🎖️ Должность: {formatted_p}\n📱 Связь: {tg}\n───────────────────\n"
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    @bot.message_handler(commands=['должность'])
    def handle_position_cmd(message):
        if message.chat.id not in ADMIN_IDS: return
        try:
            parts = message.text.split(maxsplit=2)
            username = parts[1]
            new_pos = parts[2].strip()
            
            # Разрешаем таргет
            if username.startswith("@"):
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (username.lstrip("@").lower(),))
                row = c.fetchone(); conn.close()
                target_id = row[0] if row else None
            else:
                target_id = int(username)
                
            if not target_id:
                bot.reply_to(message, "❌ Пользователь не найден.")
                return
                
            set_position(target_id, new_pos)
            bot.reply_to(message, f"✅ Должность игрока изменена на: {format_pos_string(new_pos)}", parse_mode="HTML")
        except:
            bot.reply_to(message, "❌ Формат: /должность [@username / ID] [Название]")

    @bot.message_handler(commands=['админ'])
    def handle_add_admin_cmd(message):
        if message.chat.id not in ADMIN_IDS: return
        try:
            parts = message.text.split(maxsplit=2)
            target_id = int(parts[1]) if not parts[1].startswith("@") else None
            lvl = int(parts[2])
            if target_id:
                add_admin_db(target_id, lvl)
                bot.reply_to(message, f"✅ Пользователю {target_id} выдан уровень прав: {lvl}")
        except: pass

    @bot.message_handler(commands=['разадмин'])
    def handle_remove_admin_cmd(message):
        if message.chat.id not in ADMIN_IDS: return
        try:
            parts = message.text.split()
            target_id = int(parts[1])
            remove_admin_db(target_id)
            bot.reply_to(message, f"✅ С пользователя {target_id} сняты права администратора.")
        except: pass

    @bot.message_handler(commands=['стата'])
    def handle_stat_cmd(message):
        uid = message.chat.id
        nick = get_nickname(uid)
        if not nick: return
        bot.send_message(uid, f"📋 <b>Ваш профиль:</b>\n\n🎮 Никнейм: <code>{nick}</code>\n🆔 ID: <code>{uid}</code>\n🎖️ Роль: {get_formatted_position(uid)}", parse_mode="HTML")

    # ===================== ОБРАБОТЧИКИ МЕНЮ И КНОПОК =====================
    @bot.message_handler(func=lambda message: True)
    def handle_reply_keyboard(message):
        uid = message.chat.id
        text = message.text
        if not text or text.startswith('/'): return
        
        if not is_subscribed(uid):
            bot.send_message(uid, "❌ Доступ ограничен! Пожалуйста, подпишитесь на новостной канал.")
            return

        # ----- Онлайн -----
        if text == "🌐 Онлайн":
            bot.send_message(uid, "⏳ Опрашиваю игровой сервер...", parse_mode="HTML")
            bot.send_message(uid, get_online(), parse_mode="HTML", reply_markup=main_kb(uid))

        # ----- Ссылки -----
        elif text == "🔗 Полезные ссылки":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📢 Новостной канал бота", url="https://t.me/santropetrilogybot_news"),
                types.InlineKeyboardButton("📣 Официальный Telegram-канал", url="https://t.me/santrope_trilogyrp"),
                types.InlineKeyboardButton("🌐 Официальный форум", url="https://wh32893.web3.maze-tech.ru/index.php"),
                types.InlineKeyboardButton("📱 Сообщество ВКонтакте", url="https://vk.ru/santropetrilogy")
            )
            text_msg = (
                "🔗 <b>Полезные ссылки проекта</b>\n\n"
                "📢 <b>Новости и объявления</b>\n"
                "Следите за обновлениями, конкурсами и важными сообщениями.\n\n"
                "🌐 <b>Форум проекта</b>\n"
                "Правила, заявки, обсуждения и полезная информация.\n\n"
                "📱 <b>Сообщество ВКонтакте</b>\n"
                "Новости проекта и общение с игроками.\n\n"
                "👇 <i>Выберите нужный ресурс:</i>"
            )
            bot.send_message(uid, text_msg, reply_markup=markup, parse_mode="HTML")

        # ----- Список Лидеров -----
        elif text == "💼 Список лидеров":
            all_leaders = leaders_get_all()
            markup = types.InlineKeyboardMarkup()
            if not all_leaders:
                if uid in ADMIN_IDS: markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
                bot.send_message(uid, "📭 Список лидеров пуст.", reply_markup=markup, parse_mode="HTML")
            else:
                for lid, fraction, nickname, username, date in all_leaders:
                    markup.add(types.InlineKeyboardButton(f"💼 {fraction}: {nickname}", callback_data=f"lv_{lid}"))
                if uid in ADMIN_IDS: markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
                bot.send_message(uid, "💼 <b>Лидерский состав нашего проекта:</b>\nВыберите организацию для просмотра карточки:", reply_markup=markup, parse_mode="HTML")

        # ----- Перенос Аккаунта -----
        elif text == "🔄 Перенос аккаунта":
            form = (
                "🔄 <b>Перенос игровых аккаунтов с других SAMP проектов!</b>\n\n"
                "📋 <b>Обязательная форма подачи заявления:</b>\n"
                "▫️ <b>Ваш будущий Nick_Name:</b>\n"
                "▫️ <b>Проект, с которого переносите имущество:</b>\n"
                "▫️ <b>Что конкретно планируете перенести:</b>\n"
                "▫️ <b>Доказательства владения (/time):</b>\n\n"
                "✍️ <b>Заполните анкету и отправьте прямо сейчас одним сообщением!</b>\n"
                "📸 <i>Не забудьте прикрепить скриншот с /time к вашей анкете.</i>"
            )
            msg = bot.send_message(uid, form, parse_mode="HTML")
            bot.register_next_step_handler(msg, process_transfer)

        # ----- Техническая Поддержка -----
        elif text == "🎫 Тех поддержка":
            if uid in ADMIN_IDS:
                reqs = get_unread_requests()
                if not reqs:
                    bot.send_message(uid, "✅ Активных обращений от игроков нет.")
                    return
                lines = [f"📬 <b>Необработанные обращения ({len(reqs)}):</b>\n"]
                for i, r in enumerate(reqs, start=1):
                    lines.append(f"<b>{i}.</b> №{r[0]} | 🎮 <code>{r[2]}</code>\n❓ {r[4][:50]}...")
                lines.append("\n✍️ Чтобы ответить, напишите: <code>[ID обращения] [Текст ответа]</code>")
                msg = bot.send_message(uid, "\n".join(lines), parse_mode="HTML")
                bot.register_next_step_handler(msg, process_admin_reply)
            else:
                msg = bot.send_message(uid, "✍️ <b>Опишите возникшую проблему:</b>\nАдминистрация оперативно ответит прямо в этот чат.", parse_mode="HTML")
                bot.register_next_step_handler(msg, process_player_ticket)

        # ----- Новости Сервера -----
        elif text == "📰 Новости сервера":
            all_news = news_get_all()
            markup = types.InlineKeyboardMarkup()
            if uid in ADMIN_IDS:
                markup.add(
                    types.InlineKeyboardButton("➕ Добавить", callback_data="n_add"),
                    types.InlineKeyboardButton("🗑 Удалить", callback_data="n_del_list")
                )
            for nid, title, date in all_news:
                markup.add(types.InlineKeyboardButton(f"📰 {title} [{date}]", callback_data=f"nv_{nid}"))
            bot.send_message(uid, "📰 <b>Новостной раздел проекта:</b>", reply_markup=markup, parse_mode="HTML")

        # ----- Статистика -----
        elif text == "📊 Статистика" and uid in ADMIN_IDS:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM admins")
            adms = c.fetchone()[0]
            conn.close()
            bot.send_message(uid, f"📊 <b>Статистика бота:</b>\n\n👤 Игроков: <code>{users}</code>\n👑 Администраторов: <code>{adms}</code>\n📬 Непрочитанных тикетов: <code>{get_unread_count()}</code>", parse_mode="HTML")

        # ----- Рассылка -----
        elif text == "📢 Рассылка" and uid in ADMIN_IDS:
            msg = bot.send_message(uid, "📨 <b>Введите текст для глобальной рассылки:</b>\nВы можете использовать стандартную HTML разметку.", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_broadcast)

        # ----- Помощь -----
        elif text == "📋 Помощь" and uid in ADMIN_IDS:
            help_text = (
                "📋 <b>Команды Главного Администратора:</b>\n\n"
                "👤 <b>Управление пользователями:</b>\n"
                "/админ [ID] [уровень] — выдать права доступа\n"
                "/разадмин [ID] — аннулировать админ-права\n"
                "/должность [ID/@username] [Роль] — установить роль\n"
                "/поиск [Ник] — найти ID и данные аккаунта\n"
                "/admlist — полный список админ-состава\n\n"
                "🎮 <b>Профиль игрока:</b>\n"
                "/стата — посмотреть текущий статус\n"
                "/ник — поменять свой никнейм"
            )
            bot.send_message(uid, help_text, parse_mode="HTML")

    # ===================== ПОДДЕРЖКА & ПЕРЕНОСЫ (ФУНКЦИИ) =====================
    def process_player_ticket(message):
        if message.text in MENU_BUTTONS: return
        req_id = save_support_request(message.chat.id, get_nickname(message.chat.id) or "Без ника", f"@{message.from_user.username}", message.text)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Написать ответ", callback_data=f"ans_{req_id}_{message.chat.id}"))
        
        alert = f"🔔 <b>Новое обращение №{req_id}!</b>\n🎮 Игрок: {get_nickname(message.chat.id)}\n❓ Вопрос:\n{message.text}"
        for aid in ADMIN_IDS:
            try: bot.send_message(aid, alert, reply_markup=markup, parse_mode="HTML")
            except: pass
        bot.send_message(message.chat.id, "✅ Ваш вопрос успешно отправлен. Ожидайте ответа администратора!")

    def process_admin_reply(message):
        if message.text in MENU_BUTTONS: return
        try:
            parts = message.text.strip().split(maxsplit=1)
            req_id = int(parts[0])
            ans = parts[1]
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT user_id, nickname, question, date FROM support_requests WHERE id = ?", (req_id,))
            row = c.fetchone(); conn.close()
            if not row:
                bot.send_message(message.chat.id, "❌ Обращение не найдено.")
                return
            bot.send_message(row[0], f"✉️ <b>Ответ администрации на тикет №{req_id}:</b>\n\n💬 {ans}", parse_mode="HTML")
            log_support_answer(req_id, row[1], row[2], "Администрация", ans, row[3])
            mark_request_answered(req_id)
            bot.send_message(message.chat.id, "✅ Ваш ответ успешно доставлен.")
        except:
            bot.send_message(message.chat.id, "❌ Ошибка формата. Попробуйте еще раз.")

    def process_transfer(message):
        if message.text in MENU_BUTTONS or (message.caption and message.caption in MENU_BUTTONS):
            bot.send_message(message.chat.id, "❌ Подача анкеты отменена.")
            return
        uid = message.chat.id
        text_data = message.caption if message.caption else message.text
        photo_id = message.photo[-1].file_id if message.photo else None
        
        if not text_data and not photo_id:
            bot.send_message(uid, "❌ Ошибка: отправьте заполненную форму и прикрепите фото.")
            return
            
        req_id = save_transfer_request(uid, get_nickname(uid) or "Без ника", f"@{message.from_user.username}", text_data or "[Без описания]", photo_id)
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"tr_app_{req_id}_{uid}"),
            types.InlineKeyboardButton("❌ Отказать", callback_data=f"tr_rej_{req_id}_{uid}")
        )
        
        alert = f"📦 <b>Заявка на перенос аккаунта №{req_id}</b>\n👤 Отправитель: @{message.from_user.username}\n📝 Анкета:\n{text_data}"
        for aid in ADMIN_IDS:
            try:
                if photo_id: bot.send_photo(aid, photo_id, caption=alert, reply_markup=markup, parse_mode="HTML")
                else: bot.send_message(aid, alert, reply_markup=markup, parse_mode="HTML")
            except: pass
            
        bot.send_message(uid, f"✅ Ваше заявление №{req_id} на перенос успешно подано администрации проекта.")

    # ===================== ИНЛАЙН ОБРАБОТЧИКИ (ОТВЕТЫ, ЛИДЕРЫ, НОВОСТИ) =====================
    @bot.callback_query_handler(func=lambda call: call.data.startswith(("tr_app_", "tr_rej_", "ans_", "nv_", "lv_", "l_add", "l_del_")))
    def handle_inline_callbacks(call):
        if not is_subscribed(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Доступ ограничен. Сначала подпишитесь на канал!", show_alert=True)
            return

        data = call.data
        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        # Одобрение переноса
        if data.startswith("tr_app_"):
            if chat_id not in ADMIN_IDS: return
            parts = data.split("_")
            req_id, target_id = int(parts[2]), int(parts[3])
            set_transfer_status(req_id, "approved")
            try: bot.send_message(target_id, f"🎉 <b>Ваша заявка на перенос №{req_id} ОДОБРЕНА!</b> С вами свяжутся в ближайшее время.", parse_mode="HTML")
            except: pass
            bot.answer_callback_query(call.id, "✅ Заявка одобрена!")
            try: bot.edit_message_caption(call.message.caption + "\n\n🟢 <b>СТАТУС: ОДОБРЕНО</b>", chat_id, msg_id, reply_markup=None, parse_mode="HTML")
            except: pass

        # Отказ переноса
        elif data.startswith("tr_rej_"):
            if chat_id not in ADMIN_IDS: return
            parts = data.split("_")
            req_id, target_id = int(parts[2]), int(parts[3])
            msg = bot.send_message(chat_id, f"✍️ Введите причину отказа для заявки на перенос №{req_id}:")
            bot.register_next_step_handler(msg, process_transfer_reject, req_id, target_id, msg_id)
            bot.answer_callback_query(call.id)

        # Ответ на техподдержку
        elif data.startswith("ans_"):
            if chat_id not in ADMIN_IDS: return
            parts = data.split("_")
            req_id, target_id = int(parts[1]), int(parts[2])
            msg = bot.send_message(chat_id, f"✍️ Введите ответ на тикет №{req_id}:")
            bot.register_next_step_handler(msg, process_support_reply, req_id, target_id)
            bot.answer_callback_query(call.id)

        # Просмотр новостей
        elif data.startswith("nv_"):
            nid = int(data[3:])
            row = news_get_by_id(nid)
            if not row: return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("« Назад к новостям", callback_data="n_list"))
            bot.edit_message_text(f"📰 <b>{row[1]}</b>\n\n{row[2]}\n\n📅 <i>Дата: {row[3]}</i>", chat_id, msg_id, reply_markup=markup, parse_mode="HTML")

        # Просмотр лидера
        elif data.startswith("lv_"):
            lid = int(data[3:])
            row = leaders_get_by_id(lid)
            if not row: return
            markup = types.InlineKeyboardMarkup()
            if chat_id in ADMIN_IDS:
                markup.add(types.InlineKeyboardButton("🗑 Снять лидера", callback_data=f"l_del_{lid}"))
            markup.add(types.InlineKeyboardButton("« Назад к списку", callback_data="l_list_back"))
            text = f"💼 <b>Лидер фракции: {row[1]}</b>\n\n🎮 NickName: <code>{row[2]}</code>\n📱 Telegram: @{row[3] if row[3] else 'Не указан'}"
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="HTML")

        # Удаление лидера
        elif data.startswith("l_del_"):
            if chat_id not in ADMIN_IDS: return
            lid = int(data[6:])
            leaders_delete(lid)
            bot.answer_callback_query(call.id, "✅ Лидер снят!")
            try: bot.delete_message(chat_id, msg_id)
            except: pass

        # Добавление лидера
        elif data == "l_add":
            if chat_id not in ADMIN_IDS: return
            msg = bot.send_message(chat_id, "💼 Введите <b>название организации/фракции</b>:")
            bot.register_next_step_handler(msg, process_leader_fraction)

        # Назад к лидерам
        elif data == "l_list_back":
            all_leaders = leaders_get_all()
            markup = types.InlineKeyboardMarkup()
            for lid, fraction, nickname, username, date in all_leaders:
                markup.add(types.InlineKeyboardButton(f"💼 {fraction}: {nickname}", callback_data=f"lv_{lid}"))
            if chat_id in ADMIN_IDS: markup.add(types.InlineKeyboardButton("➕ Добавить лидера", callback_data="l_add"))
            bot.edit_message_text("💼 <b>Список лидеров:</b>", chat_id, msg_id, reply_markup=markup, parse_mode="HTML")

    # ===================== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ОБРАБОТКИ ДАННЫХ =====================
    def process_transfer_reject(message, req_id, target_id, old_msg_id):
        reason = message.text.strip()
        set_transfer_status(req_id, f"rejected: {reason}")
        try: bot.send_message(target_id, f"❌ <b>Ваша заявка на перенос №{req_id} ОТКЛОНЕНА.</b>\n📌 Причина отказа: {reason}", parse_mode="HTML")
        except: pass
        bot.send_message(message.chat.id, f"❌ Заявка №{req_id} отклонена.")

    def process_support_reply(message, req_id, target_id):
        if message.text in MENU_BUTTONS: return
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT nickname, question, date FROM support_requests WHERE id = ?", (req_id,))
            row = c.fetchone(); conn.close()
            bot.send_message(target_id, f"✉️ <b>Ответ администрации на тикет №{req_id}:</b>\n\n💬 {message.text}", parse_mode="HTML")
            log_support_answer(req_id, row[0] if row else "N/A", row[1] if row else "—", "Администрация", message.text, row[2] if row else "—")
            mark_request_answered(req_id)
            bot.send_message(message.chat.id, "✅ Ответ доставлен пользователю.")
        except: pass

    def process_leader_fraction(message):
        fraction = message.text.strip()
        msg = bot.send_message(message.chat.id, f"✅ Фракция: {fraction}\n\nТеперь укажите <b>Nick_Name игрока</b>:")
        bot.register_next_step_handler(msg, process_leader_nick, fraction)

    def process_leader_nick(message, fraction):
        nick = message.text.strip()
        msg = bot.send_message(message.chat.id, f"✅ Ник лидера: {nick}\n\nВведите <b>Telegram Username</b> (без @, или «-» если нет):")
        bot.register_next_step_handler(msg, process_leader_tg, fraction, nick)

    def process_leader_tg(message, fraction, nick):
        tg = message.text.strip().replace("@", "")
        if tg == "-": tg = ""
        leaders_add(fraction, nick, tg)
        bot.send_message(message.chat.id, f"✅ Лидер {nick} успешно добавлен в организацию {fraction}!")

    def process_broadcast(message):
        if message.text in MENU_BUTTONS: return
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        uids = [r[0] for r in c.fetchall()]; conn.close()
        sent, blocked = 0, 0
        for uid in uids:
            try:
                bot.send_message(uid, message.text, parse_mode="HTML")
                sent += 1
                time.sleep(0.05)
            except: blocked += 1
        bot.send_message(message.chat.id, f"📢 Рассылка завершена!\n✅ Доставлено: {sent}\n🚫 Заблокировано: {blocked}")

# ===================== ЗАПУСК ПРИЛОЖЕНИЯ =====================
def start_polling():
    def _poll():
        while True:
            try: bot.polling(skip_pending=True, non_stop=True, timeout=60)
            except: time.sleep(5)
    t = threading.Thread(target=_poll, daemon=True)
    t.start()

if __name__ == "__main__":
    keep_alive()
    if not TOKEN:
        print("Railway: Токен отсутствует на этапе сборки. Ожидание деплоя...")
    else:
        init_db()
        print("✅ Telegram-Бот успешно запущен!")
        start_polling()
        while True:
            time.sleep(10)

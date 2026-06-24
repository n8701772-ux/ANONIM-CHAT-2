import telebot
from telebot.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
import time
from collections import defaultdict
from datetime import datetime
import random
import re

TOKEN = "8666576626:AAHFlk3KhsRsmBnd_YjGZ_YsO7YblsA5vw4"

bot = telebot.TeleBot(TOKEN)

# Хранилища
users = {}                 # user_id: {state, partner_id, chat_id, username, gender, age, search_gender, last_filter}
waiting_list = []          # список id ожидающих
chats = {}                 # chat_id: {user1, user2, created_at}
chat_messages = defaultdict(list)  # история сообщений (опционально)

# Игры: ключ – chat_id, значение – состояние игры
games = {}

# ==============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================

def format_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime('%d.%m.%Y %H:%M:%S')

def get_username(uid: int) -> str:
    return users.get(uid, {}).get('username', str(uid))

def gender_emoji(g: str) -> str:
    if g == 'male':
        return '🚹'
    if g == 'female':
        return '🚺'
    return '⚧'

def age_str(age) -> str:
    if age is None:
        return 'скрыт'
    return str(age)

def partner_info(uid: int) -> str:
    """Возвращает строку с полом и возрастом собеседника"""
    u = users.get(uid, {})
    g = u.get('gender')
    a = u.get('age')
    parts = []
    if g:
        parts.append(f"Пол: {gender_emoji(g)} {'мужской' if g=='male' else 'женский'}")
    if a is not None:
        parts.append(f"Возраст: {a}")
    if not parts:
        return "Профиль не заполнен"
    return ', '.join(parts)

# ==============================================
# ИГРА КРЕСТИКИ-НОЛИКИ
# ==============================================

WIN_COMBOS = [
    [0,1,2], [3,4,5], [6,7,8],  # горизонтали
    [0,3,6], [1,4,7], [2,5,8],  # вертикали
    [0,4,8], [2,4,6]            # диагонали
]

def create_game_board():
    return [' ' for _ in range(9)]

def board_to_keyboard(board, active=True):
    """Преобразует поле в инлайн-клавиатуру 3x3 с эмодзи клеток"""
    markup = InlineKeyboardMarkup(row_width=3)
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            cell = board[idx]
            if cell == 'X':
                text = '❌'
            elif cell == 'O':
                text = '⭕'
            else:
                text = '▫️'
            # callback: cell_{idx}
            row.append(InlineKeyboardButton(text=text, callback_data=f"cell_{idx}" if active else "none"))
        markup.add(*row)
    return markup

def check_winner(board):
    for combo in WIN_COMBOS:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != ' ':
            return board[combo[0]]
    return None

def board_full(board):
    return ' ' not in board

def end_game(chat_id, winner_id=None):
    """Завершает игру и очищает состояние"""
    if chat_id in games:
        g = games.pop(chat_id)
        # Отправляем финальное сообщение с результатом
        if winner_id:
            winner_name = get_username(winner_id)
            text = f"🏆 Победил @{winner_name}!"
        else:
            text = "🤝 Ничья!"
        # Обновляем игровое сообщение у обоих
        try:
            bot.edit_message_text(
                f"Игра окончена!\n{text}",
                chat_id=g['player1'],
                message_id=g['msg1_id']
            )
        except: pass
        try:
            bot.edit_message_text(
                f"Игра окончена!\n{text}",
                chat_id=g['player2'],
                message_id=g['msg2_id']
            )
        except: pass

# ==============================================
# ОСНОВНЫЕ ФУНКЦИИ БОТА
# ==============================================

def send_welcome(message: Message):
    uid = message.from_user.id
    username = message.from_user.username or str(uid)
    users[uid] = {
        "state": "none",
        "partner_id": None,
        "chat_id": None,
        "username": username,
        "gender": None,
        "age": None,
        "search_gender": 'any',   # последний использованный фильтр
        "last_filter": 'any'
    }
    bot.send_message(
        message.chat.id,
        "🔥 *ANONIM CHAT 2.0* 🔥\n\n"
        "Абсолютная свобода общения.\n"
        "Без цензуры, без банов – можно всё!\n\n"
        "👤 *Создатель: Белый Дарон*\n\n"
        "📌 Основные команды:\n"
        "/find – найти собеседника (с фильтром)\n"
        "/leave – выйти из чата\n"
        "/next – сменить собеседника\n"
        "/profile – твой профиль\n"
        "/setgender – указать пол\n"
        "/setage – указать возраст\n"
        "/help – помощь\n"
        "/game – сыграть в крестики-нолики",
        parse_mode='Markdown'
    )

def show_help(message: Message):
    bot.send_message(
        message.chat.id,
        "📋 *Команды ANONIM CHAT:*\n\n"
        "/find – поиск собеседника (с выбором пола)\n"
        "/leave – выйти из чата\n"
        "/next – выйти и сразу искать нового\n"
        "/profile – просмотр профиля\n"
        "/setgender [male/female/none] – указать пол\n"
        "/setage [число] – указать возраст\n"
        "/game – предложить игру в крестики-нолики\n"
        "/stopgame – завершить игру\n"
        "/help – эта справка\n\n"
        "💬 Всё анонимно. Без регистрации.\n"
        "🔞 Никаких запретов – контент 18+ разрешён.\n\n"
        "👤 Создатель: Белый Дарон",
        parse_mode='Markdown'
    )

def show_profile(uid: int, chat_id: int):
    u = users.get(uid)
    if not u:
        send_welcome(Message(chat_id, None, None, None))  # заглушка, не вызывается напрямую
        return
    g = u.get('gender')
    a = u.get('age')
    gender_display = 'не указан' if not g else ('мужской' if g=='male' else 'женский')
    age_display = 'не указан' if a is None else str(a)
    text = (
        f"👤 *Твой профиль*\n"
        f"ID: `{uid}`\n"
        f"Пол: {gender_emoji(g) if g else '⚧'} {gender_display}\n"
        f"Возраст: {age_display}\n"
        f"Последний фильтр поиска: {u.get('last_filter','any')}\n\n"
        "Изменить: /setgender /setage"
    )
    bot.send_message(chat_id, text, parse_mode='Markdown')

def set_gender(message: Message):
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Используй: /setgender male / female / none")
        return
    val = parts[1].lower()
    if val in ('male', 'м'):
        users[uid]['gender'] = 'male'
        bot.send_message(message.chat.id, "✅ Пол установлен: мужской 🚹")
    elif val in ('female', 'ж'):
        users[uid]['gender'] = 'female'
        bot.send_message(message.chat.id, "✅ Пол установлен: женский 🚺")
    elif val == 'none':
        users[uid]['gender'] = None
        bot.send_message(message.chat.id, "✅ Пол скрыт")
    else:
        bot.send_message(message.chat.id, "Неверно. Допустимо: male, female, none")

def set_age(message: Message):
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Используй: /setage 25")
        return
    try:
        age = int(parts[1])
        if age < 1 or age > 150:
            raise ValueError
        users[uid]['age'] = age
        bot.send_message(message.chat.id, f"✅ Возраст установлен: {age}")
    except:
        bot.send_message(message.chat.id, "Укажи число от 1 до 150")

def start_find(message: Message):
    """Предлагает выбрать пол для поиска (инлайн кнопки)"""
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    if users[uid]['state'] != 'none':
        bot.send_message(message.chat.id, "❌ Ты уже в чате или в поиске. Сначала /leave")
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚹 Мужчин", callback_data="search_male"),
        InlineKeyboardButton("🚺 Женщин", callback_data="search_female"),
        InlineKeyboardButton("⚧ Без разницы", callback_data="search_any")
    )
    bot.send_message(message.chat.id, "Кого ищем?", reply_markup=markup)

def find_partner(uid: int, search_gender: str, message: Message = None):
    """Непосредственно запускает поиск с заданным фильтром"""
    if uid not in users or users[uid]['state'] != 'none':
        if message:
            bot.send_message(message.chat.id, "❌ Нельзя начать поиск сейчас")
        return
    users[uid]['state'] = 'waiting'
    users[uid]['search_gender'] = search_gender
    users[uid]['last_filter'] = search_gender
    waiting_list.append(uid)
    if message:
        bot.send_message(message.chat.id, "🔍 Ищем собеседника...")
    try_find_pair()

def try_find_pair():
    """Пытается составить пару из ожидающих с учётом пола"""
    i = 0
    while i < len(waiting_list):
        uid1 = waiting_list[i]
        if uid1 not in users or users[uid1]['state'] != 'waiting':
            waiting_list.pop(i)
            continue
        found = -1
        for j in range(i+1, len(waiting_list)):
            uid2 = waiting_list[j]
            if uid2 not in users or users[uid2]['state'] != 'waiting':
                continue
            # Проверка совместимости фильтров
            sg1 = users[uid1].get('search_gender', 'any')
            sg2 = users[uid2].get('search_gender', 'any')
            gender1 = users[uid1].get('gender')
            gender2 = users[uid2].get('gender')
            # Соответствует ли uid2 тому, кого ищет uid1
            ok1 = (sg1 == 'any') or (gender2 == sg1)
            # Соответствует ли uid1 тому, кого ищет uid2
            ok2 = (sg2 == 'any') or (gender1 == sg2)
            if ok1 and ok2:
                found = j
                break
        if found != -1:
            uid2 = waiting_list.pop(found)
            uid1 = waiting_list.pop(i)  # удаляем текущего
            # Создаём чат
            chat_id = f"{uid1}_{uid2}_{int(time.time())}"
            chats[chat_id] = {
                "user1": uid1,
                "user2": uid2,
                "created_at": time.time()
            }
            users[uid1].update({"state": "chatting", "partner_id": uid2, "chat_id": chat_id})
            users[uid2].update({"state": "chatting", "partner_id": uid1, "chat_id": chat_id})
            # Отправляем приветствия с информацией о собеседнике
            info1 = partner_info(uid2)
            info2 = partner_info(uid1)
            bot.send_message(uid1,
                f"💬 *Собеседник найден!*\n{info1}\nНачинайте общение.",
                parse_mode='Markdown')
            bot.send_message(uid2,
                f"💬 *Собеседник найден!*\n{info2}\nНачинайте общение.",
                parse_mode='Markdown')
            # i не увеличиваем, т.к. список изменился
        else:
            i += 1

def leave_chat(message: Message):
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    state = users[uid]['state']
    if state == 'none':
        bot.send_message(message.chat.id, "❌ Ты не в чате")
        return
    # Остановка игры, если идёт
    chat_id = users[uid].get('chat_id')
    if chat_id and chat_id in games:
        end_game(chat_id)  # игра завершается без победителя
    if state == 'waiting':
        if uid in waiting_list:
            waiting_list.remove(uid)
        users[uid]['state'] = 'none'
        bot.send_message(message.chat.id, "🔎 Поиск остановлен")
        return
    # state == chatting
    partner_id = users[uid]['partner_id']
    users[uid]['state'] = 'none'
    users[uid]['partner_id'] = None
    users[uid]['chat_id'] = None
    bot.send_message(message.chat.id, "✅ Ты вышел из чата")
    if partner_id in users and users[partner_id]['state'] == 'chatting':
        bot.send_message(partner_id, "❌ Собеседник покинул чат")
        users[partner_id]['state'] = 'none'
        users[partner_id]['partner_id'] = None
        users[partner_id]['chat_id'] = None
        # если у партнёра была игра, завершаем
        p_chat_id = users[partner_id].get('chat_id')
        if p_chat_id in games:
            end_game(p_chat_id)

def next_partner(message: Message):
    """Выход из чата и моментальный запуск поиска с последним фильтром"""
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    if users[uid]['state'] == 'chatting':
        leave_chat(message)  # выходим
    elif users[uid]['state'] == 'waiting':
        if uid in waiting_list:
            waiting_list.remove(uid)
        users[uid]['state'] = 'none'
    # Запускаем поиск с последним фильтром
    last = users[uid].get('last_filter', 'any')
    find_partner(uid, last, message)

def forward_message(message: Message):
    uid = message.from_user.id
    u = users.get(uid)
    if not u or u['state'] != 'chatting' or u['partner_id'] not in users:
        bot.send_message(message.chat.id, "❌ Собеседник покинул чат")
        if uid in users:
            users[uid]['state'] = 'none'
        return
    partner_id = u['partner_id']
    chat_id = u['chat_id']
    # Сохраняем историю
    content = None
    if message.content_type == 'text':
        content = message.text
    else:
        # Для медиа – file_id
        if message.content_type == 'photo':
            content = message.photo[-1].file_id
        elif message.content_type == 'video':
            content = message.video.file_id
        elif message.content_type == 'document':
            content = message.document.file_id
        elif message.content_type == 'audio':
            content = message.audio.file_id
        elif message.content_type == 'voice':
            content = message.voice.file_id
        elif message.content_type == 'sticker':
            content = message.sticker.file_id
        else:
            return
    chat_messages[chat_id].append({
        "sender": uid,
        "type": message.content_type,
        "content": content,
        "timestamp": time.time()
    })
    # Пересылка партнёру
    try:
        if message.content_type == 'text':
            bot.send_message(partner_id, message.text)
        elif message.content_type == 'photo':
            bot.send_photo(partner_id, message.photo[-1].file_id)
        elif message.content_type == 'video':
            bot.send_video(partner_id, message.video.file_id)
        elif message.content_type == 'document':
            bot.send_document(partner_id, message.document.file_id)
        elif message.content_type == 'audio':
            bot.send_audio(partner_id, message.audio.file_id)
        elif message.content_type == 'voice':
            bot.send_voice(partner_id, message.voice.file_id)
        elif message.content_type == 'sticker':
            bot.send_sticker(partner_id, message.sticker.file_id)
    except Exception as e:
        print(f"Ошибка пересылки: {e}")
        bot.send_message(uid, "❌ Собеседник покинул чат")
        leave_chat(message)

# ==============================================
# ОБРАБОТЧИКИ КОМАНД
# ==============================================

@bot.message_handler(commands=['start', 'help', 'find', 'leave', 'next', 'profile', 'setgender', 'setage', 'game', 'stopgame'])
def handle_commands(message: Message):
    cmd = message.text.split()[0].lower()
    if cmd == '/start':
        send_welcome(message)
    elif cmd == '/help':
        show_help(message)
    elif cmd == '/find':
        start_find(message)
    elif cmd == '/leave':
        leave_chat(message)
    elif cmd == '/next':
        next_partner(message)
    elif cmd == '/profile':
        show_profile(message.from_user.id, message.chat.id)
    elif cmd == '/setgender':
        set_gender(message)
    elif cmd == '/setage':
        set_age(message)
    elif cmd == '/game':
        handle_game_command(message)
    elif cmd == '/stopgame':
        stop_game_command(message)

def handle_game_command(message: Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['state'] != 'chatting':
        bot.send_message(message.chat.id, "❌ Нужно находиться в чате, чтобы предложить игру")
        return
    partner_id = users[uid]['partner_id']
    chat_id = users[uid]['chat_id']
    if chat_id in games:
        bot.send_message(message.chat.id, "🎮 Игра уже идёт!")
        return
    # Отправляем запрос партнёру
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Принять", callback_data=f"game_accept_{uid}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"game_decline_{uid}")
    )
    bot.send_message(partner_id,
        f"🎲 @{get_username(uid)} предлагает сыграть в крестики-нолики!",
        reply_markup=markup)
    bot.send_message(uid, "⌛ Ожидаем ответа собеседника...")
    # Временно запоминаем запрос
    games[chat_id] = {'status': 'pending', 'from': uid, 'to': partner_id}

def stop_game_command(message: Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['state'] != 'chatting':
        bot.send_message(message.chat.id, "❌ Ты не в чате")
        return
    chat_id = users[uid].get('chat_id')
    if chat_id not in games:
        bot.send_message(message.chat.id, "🎮 Нет активной игры")
        return
    end_game(chat_id)
    bot.send_message(message.chat.id, "🛑 Игра завершена")

# Обработка инлайн-кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data
    # Обработка выбора фильтра поиска
    if data.startswith('search_'):
        gender = data.split('_')[1]  # male, female, any
        if uid not in users or users[uid]['state'] != 'none':
            bot.answer_callback_query(call.id, "Недоступно сейчас")
            return
        bot.answer_callback_query(call.id, "Запускаем поиск")
        # Удаляем клавиатуру у сообщения
        try:
            bot.edit_message_text(
                f"Поиск: {gender}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except: pass
        find_partner(uid, gender, call.message)
        return

    # Обработка игры: принять/отклонить
    if data.startswith('game_accept_'):
        # Получаем инициатора игры
        try:
            initiator_id = int(data.split('_')[2])
        except:
            bot.answer_callback_query(call.id, "Ошибка")
            return
        if uid not in users or users[uid]['state'] != 'chatting':
            bot.answer_callback_query(call.id, "Ты не в чате")
            return
        chat_id = users[uid].get('chat_id')
        if chat_id not in games or games[chat_id].get('status') != 'pending':
            bot.answer_callback_query(call.id, "Запрос устарел")
            return
        game = games[chat_id]
        if game['to'] != uid:
            bot.answer_callback_query(call.id, "Не тебе предложили")
            return
        # Начинаем игру
        bot.answer_callback_query(call.id, "Игра началась!")
        try:
            bot.edit_message_text(
                "🎮 Игра начинается!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except: pass
        start_game(chat_id, initiator_id, uid)
        return

    if data.startswith('game_decline_'):
        try:
            initiator_id = int(data.split('_')[2])
        except:
            return
        if uid not in users or users[uid]['state'] != 'chatting':
            return
        chat_id = users[uid].get('chat_id')
        if chat_id in games and games[chat_id].get('status') == 'pending':
            # Удаляем запрос
            del games[chat_id]
            bot.answer_callback_query(call.id, "Отклонено")
            try:
                bot.edit_message_text(
                    "❌ Предложение отклонено",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
            except: pass
            bot.send_message(initiator_id, "❌ Собеседник отказался от игры")
        return

    # Обработка хода в игре: cell_<index>
    if data.startswith('cell_'):
        if uid not in users or users[uid]['state'] != 'chatting':
            bot.answer_callback_query(call.id, "Не в чате")
            return
        chat_id = users[uid].get('chat_id')
        if chat_id not in games or games[chat_id].get('status') != 'active':
            bot.answer_callback_query(call.id, "Игра неактивна")
            return
        game = games[chat_id]
        if game['current_turn'] != uid:
            bot.answer_callback_query(call.id, "Не твой ход!")
            return
        idx = int(data.split('_')[1])
        if game['board'][idx] != ' ':
            bot.answer_callback_query(call.id, "Клетка занята")
            return
        # Делаем ход
        symbol = 'X' if uid == game['player1'] else 'O'
        game['board'][idx] = symbol
        winner = check_winner(game['board'])
        if winner or board_full(game['board']):
            # Игра завершена
            win_id = None
            if winner == 'X':
                win_id = game['player1']
            elif winner == 'O':
                win_id = game['player2']
            # Показываем финальное поле (неактивное)
            markup = board_to_keyboard(game['board'], active=False)
            msg1_text = f"🎮 Игра (завершена)\n{'🏆 Победил @'+get_username(win_id) if win_id else '🤝 Ничья'}"
            msg2_text = msg1_text
            try:
                bot.edit_message_text(msg1_text,
                    chat_id=game['player1'], message_id=game['msg1_id'],
                    reply_markup=markup)
            except: pass
            try:
                bot.edit_message_text(msg2_text,
                    chat_id=game['player2'], message_id=game['msg2_id'],
                    reply_markup=markup)
            except: pass
            # Удаляем игру
            del games[chat_id]
        else:
            # Передаём ход другому
            game['current_turn'] = game['player2'] if uid == game['player1'] else game['player1']
            # Обновляем доски у обоих
            markup = board_to_keyboard(game['board'])
            turn_name = get_username(game['current_turn'])
            for pid, mid in [(game['player1'], game['msg1_id']), (game['player2'], game['msg2_id'])]:
                txt = f"🎮 Крестики-нолики\nХод: @{turn_name}" if pid != game['current_turn'] else "🎮 Твой ход!"
                try:
                    bot.edit_message_text(txt,
                        chat_id=pid, message_id=mid,
                        reply_markup=markup)
                except Exception as e:
                    print(f"Ошибка обновления у {pid}: {e}")
        bot.answer_callback_query(call.id, "Ход сделан")
        return

    bot.answer_callback_query(call.id, "Неизвестная команда")

def start_game(chat_id, player1, player2):
    board = create_game_board()
    games[chat_id] = {
        'status': 'active',
        'board': board,
        'player1': player1,
        'player2': player2,
        'current_turn': player1,
        'msg1_id': None,
        'msg2_id': None
    }
    # Отправляем игровые сообщения
    markup = board_to_keyboard(board)
    m1 = bot.send_message(player1, "🎮 Крестики-нолики\nТвой ход!", reply_markup=markup)
    m2 = bot.send_message(player2, f"🎮 Крестики-нолики\nХод: @{get_username(player1)}", reply_markup=markup)
    games[chat_id]['msg1_id'] = m1.message_id
    games[chat_id]['msg2_id'] = m2.message_id

# ==============================================
# ПЕРЕСЫЛКА СООБЩЕНИЙ
# ==============================================

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    uid = message.from_user.id
    if uid not in users:
        send_welcome(message)
        return
    if users[uid]['state'] != 'chatting':
        bot.send_message(message.chat.id, "ℹ️ Используй /find для поиска собеседника")
        return
    forward_message(message)

@bot.message_handler(content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_media(message: Message):
    uid = message.from_user.id
    if uid not in users or users[uid]['state'] != 'chatting':
        return
    forward_message(message)

# ==============================================
# ЗАПУСК
# ==============================================

if __name__ == '__main__':
    print("🔥 ANONIM CHAT 2.0 ЗАПУЩЕН! 🔥")
    print("👤 Создатель: Белый Дарон")
    print("📅", datetime.now())
    print("🎮 Игры, фильтр по полу, возраст – всё внутри!")
    bot.infinity_polling()

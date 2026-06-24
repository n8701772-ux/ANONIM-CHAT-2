import telebot
from telebot.types import Message
import time
from collections import defaultdict
from datetime import datetime
import random
import re
import requests
import threading
import os

# === ТОКЕН ИЗ ПЕРЕМЕННОЙ ОКРУЖЕНИЯ ИЛИ ВВОД В ТЕРМУКС ===
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("⚠️ Переменная окружения TOKEN не найдена.")
    TOKEN = input("👉 Введите ваш токен Telegram-бота: ").strip()
    if not TOKEN:
        print("❌ Без токена запуск невозможен!")
        import sys
        sys.exit(1)

# === АВТОПИНГ ДЛЯ RENDER (НЕ ЗАСЫПАЕТ) ===
RENDER_URL = os.getenv("RENDER_APP_URL", "https://dark-chat.onrender.com")

def keep_alive():
    while True:
        try:
            # Пингуем как Render, так и сервера Telegram для поддержания сокета
            response = requests.get(RENDER_URL, timeout=10)
            print(f"[Пинг] Статус: {response.status_code} в {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[Пинг] Ожидание сети... ({e})")
        time.sleep(120) # Уменьшили интервал до 2 минут для супер-стабильности

threading.Thread(target=keep_alive, daemon=True).start()

bot = telebot.TeleBot(TOKEN)

# Хранилища данных
users = {}
waiting_list = []
chats = {}
games = {}

# ==============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================

def init_user(uid, username="Пользователь"):
    if uid not in users:
        users[uid] = {
            "state": "none",
            "partner_id": None,
            "chat_id": None,
            "username": username,
            "gender": None,
            "age": None,
            "search_gender": 'any',
            "last_filter": 'any',
            "rep": 0  # КРУТОЕ: Система репутации
        }

def gender_emoji(g):
    if g == 'male': return '🚹'
    if g == 'female': return '🚺'
    return '⚧'

def partner_info(uid):
    u = users.get(uid, {})
    g = u.get('gender')
    a = u.get('age')
    rep = u.get('rep', 0)
    parts = []
    if g:
        parts.append(f"Пол: {gender_emoji(g)} {'мужской' if g=='male' else 'женский'}")
    if a is not None:
        parts.append(f"Возраст: {a}")
    parts.append(f"⭐️ Репутация: {rep}")
    return '\n'.join(parts)

# ==============================================
# ИГРА КРЕСТИКИ-НОЛИКИ
# ==============================================

WIN_COMBOS = [[0,1,2], [3,4,5], [6,7,8], [0,3,6], [1,4,7], [2,5,8], [0,4,8], [2,4,6]]

def create_game_board():
    return [' ' for _ in range(9)]

def board_to_keyboard(board, active=True):
    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            cell = board[idx]
            if cell == 'X': text = '❌'
            elif cell == 'O': text = '⭕'
            else: text = '▫️'
            row.append(telebot.types.InlineKeyboardButton(
                text=text,
                callback_data=f"cell_{idx}" if active else "none"
            ))
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
    if chat_id in games:
        g = games.pop(chat_id)
        text = f"🏆 Победил один из игроков!" if winner_id else "🤝 Ничья!"
        for pid, mid in [(g['player1'], g['msg1_id']), (g['player2'], g['msg2_id'])]:
            try: bot.edit_message_text(f"Игра окончена!\n{text}", chat_id=pid, message_id=mid)
            except: pass

# ==============================================
# ОСНОВНЫЕ ФУНКЦИИ БОТА
# ==============================================

def send_welcome(message):
    uid = message.from_user.id
    init_user(uid, message.from_user.username)
    bot.send_message(
        message.chat.id,
        "🔥 *DARK CHAT — СУПЕР СКОРОСТЬ* 🔥\n\n"
        "Абсолютная свобода общения без цензуры!\n"
        "Работает 24/7 без задержек.\n\n"
        "👤 *Создатель: Белый Дарон*\n\n"
        "📌 *Команды управления:* \n"
        "➕ `/find` – найти собеседника\n"
        "⏭ `/next` – следующий чат\n"
        "🚪 `/leave` – выйти из чата\n\n"
        "👤 *Профиль и фичи:* \n"
        "ℹ️ `/profile` – твой профиль и карма\n"
        "⚧ `/setgender` [male/female/none]\n"
        "🎂 `/setage` [возраст]\n\n"
        "🎉 *Интерактив в чате:* \n"
        "🎮 `/game` – сыграть в Крестики-Нолики\n"
        "🎲 `/dice` – бросить кубик анонимно\n"
        "👍 `/like` / 👎 `/dislike` – оценить собеседника",
        parse_mode='Markdown'
    )

def show_profile(uid, chat_id):
    init_user(uid)
    u = users[uid]
    g = u.get('gender')
    gender_display = 'не указан' if not g else ('мужской' if g=='male' else 'женский')
    bot.send_message(
        chat_id,
        f"👤 *Твой профиль*\n"
        f"🆔 ID: `{uid}`\n"
        f"⚧ Пол: {gender_display}\n"
        f"🎂 Возраст: {u.get('age', 'не указан')}\n"
        f"⭐️ Репутация: *{u.get('rep', 0)}* пунктов\n"
        f"🔍 Последний фильтр поиска: {u.get('last_filter','any')}",
        parse_mode='Markdown'
    )

def start_find(message):
    uid = message.from_user.id
    init_user(uid)
    if users[uid]['state'] != 'none':
        bot.send_message(message.chat.id, "❌ Сначала выйдите из текущего диалога: /leave")
        return
    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        telebot.types.InlineKeyboardButton("🚹 Парня", callback_data="search_male"),
        telebot.types.InlineKeyboardButton("🚺 Девушку", callback_data="search_female"),
        telebot.types.InlineKeyboardButton("⚧ Любого", callback_data="search_any")
    )
    bot.send_message(message.chat.id, "✨ Кого вы хотите найти?", reply_markup=markup)

def find_partner(uid, search_gender, message=None):
    init_user(uid)
    if users[uid]['state'] != 'none': return
    users[uid]['state'] = 'waiting'
    users[uid]['search_gender'] = search_gender
    users[uid]['last_filter'] = search_gender
    if uid not in waiting_list:
        waiting_list.append(uid)
    if message:
        bot.send_message(message.chat.id, "🔍 Поиск запущен... Ищем свободного собеседника...")
    try_find_pair()

def try_find_pair():
    i = 0
    while i < len(waiting_list):
        uid1 = waiting_list[i]
        if uid1 not in users or users[uid1]['state'] != 'waiting':
            waiting_list.pop(i)
            continue
        found = -1
        for j in range(i+1, len(waiting_list)):
            uid2 = waiting_list[j]
            if uid2 not in users or users[uid2]['state'] != 'waiting': continue
            
            sg1 = users[uid1].get('search_gender', 'any')
            sg2 = users[uid2].get('search_gender', 'any')
            gender1 = users[uid1].get('gender')
            gender2 = users[uid2].get('gender')
            
            if (sg1 == 'any' or gender2 == sg1) and (sg2 == 'any' or gender1 == sg2):
                found = j
                break
        if found != -1:
            uid2 = waiting_list.pop(found)
            uid1 = waiting_list.pop(i)
            chat_id = f"{uid1}_{uid2}_{int(time.time())}"
            chats[chat_id] = {"user1": uid1, "user2": uid2}
            users[uid1].update({"state": "chatting", "partner_id": uid2, "chat_id": chat_id})
            users[uid2].update({"state": "chatting", "partner_id": uid1, "chat_id": chat_id})
            
            bot.send_message(uid1, f"🎉 *Собеседник найден!*\n\n{partner_info(uid2)}\n\n✍️ Пишите сообщение...", parse_mode='Markdown')
            bot.send_message(uid2, f"🎉 *Собеседник найден!*\n\n{partner_info(uid1)}\n\n✍️ Пишите сообщение...", parse_mode='Markdown')
        else:
            i += 1

def leave_chat(message):
    uid = message.from_user.id
    if uid not in users: return
    state = users[uid]['state']
    if state == 'none':
        bot.send_message(message.chat.id, "❌ Вы сейчас не находитесь в поиске или чате.")
        return
    chat_id = users[uid].get('chat_id')
    if chat_id and chat_id in games: end_game(chat_id)
    
    if state == 'waiting':
        if uid in waiting_list: waiting_list.remove(uid)
        users[uid]['state'] = 'none'
        bot.send_message(message.chat.id, "🔎 Поиск остановлен.")
        return
        
    partner_id = users[uid]['partner_id']
    for usr in [uid, partner_id]:
        if usr in users:
            users[usr].update({"state": "none", "partner_id": None, "chat_id": None})
    bot.send_message(message.chat.id, "🚪 Вы покинули чат.")
    bot.send_message(partner_id, "❌ Собеседник отключился от чата.")

def handle_rate(message, rate_type):
    uid = message.from_user.id
    if uid not in users or users[uid]['state'] != 'chatting':
        bot.send_message(message.chat.id, "❌ Оценивать можно только в чате!")
        return
    pid = users[uid]['partner_id']
    init_user(pid)
    if rate_type == 'like':
        users[pid]['rep'] += 1
        bot.send_message(message.chat.id, "👍 Вы поставили лайк собеседнику!")
        bot.send_message(pid, "🔥 Кто-то оценил вас положительно! Ваша репутация выросла.")
    else:
        users[pid]['rep'] -= 1
        bot.send_message(message.chat.id, "👎 Вы поставили дизлайк.")

def forward_message(message):
    uid = message.from_user.id
    u = users.get(uid)
    if not u or u['state'] != 'chatting': return
    pid = u['partner_id']
    try:
        if message.content_type == 'text': bot.send_message(pid, message.text)
        elif message.content_type == 'photo': bot.send_photo(pid, message.photo[-1].file_id, caption=message.caption)
        elif message.content_type == 'video': bot.send_video(pid, message.video.file_id, caption=message.caption)
        elif message.content_type == 'sticker': bot.send_sticker(pid, message.sticker.file_id)
        elif message.content_type == 'voice': bot.send_voice(pid, message.voice.file_id)
        elif message.content_type == 'audio': bot.send_audio(pid, message.audio.file_id, caption=message.caption)
        elif message.content_type == 'dice': bot.send_dice(pid, emoji=message.dice.emoji)
    except:
        bot.send_message(uid, "❌ Ошибка отправки медиа.")

# ==============================================
# ОБРАБОТЧИКИ КОМАНД
# ==============================================

@bot.message_handler(commands=['start', 'help', 'find', 'leave', 'next', 'profile', 'like', 'dislike', 'dice', 'game', 'stopgame'])
def commands_router(message):
    cmd = message.text.split()[0].lower()
    uid = message.from_user.id
    
    if cmd == '/start' or cmd == '/help': send_welcome(message)
    elif cmd == '/find': start_find(message)
    elif cmd == '/leave': leave_chat(message)
    elif cmd == '/next':
        if uid in users and users[uid]['state'] == 'chatting': leave_chat(message)
        elif uid in users and users[uid]['state'] == 'waiting':
            if uid in waiting_list: waiting_list.remove(uid)
            users[uid]['state'] = 'none'
        init_user(uid)
        find_partner(uid, users[uid].get('last_filter', 'any'), message)
    elif cmd == '/profile': show_profile(uid, message.chat.id)
    elif cmd == '/like': handle_rate(message, 'like')
    elif cmd == '/dislike': handle_rate(message, 'dislike')
    elif cmd == '/dice':
        if uid in users and users[uid]['state'] == 'chatting':
            m = bot.send_dice(message.chat.id)
            bot.send_dice(users[uid]['partner_id'])
        else:
            bot.send_message(message.chat.id, "❌ Бросать кубик можно только в активном чате!")
    elif cmd == '/game':
        if uid not in users or users[uid]['state'] != 'chatting':
            bot.send_message(message.chat.id, "❌ Начать игру можно только находясь в чате.")
            return
        chat_id = users[uid]['chat_id']
        if chat_id in games: return
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ Играем!", callback_data=f"g_a_{uid}"),
                   telebot.types.InlineKeyboardButton("❌ Отказ", callback_data=f"g_d_{uid}"))
        bot.send_message(users[uid]['partner_id'], "🎲 Собеседник зовет вас играть в Крестики-Нолики!", reply_markup=markup)
        bot.send_message(uid, "⏳ Ждем ответа оппонента...")
        games[chat_id] = {'status': 'pending', 'from': uid, 'to': users[uid]['partner_id']}
    elif cmd == '/stopgame':
        if uid in users and users[uid].get('chat_id') in games:
            end_game(users[uid]['chat_id'])
            bot.send_message(message.chat.id, "🛑 Игра остановлена.")

@bot.message_handler(commands=['setgender', 'setage'])
def settings_handler(message):
    uid = message.from_user.id
    init_user(uid)
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, f"Использование команды: {parts[0]} [значение]")
        return
    val = parts[1].lower()
    if parts[0] == '/setgender':
        if val in ('male', 'м'): users[uid]['gender'] = 'male'
        elif val in ('female', 'ж'): users[uid]['gender'] = 'female'
        else: users[uid]['gender'] = None
        bot.send_message(message.chat.id, "✅ Пол успешно обновлен.")
    elif parts[0] == '/setage':
        try:
            age = int(val)
            if 1 <= age <= 100:
                users[uid]['age'] = age
                bot.send_message(message.chat.id, f"✅ Возраст изменен на {age}")
            else: raise ValueError
        except: bot.send_message(message.chat.id, "❌ Неверный формат возраста.")

# ==============================================
# КОЛБЭКИ И ИНЛАЙН-КНОПКИ
# ==============================================

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    uid = call.from_user.id
    data = call.data
    
    if data.startswith('search_'):
        gender = data.split('_')[1]
        init_user(uid)
        if users[uid]['state'] != 'none': return
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        find_partner(uid, gender, call.message)
        
    elif data.startswith('g_a_'): # Принять игру
        init_user(uid)
        cid = users[uid].get('chat_id')
        if cid in games and games[cid]['status'] == 'pending' and games[cid]['to'] == uid:
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            p1, p2 = games[cid]['from'], uid
            board = create_game_board()
            games[cid] = {'status': 'active', 'board': board, 'player1': p1, 'player2': p2, 'current_turn': p1}
            markup = board_to_keyboard(board)
            m1 = bot.send_message(p1, "🎮 Твой ход! (Вы ходите Крестиками)", reply_markup=markup)
            m2 = bot.send_message(p2, "🎮 Ожидание хода противника...", reply_markup=markup)
            games[cid]['msg1_id'] = m1.message_id
            games[cid]['msg2_id'] = m2.message_id

    elif data.startswith('g_d_'): # Отклонить игру
        cid = users.get(uid, {}).get('chat_id')
        if cid in games:
            p1 = games[cid]['from']
            del games[cid]
            try: bot.edit_message_text("❌ Приглашение отклонено.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except: pass
            bot.send_message(p1, "❌ Собеседник отклонил приглашение к игре.")

    elif data.startswith('cell_'):
        cid = users.get(uid, {}).get('chat_id')
        if cid not in games or games[cid]['status'] != 'active' or games[cid]['current_turn'] != uid:
            bot.answer_callback_query(call.id, "Сейчас не ваш ход!")
            return
        game = games[cid]
        idx = int(data.split('_')[1])
        if game['board'][idx] != ' ': return
        
        symbol = 'X' if uid == game['player1'] else 'O'
        game['board'][idx] = symbol
        winner = check_winner(game['board'])
        
        if winner or board_full(game['board']):
            markup = board_to_keyboard(game['board'], active=False)
            res_txt = "🎮 Игра завершена! " + ("🏆 Вы победили!" if winner else "🤝 Ничья!")
            opp_txt = "🎮 Игра завершена! " + ("💀 Вы проиграли." if winner else "🤝 Ничья!")
            bot.send_message(uid, res_txt)
            bot.send_message(game['player2'] if uid == game['player1'] else game['player1'], opp_txt)
            end_game(cid)
        else:
            game['current_turn'] = game['player2'] if uid == game['player1'] else game['player1']
            markup = board_to_keyboard(game['board'])
            for pid, mid in [(game['player1'], game['msg1_id']), (game['player2'], game['msg2_id'])]:
                txt = "🎮 Ваш ход!" if pid == game['current_turn'] else "🎮 Ожидание хода противника..."
                try: bot.edit_message_text(txt, chat_id=pid, message_id=mid, reply_markup=markup)
                except: pass
        bot.answer_callback_query(call.id)

# ==============================================
# ОБРАБОТКА ЛЮБЫХ СООБЩЕНИЙ
# ==============================================

@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'voice', 'audio', 'dice'])
def global_message_handler(message):
    uid = message.from_user.id
    if uid not in users or users[uid]['state'] == 'none':
        bot.send_message(message.chat.id, "ℹ️ Напишите `/find`, чтобы найти тайного собеседника.", parse_mode='Markdown')
        return
    if users[uid]['state'] == 'waiting':
        bot.send_message(message.chat.id, "⏳ Секунду, мы всё ещё ищем пару. Наберитесь терпения или используйте `/leave`.")
        return
    forward_message(message)

# ==============================================
# ЗАПУСК И СТАБИЛИЗАЦИЯ ПОД ТЕРМУКС / RENDER
# ==============================================

if __name__ == '__main__':
    print("🚀 СКОРОСТНОЙ АНОНИМНЫЙ ЧАТ ЗАПУЩЕН!")
    print("⚡ Режим infinity_polling включен (защита от падений и пинги активны)")
    bot.remove_webhook()
    # long_polling_timeout держит соединение открытым и моментально обрабатывает входящие апдейты без задержек
    bot.infinity_polling(timeout=60, long_polling_timeout=5)

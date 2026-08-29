import telebot
import random
import requests
import json
import re
import os
import threading
from flask import Flask
from io import BytesIO

# === НАСТРОЙКИ ===
TOKEN = "8991988855:AAFL12okgGp6WfGuSVHTxHWA1MxaoM25-30"
WIKI_URL = "https://ins1826.github.io/zazer_kalye_wiki_bot/"
OWNER_ID = 412598271

# Ссылка на data.json на GitHub
DATA_URL = "https://raw.githubusercontent.com/ins1826/zazer_kalye_wiki_bot/refs/heads/main/data.json"

# Базовый URL для картинок (GitHub Pages)
IMAGES_BASE_URL = "https://ins1826.github.io/zazer_kalye_wiki_bot/"

bot = telebot.TeleBot(TOKEN)

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
app = Flask(__name__)

@app.route('/')
def health_check():
    return "🪞 Бот Зазеркалья работает!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# === ЗАГРУЗКА ДАННЫХ ===
wiki_data = {}

def load_wiki_data():
    global wiki_data
    try:
        response = requests.get(DATA_URL, timeout=10)
        if response.status_code == 200:
            wiki_data = response.json()
            chars_count = len(wiki_data.get('characters', []))
            print(f"✅ Данные загружены: {chars_count} персонажей")
            return True
        else:
            print(f"❌ Ошибка загрузки: код {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

load_wiki_data()

feedback_mode = {}
search_results_cache = {}

# === ФУНКЦИИ ===
def parse_wiki_links(text):
    if not text:
        return ""
    text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', text)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    return text

def escape_html(text):
    if not text:
        return ""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def get_main_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("🎲 Ещё персонажа", callback_data='random_char'),
        telebot.types.InlineKeyboardButton("✉️ Написать автору", callback_data='feedback_mode')
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton("📖 Открыть Энциклопедию", web_app=telebot.types.WebAppInfo(url=WIKI_URL))
    )
    return keyboard

def send_item_card(chat_id, item, label, send_photo=True):
    """Отправляет карточку элемента с картинкой (если есть)"""
    text = f"{label}: <b>{escape_html(item['name'])}</b>\n"
    if item.get('type'): text += f"🏷️ {escape_html(item['type'])}\n"
    if item.get('short'): text += f"\n📜 {escape_html(parse_wiki_links(item['short']))}\n"
    if item.get('full'):
        full_text = parse_wiki_links(item['full'])
        text += f"\n{escape_html(full_text[:500] + '...' if len(full_text) > 500 else full_text)}\n"
    if item.get('episodes') and len(item['episodes']) > 0:
        text += f"\n Эпизоды: {', '.join([f'ep.{e}' for e in item['episodes'][:5]])}"
    
    # Отправляем с картинкой (если есть и включена отправка фото)
    if send_photo and item.get('image'):
        try:
            image_url = IMAGES_BASE_URL + item['image']
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                # Отправляем фото с текстом в caption
                photo_file = BytesIO(response.content)
                bot.send_photo(chat_id, photo_file, caption=text, parse_mode="HTML", reply_markup=get_main_keyboard())
                return
        except Exception as e:
            print(f"❌ Не удалось отправить картинку: {e}")
            # Если не получилось отправить картинку, отправляем просто текст
    
    # Если нет картинки или не удалось отправить — отправляем текст
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_main_keyboard())

# === 1. КОМАНДА /start ===
@bot.message_handler(commands=['start'])
def start(message):
    text = """ <b>Добро пожаловать в Зазеркалье!</b>

Ты стоишь на пороге мира, где Хрычи растут на огороде у бабы Жули, а в подпольном щекоточном клубе высокие требования к кандидатам...

💡 Напиши имя персонажа (например, "Баба Жуля") — я найду его
💡 Или используй кнопки ниже!"""
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# === 2. ОБРАБОТКА КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == 'random_char':
        send_random_character(call.message.chat.id)
        bot.answer_callback_query(call.id, " Держи нового персонажа!")
    
    elif call.data == 'feedback_mode':
        feedback_mode[call.from_user.id] = True
        cancel_kb = telebot.types.InlineKeyboardMarkup()
        cancel_kb.add(telebot.types.InlineKeyboardButton("❌ Отменить", callback_data='cancel_feedback'))
        bot.send_message(
            call.message.chat.id, 
            "✉️ <b>Режим обратной связи включён!</b>\n\nНапиши своё сообщение, и я передам его помощнице Грибного Архивариуса. \n\n<i>(Если передумал, нажми кнопку ниже)</i>",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "✉️ Режим активирован!")

    elif call.data == 'cancel_feedback':
        if call.from_user.id in feedback_mode:
            del feedback_mode[call.from_user.id]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ <b>Режим обратной связи отменён.</b>\n\nЕсли захочешь написать снова, просто нажми кнопку «✉️ Написать автору» в главном меню.",
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "Режим отменён")
        
    elif call.data == 'cancel_search':
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ <b>Поиск отменён.</b>\n\nНапиши другое имя или используй кнопки ниже:",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
        bot.answer_callback_query(call.id, "Поиск отменён")
        
    elif call.data.startswith('select_'):
        result_id = call.data.replace('select_', '')
        user_id = call.from_user.id
        
        if user_id in search_results_cache and result_id in search_results_cache[user_id]:
            result = search_results_cache[user_id][result_id]
            send_item_card(call.message.chat.id, result['item'], result['label'])
            del search_results_cache[user_id]
        
        bot.answer_callback_query(call.id, "Выбрано!")

# === 3. КОМАНДА /random ===
@bot.message_handler(commands=['random'])
def random_character(message):
    send_random_character(message.chat.id)

def send_random_character(chat_id):
    if not wiki_data or 'characters' not in wiki_data:
        bot.send_message(chat_id, "❌ Ой, данные ещё не загрузились. Попробуй через минуту!")
        return
    char = random.choice(wiki_data['characters'])
    send_item_card(chat_id, char, "👤 Персонаж")

# === 4. ПОИСК С УМНЫМ ВЫБОРОМ ===
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text.startswith('/'):
        if message.text.lower() == '/cancel':
            if message.from_user.id in feedback_mode:
                del feedback_mode[message.from_user.id]
                bot.send_message(message.chat.id, "❌ <b>Режим обратной связи отменён.</b>", parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                bot.send_message(message.chat.id, "У тебя и так не включён режим обратной связи.", reply_markup=get_main_keyboard())
        return
    
    if feedback_mode.get(message.from_user.id):
        username = f"@{message.from_user.username}" if message.from_user.username else "Без username"
        forward_text = f"💬 <b>Новое сообщение!</b>\n👤 <b>От:</b> {escape_html(message.from_user.first_name)} ({escape_html(username)})\n🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n📝 <b>Текст:</b>\n{escape_html(message.text)}"
        try:
            bot.send_message(OWNER_ID, forward_text, parse_mode="HTML")
            bot.send_message(message.chat.id, "✅ Спасибо! Сообщение отправлено помощнице Грибного Архивариуса! 🪞✨", reply_markup=get_main_keyboard(), parse_mode="HTML")
        except:
            bot.send_message(message.chat.id, "❌ Не удалось отправить сообщение.")
        del feedback_mode[message.from_user.id]
        return
    
    if not wiki_data:
        bot.send_message(message.chat.id, " Данные ещё загружаются!")
        return
    
    query = message.text.strip().lower()
    found_items = []
    categories = {'characters': '👤 Персонаж', 'locations': '️ Локация', 'items': ' Предмет', 'events': '🎭 Ивент', 'organizations': '🏛️ Организация', 'races': '🧬 Раса'}
    
    for category, label in categories.items():
        if category not in wiki_data: continue
        for item in wiki_data[category]:
            if query == item.get('name', '').lower() or query in item.get('name', '').lower():
                found_items.append({'category': category, 'label': label, 'item': item})
    
    if not found_items:
        bot.send_message(message.chat.id, "🤔 Хм, я не нашёл такого в базе. Попробуй написать точное имя или используй кнопки:", reply_markup=get_main_keyboard(), parse_mode="HTML")
        return
    
    if len(found_items) == 1:
        result = found_items[0]
        send_item_card(message.chat.id, result['item'], result['label'])
        return
    
    if len(found_items) <= 6:
        keyboard = telebot.types.InlineKeyboardMarkup()
        user_id = message.from_user.id
        search_results_cache[user_id] = {}
        
        for i, result in enumerate(found_items):
            button_text = f"{result['label']} {result['item']['name']}"
            button_id = f"result_{i}"
            search_results_cache[user_id][button_id] = result
            keyboard.add(telebot.types.InlineKeyboardButton(button_text, callback_data=f'select_{button_id}'))
        
        keyboard.add(telebot.types.InlineKeyboardButton("❌ Отмена", callback_data='cancel_search'))
        
        bot.send_message(
            message.chat.id, 
            f"🔍 Найдено {len(found_items)} результатов. Что именно ты ищешь?",
            reply_markup=keyboard
        )
        return
    
    text = f" Найдено {len(found_items)} результатов. Напиши номер нужного:\n\n"
    for i, result in enumerate(found_items[:10], 1):
        text += f"{i}. {result['label']} {result['item']['name']}\n"
    
    if len(found_items) > 10:
        text += f"\n...и ещё {len(found_items) - 10} результатов. Уточни запрос!"
    
    user_id = message.from_user.id
    search_results_cache[user_id] = {str(i): result for i, result in enumerate(found_items[:10], 1)}
    
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard())

@bot.message_handler(content_types=['text'])
def handle_number_selection(message):
    if message.text.isdigit():
        user_id = message.from_user.id
        num = message.text
        
        if user_id in search_results_cache and num in search_results_cache[user_id]:
            result = search_results_cache[user_id][num]
            send_item_card(message.chat.id, result['item'], result['label'])
            del search_results_cache[user_id]
            return

# === 5. КОМАНДА /reload ===
@bot.message_handler(commands=['reload'])
def reload_data(message):
    if message.from_user.id != OWNER_ID:
        bot.send_message(message.chat.id, "❌ Эта команда только для администратора!")
        return
    if load_wiki_data():
        bot.send_message(message.chat.id, f"✅ Данные перезагружены! {len(wiki_data.get('characters', []))} персонажей.")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось перезагрузить данные.")

print("🤖 Бот запущен и готов к работе 24/7!")
bot.polling()
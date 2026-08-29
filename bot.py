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

# === СЛОВАРЬ СТИКЕРОВ ===
STICKERS = {
    "Коленыч": ["CAACAgIAAxkBAAFTCuVqk1Gsjo9H5j009LQ1ZAuFGdj5OAACzLIAAsem0UsmUDzySoinAT0E"],
    "Акакий Куролесов": [
        "CAACAgIAAxkBAAFTCulqk1GyFTtCxtb7Za0F3Cy3evGMlgAClKQAAvjJ0UsRpht3yVpbgT0E",
        "CAACAgIAAxkBAAFTCutqk1G2rdNWLfg5OcPX-V8jMKNOxwACHasAAshRgEgwiGMJ1hm9tD0E",
        "CAACAgIAAxkBAAFTCvdqk1HLemkwR7MVjrWCb_1y4G3newACwJcAAshsKUj97YMpXPBZzj0E"
    ],
    "ПВЗ": ["CAACAgIAAxkBAAFTCu1qk1G54034Vd5iNNbh37zYSJTzJgACX7MAArNy0EsGJFZFHJ0JkD0E"],
    "Поленыч": ["CAACAgIAAxkBAAFTCu1qk1G54034Vd5iNNbh37zYSJTzJgACX7MAArNy0EsGJFZFHJ0JkD0E"],
    "Доктор Эпикантус": ["CAACAgIAAxkBAAFTCu9qk1G8AeVfrDLSh3tzkiMWOpB1rgACAaoAAu2K0EsX60LcXYD2eT0E"],
    "Вальтасар": [
        "CAACAgIAAxkBAAFTCu9qk1G8AeVfrDLSh3tzkiMWOpB1rgACAaoAAu2K0EsX60LcXYD2eT0E",
        "CAACAgIAAxkBAAFTCxBqk1HzGP-t3w6SAgVqUiWoWU62uAACpK0AAhDD6EtXJKbixbcWsj0E",
        "CAACAgIAAxkBAAFTCvFqk1HBuJvUCK_URUjQvRhQBhlBzwACT7EAAnDdeUgzAnv7tV7Lpz0E",
        "CAACAgIAAxkBAAFTCxJqk1H2JAmmPduOe5EaoTcoKVMXWQACy5cAAmcNgUgPcTdR0xGnjj0E"
    ],
    "Выбор зелья Вальтасара": ["CAACAgIAAxkBAAFTCxJqk1H2JAmmPduOe5EaoTcoKVMXWQACy5cAAmcNgUgPcTdR0xGnjj0E"],
    "Истуканус": ["CAACAgIAAxkBAAFTCvNqk1HFnkAu7y3eqk-Ri0O5dt9HHAACz6UAAjph0EvH342gWx6sSD0E"],
    "Дон Окунь": ["CAACAgIAAxkBAAFTCvVqk1HIDHRo4UZ5AAHL9FEguEMwchUAAtmxAALbF9FLxtdZhV1AFWg9BA"],
    "Пацаноиды": [
        "CAACAgIAAxkBAAFTCvlqk1HOUUaDU7_Gje-KPOnPmAK-hAACC6sAAu2o0Usm-vgvixRWAT0E",
        "CAACAgIAAxkBAAFTCvtqk1HSmuuI5qVJW7k0jqC58q6fUgACfKkAAq8cEEidpolWgmHh6D0E",
        "CAACAgIAAxkBAAFTCttqk1DdCtK140wd2E4jXQ9TfIIu1QACvqAAAryMKEhxcEib__xeMD0E"
    ],
    "Бобыли": ["CAACAgIAAxkBAAFTCv1qk1HWAAHFIUt_D8fnJQ7VDzf-oEYAAn2pAALJ19FLcb1M3EVoQiY9BA"],
    "Лесной бобыль": ["CAACAgIAAxkBAAFTCv1qk1HWAAHFIUt_D8fnJQ7VDzf-oEYAAn2pAALJ19FLcb1M3EVoQiY9BA"],
    "Сатор Арепыч": ["CAACAgIAAxkBAAFTCv9qk1Ha_JZZEfQtkTmCJF845cD2ygACTKIAAoJr4UuN6bkqhtCziz0E"],
    "Кокалка": [
        "CAACAgIAAxkBAAFTCv9qk1Ha_JZZEfQtkTmCJF845cD2ygACTKIAAoJr4UuN6bkqhtCziz0E",
        "CAACAgIAAxkBAAFTC0Jqk1JR0-192CVpyXQKb_g3g8KSVgACxqkAAqClEEgm05Dj2lIaJj0E"
    ],
    "ОНО": ["CAACAgIAAxkBAAFTCwNqk1HeGIHzrHv2lzJ9J3fERtE7gwACzZ4AApCw2UtOrQPh_6vRLT0E"],
    "ОНА": ["CAACAgIAAxkBAAFTCwVqk1HhaDZkH5-DDgPKplFltizbBgAC8KMAAvfm0EtpGJW18CY4Wz0E"],
    "Евдокия": ["CAACAgIAAxkBAAFTCwpqk1HnIWRNbybqnbYghqct4MI83AACLrAAArjA2Ev3WAy5Y5T4-D0E"],
    "Михаил": ["CAACAgIAAxkBAAFTCwxqk1HrLkV0epDp_CzD5jaMbMRLMAAC6JsAAhIf0UuDw-f0HDDRID0E"],
    "Пахомий": ["CAACAgIAAxkBAAFTCw5qk1HvOFXtMGu1YBXrwCJXwkfIlgAC86UAAudtIEh4ZVIU35iM5T0E"],
    "Раз - и квас!": ["CAACAgIAAxkBAAFTCxBqk1HzGP-t3w6SAgVqUiWoWU62uAACpK0AAhDD6EtXJKbixbcWsj0E"],
    "Господин Кривин": ["CAACAgIAAxkBAAFTCxRqk1H6dccOUWvXlD9xnP1vAceQ7gAC2qYAAskAAdBLRBDemo10hOI9BA"],
    "Дядюшка Фантасмагор": ["CAACAgIAAxkBAAFTCxZqk1H-izBaJzB5qhqHPXfW8zu-lAACE6AAAnNr0UunCaQnVthVxz0E"],
    "Подводный Гоша": ["CAACAgIAAxkBAAFTCxhqk1IB8CvbxoWJqDZ5IJOTUDBvAwAC1bMAAunF0UtMTycOMn4pwj0E"],
    "Тётя Варя": ["CAACAgIAAxkBAAFTCxpqk1IGLKzZooWfN1rsvmY8Q0sZKQACH6sAAmDe0Eub8IX0xiSsVj0E"],
    "Подпольный щекоточный клуб": ["CAACAgIAAxkBAAFTCxpqk1IGLKzZooWfN1rsvmY8Q0sZKQACH6sAAmDe0Eub8IX0xiSsVj0E"],
    "Евген": ["CAACAgIAAxkBAAFTCxxqk1IJZDaAw36sYmxQKAskDj9J-QACmZ0AAqs28Es0y3Yjmx1SOT0E"],
    "Грибной Архивариус": ["CAACAgIAAxkBAAFTCx5qk1IOtXIvl3ToezJ_gMkN5qnjKAACaKoAAugQ0Euu9mYXxOXkBz0E"],
    "Баба Жуля": ["CAACAgIAAxkBAAFTCyBqk1IRw3ITxXZG4PJpIuFg1iMjmgACw6sAAv8z4EvMtzrYEkFeFj0E"],
    "Толстомясочка": ["CAACAgIAAxkBAAFTCyJqk1IV62G1A4Faet3OXCCJ0IjqbwACOrIAAlhtmEi0D0sCHKoptD0E"],
    "Жадность на лайке": ["CAACAgIAAxkBAAFTCyRqk1IY2Kp4vS5cnCmWbE4Mrm4eTgACUJwAAqhm-Etas7UTJD7a1D0E"],
    "Зукя": ["CAACAgIAAxkBAAFTCyZqk1Ic0gxZ96ktz6H5ERlSkbDmRQAC958AAmQnIEh5nzsq_mLwpT0E"],
    "Пуча": ["CAACAgIAAxkBAAFTCyhqk1IfkSXFCfT76G-1ugGFNudhfwAC7aAAAmc1KEgL2MpnC255Uj0E"],
    "Борька": ["CAACAgIAAxkBAAFTCypqk1IiUHkCqgXOm4Ff_pYIwFyyEAACTLQAAl3l0Es1mt5r9M1jSj0E"],
    "Провансалла": ["CAACAgIAAxkBAAFTCyxqk1IlkgNo1-3O2pkW-jHu3GrqdgACEaUAAu0P2Utv4hCU8sEEHT0E"],
    "Майонезные тётеньки": ["CAACAgIAAxkBAAFTCyxqk1IlkgNo1-3O2pkW-jHu3GrqdgACEaUAAu0P2Utv4hCU8sEEHT0E"],
    "Хрычи": ["CAACAgIAAxkBAAFTCy5qk1IoZNGmrhN9Ym7wNWUbjAjrwAAC4KsAAsZB0UspKcWE_kUhDj0E"],
    "Смоломаз": ["CAACAgIAAxkBAAFTCzRqk1Ivq11JdPIdsuEYCEuKg1ZHzwACKaMAAmHV2UtDtpNWrfgzED0E"],
    "Морковные пятки": ["CAACAgIAAxkBAAFTCzZqk1IzUihVY8XrlrYBcAnkhWoesQACc6IAAqhV2Uu-uIKpmJJHIz0E"],
    "Битубисас": ["CAACAgIAAxkBAAFTCzhqk1I2AAF3jMSbbaaN-KneqgXpqgEAAl-cAAITTtlLxseuKXPD9WM9BA"],
    "Бубоня": ["CAACAgIAAxkBAAFTCzpqk1I5u6QWo7JOLuzF_1rnCFjEEwACF6UAAusb2EvHY-wO3NeEUj0E"],
    "Синие ящеры": ["CAACAgIAAxkBAAFTCzpqk1I5u6QWo7JOLuzF_1rnCFjEEwACF6UAAusb2EvHY-wO3NeEUj0E"],
    "Реутень": [
        "CAACAgIAAxkBAAFTCzxqk1I8hphL34UUaU7PNtB3mduoMQACfKQAAtJd4EukOo_gKnt4CD0E",
        "CAACAgIAAxkBAAFTCz5qk1JDGiU9yHf7PBL2LqVOU8VFzgACoqgAAr2B4EuYxuf2RyjrjD0E"
    ],
    "Подмыхан": ["CAACAgIAAxkBAAFTC0Bqk1JM6E8ml8jD4rOAL2e9LMIHnQACO6gAAkkJ6EtV-eZwjcTAND0E"],
    "Лесной Курбак": ["CAACAgIAAxkBAAFTC4Bqk1KxejJOThJhHp1WYk5mB-k3mgAC16cAAvHmmEhvFvjGS8jjST0E"],
    "Калач": ["CAACAgIAAxkBAAFTC35qk1KvEKJPsH8dTKGlc6K813DDVAACaq0AArYnKUjjoc77h49J-j0E"],
    "Харитон Ряков": ["CAACAgIAAxkBAAFTC3xqk1KsKECJqPA_CwVSQk3ieqsieQACTqoAAuJmIUi5iZdIHxDisD0E"],
    "Конгресс путешественников": ["CAACAgIAAxkBAAFTC3xqk1KsKECJqPA_CwVSQk3ieqsieQACTqoAAuJmIUi5iZdIHxDisD0E"],
    "Сеньор Понполомео": ["CAACAgIAAxkBAAFTC3pqk1Ko52Z7xO9lW9OD5FIgpDiJVAAChKAAAqCbMEg_HC3--4mhxD0E"],
    "Гузлик": ["CAACAgIAAxkBAAFTC0Rqk1JUSqdgGdIkZpyhPQ6wRyixyAACvpwAAgrP-UuFMiQAAVw5MHo9BA"],
    "Летописный Артём": [
        "CAACAgIAAxkBAAFTC0Zqk1JYcvtxoUcirgZDhWJ5wS8k_wACV6IAApI9-EvqUXEIs8EV_j0E",
        "CAACAgIAAxkBAAFTC0hqk1JbNDAcT_iG7AABzK-2s_Sr6p4AAsGfAAKhz2FIfTOKN3tvn4A9BA"
    ],
    "Мопсосвины": ["CAACAgIAAxkBAAFTC0pqk1JefY-ZnPr6mjjz6jX2d0rQFAACMKAAAp12UUju8ZPhuUtGZj0E"],
    "Грязуны": ["CAACAgIAAxkBAAFTC0xqk1Jh1Qp1sVC45EzzDEhlXOzGBwACJZ8AArUwmUh2Nee5Ad9Rej0E"],
    "Григорий": ["CAACAgIAAxkBAAFTC05qk1JkG6GWxuGwXNmGhUSneydCaQAC2KEAAmxvCUhxZIooEbnJnT0E"],
    "Кокша": ["CAACAgIAAxkBAAFTC1Bqk1JoY41z09x0V9yf97aWMxc7tAACLaUAAg9MQUiZ4I0FnDp5ij0E"],
    "Маня Понич": ["CAACAgIAAxkBAAFTC1Bqk1JoY41z09x0V9yf97aWMxc7tAACLaUAAg9MQUiZ4I0FnDp5ij0E"],
    "Мальчик-Педаль": ["CAACAgIAAxkBAAFTC1Jqk1JtLtCCSHO0MfRKlgHm-dJ1iAACcK0AAq_QMEjyIUpi8K57PT0E"],
    "Пальчик-Медаль": ["CAACAgIAAxkBAAFTC1Rqk1JwQ7KlP2UanvoKC8IDf85f4QADowACVqhZSAsCi9BjpQPYPQQ"],
    "Пыльный Глеб": ["CAACAgIAAxkBAAFTC1Zqk1Jz4mIhDXZ60n0SG1ob7MPtlAACdq8AAtzQcEiaGzQM6U_E9D0E"],
    "Многоликий Филипп": ["CAACAgIAAxkBAAFTC1hqk1J3oD8K-IcAASI4WAMw39QFFjUAAlSqAAIBW3BI5y5ce48v-qU9BA"],
    "Профессор Игорь Диод": ["CAACAgIAAxkBAAFTC1pqk1J615GEej5oePrl9tyO9wOv2wACHbYAAr8AAQhI1Ta2SAgG1us9BA"],
    "Сырный Джо": ["CAACAgIAAxkBAAFTC15qk1J9sSYqk182m1Hd7BgExN8hrgAC1KQAAsCnCUg2IJ49oRE8MD0E"],
    "Принцесса Пармезанна": ["CAACAgIAAxkBAAFTC2Bqk1KA3pauT990rL96Puz7uAwdMAAC0pwAAsn9gEgOZ1ceeAUmRD0E"],
    "Птозный Эдгар": ["CAACAgIAAxkBAAFTC2Jqk1KD5JYhEXgXUUet3e0SvsuavwACD6oAAozvEUgoWoRSg1LMqj0E"],
    "Большой Дима": ["CAACAgIAAxkBAAFTC2Rqk1KHW6esC82XEg47sv8yOJF5iwACaq4AAlHFOUiAZx6Oq28DZT0E"],
    "Волнистый попугай Николай": ["CAACAgIAAxkBAAFTC2Zqk1KK7Qth2oVgtIZ2HHLGlQZvYgAC86MAAtZ0kEhWc_sErCP-Gj0E"],
    "Луп Лупыч": ["CAACAgIAAxkBAAFTC2hqk1KOK3rdNSWSTF-2cOKBbCbQBQACCa4AAi0n6EuSfn-EZc_QkT0E"],
    "Улитолий": ["CAACAgIAAxkBAAFTC2pqk1KRWEij6Y2OKKI9GQPg9KdVgwACQ9cAAv0BOEglR1smInc4FT0E"],
    "Грочилы": ["CAACAgIAAxkBAAFTC2xqk1KUurvNwbjRkiY9uIr01uFOGAACB6gAAuNPUEhJ6qiSKhj1dT0E"],
    "Шапец": ["CAACAgIAAxkBAAFTC3Bqk1KXeJU4gesxYrDpkVi3sf_qigACYp8AAlfoaUjxErIad-LXMj0E"],
    "Доктор Лист": ["CAACAgIAAxkBAAFTC3Jqk1Kak4vOBV-VeFbZ8o2XhkeZ5QAC1a8AAhTVWEiSRMQhECPgKD0E"],
    "Пакет": ["CAACAgIAAxkBAAFTC3Rqk1KewCyo_u3wzCqUnBMXH7BbBAACBZoAAhn3mEgure_syXenCT0E"],
    "Дырки от дверей": ["CAACAgIAAxkBAAFTC3Zqk1Kh3r5gfvPqfHKQz3TJRq6wJAACGbAAAphnWEgE8dLJRGnIeD0E"],
    "Магога": ["CAACAgIAAxkBAAFTC3hqk1Klc14pBpwT2O7PGY1-mjhQhwACqaoAAu5ZSEiXRnB-6LFp9j0E"],
}

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
    
    # 1. Сначала отправляем карточку (с картинкой или без)
    if send_photo and item.get('image'):
        try:
            image_url = IMAGES_BASE_URL + item['image']
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                photo_file = BytesIO(response.content)
                bot.send_photo(chat_id, photo_file, caption=text, parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_main_keyboard())
        except Exception as e:
            print(f"❌ Не удалось отправить картинку: {e}")
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_main_keyboard())
    
    # 2. Затем отправляем случайный стикер (если есть)
    if item['name'] in STICKERS:
        try:
            sticker_list = STICKERS[item['name']]
            random_sticker = random.choice(sticker_list)
            bot.send_sticker(chat_id, random_sticker)
        except Exception as e:
            print(f"❌ Не удалось отправить стикер для {item['name']}: {e}")

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
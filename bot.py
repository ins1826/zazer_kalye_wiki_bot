import telebot
import random
import requests
import re
import os
import time
import json
import logging
import traceback
from flask import Flask, request
from io import BytesIO

# === НАСТРОЙКИ ===
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "").strip().strip("/")

WIKI_URL = "https://ins1826.github.io/zazer_kalye_wiki_bot/"

if not TOKEN:
    raise SystemExit("❌ BOT_TOKEN не задан в переменных окружения Render")
if not WEBHOOK_PATH:
    raise SystemExit("❌ WEBHOOK_PATH не задан в переменных окружения Render")

OWNER_ID = 412598271

DATA_URL = "https://raw.githubusercontent.com/ins1826/zazer_kalye_wiki_bot/refs/heads/main/data.json"
IMAGES_BASE_URL = "https://ins1826.github.io/zazer_kalye_wiki_bot/"

bot = telebot.TeleBot(TOKEN)

# === МАСКИРОВКА СЕКРЕТОВ В ЛОГАХ ===
def mask_secret(s):
    """8991988855:AAF... -> 89919…:AAF…"""
    if not s:
        return s
    if ":" in s:
        left, _, right = s.partition(":")
        if len(left) >= 5 and len(right) >= 4:
            return f"{left[:5]}…:{right[:4]}…"
    if len(s) > 10:
        return s[:5] + "…"
    return "…"


def mask_path(path):
    """wh_a94f7c2e1b8d4e9f… -> wh_a94f…1a7c (для логов/сообщений)"""
    if not path:
        return path
    if len(path) <= 12:
        return path
    return f"{path[:6]}…{path[-4:]}"


def log(*args):
    print(*args, flush=True)


# === WEB ===
app = Flask(__name__)
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")

# Необязательно: прячем WEBHOOK_PATH в логах Werkzeug
class _MaskWerkzeugFilter(logging.Filter):
    def filter(self, record):
        try:
            if WEBHOOK_PATH and record.args:
                def _mask(x):
                    if isinstance(x, str) and WEBHOOK_PATH in x:
                        return x.replace(WEBHOOK_PATH, mask_path(WEBHOOK_PATH))
                    return x
                if isinstance(record.args, tuple):
                    record.args = tuple(_mask(a) for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = {k: _mask(v) for k, v in record.args.items()}
        except Exception:
            pass
        return True

logging.getLogger("werkzeug").addFilter(_MaskWerkzeugFilter())


@app.route('/')
@app.route('/health')
def health_check():
    return "OK", 200


@app.route('/webhook_info')
def webhook_info_route():
    try:
        info = bot.get_webhook_info()
        safe_url = info.url
        if WEBHOOK_PATH and WEBHOOK_PATH in safe_url:
            safe_url = safe_url.replace(WEBHOOK_PATH, mask_path(WEBHOOK_PATH))
        return {
            "url": safe_url,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message,
        }, 200
    except Exception as e:
        return {"error": str(e)}, 500


# === ЗАГРУЗКА ДАННЫХ ===
wiki_data = {}


def load_wiki_data():
    global wiki_data
    try:
        response = requests.get(DATA_URL, timeout=10)
        if response.status_code == 200:
            wiki_data = response.json()
            log(f"✅ Данные загружены: {len(wiki_data.get('characters', []))} персонажей")
            return True
        log(f"❌ Ошибка загрузки: код {response.status_code}")
        return False
    except Exception as e:
        log(f"❌ Ошибка загрузки: {e}")
        return False


load_wiki_data()

feedback_mode = {}
search_results_cache = {}


# === ХЕЛПЕРЫ ===
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
        telebot.types.InlineKeyboardButton("✉️ Написать автору вики", callback_data='feedback_mode')
    )
    keyboard.row(
        telebot.types.InlineKeyboardButton(
            "📖 Открыть Энциклопедию",
            web_app=telebot.types.WebAppInfo(url=WIKI_URL)
        )
    )
    return keyboard


# === СТИКЕРЫ ===
STICKERS = {
    "Коленыч": ["CAACAgIAAxkBAAFTCuVqk1Gsjo9H5j009LQ1ZAuFGdj5OAACzLIAAsem0UsmUDzySoinAT0E"],
    "Брунявая Чуня": ["CAACAgIAAxkBAAFTlklqnTHf4nDUFovhPvD5tvmWZAWx4gACyaoAAkOZsUio7JEAAY7kciE9BA", "CAACAgIAAxkBAAFTllVqnTJmJEH3y5ZWpRdlPSsvJx3ZaAACyacAAigPsEgSWPZ-IU_EDT0E"],
    "Чунявая Бруня": ["CAACAgIAAxkBAAFTllFqnTIxaLxuzniRPTQkaGZVLG7MgAACdrUAAvRxsEifbFEQTwMChz0E", "CAACAgIAAxkBAAFTllVqnTJmJEH3y5ZWpRdlPSsvJx3ZaAACyacAAigPsEgSWPZ-IU_EDT0E"],
    "Акакий Куролесов": ["CAACAgIAAxkBAAFTCulqk1GyFTtCxtb7Za0F3Cy3evGMlgAClKQAAvjJ0UsRpht3yVpbgT0E", "CAACAgIAAxkBAAFTCutqk1G2rdNWLfg5OcPX-V8jMKNOxwACHasAAshRgEgwiGMJ1hm9tD0E", "CAACAgIAAxkBAAFTCvdqk1HLemkwR7MVjrWCb_1y4G3newACwJcAAshsKUj97YMpXPBZzj0E"],
    "ПВЗ": ["CAACAgIAAxkBAAFTCu1qk1G54034Vd5iNNbh37zYSJTzJgACX7MAArNy0EsGJFZFHJ0JkD0E"],
    "Поленыч": ["CAACAgIAAxkBAAFTCu1qk1G54034Vd5iNNbh37zYSJTzJgACX7MAArNy0EsGJFZFHJ0JkD0E"],
    "Доктор Эпикантус": ["CAACAgIAAxkBAAFTCu9qk1G8AeVfrDLSh3tzkiMWOpB1rgACAaoAAu2K0EsX60LcXYD2eT0E"],
    "Вальтасар": ["CAACAgIAAxkBAAFTCu9qk1G8AeVfrDLSh3tzkiMWOpB1rgACAaoAAu2K0EsX60LcXYD2eT0E", "CAACAgIAAxkBAAFTCxBqk1HzGP-t3w6SAgVqUiWoWU62uAACpK0AAhDD6EtXJKbixbcWsj0E", "CAACAgIAAxkBAAFTCvFqk1HBuJvUCK_URUjQvRhQBhlBzwACT7EAAnDdeUgzAnv7tV7Lpz0E", "CAACAgIAAxkBAAFTCxJqk1H2JAmmPduOe5EaoTcoKVMXWQACy5cAAmcNgUgPcTdR0xGnjj0E"],
    "Выбор зелья Вальтасара": ["CAACAgIAAxkBAAFTCxJqk1H2JAmmPduOe5EaoTcoKVMXWQACy5cAAmcNgUgPcTdR0xGnjj0E"],
    "Истуканус": ["CAACAgIAAxkBAAFTCvNqk1HFnkAu7y3eqk-Ri0O5dt9HHAACz6UAAjph0EvH342gWx6sSD0E"],
    "Дон Окунь": ["CAACAgIAAxkBAAFTCvVqk1HIDHRo4UZ5AAHL9FEguEMwchUAAtmxAALbF9FLxtdZhV1AFWg9BA"],
    "Пацаноиды": ["CAACAgIAAxkBAAFTCvlqk1HOUUaDU7_Gje-KPOnPmAK-hAACC6sAAu2o0Usm-vgvixRWAT0E", "CAACAgIAAxkBAAFTCvtqk1HSmuuI5qVJW7k0jqC58q6fUgACfKkAAq8cEEidpolWgmHh6D0E", "CAACAgIAAxkBAAFTCttqk1DdCtK140wd2E4jXQ9TfIIu1QACvqAAAryMKEhxcEib__xeMD0E"],
    "Бобыли": ["CAACAgIAAxkBAAFTCv1qk1HWAAHFIUt_D8fnJQ7VDzf-oEYAAn2pAALJ19FLcb1M3EVoQiY9BA"],
    "Лесной бобыль": ["CAACAgIAAxkBAAFTCv1qk1HWAAHFIUt_D8fnJQ7VDzf-oEYAAn2pAALJ19FLcb1M3EVoQiY9BA"],
    "Сатор Арепыч": ["CAACAgIAAxkBAAFTCv9qk1Ha_JZZEfQtkTmCJF845cD2ygACTKIAAoJr4UuN6bkqhtCziz0E"],
    "Кокалка": ["CAACAgIAAxkBAAFTCv9qk1Ha_JZZEfQtkTmCJF845cD2ygACTKIAAoJr4UuN6bkqhtCziz0E", "CAACAgIAAxkBAAFTC0Jqk1JR0-192CVpyXQKb_g3g8KSVgACxqkAAqClEEgm05Dj2lIaJj0E"],
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
    "Реутень": ["CAACAgIAAxkBAAFTCzxqk1I8hphL34UUaU7PNtB3mduoMQACfKQAAtJd4EukOo_gKnt4CD0E", "CAACAgIAAxkBAAFTCz5qk1JDGiU9yHf7PBL2LqVOU8VFzgACoqgAAr2B4EuYxuf2RyjrjD0E"],
    "Подмыхан": ["CAACAgIAAxkBAAFTC0Bqk1JM6E8ml8jD4rOAL2e9LMIHnQACO6gAAkkJ6EtV-eZwjcTAND0E"],
    "Лесной Курбак": ["CAACAgIAAxkBAAFTC4Bqk1KxejJOThJhHp1WYk5mB-k3mgAC16cAAvHmmEhvFvjGS8jjST0E"],
    "Калач": ["CAACAgIAAxkBAAFTC35qk1KvEKJPsH8dTKGlc6K813DDVAACaq0AArYnKUjjoc77h49J-j0E"],
    "Харитон Ряков": ["CAACAgIAAxkBAAFTC3xqk1KsKECJqPA_CwVSQk3ieqsieQACTqoAAuJmIUi5iZdIHxDisD0E"],
    "Конгресс путешественников": ["CAACAgIAAxkBAAFTC3xqk1KsKECJqPA_CwVSQk3ieqsieQACTqoAAuJmIUi5iZdIHxDisD0E"],
    "Сеньор Понполомео": ["CAACAgIAAxkBAAFTC3pqk1Ko52Z7xO9lW9OD5FIgpDiJVAAChKAAAqCbMEg_HC3--4mhxD0E"],
    "Гузлик": ["CAACAgIAAxkBAAFTC0Rqk1JUSqdgGdIkZpyhPQ6wRyixyAACvpwAAgrP-UuFMiQAAVw5MHo9BA"],
    "Летописный Артём": ["CAACAgIAAxkBAAFTC0Zqk1JYcvtxoUcirgZDhWJ5wS8k_wACV6IAApI9-EvqUXEIs8EV_j0E", "CAACAgIAAxkBAAFTC0hqk1JbNDAcT_iG7AABzK-2s_Sr6p4AAsGfAAKhz2FIfTOKN3tvn4A9BA"],
    "Мопсосвины": ["CAACAgIAAxkBAAFTC0pqk1JefY-ZnPr6mjjz6jX2d0rQFAACMKAAAp12UUju8ZPhuUtGZj0E"],
    "Грязуны": ["CAACAgIAAxkBAAFTC0xqk1Jh1Qp1sVC45EzzDEhlXOzGBwACJZ8AArUwmUh2Nee5Ad9Rej0E"],
    "Григорий": ["CAACAgIAAxkBAAFTC05qk1JkG6GWxuGwXNmGhUSneydCaQAC2KEAAmxvCUhxZIooEbnJnT0E"],
    "Кокша": ["CAACAgIAAxkBAAFTC1Bqk1JoY41z09x0V9yf97aWMxc7tAACLaUAAg9MQUiZ4I0FnDp5ij0E", "CAACAgIAAxkBAAFTloVqnTNk-r0sRvY87qu9plU_M-pPYgACGaQAAtGDwEjZ3Oo4J4KOqz0E"],
    "Гычеедка": ["CAACAgIAAxkBAAFTloVqnTNk-r0sRvY87qu9plU_M-pPYgACGaQAAtGDwEjZ3Oo4J4KOqz0E"],
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
    "Кловунец": ["CAACAgIAAxkBAAFTlxBqnTaOPa4VCr9Q70WA0sTZu7meOAACtJoAAsK1oUgv114Yyvhtnj0E"],
    "Шапец": ["CAACAgIAAxkBAAFTC3Bqk1KXeJU4gesxYrDpkVi3sf_qigACYp8AAlfoaUjxErIad-LXMj0E"],
    "Доктор Лист": ["CAACAgIAAxkBAAFTC3Jqk1Kak4vOBV-VeFbZ8o2XhkeZ5QAC1a8AAhTVWEiSRMQhECPgKD0E"],
    "Пакет": ["CAACAgIAAxkBAAFTC3Rqk1KewCyo_u3wzCqUnBMXH7BbBAACBZoAAhn3mEgure_syXenCT0E"],
    "Дырки от дверей": ["CAACAgIAAxkBAAFTC3Zqk1Kh3r5gfvPqfHKQz3TJRq6wJAACGbAAAphnWEgE8dLJRGnIeD0E"],
    "Магога": ["CAACAgIAAxkBAAFTC3hqk1Klc14pBpwT2O7PGY1-mjhQhwACqaoAAu5ZSEiXRnB-6LFp9j0E"],
    "Пчелисей": ["CAACAgIAAxkBAAFTlypqnTcOp7smPhhPkOhYB23iLXGlHQACNaEAApXMwUgDLNOvqaRjGT0E"],
    "Корпораты": ["CAACAgIAAxkBAAFTlyJqnTbgZTLkE9R8F4bmfa308zCWLgACWqsAAhmUmUgkDojNQ1fB5D0E"],
}


# === ДЛИННЫЕ СООБЩЕНИЯ ===
def send_long_message(chat_id, text, parse_mode="HTML", reply_markup=None):
    MAX_LENGTH = 4000
    if len(text.encode('utf-8')) <= MAX_LENGTH:
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        return
    parts = []
    while len(text.encode('utf-8')) > MAX_LENGTH:
        split_at = text.rfind('\n', 0, MAX_LENGTH)
        if split_at == -1:
            split_at = text.rfind(' ', 0, MAX_LENGTH)
        if split_at == -1:
            split_at = MAX_LENGTH
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        bot.send_message(chat_id, part, parse_mode=parse_mode, reply_markup=markup)


# === КАРТОЧКА ===
def send_item_card(chat_id, item, label, send_photo=True):
    text = f"{label}: <b>{escape_html(item['name'])}</b>\n"
    if item.get('type'):
        text += f"🏷️ {escape_html(item['type'])}\n"
    if item.get('short'):
        text += f"\n📜 {escape_html(parse_wiki_links(item['short']))}\n"
    if item.get('full'):
        full_text = parse_wiki_links(item['full'])
        text += f"\n{escape_html(full_text)}\n"

    if item.get('episodes') and len(item['episodes']) > 0:
        eps = []
        for e in item['episodes'][:5]:
            parsed = parse_wiki_links(str(e)).strip()
            if parsed:
                eps.append(escape_html(parsed))
        if eps:
            text += f"\n🎬 Эпизоды: {', '.join(f'ep. {e}' for e in eps)}"

    if send_photo and item.get('image'):
        try:
            image_url = IMAGES_BASE_URL + item['image']
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                bot.send_photo(chat_id, BytesIO(response.content))
        except Exception as e:
            log(f"❌ Картинка: {e}")

    send_long_message(chat_id, text, parse_mode="HTML", reply_markup=get_main_keyboard())

    if item['name'] in STICKERS:
        try:
            bot.send_sticker(chat_id, random.choice(STICKERS[item['name']]))
        except Exception as e:
            log(f"❌ Стикер для {item['name']}: {e}")


def send_random_character(chat_id):
    if not wiki_data or 'characters' not in wiki_data:
        bot.send_message(chat_id, "❌ Данные ещё не загрузились.")
        return
    char = random.choice(wiki_data['characters'])
    send_item_card(chat_id, char, "👤 Персонаж")


def send_welcome(chat_id):
    text = """🪞 <b>Добро пожаловать в Зазеркалье!</b>

Ты стоишь на пороге мира, где Хрычи растут на огороде у бабы Жули, а в подпольном щекоточном клубе высокие требования к кандидатам...

💡 Напиши имя персонажа (например, "Баба Жуля") — я найду его
💡 Или используй кнопки ниже!"""
    bot.send_message(chat_id, text, reply_markup=get_main_keyboard(), parse_mode="HTML")


# =========================================================
# ОБЩАЯ ЛОГИКА КНОПОК
# =========================================================
def process_callback(data, from_user, chat_id, message_id=None, callback_id=None):
    log(f"   🎯 process_callback: data={data!r}, from={from_user.id}")

    if callback_id:
        try:
            bot.answer_callback_query(callback_id)
        except Exception as e:
            log(f"   ⚠️ answer_callback_query: {e}")

    try:
        if data == 'random_char':
            send_random_character(from_user.id)

        elif data == 'feedback_mode':
            feedback_mode[from_user.id] = True
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("❌ Отменить", callback_data='cancel_feedback'))
            bot.send_message(
                from_user.id,
                "✉️ <b>Режим обратной связи включён!</b>\n\nНапиши своё сообщение, и я передам его помощнице Грибного Архивариуса.\n\n<i>(Если передумал, нажми кнопку ниже)</i>",
                reply_markup=kb,
                parse_mode="HTML"
            )

        elif data == 'cancel_feedback':
            feedback_mode.pop(from_user.id, None)
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ <b>Режим обратной связи отменён.</b>",
                    parse_mode="HTML"
                )

        elif data == 'cancel_search':
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ <b>Поиск отменён.</b>\n\nНапиши другое имя:",
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )

        elif data.startswith('select_'):
            result_id = data.replace('select_', '')
            uid = from_user.id
            if uid in search_results_cache and result_id in search_results_cache[uid]:
                result = search_results_cache[uid][result_id]
                send_item_card(uid, result['item'], result['label'])
                del search_results_cache[uid]

        elif data == 'test_click':
            bot.send_message(from_user.id, "✅ Тест-кнопка сработала!")

        else:
            log(f"   ⚠️ неизвестный callback_data: {data}")

    except Exception as e:
        log(f"   ❌ process_callback error: {e}")
        traceback.print_exc()


# =========================================================
# ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# =========================================================
def do_search(chat_id, user_id, query):
    if not wiki_data:
        bot.send_message(chat_id, "⏳ Данные ещё загружаются!")
        return

    q = query.strip().lower()
    found_items = []
    categories = {
        'characters': '👤 Персонаж',
        'locations': '🗺️ Локация',
        'items': '🎒 Предмет',
        'events': '🎭 Ивент',
        'organizations': '🏛️ Организация',
        'races': '🧬 Раса',
    }
    for category, label in categories.items():
        if category not in wiki_data:
            continue
        for item in wiki_data[category]:
            if q == item.get('name', '').lower() or q in item.get('name', '').lower():
                found_items.append({'category': category, 'label': label, 'item': item})

    if not found_items:
        bot.send_message(chat_id, "🤔 Не нашёл. Попробуй точное имя:", reply_markup=get_main_keyboard())
        return

    if len(found_items) == 1:
        send_item_card(chat_id, found_items[0]['item'], found_items[0]['label'])
        return

    if len(found_items) <= 6:
        kb = telebot.types.InlineKeyboardMarkup()
        search_results_cache[user_id] = {}
        for i, result in enumerate(found_items):
            btn_text = f"{result['label']} {result['item']['name']}"
            btn_id = f"result_{i}"
            search_results_cache[user_id][btn_id] = result
            kb.add(telebot.types.InlineKeyboardButton(btn_text, callback_data=f'select_{btn_id}'))
        kb.add(telebot.types.InlineKeyboardButton("❌ Отмена", callback_data='cancel_search'))
        bot.send_message(chat_id, f"🔍 Найдено {len(found_items)} результатов:", reply_markup=kb)
        return

    text = f"🔍 Найдено {len(found_items)} результатов. Напиши номер:\n\n"
    for i, result in enumerate(found_items[:10], 1):
        text += f"{i}. {result['label']} {result['item']['name']}\n"
    if len(found_items) > 10:
        text += f"\n...и ещё {len(found_items) - 10}. Уточни запрос!"
    search_results_cache[user_id] = {str(i): r for i, r in enumerate(found_items[:10], 1)}
    bot.send_message(chat_id, text, reply_markup=get_main_keyboard())


def handle_message(message):
    user_id = message.from_user.id
    text = message.text or ""
    log(f"   → message text = {text[:100]!r}, from = {user_id}")

    # --- Команды ---
    if text.startswith('/'):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().lstrip('/').split('@')[0]
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == 'start':
            send_welcome(message.chat.id)

        elif cmd == 'random':
            send_random_character(message.chat.id)

        elif cmd == 'cancel':
            if user_id in feedback_mode:
                del feedback_mode[user_id]
                bot.send_message(message.chat.id, "❌ <b>Режим обратной связи отменён.</b>",
                                 parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                bot.send_message(message.chat.id, "У тебя и так не включён режим обратной связи.",
                                 reply_markup=get_main_keyboard())

        elif cmd == 'testkb':
            # Тест-команда только для владельца — обычным юзерам не нужна
            if user_id != OWNER_ID:
                return
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("🟢 Тест-кнопка", callback_data='test_click'))
            bot.send_message(message.chat.id,
                             "Если эта кнопка не нажмётся — проблема в доставке callback'ов.\n"
                             "Для проверки обработчика можно написать: /click test_click",
                             reply_markup=kb)

        elif cmd == 'click':
            # Только владелец
            if user_id != OWNER_ID:
                return
            if not arg:
                bot.send_message(message.chat.id,
                                 "Использование: /click random_char  или  /click feedback_mode  или  /click test_click")
                return
            process_callback(arg, message.from_user, message.chat.id,
                             message_id=message.message_id, callback_id=None)

        elif cmd == 'reload':
            if user_id != OWNER_ID:
                bot.send_message(message.chat.id, "❌ Только для администратора!")
                return
            if load_wiki_data():
                bot.send_message(message.chat.id,
                                 f"✅ Данные перезагружены! {len(wiki_data.get('characters', []))} персонажей.")
            else:
                bot.send_message(message.chat.id, "❌ Не удалось перезагрузить данные.")

        elif cmd in ('whoami', 'debug'):
            if user_id != OWNER_ID:
                bot.send_message(message.chat.id, "❌ Только для администратора!")
                return
            try:
                info = bot.get_webhook_info()
                safe_url = info.url
                if WEBHOOK_PATH and WEBHOOK_PATH in safe_url:
                    safe_url = safe_url.replace(WEBHOOK_PATH, mask_path(WEBHOOK_PATH))
                tb_ver = getattr(telebot, "__version__", "неизвестно")
                txt = (
                    f"🐞 <b>Debug</b>\n"
                    f"<b>telebot:</b> <code>{tb_ver}</code>\n"
                    f"<b>webhook url:</b> <code>{safe_url}</code>\n"
                    f"<b>pending:</b> <code>{info.pending_update_count}</code>\n"
                    f"<b>last_err_date:</b> <code>{info.last_error_date}</code>\n"
                    f"<b>last_err_msg:</b> <code>{info.last_error_message}</code>\n"
                    f"<b>characters:</b> <code>{len(wiki_data.get('characters', []))}</code>"
                )
                bot.send_message(message.chat.id, txt, parse_mode="HTML")
            except Exception as e:
                bot.send_message(message.chat.id, f"Ошибка: <code>{e}</code>", parse_mode="HTML")

        return

    # --- Режим обратной связи ---
    if feedback_mode.get(user_id):
        username = f"@{message.from_user.username}" if message.from_user.username else "Без username"
        forward_text = (
            f"💬 <b>Новое сообщение!</b>\n"
            f"👤 <b>От:</b> {escape_html(message.from_user.first_name)} ({escape_html(username)})\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📝 <b>Текст:</b>\n{escape_html(text)}"
        )
        try:
            bot.send_message(OWNER_ID, forward_text, parse_mode="HTML")
            bot.send_message(message.chat.id,
                             "✅ Спасибо! Сообщение отправлено помощнице Грибного Архивариуса! 🪞✨",
                             reply_markup=get_main_keyboard(), parse_mode="HTML")
        except Exception as e:
            log(f"❌ Отправка владельцу: {e}")
            bot.send_message(message.chat.id, "❌ Не удалось отправить сообщение.")
        del feedback_mode[user_id]
        return

    # --- Выбор номера из длинного списка ---
    if text.isdigit():
        if user_id in search_results_cache and text in search_results_cache[user_id]:
            result = search_results_cache[user_id][text]
            send_item_card(message.chat.id, result['item'], result['label'])
            del search_results_cache[user_id]
            return

    # --- Обычный поиск ---
    do_search(message.chat.id, user_id, text)


# =========================================================
# WEBHOOK
# =========================================================
@app.route(f'/{WEBHOOK_PATH}', methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        log(f"📥 UPDATE: {json_string[:300]}")

        data = json.loads(json_string)
        log(f"   → keys = {list(data.keys())}")

        if data.get('callback_query'):
            cq = data['callback_query']
            user = cq.get('from', {})
            msg = cq.get('message', {})
            chat = msg.get('chat', {}) if msg else {}
            log(f"   → CALLBACK_QUERY data={cq.get('data')!r} from={user.get('id')}")
            process_callback(
                data=cq.get('data', ''),
                from_user=telebot.types.User.de_json(user),
                chat_id=chat.get('id', user.get('id')),
                message_id=msg.get('message_id') if msg else None,
                callback_id=cq.get('id'),
            )
            return '', 200

        if data.get('message'):
            msg = telebot.types.Message.de_json(data['message'])
            handle_message(msg)
            return '', 200

        log(f"   ❓ неизвестный тип апдейта: keys={list(data.keys())}")
        return '', 200

    except Exception as e:
        log(f"❌ webhook error: {e}")
        traceback.print_exc()
        return '', 200


# === УСТАНОВКА ВЕБХУКА ===
def setup_webhook():
    base_url = WEBHOOK_BASE_URL or os.environ.get("RENDER_EXTERNAL_URL")
    if not base_url:
        log("⚠️ Не найден RENDER_EXTERNAL_URL. Задай WEBHOOK_BASE_URL вручную.")
        return

    webhook_url = f"{base_url.rstrip('/')}/{WEBHOOK_PATH}"
    log(f"🔗 Регистрирую вебхук: {base_url.rstrip('/')}/{mask_path(WEBHOOK_PATH)}")

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        log(f"⚠️ remove_webhook: {e}")

    ok = bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=["message", "edited_message", "callback_query", "inline_query", "channel_post"],
    )
    log(f"{'✅' if ok else '❌'} set_webhook -> {ok}")

    try:
        info = bot.get_webhook_info()
        safe_url = info.url
        if WEBHOOK_PATH and WEBHOOK_PATH in safe_url:
            safe_url = safe_url.replace(WEBHOOK_PATH, mask_path(WEBHOOK_PATH))
        log(f"ℹ️ webhook info: url={safe_url}, pending={info.pending_update_count}, "
            f"last_err={info.last_error_message}")
    except Exception as e:
        log(f"⚠️ get_webhook_info: {e}")


# === ЗАПУСК ===
setup_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    log(f"🤖 Бот запущен на порту {port} (webhook + ручной dispatch)")
    app.run(host='0.0.0.0', port=port, threaded=True)
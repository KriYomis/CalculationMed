import logging
import math
import os
from typing import Dict, Optional

import telebot
from telebot import types
from dotenv import load_dotenv


load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Создайте .env файл и укажите токен бота.")

bot = telebot.TeleBot(BOT_TOKEN)


MODE_NAMES = {
    "esr": "DAS28-ESR",
    "crp": "DAS28-CRP",
}

FORMULAS = {
    "esr": (
        "DAS28-ESR = 0.56 × √TJC28 + 0.28 × √SJC28 + 0.70 × ln(ESR) + 0.014 × GH\n\n"
        "TJC28 — число болезненных суставов\n"
        "SJC28 — число припухших суставов\n"
        "GH — оценка общего состояния по VAS (0–100 мм)\n"
        "ESR — скорость оседания эритроцитов (мм/ч)"
    ),
    "crp": (
        "DAS28-CRP = 0.56 × √TJC28 + 0.28 × √SJC28 + 0.36 × ln(CRP + 1) + 0.014 × GH + 0.96\n\n"
        "TJC28 — число болезненных суставов\n"
        "SJC28 — число припухших суставов\n"
        "GH — оценка общего состояния по VAS (0–100 мм)\n"
        "CRP — C-реактивный белок (мг/л)"
    ),
}

LIMITS_TEXT = (
    "Интерпретация результата:\n"
    "• Ремиссия: < 2.6\n"
    "• Низкая активность: 2.6–3.2\n"
    "• Умеренная активность: > 3.2–5.1\n"
    "• Высокая активность: > 5.1"
)

START_TEXT = (
    "Это Telegram-бот для расчёта международного индекса DAS28.\n\n"
    "Доступны две формулы:\n"
    "• DAS28-ESR\n"
    "• DAS28-CRP\n\n"
    "Команды:\n"
    "/start — начать работу\n"
    "/help — помощь\n"
    "/formula — показать формулы\n"
    "/cancel — отменить текущий ввод"
)


user_sessions: Dict[int, Dict[str, object]] = {}


def mode_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("DAS28-ESR", callback_data="mode:esr"))
    keyboard.add(types.InlineKeyboardButton("DAS28-CRP", callback_data="mode:crp"))
    return keyboard



def restart_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Рассчитать заново", callback_data="restart"))
    return keyboard



def classify(score: float) -> tuple[str, str]:
    if score < 2.6:
        return "Ремиссия", "Значение соответствует ремиссии заболевания."
    if score <= 3.2:
        return "Низкая активность", "Значение соответствует низкой активности заболевания."
    if score <= 5.1:
        return "Умеренная активность", "Значение соответствует умеренной активности заболевания."
    return "Высокая активность", "Значение соответствует высокой активности заболевания."



def calculate_das28(mode: str, tjc: int, sjc: int, gh: float, marker_value: float) -> float:
    if mode == "esr":
        return 0.56 * math.sqrt(tjc) + 0.28 * math.sqrt(sjc) + 0.70 * math.log(marker_value) + 0.014 * gh
    return 0.56 * math.sqrt(tjc) + 0.28 * math.sqrt(sjc) + 0.36 * math.log(marker_value + 1) + 0.014 * gh + 0.96



def set_user_state(chat_id: int, step: str, **data: object) -> None:
    session = user_sessions.get(chat_id, {})
    session.update(data)
    session["step"] = step
    user_sessions[chat_id] = session



def get_user_state(chat_id: int) -> Optional[Dict[str, object]]:
    return user_sessions.get(chat_id)



def clear_user_state(chat_id: int) -> None:
    if chat_id in user_sessions:
        del user_sessions[chat_id]



def ask_mode(chat_id: int) -> None:
    set_user_state(chat_id, "choosing_mode")
    bot.send_message(chat_id, "Выберите формулу для расчёта:", reply_markup=mode_keyboard())



def safe_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", ".").strip())
    except (AttributeError, ValueError):
        return None



def safe_int(text: str) -> Optional[int]:
    try:
        stripped = text.strip()
        if "." in stripped or "," in stripped:
            return None
        return int(stripped)
    except (AttributeError, ValueError):
        return None


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message) -> None:
    clear_user_state(message.chat.id)
    bot.send_message(message.chat.id, START_TEXT)
    ask_mode(message.chat.id)


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message) -> None:
    bot.send_message(message.chat.id, START_TEXT)


@bot.message_handler(commands=["formula"])
def cmd_formula(message: types.Message) -> None:
    text = (
        "Формулы расчёта:\n\n"
        f"1) {FORMULAS['esr']}\n\n"
        f"2) {FORMULAS['crp']}\n\n"
        f"{LIMITS_TEXT}"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message: types.Message) -> None:
    clear_user_state(message.chat.id)
    bot.send_message(message.chat.id, "Текущий ввод отменён. Нажмите /start, чтобы начать заново.")


@bot.callback_query_handler(func=lambda call: call.data == "restart")
def callback_restart(call: types.CallbackQuery) -> None:
    clear_user_state(call.message.chat.id)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Начинаем новый расчёт.")
    ask_mode(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("mode:"))
def callback_mode(call: types.CallbackQuery) -> None:
    mode = call.data.split(":", 1)[1]
    set_user_state(call.message.chat.id, "entering_gh", mode=mode)
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"Выбрана формула {MODE_NAMES[mode]}.\n\n"
        f"{FORMULAS[mode]}\n\n"
        "Введите GH / VAS общего состояния от 0 до 100:"
    )


@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_text(message: types.Message) -> None:
    session = get_user_state(message.chat.id)
    if not session:
        bot.send_message(message.chat.id, "Нажмите /start, чтобы начать расчёт.")
        return

    step = session.get("step")

    if step == "choosing_mode":
        bot.send_message(message.chat.id, "Нужно выбрать формулу кнопкой ниже.", reply_markup=mode_keyboard())
        return

    if step == "entering_gh":
        gh = safe_float(message.text)
        if gh is None or gh < 0 or gh > 100:
            bot.send_message(message.chat.id, "GH должен быть числом от 0 до 100. Введите значение заново.")
            return

        set_user_state(message.chat.id, "entering_tjc", gh=gh)
        bot.send_message(message.chat.id, "Введите число болезненных суставов TJC28 (целое число от 0 до 28):")
        return

    if step == "entering_tjc":
        tjc = safe_int(message.text)
        if tjc is None or tjc < 0 or tjc > 28:
            bot.send_message(message.chat.id, "TJC28 должен быть целым числом от 0 до 28. Введите значение заново.")
            return

        set_user_state(message.chat.id, "entering_sjc", tjc=tjc)
        bot.send_message(message.chat.id, "Введите число припухших суставов SJC28 (целое число от 0 до 28):")
        return

    if step == "entering_sjc":
        sjc = safe_int(message.text)
        if sjc is None or sjc < 0 or sjc > 28:
            bot.send_message(message.chat.id, "SJC28 должен быть целым числом от 0 до 28. Введите значение заново.")
            return

        mode = str(session.get("mode"))
        set_user_state(message.chat.id, "entering_marker", sjc=sjc)

        if mode == "esr":
            bot.send_message(message.chat.id, "Введите СОЭ (ESR) в мм/ч. Значение должно быть больше 0:")
        else:
            bot.send_message(message.chat.id, "Введите CRP в мг/л. Значение не может быть отрицательным:")
        return

    if step == "entering_marker":
        marker_value = safe_float(message.text)
        if marker_value is None:
            bot.send_message(message.chat.id, "Показатель должен быть числом. Введите значение заново.")
            return

        mode = str(session.get("mode"))
        if mode == "esr" and marker_value <= 0:
            bot.send_message(message.chat.id, "Для DAS28-ESR значение СОЭ должно быть больше 0. Введите значение заново.")
            return

        if mode == "crp" and marker_value < 0:
            bot.send_message(message.chat.id, "Для DAS28-CRP значение CRP не может быть отрицательным. Введите значение заново.")
            return

        gh = float(session["gh"])
        tjc = int(session["tjc"])
        sjc = int(session["sjc"])

        score = calculate_das28(mode=mode, tjc=tjc, sjc=sjc, gh=gh, marker_value=marker_value)
        stage_name, detail = classify(score)
        rounded = f"{score:.2f}"
        marker_name = "СОЭ (ESR)" if mode == "esr" else "CRP"

        result_text = (
            f"Результат расчёта {MODE_NAMES[mode]}:\n\n"
            f"• GH: {gh}\n"
            f"• TJC28: {tjc}\n"
            f"• SJC28: {sjc}\n"
            f"• {marker_name}: {marker_value}\n\n"
            f"Индекс активности: {rounded}\n"
            f"Категория: {stage_name}\n"
            f"Комментарий: {detail}\n\n"
            f"{LIMITS_TEXT}"
        )

        clear_user_state(message.chat.id)
        bot.send_message(message.chat.id, result_text, reply_markup=restart_keyboard())
        return

    clear_user_state(message.chat.id)
    bot.send_message(message.chat.id, "Состояние было сброшено. Нажмите /start, чтобы начать заново.")


if __name__ == "__main__":
    logging.info("Starting DAS28 TeleBot")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

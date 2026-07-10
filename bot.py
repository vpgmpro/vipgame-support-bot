import json
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from rapidfuzz import fuzz

from config import BOT_TOKEN, SUPPORT_CHAT_ID


# ===========================
# Проверка настроек
# ===========================

if not BOT_TOKEN:
    raise RuntimeError("Не указан BOT_TOKEN")

if not SUPPORT_CHAT_ID:
    raise RuntimeError("Не указан SUPPORT_CHAT_ID")


SUPPORT_CHAT_ID = int(SUPPORT_CHAT_ID)


# ===========================
# Логирование
# ===========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ===========================
# Загрузка FAQ
# ===========================

FAQ_FILE = Path("faq.json")

if not FAQ_FILE.exists():
    raise RuntimeError("Файл faq.json не найден")


with open(FAQ_FILE, "r", encoding="utf-8") as f:
    FAQ = json.load(f)

logger.info(f"Загружено вопросов: {len(FAQ)}")


# ===========================
# Bot
# ===========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()


# ===========================
# Хранилище соответствий
# ===========================

support_messages = {}


# ===========================
# Поиск ответа
# ===========================

def find_answer(text: str):

    text = text.lower().strip()

    best_score = 0
    best_answer = None

    for question, answer in FAQ.items():

        score = fuzz.token_sort_ratio(
            text,
            question.lower()
        )

        if score > best_score:
            best_score = score
            best_answer = answer

    if best_score >= 75:
        return best_answer

    return None
# ===========================
# Команда /start
# ===========================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Я бот службы поддержки VIP Game.\n\n"
        "Напишите свой вопрос, и я постараюсь помочь.\n"
        "Если не найду ответ, ваш вопрос будет автоматически передан оператору."
    )


# ===========================
# Обработка вопросов
# ===========================

@dp.message(F.chat.type == "private")
async def user_question(message: Message):

    text = message.text or ""

    answer = find_answer(text)

    if answer:
        await message.answer(answer)
        return

    sent = await bot.send_message(
        SUPPORT_CHAT_ID,
        f"""
🆕 <b>Новый вопрос</b>

👤 <b>Пользователь:</b>
{message.from_user.full_name}

🆔 ID: <code>{message.from_user.id}</code>

💬 <b>Вопрос:</b>

{text}
"""
    )

    support_messages[sent.message_id] = message.from_user.id

    await message.answer(
        "❗ Я не смог найти готовый ответ.\n\n"
        "Ваш вопрос отправлен оператору поддержки.\n"
        "Как только оператор ответит, я сразу пришлю ответ."
    )
# ===========================
# Ответ оператора через Reply
# ===========================

@dp.message(F.chat.id == SUPPORT_CHAT_ID)
async def support_reply(message: Message):

    if message.reply_to_message is None:
        return

    original_message_id = message.reply_to_message.message_id

    if original_message_id not in support_messages:
        return

    user_id = support_messages[original_message_id]

    try:

        await bot.send_message(
            chat_id=user_id,
            text=f"💬 <b>Ответ службы поддержки</b>\n\n{message.text}"
        )

        await message.reply("✅ Ответ отправлен пользователю.")

    except Exception as e:

        logger.exception(e)

        await message.reply(
            "❌ Не удалось отправить сообщение пользователю."
        )
# ===========================
# Запуск бота
# ===========================

async def main():

    logger.info("VIP Game Support Bot started.")

    await dp.start_polling(bot)


if __name__ == "__main__":

    import asyncio

    asyncio.run(main())
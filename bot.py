# bot.py - Полная версия бота поддержки (БЕЗ FLASK)

import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext
)

# Импортируем настройки
from config import TOKEN, ADMIN_CHAT_ID, FAQ_FILE

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === РАБОТА С FAQ ===
def load_faq():
    try:
        with open(FAQ_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('faq', [])
    except:
        return []

def find_answer(question):
    faq_list = load_faq()
    question_lower = question.lower()
    best_match = None
    max_matches = 0
    
    for faq in faq_list:
        keywords = faq.get('keywords', [])
        matches = sum(1 for keyword in keywords if keyword in question_lower)
        if matches > max_matches:
            max_matches = matches
            best_match = faq.get('answer')
    
    return best_match if max_matches > 0 else None

# === ОБРАБОТЧИКИ ===
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📋 Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton("📞 Связаться с оператором", callback_data="operator")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот поддержки. Напишите свой вопрос!",
        reply_markup=reply_markup
    )

def faq_list(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    faq_list = load_faq()
    if not faq_list:
        query.edit_message_text("📋 Список вопросов пуст.")
        return
    
    text = "📋 Частые вопросы:\n\n"
    for idx, faq in enumerate(faq_list, 1):
        keywords = faq.get('keywords', [])
        text += f"{idx}. {keywords[0].capitalize()}\n"
    
    query.edit_message_text(text)

def operator_request(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.edit_message_text("✏️ Напишите ваш вопрос, я перешлю его оператору.")
    context.user_data['waiting_for_operator'] = True

def handle_message(update: Update, context: CallbackContext):
    user = update.effective_user
    question = update.message.text
    
    if question.startswith('/'):
        return
    
    if context.user_data.get('waiting_for_operator'):
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🆘 Вопрос от @{user.username or user.first_name}:\n\n{question}"
        )
        update.message.reply_text("✅ Вопрос передан оператору!")
        context.user_data['waiting_for_operator'] = False
        return
    
    answer = find_answer(question)
    if answer:
        update.message.reply_text(answer)
    else:
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"❓ Вопрос от @{user.username or user.first_name}:\n\n{question}"
        )
        update.message.reply_text("🤔 Я не знаю ответа, но передал вопрос оператору!")

def admin_reply(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_CHAT_ID:
        update.message.reply_text("⛔ Нет прав")
        return
    
    try:
        parts = update.message.text.split(' ', 2)
        if len(parts) < 3:
            update.message.reply_text("❌ Используйте: /reply ID Текст")
            return
        
        user_id = int(parts[1])
        reply_text = parts[2]
        context.bot.send_message(chat_id=user_id, text=f"📨 Ответ поддержки:\n\n{reply_text}")
        update.message.reply_text("✅ Отправлено!")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("reply", admin_reply))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(faq_list, pattern="faq"))
    dp.add_handler(CallbackQueryHandler(operator_request, pattern="operator"))
    
    logger.info("🤖 Бот поддержки запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

# bot.py - с полными уведомлениями в группу

import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters

from config import TOKEN, ADMIN_CHAT_ID, FAQ_FILE

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_faq():
    try:
        with open(FAQ_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('faq', [])
    except Exception as e:
        logger.error(f"Ошибка загрузки FAQ: {e}")
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

def start(update: Update, context):
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

def faq_list(update: Update, context):
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

def operator_request(update: Update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text("✏️ Напишите ваш вопрос, я перешлю его оператору.")
    context.user_data['waiting_for_operator'] = True

def send_to_admin(context, user, question):
    """Отправляет вопрос админу с полным форматированием"""
    try:
        # Формируем красивое сообщение как раньше
        message_text = (
            f"❓ *НЕИЗВЕСТНЫЙ ВОПРОС*\n\n"
            f"👤 Пользователь: @{user.username or user.first_name}\n"
            f"🆔 ID: `{user.id}`\n"
            f"📝 Вопрос:\n{question}\n\n"
            f"💡 Чтобы ответить, напишите:\n"
            f"`/reply {user.id} Ваш ответ`\n\n"
            f"✏️ Чтобы добавить в базу знаний:\n"
            f"`/addfaq ключевые_слова | ответ`"
        )
        
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message_text,
            parse_mode='Markdown'
        )
        logger.info(f"Вопрос переслан админу: {user.id}")
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить админу: {e}")
        return False

def handle_message(update: Update, context):
    user = update.effective_user
    question = update.message.text
    
    if question.startswith('/'):
        return
    
    # Если пользователь ждет оператора
    if context.user_data.get('waiting_for_operator'):
        sent = send_to_admin(context, user, question)
        if sent:
            update.message.reply_text("✅ Ваш вопрос передан оператору!")
        else:
            update.message.reply_text(
                "⚠️ Не удалось передать вопрос оператору. "
                "Пожалуйста, попробуйте позже."
            )
        context.user_data['waiting_for_operator'] = False
        return
    
    # Ищем ответ в FAQ
    answer = find_answer(question)
    
    if answer:
        update.message.reply_text(answer)
    else:
        # Отправляем админу с полным форматированием
        sent = send_to_admin(context, user, question)
        
        if sent:
            update.message.reply_text(
                "🤔 Я не знаю ответа на этот вопрос.\n\n"
                "Но я уже передал его оператору! Он свяжется с вами в ближайшее время."
            )
        else:
            update.message.reply_text(
                "🤔 Я не знаю ответа на этот вопрос.\n\n"
                "К сожалению, не удалось связаться с оператором. "
                "Пожалуйста, попробуйте позже."
            )

def admin_reply(update: Update, context):
    """Команда для ответа пользователю: /reply ID Текст"""
    # Проверяем, что команда из группы или от админа
    if update.effective_user.id != ADMIN_CHAT_ID:
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 2)
        if len(parts) < 3:
            update.message.reply_text("❌ Используйте: /reply ID_пользователя Текст")
            return
        
        user_id = int(parts[1])
        reply_text = parts[2]
        
        # Отправляем ответ пользователю
        context.bot.send_message(
            chat_id=user_id,
            text=f"📨 *Ответ поддержки:*\n\n{reply_text}\n\n"
                 f"✉️ Если у вас остались вопросы, просто напишите ещё раз.",
            parse_mode='Markdown'
        )
        update.message.reply_text(f"✅ Ответ отправлен пользователю {user_id}!")
        
    except ValueError:
        update.message.reply_text("❌ ID пользователя должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при ответе: {e}")
        update.message.reply_text(f"❌ Не удалось отправить ответ. Ошибка: {e}")

def add_faq(update: Update, context):
    """Добавление FAQ: /addfaq ключевые_слова | ответ"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text(
                "❌ Использование: `/addfaq ключевые_слова | ответ`\n\n"
                "Например: `/addfaq оплата,карта | Мы принимаем карты всех банков.`",
                parse_mode='Markdown'
            )
            return
        
        content = parts[1]
        if '|' not in content:
            update.message.reply_text(
                "❌ Используйте `|` для разделения ключевых слов и ответа.",
                parse_mode='Markdown'
            )
            return
        
        keywords_str, answer = content.split('|', 1)
        keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
        answer = answer.strip()
        
        if not keywords or not answer:
            update.message.reply_text("❌ Ключевые слова и ответ не могут быть пустыми.")
            return
        
        faq_list = load_faq()
        new_id = max([item.get('id', 0) for item in faq_list], default=0) + 1
        faq_list.append({
            'id': new_id,
            'keywords': keywords,
            'answer': answer
        })
        save_faq(faq_list)
        
        update.message.reply_text(
            f"✅ FAQ добавлен! (ID: {new_id})\n\n"
            f"📌 Ключевые слова: {', '.join(keywords)}\n"
            f"📝 Ответ: {answer}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка добавления FAQ: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def save_faq(faq_list):
    """Сохраняет FAQ в JSON файл"""
    try:
        with open(FAQ_FILE, 'w', encoding='utf-8') as f:
            json.dump({'faq': faq_list}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения FAQ: {e}")
        return False

def error_handler(update, context):
    """Обработчик ошибок"""
    logger.error(f'Update "{update}" вызвал ошибку "{context.error}"')

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("reply", admin_reply))
    dp.add_handler(CommandHandler("addfaq", add_faq))
    
    # Обработчики
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(faq_list, pattern="faq"))
    dp.add_handler(CallbackQueryHandler(operator_request, pattern="operator"))
    
    # Обработчик ошибок
    dp.add_error_handler(error_handler)
    
    logger.info("🤖 Бот поддержки запущен!")
    logger.info(f"📌 Админ ID: {ADMIN_CHAT_ID}")
    logger.info("📌 Команды администратора:")
    logger.info("  /reply ID Текст - ответить пользователю")
    logger.info("  /addfaq ключи | ответ - добавить в базу знаний")
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

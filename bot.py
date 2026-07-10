# bot.py - полная версия со всеми командами

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

def save_faq(faq_list):
    try:
        with open(FAQ_FILE, 'w', encoding='utf-8') as f:
            json.dump({'faq': faq_list}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения FAQ: {e}")
        return False

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

def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_CHAT_ID

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
    """Отправляет вопрос админу"""
    try:
        message_text = (
            f"❓ *Новый вопрос*\n\n"
            f"👤 Пользователь: @{user.username or user.first_name}\n"
            f"🆔 ID: `{user.id}`\n"
            f"📝 Вопрос:\n{question}\n\n"
            f"💡 Чтобы ответить:\n"
            f"`/reply {user.id} Ваш ответ`"
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
    
    if context.user_data.get('waiting_for_operator'):
        sent = send_to_admin(context, user, question)
        if sent:
            update.message.reply_text("✅ Ваш вопрос передан оператору!")
        else:
            update.message.reply_text("⚠️ Не удалось передать вопрос.")
        context.user_data['waiting_for_operator'] = False
        return
    
    answer = find_answer(question)
    if answer:
        update.message.reply_text(answer)
    else:
        sent = send_to_admin(context, user, question)
        if sent:
            update.message.reply_text(
                "🤔 Я не знаю ответа на этот вопрос.\n\n"
                "Но я уже передал его оператору!"
            )
        else:
            update.message.reply_text(
                "🤔 Я не знаю ответа.\n\n"
                "Не удалось связаться с оператором. Попробуйте позже."
            )

# === КОМАНДЫ АДМИНИСТРАТОРА ===

def admin_reply(update: Update, context):
    """/reply ID_пользователя Текст ответа"""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 2)
        if len(parts) < 3:
            update.message.reply_text("❌ Используйте: /reply ID_пользователя Текст")
            return
        
        user_id = int(parts[1])
        reply_text = parts[2]
        
        context.bot.send_message(
            chat_id=user_id,
            text=f"📨 *Ответ поддержки:*\n\n{reply_text}"
        )
        update.message.reply_text(f"✅ Ответ отправлен пользователю {user_id}!")
        
    except ValueError:
        update.message.reply_text("❌ ID пользователя должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при ответе: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def list_faq(update: Update, context):
    """/listfaq - показать все FAQ"""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    
    if not faq_list:
        update.message.reply_text("📋 База знаний пуста.")
        return
    
    text = "📚 *База знаний:*\n\n"
    for faq in faq_list:
        faq_id = faq.get('id')
        keywords = faq.get('keywords', [])
        answer = faq.get('answer', '')
        text += f"*ID {faq_id}. {', '.join(keywords)}*\n"
        text += f"📝 {answer[:100]}{'...' if len(answer) > 100 else ''}\n\n"
    
    update.message.reply_text(text, parse_mode='Markdown')

def add_faq(update: Update, context):
    """/addfaq ключевые_слова | ответ"""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text(
                "❌ Использование: `/addfaq ключи | ответ`\n"
                "Например: `/addfaq оплата,карта | Мы принимаем карты`",
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

def delete_faq(update: Update, context):
    """/delfaq ID"""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 2:
            update.message.reply_text("❌ Используйте: `/delfaq ID`", parse_mode='Markdown')
            return
        
        faq_id = int(parts[1])
        faq_list = load_faq()
        faq_list = [item for item in faq_list if item.get('id') != faq_id]
        save_faq(faq_list)
        
        update.message.reply_text(f"✅ FAQ #{faq_id} удален.")
        
    except ValueError:
        update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка удаления FAQ: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def error_handler(update, context):
    """Обработчик ошибок"""
    logger.error(f'Update "{update}" вызвал ошибку "{context.error}"')

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Команды для всех
    dp.add_handler(CommandHandler("start", start))
    
    # Команды для админа (работают в личном чате)
    dp.add_handler(CommandHandler("reply", admin_reply))
    dp.add_handler(CommandHandler("listfaq", list_faq))  # ← ДОБАВЛЕНА КОМАНДА
    dp.add_handler(CommandHandler("addfaq", add_faq))
    dp.add_handler(CommandHandler("delfaq", delete_faq))  # ← ДОБАВЛЕНА КОМАНДА
    
    # Обработчики
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(faq_list, pattern="faq"))
    dp.add_handler(CallbackQueryHandler(operator_request, pattern="operator"))
    
    dp.add_error_handler(error_handler)
    
    logger.info("🤖 Бот поддержки запущен!")
    logger.info(f"📌 Админ ID: {ADMIN_CHAT_ID}")
    logger.info("📌 Команды администратора:")
    logger.info("  /reply ID Текст - ответить пользователю")
    logger.info("  /listfaq - список FAQ")
    logger.info("  /addfaq ключи | ответ - добавить FAQ")
    logger.info("  /delfaq ID - удалить FAQ")
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

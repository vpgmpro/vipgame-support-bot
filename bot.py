# bot.py - Добавьте это в начало файла, после других импортов

from flask import Flask
import threading
import os

# Создаем Flask-приложение
app = Flask(__name__)

@app.route('/')
def hello():
    return "🤖 Бот поддержки работает!"

def run_flask():
    """Запускает Flask-сервер в отдельном потоке"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запускаем Flask в фоновом потоке (это не помешает боту)
threading.Thread(target=run_flask, daemon=True).start()
# bot.py
import logging
import json
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackContext, 
    CallbackQueryHandler,
    filters
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
    """Загружает FAQ из JSON файла"""
    try:
        with open(FAQ_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('faq', [])
    except FileNotFoundError:
        logger.error(f"Файл {FAQ_FILE} не найден!")
        return []
    except json.JSONDecodeError:
        logger.error(f"Ошибка чтения {FAQ_FILE}!")
        return []

def save_faq(faq_list):
    """Сохраняет FAQ в JSON файл"""
    try:
        with open(FAQ_FILE, 'w', encoding='utf-8') as f:
            json.dump({'faq': faq_list}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения FAQ: {e}")
        return False

def find_answer(question):
    """Ищет ответ в FAQ по ключевым словам"""
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

def add_faq_item(keywords, answer):
    """Добавляет новый FAQ"""
    faq_list = load_faq()
    new_id = max([item.get('id', 0) for item in faq_list], default=0) + 1
    faq_list.append({
        'id': new_id,
        'keywords': [k.strip().lower() for k in keywords if k.strip()],
        'answer': answer.strip()
    })
    save_faq(faq_list)
    return new_id

def delete_faq_item(faq_id):
    """Удаляет FAQ по ID"""
    faq_list = load_faq()
    faq_list = [item for item in faq_list if item.get('id') != faq_id]
    save_faq(faq_list)
    return True

# === ОБРАБОТЧИКИ КОМАНД ===
async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("📋 Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton("📞 Связаться с оператором", callback_data="operator")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я умный бот поддержки. Я могу:\n"
        "✅ Ответить на частые вопросы\n"
        "✅ Связать вас с оператором\n\n"
        "Просто напишите свой вопрос, или выберите действие ниже:",
        reply_markup=reply_markup
    )

async def faq_list(update: Update, context: CallbackContext):
    """Показывает список частых вопросов"""
    query = update.callback_query
    await query.answer()
    
    faq_list = load_faq()
    
    if not faq_list:
        await query.edit_message_text("📋 Список вопросов пока пуст.")
        return
    
    text = "📋 *Частые вопросы:*\n\n"
    for idx, faq in enumerate(faq_list, 1):
        keywords = faq.get('keywords', [])
        text += f"{idx}. {keywords[0].capitalize()}\n"
    
    text += "\n✏️ Просто напишите свой вопрос, и я постараюсь ответить!"
    
    await query.edit_message_text(text, parse_mode='Markdown')

async def operator_request(update: Update, context: CallbackContext):
    """Запрос на связь с оператором"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ Напишите ваш вопрос, и я перешлю его оператору.\n\n"
        "Оператор свяжется с вами в ближайшее время (обычно до 15 минут)."
    )
    context.user_data['waiting_for_operator'] = True

async def handle_message(update: Update, context: CallbackContext):
    """Обработка сообщений от пользователей"""
    user = update.effective_user
    question = update.message.text
    
    # Проверяем, что это не команда
    if question.startswith('/'):
        return
    
    # Если пользователь ждет оператора
    if context.user_data.get('waiting_for_operator'):
        # Отправляем оператору
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🆘 *НОВОЕ ОБРАЩЕНИЕ*\n\n"
                 f"👤 Пользователь: @{user.username or user.first_name}\n"
                 f"🆔 ID: `{user.id}`\n"
                 f"📝 Вопрос:\n{question}\n\n"
                 f"💡 Чтобы ответить, напишите:\n"
                 f"`/reply {user.id} Ваш ответ`",
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(
            "✅ Ваш вопрос передан оператору!\n"
            "Ожидайте ответа в ближайшее время."
        )
        context.user_data['waiting_for_operator'] = False
        return
    
    # Ищем ответ в FAQ
    answer = find_answer(question)
    
    if answer:
        await update.message.reply_text(answer)
    else:
        # Отправляем оператору
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"❓ *НЕИЗВЕСТНЫЙ ВОПРОС*\n\n"
                 f"👤 Пользователь: @{user.username or user.first_name}\n"
                 f"🆔 ID: `{user.id}`\n"
                 f"📝 Вопрос:\n{question}\n\n"
                 f"💡 Чтобы ответить, напишите:\n"
                 f"`/reply {user.id} Ваш ответ`\n\n"
                 f"✏️ Чтобы добавить в базу знаний:\n"
                 f"`/addfaq ключевые_слова | ответ`",
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(
            "🤔 Я не знаю ответа на этот вопрос.\n\n"
            "Но я уже передал его оператору! Он свяжется с вами в ближайшее время.\n"
            "⏱️ Обычно ответ занимает до 15 минут."
        )

# === КОМАНДЫ АДМИНИСТРАТОРА ===
async def admin_reply(update: Update, context: CallbackContext):
    """Ответ пользователю: /reply user_id текст"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 2)
        if len(parts) < 3:
            await update.message.reply_text(
                "❌ Использование: `/reply ID_пользователя Текст ответа`\n\n"
                "Например: `/reply 123456789 Здравствуйте!`",
                parse_mode='Markdown'
            )
            return
        
        user_id = int(parts[1])
        reply_text = parts[2]
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📨 *Ответ поддержки:*\n\n{reply_text}\n\n"
                 f"✉️ Если у вас остались вопросы, просто напишите ещё раз.",
            parse_mode='Markdown'
        )
        
        await update.message.reply_text("✅ Ответ отправлен пользователю.")
        
    except ValueError:
        await update.message.reply_text("❌ ID пользователя должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def add_faq(update: Update, context: CallbackContext):
    """Добавление FAQ: /addfaq ключевые_слова | ответ"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Использование: `/addfaq ключевые_слова | ответ`\n\n"
                "Например: `/addfaq оплата,карта | Мы принимаем карты всех банков.`",
                parse_mode='Markdown'
            )
            return
        
        content = parts[1]
        if '|' not in content:
            await update.message.reply_text(
                "❌ Используйте `|` для разделения ключевых слов и ответа.",
                parse_mode='Markdown'
            )
            return
        
        keywords_str, answer = content.split('|', 1)
        keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
        answer = answer.strip()
        
        if not keywords or not answer:
            await update.message.reply_text("❌ Ключевые слова и ответ не могут быть пустыми.")
            return
        
        faq_id = add_faq_item(keywords, answer)
        
        await update.message.reply_text(
            f"✅ FAQ добавлен! (ID: {faq_id})\n\n"
            f"📌 Ключевые слова: {', '.join(keywords)}\n"
            f"📝 Ответ: {answer}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def list_faq(update: Update, context: CallbackContext):
    """Просмотр всех FAQ: /listfaq"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    
    if not faq_list:
        await update.message.reply_text("📋 База знаний пуста.")
        return
    
    text = "📚 *База знаний:*\n\n"
    for faq in faq_list:
        faq_id = faq.get('id')
        keywords = faq.get('keywords', [])
        answer = faq.get('answer', '')
        text += f"*ID {faq_id}. {', '.join(keywords)}*\n"
        text += f"📝 {answer[:100]}{'...' if len(answer) > 100 else ''}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def delete_faq(update: Update, context: CallbackContext):
    """Удаление FAQ: /delfaq ID"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 2:
            await update.message.reply_text("❌ Использование: `/delfaq ID_вопроса`", parse_mode='Markdown')
            return
        
        faq_id = int(parts[1])
        delete_faq_item(faq_id)
        
        await update.message.reply_text(f"✅ FAQ #{faq_id} удален.")
        
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    """Запуск бота"""
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Команды для пользователей
    app.add_handler(CommandHandler("start", start))
    
    # Команды для администратора
    app.add_handler(CommandHandler("reply", admin_reply))
    app.add_handler(CommandHandler("addfaq", add_faq))
    app.add_handler(CommandHandler("listfaq", list_faq))
    app.add_handler(CommandHandler("delfaq", delete_faq))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(faq_list, pattern="faq"))
    app.add_handler(CallbackQueryHandler(operator_request, pattern="operator"))
    
    # Обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Бот поддержки запущен!")
    logger.info("📌 Команды администратора:")
    logger.info("  /reply ID Текст - ответить пользователю")
    logger.info("  /addfaq слова | ответ - добавить в базу знаний")
    logger.info("  /listfaq - список всех FAQ")
    logger.info("  /delfaq ID - удалить FAQ")
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

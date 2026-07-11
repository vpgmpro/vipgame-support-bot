# bot.py - с Mini-Web-сервером для Render

import logging
import json
import os
import requests
import base64
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters

from config import TOKEN, ADMIN_CHAT_ID, FAQ_FILE

# === Mini-Web-сервер для Render ===
app_flask = Flask(__name__)

@app_flask.route('/')
def health_check():
    return "✅ Бот работает!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Запускаем Flask в отдельном потоке (не мешает боту)
threading.Thread(target=run_flask, daemon=True).start()
# === Конец Mini-Web-сервера ===

# Переменные для GitHub API
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'vpgmpro/vipgame-support-bot')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')
GITHUB_FILE_PATH = os.environ.get('GITHUB_FILE_PATH', 'faq.json')

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

def save_faq_local(faq_list):
    try:
        with open(FAQ_FILE, 'w', encoding='utf-8') as f:
            json.dump({'faq': faq_list}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка локального сохранения: {e}")
        return False

def push_to_github():
    if not GITHUB_TOKEN:
        logger.warning("GitHub токен не настроен, пропускаем push")
        return False, "❌ GitHub токен не настроен"
    
    try:
        with open(FAQ_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sha = response.json()['sha']
        else:
            return False, f"❌ Не удалось получить SHA: {response.status_code}"
        
        data = {
            'message': 'Update faq.json from bot',
            'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            'sha': sha,
            'branch': GITHUB_BRANCH
        }
        
        response = requests.put(url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            logger.info("✅ Файл отправлен на GitHub")
            return True, "✅ Обновлено на GitHub!"
        else:
            return False, f"❌ Ошибка GitHub: {response.status_code}"
            
    except Exception as e:
        logger.error(f"Ошибка push: {e}")
        return False, f"❌ Ошибка: {e}"

def is_admin(user_id):
    return user_id == ADMIN_CHAT_ID

def start(update: Update, context):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📋 Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton("📞 Связаться с оператором", callback_data="operator")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот поддержки. Напишите свой вопрос!",
        reply_markup=reply_markup
    )

def help_command(update: Update, context):
    user_id = update.effective_user.id
    is_admin_user = is_admin(user_id)
    
    text = "📚 Доступные команды:\n\n"
    text += "👤 Для всех пользователей:\n"
    text += "  /start - Начать диалог\n"
    text += "  /help - Показать это сообщение\n\n"
    
    if is_admin_user:
        text += "🔐 Команды администратора:\n"
        text += "  /addfaq ключи | ответ - Добавить FAQ\n"
        text += "  /editfaq ID | новый_ответ - Изменить FAQ\n"
        text += "  /delfaq ID - Удалить FAQ\n"
        text += "  /listfaq - Показать все FAQ\n"
        text += "  /reply ID Текст - Ответить пользователю\n"
        text += "  /sync - Синхронизировать с GitHub\n"
        text += "  /stats - Статистика\n\n"
        text += "📝 Примеры:\n"
        text += "  /addfaq цена,стоимость | 1000 рублей\n"
        text += "  /editfaq 5 | Новая цена: 1500 рублей\n"
        text += "  /reply 123456789 Привет!\n"
    else:
        text += "🔐 Для администраторов доступны дополнительные команды.\n"
    
    if update.callback_query:
        query = update.callback_query
        query.answer()
        query.edit_message_text(text)
    else:
        update.message.reply_text(text)

def add_faq(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text(
                "❌ Использование: /addfaq ключи | ответ\n"
                "Например: /addfaq оплата,карта | Мы принимаем карты"
            )
            return
        
        content = parts[1]
        if '|' not in content:
            update.message.reply_text("❌ Используйте | для разделения ключевых слов и ответа.")
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
        save_faq_local(faq_list)
        
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(
                f"✅ FAQ добавлен! (ID: {new_id})\n"
                f"📌 Ключевые слова: {', '.join(keywords)}\n"
                f"📝 Ответ: {answer}\n\n"
                f"🔗 {message}"
            )
        else:
            update.message.reply_text(
                f"⚠️ FAQ добавлен локально, но не загружен на GitHub.\n"
                f"❌ Ошибка: {message}"
            )
        
    except Exception as e:
        logger.error(f"Ошибка добавления FAQ: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def edit_faq(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text(
                "❌ Использование: /editfaq ID | новый_ответ\n"
                "Например: /editfaq 5 | Новая цена: 1500 рублей"
            )
            return
        
        content = parts[1]
        if '|' not in content:
            update.message.reply_text("❌ Используйте | для разделения ID и нового ответа.")
            return
        
        id_str, new_answer = content.split('|', 1)
        faq_id = int(id_str.strip())
        new_answer = new_answer.strip()
        
        if not new_answer:
            update.message.reply_text("❌ Ответ не может быть пустым.")
            return
        
        faq_list = load_faq()
        found = False
        for faq in faq_list:
            if faq.get('id') == faq_id:
                faq['answer'] = new_answer
                found = True
                break
        
        if not found:
            update.message.reply_text(f"❌ FAQ с ID {faq_id} не найден.")
            return
        
        save_faq_local(faq_list)
        
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(
                f"✅ Ответ для FAQ #{faq_id} обновлен!\n"
                f"📝 Новый ответ: {new_answer}\n\n"
                f"🔗 {message}"
            )
        else:
            update.message.reply_text(
                f"⚠️ Ответ изменен локально, но не загружен на GitHub.\n"
                f"❌ Ошибка: {message}"
            )
        
    except ValueError:
        update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка редактирования FAQ: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def delete_faq(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ')
        if len(parts) < 2:
            update.message.reply_text("❌ Используйте: /delfaq ID")
            return
        
        faq_id = int(parts[1])
        faq_list = load_faq()
        faq_list = [item for item in faq_list if item.get('id') != faq_id]
        save_faq_local(faq_list)
        
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(f"✅ FAQ #{faq_id} удален!\n🔗 {message}")
        else:
            update.message.reply_text(
                f"⚠️ FAQ #{faq_id} удален локально, но не загружен на GitHub.\n"
                f"❌ Ошибка: {message}"
            )
        
    except ValueError:
        update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка удаления FAQ: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")

def list_faq(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    if not faq_list:
        update.message.reply_text("📋 База знаний пуста.")
        return
    
    text = "📚 База знаний:\n\n"
    for faq in faq_list:
        faq_id = faq.get('id')
        keywords = faq.get('keywords', [])
        answer = faq.get('answer', '')
        text += f"ID {faq_id}. {', '.join(keywords)}\n"
        text += f"📝 {answer[:100]}{'...' if len(answer) > 100 else ''}\n\n"
    
    update.message.reply_text(text)

def sync_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    update.message.reply_text("🔄 Синхронизация с GitHub...")
    
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            
            with open(FAQ_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            
            faq_list = load_faq()
            update.message.reply_text(
                f"✅ Синхронизация выполнена!\n"
                f"📊 Всего FAQ: {len(faq_list)}"
            )
        else:
            update.message.reply_text(f"❌ Ошибка GitHub: {response.status_code}")
            
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

def stats_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    total_faq = len(faq_list)
    
    text = f"📊 Статистика бота\n\n"
    text += f"📝 Всего FAQ: {total_faq}\n"
    text += f"👤 Админ ID: {ADMIN_CHAT_ID}\n"
    text += f"🔗 GitHub: {'✅ настроен' if GITHUB_TOKEN else '❌ не настроен'}\n"
    text += f"⏰ Бот активен и работает\n"
    text += f"🔄 Статус: ✅ Онлайн"
    
    update.message.reply_text(text)

def admin_reply(update: Update, context):
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
            text=f"📨 Ответ поддержки:\n\n{reply_text}"
        )
        update.message.reply_text(f"✅ Ответ отправлен пользователю {user_id}!")
        
    except ValueError:
        update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

def faq_list_callback(update: Update, context):
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
    try:
        keyboard = [
            [
                InlineKeyboardButton("📝 Ответить", callback_data=f"reply_{user.id}"),
                InlineKeyboardButton("➕ В базу знаний", callback_data=f"addfaq_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"❓ НОВЫЙ ВОПРОС\n\n"
            f"👤 Пользователь: @{user.username or user.first_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📝 Вопрос:\n{question}"
        )
        
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message_text,
            reply_markup=reply_markup
        )
        logger.info(f"Вопрос переслан админу: {user.id}")
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить админу: {e}")
        return False

def button_callback(update: Update, context):
    query = update.callback_query
    query.answer()
    
    data = query.data
    
    if data.startswith('reply_'):
        user_id = int(data.split('_')[1])
        context.user_data['reply_to_user'] = user_id
        query.edit_message_text(
            f"✏️ Напишите ответ для пользователя {user_id}:\n\n"
            f"Просто отправьте текст — бот перешлёт его."
        )
    
    elif data.startswith('addfaq_'):
        user_id = int(data.split('_')[1])
        context.user_data['addfaq_user'] = user_id
        
        original_message = query.message.text
        try:
            question = original_message.split('📝 Вопрос:\n')[-1]
        except:
            question = "Вопрос не найден"
        context.user_data['addfaq_question'] = question
        
        query.edit_message_text(
            f"✏️ Введите ключевые слова и ответ для вопроса:\n\n"
            f"📝 Вопрос: {question}\n\n"
            f"Формат: `ключевые_слова | ответ`\n"
            f"Пример: `любовь,обожаю | Спасибо! 😊`"
        )

def handle_admin_message(update: Update, context):
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    if context.user_data.get('reply_to_user'):
        target_user_id = context.user_data['reply_to_user']
        reply_text = update.message.text
        
        try:
            context.bot.send_message(
                chat_id=target_user_id,
                text=f"📨 *Ответ поддержки:*\n\n{reply_text}"
            )
            update.message.reply_text(f"✅ Ответ отправлен пользователю {target_user_id}!")
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка при отправке: {e}")
        
        context.user_data['reply_to_user'] = None
        return
    
    if context.user_data.get('addfaq_user'):
        try:
            content = update.message.text
            if '|' not in content:
                update.message.reply_text(
                    "❌ Используйте | для разделения ключевых слов и ответа.\n"
                    "Например: `любовь,обожаю | Спасибо! 😊`"
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
            save_faq_local(faq_list)
            push_to_github()
            
            update.message.reply_text(
                f"✅ Добавлено в базу знаний (ID: {new_id})\n"
                f"📌 Ключевые слова: {', '.join(keywords)}\n"
                f"📝 Ответ: {answer}"
            )
            context.user_data['addfaq_user'] = None
            context.user_data['addfaq_question'] = None
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка: {e}")

def handle_message(update: Update, context):
    user = update.effective_user
    question = update.message.text
    
    if question.startswith('/'):
        return
    
    if context.user_data.get('reply_to_user') or context.user_data.get('addfaq_user'):
        return
    
    if context.user_data.get('waiting_for_operator'):
        sent = send_to_admin(context, user, question)
        if sent:
            update.message.reply_text("✅ Ваш вопрос передан оператору!")
        else:
            update.message.reply_text("⚠️ Не удалось передать вопрос.")
        context.user_data['waiting_for_operator'] = False
        return
    
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
    
    if best_match:
        update.message.reply_text(best_match)
    else:
        sent = send_to_admin(context, user, question)
        if sent:
            update.message.reply_text(
                "✅ Я передал ваш вопрос оператору!\n"
                "⏳ Ожидайте ответа в ближайшее время.\n\n"
                "Спасибо за терпение! 😊"
            )
        else:
            update.message.reply_text(
                "⚠️ К сожалению, не удалось связаться с оператором.\n"
                "Пожалуйста, попробуйте позже."
            )

def error_handler(update, context):
    logger.error(f'Update "{update}" вызвал ошибку "{context.error}"')

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("reply", admin_reply))
    dp.add_handler(CommandHandler("addfaq", add_faq))
    dp.add_handler(CommandHandler("editfaq", edit_faq))
    dp.add_handler(CommandHandler("delfaq", delete_faq))
    dp.add_handler(CommandHandler("listfaq", list_faq))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("sync", sync_command))
    
    dp.add_handler(CallbackQueryHandler(faq_list_callback, pattern="faq"))
    dp.add_handler(CallbackQueryHandler(operator_request, pattern="operator"))
    dp.add_handler(CallbackQueryHandler(help_command, pattern="help"))
    dp.add_handler(CallbackQueryHandler(button_callback))
    
    dp.add_handler(MessageHandler(
        Filters.text & ~Filters.command & Filters.user(ADMIN_CHAT_ID),
        handle_admin_message
    ))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    dp.add_error_handler(error_handler)
    
    logger.info("🤖 Бот поддержки запущен!")
    logger.info(f"📌 Админ ID: {ADMIN_CHAT_ID}")
    logger.info(f"🔑 GitHub токен: {'✅ настроен' if GITHUB_TOKEN else '❌ НЕ НАСТРОЕН'}")
    logger.info("📌 Команды администратора:")
    logger.info("  /addfaq ключи | ответ - добавить")
    logger.info("  /editfaq ID | ответ - изменить")
    logger.info("  /delfaq ID - удалить")
    logger.info("  /listfaq - список FAQ")
    logger.info("  /reply ID Текст - ответить пользователю")
    logger.info("  /sync - синхронизировать с GitHub")
    logger.info("  /stats - статистика")
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

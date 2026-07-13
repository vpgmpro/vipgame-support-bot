# bot.py - Финальная версия с новой архитектурой FAQ

import logging
import json
import os
import re
import requests
import base64
import threading
import time
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters

from config import TOKEN, ADMIN_CHAT_ID, FAQ_FILE, CHANNEL_ID
from database import init_db, save_user, save_question, save_answer, get_stats, get_unanswered_questions, get_last_questions, get_total_users

# === НОВАЯ АРХИТЕКТУРА ПОИСКА ===
from repository import FAQRepository
from search import SearchEngine

# === НОВЫЕ ОБРАБОТЧИКИ FAQ ===
from faq_handlers import (
    faq_categories_handler,
    faq_category_handler,
    faq_answer_handler,
    faq_search_handler,
    faq_search_result,
    faq_noop_handler
)

# === ВЕРСИЯ БОТА ===
BOT_VERSION = "2.0"
BOT_BUILD_DATE = "12.07.2026"

# === FLASK ДЛЯ RENDER ===
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "✅ Бот работает!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()
# === КОНЕЦ БЛОКА FLASK ===

# === КОНСТАНТЫ ===
MIN_MATCH_RATIO = 0.3
EXACT_MATCH_BONUS = 100
LOG_SEARCH_DEBUG = True
TOPIC_BONUS = 15

# Стоп-слова
STOP_WORDS = {'что', 'как', 'где', 'когда', 'ли', 'это', 'такое', 'то', 'чем', 'для', 'без', 'по', 'с', 'в', 'на', 'зачем', 'почему', 'откуда', 'куда', 'кто', 'чей', 'какой', 'какая', 'какое', 'какие', 'мой', 'твой', 'свой', 'наш', 'ваш', 'его', 'её', 'их', 'быть', 'стать', 'являться', 'иметь', 'можно', 'нужно', 'надо', 'будет', 'есть'}

# Темы
TOPIC_WORDS = {'аккаунт', 'игра', 'маркет', 'кристалл', 'статус', 'ячейка'}

_faq_cache = None
_faq_cache_file = None

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'vpgmpro/vipgame-support-bot')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')
GITHUB_FILE_PATH = os.environ.get('GITHUB_FILE_PATH', 'faq.json')

# === ИНИЦИАЛИЗАЦИЯ ===
init_db()

# === НОВАЯ АРХИТЕКТУРА ===
repo = FAQRepository("faq.json")
search = SearchEngine(repo)

# === РАБОТА С ФАЙЛАМИ ===

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
            return False, f"❌ Ошибка GitHub: {response.status_code}"
        
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

# === КЕШИРОВАНИЕ ===

def invalidate_faq_cache():
    global _faq_cache, _faq_cache_file
    _faq_cache = None
    _faq_cache_file = None
    repo.reload()
    logger.info("🔄 Кеш FAQ сброшен и репозиторий перезагружен")

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_faq_with_lemmas():
    global _faq_cache, _faq_cache_file
    
    if _faq_cache is not None and _faq_cache_file == FAQ_FILE:
        return _faq_cache
    
    faq_list = load_faq()
    cache_data = []
    
    for faq in faq_list:
        cache_item = {
            'id': faq.get('id'),
            'answer': faq.get('answer', ''),
            'keywords': faq.get('keywords', []),
            'normalized_keywords': [],
            'topics': set(),
            'lemmas': []
        }
        
        for keyword in faq.get('keywords', []):
            keyword_norm = normalize_text(keyword)
            cache_item['normalized_keywords'].append(keyword_norm)
            
            try:
                import pymorphy3
                morph = pymorphy3.MorphAnalyzer()
                keyword_lemmas = ' '.join(morph.parse(w)[0].normal_form for w in keyword_norm.split())
            except:
                keyword_lemmas = keyword_norm
            cache_item['lemmas'].append(keyword_lemmas)
            
            keyword_tokens = set(keyword_norm.split())
            for w in keyword_tokens:
                if w in TOPIC_WORDS:
                    cache_item['topics'].add(w)
        
        cache_data.append(cache_item)
    
    _faq_cache = cache_data
    _faq_cache_file = FAQ_FILE
    logger.info(f"✅ Кеш FAQ загружен: {len(cache_data)} записей")
    return _faq_cache

def find_answer(question):
    result = search.find_best(question)
    return result.answer

# === ОСТАЛЬНЫЕ ФУНКЦИИ ===

def is_admin(user_id):
    return user_id == ADMIN_CHAT_ID

def start(update: Update, context):
    user = update.effective_user
    save_user(user)
    
    keyboard = [
        [InlineKeyboardButton("📋 Частые вопросы", callback_data="faq_categories")],
        [InlineKeyboardButton("📞 Связаться с оператором", callback_data="operator")],
        [InlineKeyboardButton("📢 Официальный канал", url="https://t.me/vipg_channel")],
        [InlineKeyboardButton("📱 Скачать приложение", callback_data="apk")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот поддержки. Напишите свой вопрос!\n"
        "Вы также можете отправить фото, видео или файл.",
        reply_markup=reply_markup
    )

def help_command(update: Update, context):
    user_id = update.effective_user.id
    is_admin_user = is_admin(user_id)
    
    text = "🤖 *VIP Game | Support Bot*\n\n"
    text += "👤 *Команды для пользователей*\n"
    text += "/start — Начать диалог\n"
    text += "/help — Справка\n"
    text += "/apk — Скачать приложение для Android\n\n"
    text += "📎 *Вы также можете отправить:*\n"
    text += "• текстовое сообщение\n"
    text += "• фотографию\n"
    text += "• видео\n"
    text += "• документ (PDF, Word, Excel и др.)\n\n"
    
    if is_admin_user:
        text += "🔐 *Команды администратора*\n"
        text += "/addfaq ключи | ответ — Добавить FAQ\n"
        text += "/editfaq ID | ключи | ответ — Изменить FAQ\n"
        text += "/delfaq ID — Удалить FAQ\n"
        text += "/listfaq — Показать список всех FAQ\n"
        text += "/findfaq слово — Найти в FAQ\n"
        text += "/faqcount — Количество FAQ\n"
        text += "/reply — Ответить пользователю\n"
        text += "/post — Опубликовать в канал\n"
        text += "/stats — Статистика\n"
        text += "/reload — Перезагрузить FAQ\n"
        text += "/unanswered — Вопросы без ответа\n"
        text += "/last — Последние вопросы\n"
        text += "/users — Количество пользователей\n"
        text += "/sync — Синхронизировать с GitHub\n"
        text += "/ping — Проверка работы бота\n"
        text += "/version — Версия бота\n\n"
        text += "📝 *Примеры*\n"
        text += "/addfaq цена,стоимость | 1000 рублей\n"
        text += "/editfaq 5 | цена,стоимость,сколько стоит | 1500 рублей\n"
        text += "/findfaq кристаллы\n"
        text += "/reply 123456789 Привет!\n"
        text += "/post Сегодня вышло обновление!\n"
    
    if update.callback_query:
        query = update.callback_query
        query.answer()
        query.edit_message_text(text, parse_mode='Markdown')
    else:
        update.message.reply_text(text, parse_mode='Markdown')

def send_apk_document(update: Update, context):
    apk_url = "https://github.com/vpgmpro/vipgame-support-bot/releases/download/v1.1/VIPGame.apk"
    
    msg = update.message.reply_text("⏳ Загружаю приложение...")
    
    try:
        response = requests.get(apk_url, stream=True)
        if response.status_code == 200:
            context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=response.content,
                filename="VIPGame.apk",
                caption="📱 *VIP Game для Android*\n\nНажмите на файл, чтобы скачать и установить.\n\n📌 *Как установить:*\n1. Откройте файл\n2. Разрешите установку из неизвестных источников\n3. Нажмите «Установить»",
                parse_mode='Markdown'
            )
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
        else:
            update.message.reply_text("❌ Не удалось загрузить файл. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка отправки APK: {e}")
        update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

def add_faq(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    try:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text("❌ Использование: /addfaq ключи | ответ\nНапример: /addfaq оплата,карта | Мы принимаем карты")
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
            'slug': f"faq_{new_id}",
            'title': answer[:50] if answer else keywords[0].capitalize(),
            'category': 'other',
            'sort': new_id * 10,
            'keywords': keywords,
            'answer': answer
        })
        
        save_faq_local(faq_list)
        invalidate_faq_cache()
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(f"✅ FAQ #{new_id} добавлен\n📌 Ключей: {len(keywords)}\n🔄 GitHub: {message}")
        else:
            update.message.reply_text(f"⚠️ FAQ добавлен локально, но не загружен на GitHub.\n❌ Ошибка: {message}")
        
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
            update.message.reply_text("❌ Использование: /editfaq ID | новые_ключи | новый_ответ\nНапример: /editfaq 5 | регистрация,аккаунт | Текст ответа")
            return
        
        content = parts[1]
        if '|' not in content:
            update.message.reply_text("❌ Используйте | для разделения ID, ключей и ответа.")
            return
        
        parts_content = content.split('|')
        if len(parts_content) < 3:
            update.message.reply_text("❌ Формат: /editfaq ID | новые_ключи | новый_ответ\nНапример: /editfaq 5 | регистрация,аккаунт | Текст ответа")
            return
        
        faq_id = int(parts_content[0].strip())
        keywords_str = parts_content[1].strip()
        new_answer = parts_content[2].strip()
        
        if not keywords_str or not new_answer:
            update.message.reply_text("❌ Ключевые слова и ответ не могут быть пустыми.")
            return
        
        keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
        
        if not keywords:
            update.message.reply_text("❌ Нужно указать хотя бы одно ключевое слово.")
            return
        
        faq_list = load_faq()
        found = False
        for faq in faq_list:
            if faq.get('id') == faq_id:
                faq['keywords'] = keywords
                faq['answer'] = new_answer
                if 'title' in faq:
                    faq['title'] = new_answer[:50] if new_answer else keywords[0].capitalize()
                found = True
                break
        
        if not found:
            update.message.reply_text(f"❌ FAQ с ID {faq_id} не найден.")
            return
        
        save_faq_local(faq_list)
        invalidate_faq_cache()
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(f"✅ FAQ #{faq_id} обновлен\n📌 Ключей: {len(keywords)}\n🔄 GitHub: {message}")
        else:
            update.message.reply_text(f"⚠️ FAQ обновлен локально, но не загружен на GitHub.\n❌ Ошибка: {message}")
        
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
        invalidate_faq_cache()
        success, message = push_to_github()
        
        if success:
            update.message.reply_text(f"✅ FAQ #{faq_id} удален\n🔄 GitHub: {message}")
        else:
            update.message.reply_text(f"⚠️ FAQ #{faq_id} удален локально, но не загружен на GitHub.\n❌ Ошибка: {message}")
        
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
    
    text = "📚 *База знаний:*\n\n"
    for faq in faq_list:
        faq_id = faq.get('id')
        slug = faq.get('slug', 'no-slug')
        title = faq.get('title', faq.get('keywords', [''])[0].capitalize())
        keywords = faq.get('keywords', [])
        answer = faq.get('answer', '')
        text += f"*ID {faq_id}* ({slug}): {title}\n"
        text += f"📌 Ключи: {', '.join(keywords)}\n"
        text += f"📝 {answer[:100]}{'...' if len(answer) > 100 else ''}\n\n"
    
    update.message.reply_text(text, parse_mode='Markdown')

def findfaq_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    parts = update.message.text.split(' ', 1)
    if len(parts) < 2:
        update.message.reply_text("❌ Использование: /findfaq слово")
        return
    
    search_word = parts[1].lower().strip()
    faq_list = load_faq()
    
    results = []
    for faq in faq_list:
        keywords_str = ' '.join(faq.get('keywords', [])).lower()
        title = faq.get('title', '').lower()
        answer = faq.get('answer', '').lower()
        
        if search_word in keywords_str or search_word in title or search_word in answer:
            results.append(faq)
    
    if not results:
        update.message.reply_text(f"❌ По запросу '{search_word}' ничего не найдено.")
        return
    
    text = f"🔍 *Результаты поиска по '{search_word}':*\n\n"
    for faq in results[:5]:
        faq_id = faq.get('id')
        slug = faq.get('slug', 'no-slug')
        title = faq.get('title', faq.get('keywords', [''])[0].capitalize())
        answer = faq.get('answer', '')
        text += f"*ID {faq_id}* ({slug}): {title}\n"
        text += f"📝 {answer}\n\n"
    
    if len(results) > 5:
        text += f"... и ещё {len(results) - 5} результатов. Используйте /listfaq для просмотра всех."
    
    update.message.reply_text(text, parse_mode='Markdown')

def faqcount_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    update.message.reply_text(f"📚 Всего FAQ: {len(faq_list)}")

def reload_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    invalidate_faq_cache()
    faq_list = load_faq()
    update.message.reply_text(f"✅ FAQ перезагружены!\n📚 Всего записей: {len(faq_list)}")

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
            
            invalidate_faq_cache()
            
            faq_list = load_faq()
            update.message.reply_text(f"✅ Синхронизация выполнена!\n📊 Всего FAQ: {len(faq_list)}")
        else:
            update.message.reply_text(f"❌ Ошибка GitHub: {response.status_code}")
            
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

def stats_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    stats = get_stats()
    faq_list = load_faq()
    
    auto_answer_percent = 0
    if stats['total_questions'] > 0:
        auto_answer_percent = round((stats['answered'] / stats['total_questions']) * 100, 1)
    
    text = f"📊 *Статистика бота*\n\n"
    text += f"👥 Пользователей: {stats['total_users']}\n"
    text += f"💬 Всего вопросов: {stats['total_questions']}\n"
    text += f"🤖 FAQ ответил: {stats['answered']}\n"
    text += f"👨‍💼 Передано оператору: {stats['unanswered']}\n"
    text += f"📚 FAQ в базе: {len(faq_list)}\n"
    text += f"📈 Процент автоматических ответов: {auto_answer_percent}%\n"
    text += f"🔗 GitHub: {'✅ настроен' if GITHUB_TOKEN else '❌ не настроен'}\n"
    text += f"⏰ Бот активен и работает\n"
    text += f"🔄 Статус: ✅ Онлайн"
    
    update.message.reply_text(text, parse_mode='Markdown')

def unanswered_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    questions = get_unanswered_questions(20)
    
    if not questions:
        update.message.reply_text("✅ Нет вопросов без ответа!")
        return
    
    text = "📋 *Вопросы без ответа:*\n\n"
    for q in questions:
        q_id, user_id, question, username, created_at = q
        username = f"@{username}" if username else f"ID: {user_id}"
        text += f"#{q_id} | {username}\n📝 {question[:80]}...\n\n"
    
    update.message.reply_text(text, parse_mode='Markdown')

def last_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    questions = get_last_questions(10)
    
    if not questions:
        update.message.reply_text("📭 Нет вопросов.")
        return
    
    text = "📋 *Последние вопросы:*\n\n"
    for q in questions:
        q_id, user_id, question, answered, username, created_at = q
        username = f"@{username}" if username else f"ID: {user_id}"
        status = "✅" if answered else "⏳"
        text += f"{status} #{q_id} | {username}\n📝 {question[:80]}...\n\n"
    
    update.message.reply_text(text, parse_mode='Markdown')

def users_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    count = get_total_users()
    update.message.reply_text(f"👥 Всего пользователей: {count}")

def ping_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    update.message.reply_text("🟢 Бот работает!")

def version_command(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    faq_list = load_faq()
    
    text = f"🤖 *Support Bot*\n\n"
    text += f"📌 Версия: {BOT_VERSION}\n"
    text += f"📅 Сборка: {BOT_BUILD_DATE}\n"
    text += f"📚 FAQ: {len(faq_list)}\n"
    text += f"🔗 GitHub: {GITHUB_BRANCH}\n"
    text += f"🔍 Search Engine: 2.0.0\n"
    text += f"🔄 Статус: ✅ Онлайн"
    
    update.message.reply_text(text, parse_mode='Markdown')

def admin_reply(update: Update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    
    if update.message.photo:
        photo = update.message.photo[-1]
        caption = update.message.caption or "📸"
        parts = caption.split(' ', 1)
        if len(parts) >= 2 and parts[0].isdigit():
            user_id = int(parts[0])
            reply_text = parts[1] if len(parts) > 1 else "Фото"
            try:
                context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{reply_text}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Фото отправлено пользователю {user_id}!")
                return
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
                return
        else:
            update.message.reply_text("❌ Формат: /reply ID текст")
            return
    
    if update.message.video:
        video = update.message.video
        caption = update.message.caption or "🎬"
        parts = caption.split(' ', 1)
        if len(parts) >= 2 and parts[0].isdigit():
            user_id = int(parts[0])
            reply_text = parts[1] if len(parts) > 1 else "Видео"
            try:
                context.bot.send_video(
                    chat_id=user_id,
                    video=video.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{reply_text}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Видео отправлено пользователю {user_id}!")
                return
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
                return
        else:
            update.message.reply_text("❌ Формат: /reply ID текст")
            return
    
    if update.message.document:
        document = update.message.document
        caption = update.message.caption or f"📄 {document.file_name}"
        parts = caption.split(' ', 1)
        if len(parts) >= 2 and parts[0].isdigit():
            user_id = int(parts[0])
            reply_text = parts[1] if len(parts) > 1 else "Файл"
            try:
                context.bot.send_document(
                    chat_id=user_id,
                    document=document.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{reply_text}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Файл отправлен пользователю {user_id}!")
                return
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
                return
        else:
            update.message.reply_text("❌ Формат: /reply ID текст")
            return
    
    try:
        parts = update.message.text.split(' ', 2)
        if len(parts) < 3:
            update.message.reply_text("❌ Используйте: /reply ID_пользователя Текст\n\nИли отправьте фото/видео с подписью: /reply ID текст")
            return
        
        user_id = int(parts[1])
        reply_text = parts[2]
        
        context.bot.send_message(
            chat_id=user_id,
            text=f"📨 *Ответ поддержки:*\n\n{reply_text}",
            parse_mode='Markdown'
        )
        update.message.reply_text(f"✅ Ответ отправлен пользователю {user_id}!")
        
    except ValueError:
        update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

def faq_list_callback(update: Update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text("📚 Пожалуйста, выберите категорию в главном меню.")

def operator_request(update: Update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text("✏️ Напишите ваш вопрос, я перешлю его оператору.\n\n"
                           "Вы также можете отправить фото, видео или файл.")
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
    # ⚠️ Этот обработчик больше НЕ ИСПОЛЬЗУЕТСЯ для FAQ
    # Он оставлен только для обратной совместимости со старыми кнопками
    # (reply_ и addfaq_ обрабатываются в handle_admin_message)
    query = update.callback_query
    query.answer()
    
    data = query.data
    
    if data.startswith('reply_'):
        user_id = int(data.split('_')[1])
        context.user_data['reply_to_user'] = user_id
        query.edit_message_text(
            f"✏️ Напишите ответ для пользователя {user_id}:\n\n"
            f"Просто отправьте текст — бот перешлёт его.\n"
            f"Или отправьте фото/видео/файл с подписью: текст"
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
    elif data == "apk":
        chat_id = query.message.chat.id
        apk_url = "https://github.com/vpgmpro/vipgame-support-bot/releases/download/v1.1/VIPGame.apk"
        query.edit_message_text("⏳ Загружаю приложение...")
        try:
            response = requests.get(apk_url, stream=True)
            if response.status_code == 200:
                context.bot.send_document(
                    chat_id=chat_id,
                    document=response.content,
                    filename="VIPGame.apk",
                    caption="📱 *VIP Game для Android*\n\nНажмите на файл, чтобы скачать и установить.\n\n📌 *Как установить:*\n1. Откройте файл\n2. Разрешите установку из неизвестных источников\n3. Нажмите «Установить»",
                    parse_mode='Markdown'
                )
                context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
            else:
                query.edit_message_text("❌ Не удалось загрузить файл. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Ошибка отправки APK через кнопку: {e}")
            query.edit_message_text("❌ Произошла ошибка. Попробуйте позже.")

def handle_admin_message(update: Update, context):
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    if context.user_data.get('waiting_post'):
        if update.message.photo:
            photo = update.message.photo[-1]
            caption = update.message.caption or "📸"
            try:
                context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo.file_id, caption=caption)
                update.message.reply_text("✅ Фото опубликовано в канале!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.video:
            video = update.message.video
            caption = update.message.caption or "🎬"
            try:
                context.bot.send_video(chat_id=CHANNEL_ID, video=video.file_id, caption=caption)
                update.message.reply_text("✅ Видео опубликовано в канале!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.document:
            document = update.message.document
            caption = update.message.caption or f"📄 {document.file_name}"
            try:
                context.bot.send_document(chat_id=CHANNEL_ID, document=document.file_id, caption=caption)
                update.message.reply_text("✅ Файл опубликован в канале!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.text:
            text = update.message.text
            try:
                context.bot.send_message(chat_id=CHANNEL_ID, text=text)
                update.message.reply_text("✅ Опубликовано в канале!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        context.user_data['waiting_post'] = None
        return
    
    if context.user_data.get('reply_to_user'):
        target_user_id = context.user_data['reply_to_user']
        
        if update.message.photo:
            photo = update.message.photo[-1]
            caption = update.message.caption or "📸 Фото"
            try:
                context.bot.send_photo(
                    chat_id=target_user_id,
                    photo=photo.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{caption}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Фото отправлено пользователю {target_user_id}!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.video:
            video = update.message.video
            caption = update.message.caption or "🎬 Видео"
            try:
                context.bot.send_video(
                    chat_id=target_user_id,
                    video=video.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{caption}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Видео отправлено пользователю {target_user_id}!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.document:
            document = update.message.document
            caption = update.message.caption or f"📄 {document.file_name}"
            try:
                context.bot.send_document(
                    chat_id=target_user_id,
                    document=document.file_id,
                    caption=f"📨 *Ответ поддержки:*\n\n{caption}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Файл отправлен пользователю {target_user_id}!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
        elif update.message.text:
            reply_text = update.message.text
            try:
                context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📨 *Ответ поддержки:*\n\n{reply_text}",
                    parse_mode='Markdown'
                )
                update.message.reply_text(f"✅ Ответ отправлен пользователю {target_user_id}!")
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка: {e}")
        
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
                'slug': f"faq_{new_id}",
                'title': answer[:50] if answer else keywords[0].capitalize(),
                'category': 'other',
                'sort': new_id * 10,
                'keywords': keywords,
                'answer': answer
            })
            save_faq_local(faq_list)
            invalidate_faq_cache()
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

def post_command(update: Update, context):
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("⛔ У вас нет прав.")
        return
    
    context.user_data['waiting_post'] = True
    update.message.reply_text(
        "📝 Отправьте текст, фото, видео или файл для публикации в канале.\n"
        "📌 Можно добавить подпись к фото/видео."
    )

def handle_message(update: Update, context):
    user = update.effective_user
    
    save_user(user)
    
    if context.user_data.get('waiting_post') or context.user_data.get('reply_to_user') or context.user_data.get('addfaq_user'):
        return
    
    if update.message.photo:
        photo = update.message.photo[-1]
        caption = update.message.caption or "📸 Фото без подписи"
        
        context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=photo.file_id,
            caption=f"📸 ФОТО от @{user.username or user.first_name} (ID: {user.id})\n\n{caption}"
        )
        update.message.reply_text("✅ Ваше фото отправлено оператору!")
        return
    
    elif update.message.video:
        video = update.message.video
        caption = update.message.caption or "🎬 Видео без подписи"
        
        context.bot.send_video(
            chat_id=ADMIN_CHAT_ID,
            video=video.file_id,
            caption=f"🎬 ВИДЕО от @{user.username or user.first_name} (ID: {user.id})\n\n{caption}"
        )
        update.message.reply_text("✅ Ваше видео отправлено оператору!")
        return
    
    elif update.message.document:
        document = update.message.document
        caption = update.message.caption or f"📄 Файл: {document.file_name}"
        
        context.bot.send_document(
            chat_id=ADMIN_CHAT_ID,
            document=document.file_id,
            caption=f"📄 ФАЙЛ от @{user.username or user.first_name} (ID: {user.id})\n\n{caption}"
        )
        update.message.reply_text("✅ Ваш файл отправлен оператору!")
        return
    
    question = update.message.text
    logger.info(f"📩 ПОЛУЧЕН ЗАПРОС: '{question}' от {user.id}")
    
    if question.startswith('/'):
        return
    
    if context.user_data.get('waiting_for_operator'):
        sent = send_to_admin(context, user, question)
        save_question(user.id, question)
        if sent:
            update.message.reply_text("✅ Ваш вопрос передан оператору!")
        else:
            update.message.reply_text("⚠️ Не удалось передать вопрос.")
        context.user_data['waiting_for_operator'] = False
        return
    
    result = search.find_best(question)
    answer = result.answer
    
    if answer:
        update.message.reply_text(answer)
        save_question(user.id, question, answer)
    else:
        sent = send_to_admin(context, user, question)
        save_question(user.id, question)
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
    
    # === КОМАНДЫ ===
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("reply", admin_reply))
    dp.add_handler(CommandHandler("addfaq", add_faq))
    dp.add_handler(CommandHandler("editfaq", edit_faq))
    dp.add_handler(CommandHandler("delfaq", delete_faq))
    dp.add_handler(CommandHandler("listfaq", list_faq))
    dp.add_handler(CommandHandler("findfaq", findfaq_command))
    dp.add_handler(CommandHandler("faqcount", faqcount_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("sync", sync_command))
    dp.add_handler(CommandHandler("reload", reload_command))
    dp.add_handler(CommandHandler("post", post_command))
    dp.add_handler(CommandHandler("unanswered", unanswered_command))
    dp.add_handler(CommandHandler("last", last_command))
    dp.add_handler(CommandHandler("users", users_command))
    dp.add_handler(CommandHandler("ping", ping_command))
    dp.add_handler(CommandHandler("version", version_command))
    dp.add_handler(CommandHandler("apk", send_apk_document))
    
    # === НОВЫЕ ОБРАБОТЧИКИ FAQ (callback) ===
    dp.add_handler(CallbackQueryHandler(faq_categories_handler, pattern="faq_categories"))
    dp.add_handler(CallbackQueryHandler(faq_category_handler, pattern="faq_cat_"))
    dp.add_handler(CallbackQueryHandler(faq_answer_handler, pattern="faq_ans_"))
    dp.add_handler(CallbackQueryHandler(faq_search_handler, pattern="faq_search"))
    dp.add_handler(CallbackQueryHandler(faq_noop_handler, pattern="faq_noop"))
    
    # === СТАРЫЕ ОБРАБОТЧИКИ (только для reply_ и addfaq_, apk) ===
    dp.add_handler(CallbackQueryHandler(button_callback))
    
    # === ОБРАБОТЧИКИ СООБЩЕНИЙ ===
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, faq_search_result))
    dp.add_handler(MessageHandler(
        Filters.text & ~Filters.command & Filters.user(ADMIN_CHAT_ID),
        handle_admin_message
    ))
    dp.add_handler(MessageHandler(Filters.photo, handle_message))
    dp.add_handler(MessageHandler(Filters.video, handle_message))
    dp.add_handler(MessageHandler(Filters.document, handle_message))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    dp.add_error_handler(error_handler)
    
    get_faq_with_lemmas()
    
    logger.info("🤖 Бот поддержки запущен!")
    logger.info(f"📌 Админ ID: {ADMIN_CHAT_ID}")
    logger.info(f"🔑 GitHub токен: {'✅ настроен' if GITHUB_TOKEN else '❌ НЕ НАСТРОЕН'}")
    logger.info("📌 Команды администратора:")
    logger.info("  /addfaq ключи | ответ - добавить")
    logger.info("  /editfaq ID | ключи | ответ - изменить")
    logger.info("  /delfaq ID - удалить")
    logger.info("  /listfaq - список FAQ")
    logger.info("  /findfaq слово - поиск в FAQ")
    logger.info("  /faqcount - количество FAQ")
    logger.info("  /reply - ответить пользователю")
    logger.info("  /post - опубликовать в канал")
    logger.info("  /stats - статистика")
    logger.info("  /reload - перезагрузить FAQ")
    logger.info("  /unanswered - вопросы без ответа")
    logger.info("  /last - последние вопросы")
    logger.info("  /users - количество пользователей")
    logger.info("  /ping - проверка работы")
    logger.info("  /version - версия бота")
    logger.info("  /sync - синхронизировать с GitHub")
    logger.info("  /apk - скачать приложение для Android")
    logger.info("📎 Бот принимает фото, видео и файлы")

    # === СБРОС WEBHOOK И ПОВТОРНЫЕ ПОПЫТКИ ===
    updater.bot.delete_webhook()
    logger.info("⏳ Ожидание 30 секунд перед запуском...")
    time.sleep(30)

    max_retries = 10
    base_delay = 5
    for attempt in range(max_retries):
        try:
            updater.start_polling()
            logger.info("✅ Бот успешно запущен!")
            break
        except Exception as e:
            logger.error(f"Попытка {attempt+1}/{max_retries} не удалась: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Повторная попытка через {delay} секунд...")
                time.sleep(delay)
            else:
                logger.critical("Не удалось запустить бот после всех попыток.")
                raise

    updater.idle()

if __name__ == "__main__":
    main()

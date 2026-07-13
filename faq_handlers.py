import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from repository import repo
from config import FAQ_CATEGORIES, FAQ_ITEMS_PER_PAGE

logger = logging.getLogger(__name__)

def faq_categories_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    
    cats = repo.categories()
    
    # Собираем кнопки категорий
    cat_buttons = []
    for cat_key, cat_info in sorted(FAQ_CATEGORIES.items(), key=lambda x: x[1]['order']):
        if cat_key in cats and cats[cat_key]:
            cat_buttons.append(
                InlineKeyboardButton(
                    cat_info['name'],
                    callback_data=f"faq_cat_{cat_key}_0"
                )
            )
    
    # Разбиваем по 4 в ряд
    keyboard = []
    for i in range(0, len(cat_buttons), 4):
        keyboard.append(cat_buttons[i:i+4])
    
    # Нижняя строка
    keyboard.append([
        InlineKeyboardButton("🔍 Найти вопрос", callback_data="faq_search"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        "📚 *Частые вопросы*\n\n"
        "Выберите категорию или найдите ответ:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def faq_category_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    
    parts = query.data.split('_')
    category_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    
    questions = repo.by_category(category_key)
    if not questions:
        query.edit_message_text("❌ В этой категории пока нет вопросов.")
        return
    
    total_pages = (len(questions) + FAQ_ITEMS_PER_PAGE - 1) // FAQ_ITEMS_PER_PAGE
    start = page * FAQ_ITEMS_PER_PAGE
    end = min(start + FAQ_ITEMS_PER_PAGE, len(questions))
    
    keyboard = []
    for faq in questions[start:end]:
        keyboard.append([
            InlineKeyboardButton(faq.title, callback_data=f"faq_ans_{faq.slug}")  # ← изменено
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"faq_cat_{category_key}_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="faq_noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"faq_cat_{category_key}_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад к категориям", callback_data="faq_categories"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    ])
    
    cat_name = FAQ_CATEGORIES.get(category_key, {}).get('name', category_key)
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        f"📚 *{cat_name}*\n\n"
        f"Выберите вопрос:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def faq_answer_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    
    # Извлекаем slug (после "faq_ans_")
    slug = query.data.replace('faq_ans_', '')
    faq = repo.by_slug(slug)
    if not faq:
        query.edit_message_text("❌ Вопрос не найден.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=f"faq_cat_{faq.category}_0"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        faq.answer,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def faq_search_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "🔍 *Поиск по FAQ*\n\n"
        "Напишите ключевое слово или фразу для поиска.",
        parse_mode='Markdown'
    )
    context.user_data['waiting_for_faq_search'] = True

def faq_search_result(update: Update, context):
    if not context.user_data.get('waiting_for_faq_search'):
        return
    context.user_data['waiting_for_faq_search'] = False
    
    query_text = update.message.text.lower().strip()
    if not query_text:
        update.message.reply_text("❌ Введите слово для поиска.")
        return
    
    results = repo.search(query_text)
    
    if not results:
        update.message.reply_text(
            f"❌ По запросу *{query_text}* ничего не найдено.\n\n"
            f"Попробуйте переформулировать запрос.",
            parse_mode='Markdown'
        )
        return
    
    keyboard = []
    for faq in results[:10]:
        keyboard.append([
            InlineKeyboardButton(faq.title, callback_data=f"faq_ans_{faq.slug}")  # ← изменено
        ])
    
    if len(results) > 10:
        keyboard.append([InlineKeyboardButton(f"🔍 Найдено ещё {len(results)-10} результатов", callback_data="faq_noop")])
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад к категориям", callback_data="faq_categories"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        f"🔍 *Результаты поиска по '{query_text}':*\n\n"
        f"Найдено вопросов: {len(results)}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def faq_noop_handler(update: Update, context):
    query = update.callback_query
    query.answer()

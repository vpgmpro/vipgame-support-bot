import os

# === ТОКЕН БОТА ===
TOKEN = "8853582530:AAHNZcuShC7Aol1wnSL34p1X7_pb_jMfVic"  # Замените на ваш токен

# === АДМИНИСТРАТОР ===
ADMIN_CHAT_ID = 8805394165  # Ваш Telegram ID (узнать у @userinfobot)

# === ФАЙЛ С ВОПРОСАМИ ===
FAQ_FILE = "faq.json"

# === БАЗА ДАННЫХ ===
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///support.db')

# === КАНАЛ ДЛЯ ПУБЛИКАЦИЙ ===
CHANNEL_ID = -1003765070433  # ID канала (с минусом!)

# === НАСТРОЙКИ ДЛЯ FLASK (Render) ===
PORT = int(os.environ.get('PORT', 10000))

# === НАСТРОЙКИ GITHUB (для синхронизации) ===
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')          # Токен GitHub (обязательно в переменных окружения)
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'vpgmpro/vipgame-support-bot')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')
GITHUB_FILE_PATH = os.environ.get('GITHUB_FILE_PATH', 'faq.json')

# === НАСТРОЙКИ FAQ (категории и пагинация) ===
FAQ_ITEMS_PER_PAGE = 8

FAQ_CATEGORIES = {
    "general": {"name": "🔹 Общее", "order": 0},
    "account": {"name": "👤 Аккаунт", "order": 1},
    "games": {"name": "🎮 Игры", "order": 2},
    "status": {"name": "⭐ Статус", "order": 3},
    "crystals_market": {"name": "💎 Кристаллы и Маркет", "order": 4},
    "megainviter": {"name": "🚀 Mega Inviter", "order": 5},
    "about_project": {"name": "🤝 О проекте", "order": 6},
    "support": {"name": "📞 Поддержка", "order": 7}
}

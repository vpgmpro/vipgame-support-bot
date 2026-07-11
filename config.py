# config.py
import os

# Токен бота (можно хранить в переменных окружения)
TOKEN = "8853582530:AAHNZcuShC7Aol1wnSL34p1X7_pb_jMfVic"  # Замените на ваш токен

# ID администратора (узнать у @userinfobot)
ADMIN_CHAT_ID = 8805394165  # Замените на ваш ID

# Путь к файлу с FAQ
FAQ_FILE = "faq.json"

# Настройки базы данных (опционально)
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///support.db')
CHANNEL_ID = -1003765070433  # ← ВСТАВЬ СВОЙ ID (с минусом!)

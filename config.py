# config.py
import os

# Токен бота (можно хранить в переменных окружения)
TOKEN = "8709088661:AAF_wzJjk_djr4Cz8Zz3nuLNPHyDmOG-obc"  # Замените на ваш токен

# ID администратора (узнать у @userinfobot)
ADMIN_CHAT_ID = -5177697795  # Замените на ваш ID

# Путь к файлу с FAQ
FAQ_FILE = "faq.json"

# Настройки базы данных (опционально)
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///support.db')

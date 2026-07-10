# config.py
import os

# Токен бота (можно хранить в переменных окружения)
TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"  # Замените на ваш токен

# ID администратора (узнать у @userinfobot)
ADMIN_CHAT_ID = 123456789  # Замените на ваш ID

# Путь к файлу с FAQ
FAQ_FILE = "faq.json"

# Настройки базы данных (опционально)
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///support.db')

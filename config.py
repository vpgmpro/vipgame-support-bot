import os

print("=" * 50)
print("DEBUG ENV")
print("BOT_TOKEN =", os.getenv("BOT_TOKEN"))
print("SUPPORT_CHAT_ID =", os.getenv("SUPPORT_CHAT_ID"))
print("=" * 50)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")

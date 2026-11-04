import os

API_ID = int(os.environ.get("API_ID", "12345678"))
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here")
MONGO_URI = os.environ.get("MONGO_URI", "your_mongo_url_here")

admins_str = os.environ.get("ADMINS", "123456789")
ADMINS = [int(x.strip()) for x in admins_str.split(",")]

BACKUP_CHANNEL_ID = int(os.environ.get("BACKUP_CHANNEL_ID", "-1001234567890"))
DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "https://hanker.com")

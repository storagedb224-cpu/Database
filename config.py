import os

# Telegram API Credentials
API_ID = int(os.environ.get("API_ID", "12345678")) # अपना API ID डालें
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here")

# MongoDB URL
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority")

# Admin IDs (सिर्फ ये लोग बॉट इस्तेमाल कर सकेंगे)
ADMINS = [123456789, 987654321] # अपनी टेलीग्राम ID यहाँ डालें

# Universal Backup Channel (यहाँ सब कुछ सेव होगा)
BACKUP_CHANNEL_ID = int(os.environ.get("BACKUP_CHANNEL_ID", "-1001234567890"))

# डोमेन नेम (URL के लिए)
DOMAIN_NAME = "https://hanker.com"

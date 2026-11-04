from pyrogram import filters
import config

ADMIN_STATES = {}

HIERARCHY = {
    "coaching": {"next": "course", "title": "Coaching"},
    "course": {"next": "subject", "title": "Course"},
    "subject": {"next": "teacher", "title": "Subject"},
    "teacher": {"next": "topic", "title": "Teacher"},
    "topic": {"next": "upload", "title": "Topic"},
    "upload": {"next": None, "title": "Files"}
}

# 🆕 Pyrogram का नेटिव कस्टम एडमिन फिल्टर
async def check_admin(_, client, message):
    if hasattr(message, 'from_user') and message.from_user:
        return message.from_user.id in config.ADMINS
    return False

admin_filter = filters.create(check_admin)

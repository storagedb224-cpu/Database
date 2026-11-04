from functools import wraps  # 🆕 यह लाइन जोड़ी गई है
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

def is_admin(func):
    @wraps(func)  # 🆕 यह लगाना बहुत ज़रूरी है
    async def wrapper(client, message):
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.message.chat.id
        if user_id in config.ADMINS:
            return await func(client, message)
    return wrapper

import config

# Bot ka state yaad rakhne ke liye (kaun kya add kar raha hai)
ADMIN_STATES = {}

# Menu ka flow
HIERARCHY = {
    "coaching": {"next": "course", "title": "Coaching"},
    "course": {"next": "subject", "title": "Course"},
    "subject": {"next": "teacher", "title": "Subject"},
    "teacher": {"next": "topic", "title": "Teacher"},
    "topic": {"next": "upload", "title": "Topic"},
    "upload": {"next": None, "title": "Files"}
}

# Admin check karne wala lock
def is_admin(func):
    async def wrapper(client, message):
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.message.chat.id
        if user_id in config.ADMINS:
            return await func(client, message)
    return wrapper

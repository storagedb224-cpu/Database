import asyncio

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import database

app = Client(
    "StorageBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# एडमिन फिल्टर
def is_admin(func):
    async def wrapper(client, message):
        if message.from_user.id in config.ADMINS:
            return await func(client, message)
    return wrapper

# स्टेट मैनेजमेंट (यह याद रखेगा कि एडमिन अभी क्या कर रहा है)
ADMIN_STATES = {}

@app.on_message(filters.command("start") & filters.private)
@is_admin
async def start_cmd(client, message):
    buttons = [
        [InlineKeyboardButton("📁 नया कोर्स जोड़ें", callback_data="add_course")],
        [InlineKeyboardButton("✏️ कोर्स मैनेज करें", callback_data="manage_courses")],
        [InlineKeyboardButton("📊 डेटाबेस स्टैट्स", callback_data="stats")]
    ]
    await message.reply_text("👋 स्वागत है एडमिन! अपना काम चुनें:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("add_course"))
async def start_add_course(client, callback_query):
    # यहाँ डेटाबेस से कोचिंग की लिस्ट आएगी
    coachings = await database.get_items("root", "coaching")
    
    buttons = []
    for c in coachings:
        buttons.append([InlineKeyboardButton(c['name'], callback_data=f"sel_coaching_{c['_id']}")])
    
    buttons.append([InlineKeyboardButton("➕ नई कोचिंग जोड़ें", callback_data="add_new_coaching")])
    
    await callback_query.message.edit_text(
        "🏫 **कोचिंग का नाम चुनें:**", 
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# नया जोड़ने का फ्लो (जब एडमिन '➕ नया जोड़ें' पर क्लिक करे)
@app.on_callback_query(filters.regex("add_new_coaching"))
async def ask_new_coaching(client, callback_query):
    ADMIN_STATES[callback_query.from_user.id] = {"state": "waiting_for_coaching_name"}
    await callback_query.message.reply_text("✍️ नई कोचिंग का नाम टाइप करके भेजें:")

@app.on_message(filters.text & filters.private)
@is_admin
async def handle_text_input(client, message):
    user_id = message.from_user.id
    if user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id].get("state")
        
        if state == "waiting_for_coaching_name":
            name = message.text
            await database.add_item(name, "root", "coaching")
            del ADMIN_STATES[user_id]
            await message.reply_text(f"✅ '{name}' जुड़ गया! अब दोबारा /start दबाकर कोर्स जोड़ें।")

# --- फाइल्स सेव करने का मुख्य लॉजिक ---
# (जब एडमिन सब कुछ चुन ले और फाइल फॉरवर्ड करे)
@app.on_message(filters.document | filters.video & filters.private)
@is_admin
async def handle_files(client, message):
    # मान लीजिए एडमिन ने 'Topic' चुन लिया है और उसका स्टेट 'uploading_files' है
    user_id = message.from_user.id
    if user_id in ADMIN_STATES and ADMIN_STATES[user_id].get("state") == "uploading_files":
        
        # 1. यूनिवर्सल बैकअप चैनल में भेजें
        backup_msg = await message.copy(config.BACKUP_CHANNEL_ID)
        
        # 2. मेन डंप चैनल में भेजें (मान लीजिए मेन चैनल ID स्टेट में सेव है)
        main_channel_id = ADMIN_STATES[user_id].get("main_channel")
        main_msg = await message.copy(main_channel_id)
        
        # 3. मोंगो डीबी में सेव करें और URL जनरेट करें
        file_type = "video" if message.video else "pdf"
        tree_path = ADMIN_STATES[user_id].get("tree_path") # कोचिंग -> कोर्स का पाथ
        
        custom_url = await database.save_file_data(
            file_type, message.id, main_msg.id, backup_msg.id, tree_path
        )
        
        await message.reply_text(f"✅ फाइल सेव हो गई!\n🔗 लिंक: `{custom_url}`")
# ... आपका बाकी का बॉट कोड ...

if __name__ == "__main__":
    from keep_alive import keep_alive
    keep_alive()  # यह बैकग्राउंड में पोर्ट चालू कर देगा
    
    print("Storage Bot चालू हो गया है...")
    app.run()

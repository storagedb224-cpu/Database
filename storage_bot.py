from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import database

app = Client("StorageBot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)

# State save karne ke liye
ADMIN_STATES = {}

def is_admin(func):
    async def wrapper(client, message):
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.message.chat.id
        if user_id in config.ADMINS:
            return await func(client, message)
    return wrapper

# --- 1. MAIN MENU & /start ---
@app.on_message(filters.command("start") & filters.private)
@is_admin
async def start_cmd(client, message):
    # Agar user kahin fasa hai, toh /start se sab reset ho jayega
    if message.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[message.from_user.id]
        
    buttons = [
        [InlineKeyboardButton("📁 Naya Course Jodein", callback_data="add_course")],
        [InlineKeyboardButton("✏️ Course Manage Karein", callback_data="manage_courses")],
        [InlineKeyboardButton("📊 Database Stats", callback_data="stats")]
    ]
    await message.reply_text("👋 Swagat hai Admin!\n\nMain Menu:", reply_markup=InlineKeyboardMarkup(buttons))

# Jab Back button se Main Menu par aana ho
@app.on_callback_query(filters.regex("^main_menu$"))
async def main_menu_cb(client, callback_query):
    buttons = [
        [InlineKeyboardButton("📁 Naya Course Jodein", callback_data="add_course")],
        [InlineKeyboardButton("✏️ Course Manage Karein", callback_data="manage_courses")]
    ]
    await callback_query.message.edit_text("👋 Swagat hai Admin!\n\nMain Menu:", reply_markup=InlineKeyboardMarkup(buttons))

# --- 2. COACHING MENU ---
@app.on_callback_query(filters.regex("^add_course$"))
async def show_coachings(client, callback_query):
    coachings = await database.get_items("root", "coaching")
    buttons = []
    
    # Database se aayi hui coachings ke buttons
    for c in coachings:
        buttons.append([InlineKeyboardButton(c['name'], callback_data=f"c_{c['_id']}")])
        
    buttons.append([InlineKeyboardButton("➕ Nayi Coaching Jodein", callback_data="new_coaching_root")])
    buttons.append([InlineKeyboardButton("🔙 Back (Main Menu)", callback_data="main_menu")])
    
    await callback_query.message.edit_text("🏫 **Coaching ka naam chunein:**", reply_markup=InlineKeyboardMarkup(buttons))

# --- 3. COURSE MENU (Coaching par click karne ke baad) ---
@app.on_callback_query(filters.regex("^c_(.*)"))
async def show_courses(client, callback_query):
    coaching_id = callback_query.matches[0].group(1)
    courses = await database.get_items(coaching_id, "course")
    
    buttons = []
    for crs in courses:
        buttons.append([InlineKeyboardButton(crs['name'], callback_data=f"crs_{crs['_id']}")])
        
    buttons.append([InlineKeyboardButton("➕ Naya Course Jodein", callback_data=f"new_course_{coaching_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back (Coaching Menu)", callback_data="add_course")])
    
    await callback_query.message.edit_text("📚 **Course ka naam chunein:**", reply_markup=InlineKeyboardMarkup(buttons))

# --- NEW ITEM ADD KARNE KA LOGIC ---
@app.on_callback_query(filters.regex("^new_(.*)_(.*)"))
async def ask_new_item(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    
    # State me save kar rahe hain ki bot kiska wait kar raha hai
    ADMIN_STATES[callback_query.from_user.id] = {
        "state": f"waiting_{item_type}",
        "parent_id": parent_id
    }
    
    text = f"✍️ Nayi {item_type} ka naam type karke bhejein:"
    await callback_query.message.reply_text(text)

# --- TEXT INPUT HANDLER ---
@app.on_message(filters.text & filters.private)
@is_admin
async def handle_text(client, message):
    user_id = message.from_user.id
    if user_id in ADMIN_STATES:
        state_data = ADMIN_STATES[user_id]
        state = state_data["state"]
        parent_id = state_data["parent_id"]
        name = message.text
        
        if state == "waiting_coaching":
            await database.add_item(name, parent_id, "coaching")
            del ADMIN_STATES[user_id]
            btn = [[InlineKeyboardButton("🔙 Wapas Coaching Menu Me Jayein", callback_data="add_course")]]
            await message.reply_text(f"✅ '{name}' coaching jud gayi!", reply_markup=InlineKeyboardMarkup(btn))
            
        elif state == "waiting_course":
            await database.add_item(name, parent_id, "course")
            del ADMIN_STATES[user_id]
            btn = [[InlineKeyboardButton("🔙 Wapas Course Menu Me Jayein", callback_data=f"c_{parent_id}")]]
            await message.reply_text(f"✅ '{name}' course jud gaya!", reply_markup=InlineKeyboardMarkup(btn))

if __name__ == "__main__":
    from keep_alive import keep_alive
    keep_alive()
    print("Storage Bot chalu ho gaya hai...")
    app.run()

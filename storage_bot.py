import asyncio
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import database

app = Client("StorageBot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)

# State Management
ADMIN_STATES = {}

def is_admin(func):
    async def wrapper(client, message):
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.message.chat.id
        if user_id in config.ADMINS:
            return await func(client, message)
    return wrapper

# ==========================================
# 1. COMMANDS: /start, /stats, /manage
# ==========================================

@app.on_message(filters.command("start") & filters.private)
@is_admin
async def start_cmd(client, message):
    if message.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[message.from_user.id]
        
    buttons = [
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_coaching_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ]
    await message.reply_text("👑 **Admin Dashboard**\n\nSwagat hai! Yahan se aap apna pura database manage kar sakte hain:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^stats$"))
async def show_stats(client, callback_query):
    coaching, course, videos, pdfs = await database.get_stats()
    total_media = videos + pdfs
    
    text = f"""
📊 **DATABASE STATISTICS** 📊
━━━━━━━━━━━━━━━━━━━━
🏫 **Total Coachings:** `{coaching}`
📚 **Total Courses:** `{course}`
📁 **Total Channels Linked:** `{course}`

🎥 **Total Videos:** `{videos}`
📕 **Total PDFs:** `{pdfs}`
📦 **Total Media Files:** `{total_media}`
━━━━━━━━━━━━━━━━━━━━
    """
    btn = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start_menu")]]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex("^start_menu$"))
async def start_menu_cb(client, callback_query):
    buttons = [
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_coaching_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ]
    await callback_query.message.edit_text("👑 **Admin Dashboard**\n\nChunein aapko kya karna hai:", reply_markup=InlineKeyboardMarkup(buttons))


# ==========================================
# 2. DYNAMIC NAVIGATION & ADDING FLOW
# ==========================================

# Hierarchy Setup
HIERARCHY = {
    "coaching": {"next": "course", "title": "Coaching"},
    "course": {"next": "subject", "title": "Course"},
    "subject": {"next": "teacher", "title": "Subject"},
    "teacher": {"next": "topic", "title": "Teacher"},
    "topic": {"next": "upload", "title": "Topic"}
}

@app.on_callback_query(filters.regex(r"^nav_(.*)_(.*)$"))
async def navigation_handler(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    
    if item_type == "upload":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "uploading_files", "topic_id": parent_id}
        btn = [[InlineKeyboardButton("✅ Done (Main Menu)", callback_data="start_menu")]]
        await callback_query.message.edit_text("📤 **Files Bhejna Shuru Karein!**\n\nAb aap is topic ki Videos aur PDFs yahan forward kar sakte hain. Sab aane ke baad 'Done' dabayein.", reply_markup=InlineKeyboardMarkup(btn))
        return

    items = await database.get_items(parent_id, item_type)
    
    buttons = []
    for item in items:
        next_type = HIERARCHY[item_type]["next"]
        buttons.append([InlineKeyboardButton(f"📂 {item['name']}", callback_data=f"nav_{next_type}_{item['_id']}")])
        
    buttons.append([InlineKeyboardButton(f"➕ Add New {HIERARCHY[item_type]['title']}", callback_data=f"add_{item_type}_{parent_id}")])
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start_menu")])
    
    await callback_query.message.edit_text(f"📌 **Select {HIERARCHY[item_type]['title']}:**", reply_markup=InlineKeyboardMarkup(buttons))

# ==========================================
# 3. TEXT/PHOTO INPUT HANDLER (STATE MACHINE)
# ==========================================

@app.on_callback_query(filters.regex(r"^add_(.*)_(.*)$"))
async def ask_new_item(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    
    ADMIN_STATES[callback_query.from_user.id] = {
        "state": f"wait_name_{item_type}",
        "parent_id": parent_id
    }
    await callback_query.message.reply_text(f"✍️ Naye **{HIERARCHY[item_type]['title']}** ka naam type karke bhejein:")

@app.on_message((filters.text | filters.photo | filters.document | filters.video) & filters.private)
@is_admin
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_STATES:
        return
        
    state_data = ADMIN_STATES[user_id]
    state = state_data.get("state")
    
    # 1. Normal Text Input (Name)
    if state.startswith("wait_name_") and message.text:
        item_type = state.replace("wait_name_", "")
        parent_id = state_data["parent_id"]
        name = message.text
        
        # Agar COURSE add kar rahe hain, to pehle Channel mangenge
        if item_type == "course":
            ADMIN_STATES[user_id] = {
                "state": "wait_channel_course",
                "parent_id": parent_id,
                "course_name": name
            }
            await message.reply_text(f"✅ Course Name '{name}' saved.\n\n📢 Ab is course ke liye banaye gaye **Telegram Dump Channel ki ID** (jaise -1001234...) bhejein ya wahan se koi message forward karein:")
            return
            
        # Baki sabke liye direct DB me save
        new_id = await database.add_item(name, parent_id, item_type)
        del ADMIN_STATES[user_id]
        
        btn = [[InlineKeyboardButton(f"Proceed to {HIERARCHY[item_type]['title']}", callback_data=f"nav_{item_type}_{parent_id}")]]
        await message.reply_text(f"✅ '{name}' Successfully Added!", reply_markup=InlineKeyboardMarkup(btn))
        return

    # 2. Course Channel Input
    if state == "wait_channel_course":
        channel_id = message.text if message.text else message.forward_from_chat.id
        ADMIN_STATES[user_id]["channel_id"] = channel_id
        ADMIN_STATES[user_id]["state"] = "wait_thumb_course"
        await message.reply_text("🖼 Ab is Course ka **Thumbnail (Photo)** bhejein:")
        return

    # 3. Course Thumbnail Input
    if state == "wait_thumb_course" and message.photo:
        thumb_id = message.photo.file_id
        course_name = state_data["course_name"]
        parent_id = state_data["parent_id"]
        channel_id = state_data["channel_id"]
        
        # Pura Course data DB me save karna
        await database.add_item(course_name, parent_id, "course", {"channel_id": channel_id, "thumb_id": thumb_id})
        del ADMIN_STATES[user_id]
        
        btn = [[InlineKeyboardButton("Proceed to Course Menu", callback_data=f"nav_course_{parent_id}")]]
        await message.reply_text(f"✅ Course '{course_name}' with Channel & Thumbnail saved successfully!", reply_markup=InlineKeyboardMarkup(btn))
        return

    # 4. Uploading Files to Topic
    if state == "uploading_files" and (message.video or message.document):
        topic_id = state_data["topic_id"]
        file_type = "video" if message.video else "pdf"
        
        # Yahan message ko channel me forward karne ka logic laga sakte hain (main_msg_id)
        # Abhi ke liye seedha DB me record save kar rahe hain
        await database.save_file(topic_id, file_type, message.id)
        await message.reply_text("✅ File Saved to Database!", quote=True)


# ==========================================
# 4. MANAGE COMMAND (Edit / Delete)
# ==========================================

@app.on_callback_query(filters.regex("^manage_root$"))
async def manage_root(client, callback_query):
    coachings = await database.get_items("root", "coaching")
    buttons = []
    for c in coachings:
        buttons.append([InlineKeyboardButton(f"⚙️ {c['name']}", callback_data=f"man_item_{c['_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start_menu")])
    
    await callback_query.message.edit_text("⚙️ **Manage Data**\nKis Coaching ko manage karna hai?", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^man_item_(.*)$"))
async def manage_item_options(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    
    text = f"⚙️ **Managing:** {item['name']}\nType: {item['type'].upper()}"
    buttons = [
        [InlineKeyboardButton("🗑 Delete (Forever)", callback_data=f"delete_item_{item_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="manage_root")]
    ]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^delete_item_(.*)$"))
async def delete_item_cb(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    await database.delete_item(item_id)
    await callback_query.answer("✅ Item Deleted Successfully!", show_alert=True)
    await manage_root(client, callback_query)


if __name__ == "__main__":
    from keep_alive import keep_alive
    keep_alive()  # Isse Render kabhi nahi soyega!
    print("🚀 Premium Storage Bot Started Successfully...")
    app.run()

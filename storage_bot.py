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

ADMIN_STATES = {}

def is_admin(func):
    async def wrapper(client, message):
        user_id = message.from_user.id if hasattr(message, 'from_user') else message.message.chat.id
        if user_id in config.ADMINS:
            return await func(client, message)
    return wrapper

# --- 1. COMMANDS: /start, /stats ---
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
    await message.reply_text("👑 **Admin Dashboard**\nSwagat hai! Apna option chunein:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^start_menu$"))
async def start_menu_cb(client, callback_query):
    if callback_query.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[callback_query.from_user.id]
    buttons = [
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_coaching_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ]
    await callback_query.message.edit_text("👑 **Admin Dashboard**\nChunein aapko kya karna hai:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^stats$"))
async def show_stats(client, callback_query):
    coaching, course, videos, pdfs = await database.get_stats()
    text = f"📊 **DATABASE STATISTICS** 📊\n━━━━━━━━━━━━━━━━━━━━\n🏫 Total Coachings: `{coaching}`\n📚 Total Courses: `{course}`\n🎥 Total Videos: `{videos}`\n📕 Total PDFs: `{pdfs}`\n📦 Total Media: `{videos + pdfs}`\n━━━━━━━━━━━━━━━━━━━━"
    btn = [[InlineKeyboardButton("🔙 Back", callback_data="start_menu")]]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btn))

HIERARCHY = {
    "coaching": {"next": "course", "title": "Coaching"},
    "course": {"next": "subject", "title": "Course"},
    "subject": {"next": "teacher", "title": "Subject"},
    "teacher": {"next": "topic", "title": "Teacher"},
    "topic": {"next": "upload", "title": "Topic"},
    "upload": {"next": None, "title": "Files"}
}

# --- 2. ADD DATA NAVIGATION ---
@app.on_callback_query(filters.regex(r"^nav_(.*)_(.*)$"))
async def navigation_handler(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    
    if item_type == "upload":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "uploading_files", "topic_id": parent_id}
        btn = [[InlineKeyboardButton("✅ Done (Main Menu)", callback_data="start_menu")]]
        await callback_query.message.edit_text("📤 **Files Bhejna Shuru Karein!**\nAb aap is topic ki Videos/PDFs bhej sakte hain.", reply_markup=InlineKeyboardMarkup(btn))
        return

    items = await database.get_items(parent_id, item_type)
    buttons = []
    for item in items:
        next_type = HIERARCHY[item_type]["next"]
        buttons.append([InlineKeyboardButton(f"📂 {item['name']}", callback_data=f"nav_{next_type}_{item['_id']}")])
        
    buttons.append([InlineKeyboardButton(f"➕ Add New {HIERARCHY[item_type]['title']}", callback_data=f"add_{item_type}_{parent_id}")])
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start_menu")])
    await callback_query.message.edit_text(f"📌 **Select {HIERARCHY[item_type]['title']}:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^add_(.*)_(.*)$"))
async def ask_new_item(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    ADMIN_STATES[callback_query.from_user.id] = {"state": f"wait_name_{item_type}", "parent_id": parent_id}
    await callback_query.message.reply_text(f"✍️ Naye **{HIERARCHY[item_type]['title']}** ka naam type karke bhejein:")

# --- 3. INPUT HANDLER (Add & Edit Data) ---
@app.on_message((filters.text | filters.photo | filters.document | filters.video) & filters.private)
@is_admin
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_STATES:
        return
    state_data = ADMIN_STATES[user_id]
    state = state_data.get("state")
    
    # 🆕 Edit Name Logic
    if state == "wait_edit_name" and message.text:
        item_id = state_data["item_id"]
        new_name = message.text
        await database.update_item_name(item_id, new_name)
        del ADMIN_STATES[user_id]
        btn = [[InlineKeyboardButton("🔙 Back to Action Menu", callback_data=f"man_act_{item_id}")]]
        await message.reply_text(f"✅ Naam badalkar **{new_name}** ho gaya hai!", reply_markup=InlineKeyboardMarkup(btn))
        return

    # Add Name Logic
    if state.startswith("wait_name_") and message.text:
        item_type = state.replace("wait_name_", "")
        parent_id = state_data["parent_id"]
        name = message.text
        
        if item_type == "course":
            ADMIN_STATES[user_id] = {"state": "wait_channel_course", "parent_id": parent_id, "course_name": name}
            await message.reply_text(f"✅ '{name}' saved.\n📢 Ab iske **Dump Channel ki ID** bhejein:")
            return
            
        await database.add_item(name, parent_id, item_type)
        del ADMIN_STATES[user_id]
        btn = [[InlineKeyboardButton(f"Proceed to {HIERARCHY[item_type]['title']}", callback_data=f"nav_{item_type}_{parent_id}")]]
        await message.reply_text(f"✅ '{name}' Added!", reply_markup=InlineKeyboardMarkup(btn))
        return

    # Dump Channel ID & Thumbnail Logic
    if state == "wait_channel_course":
        ADMIN_STATES[user_id]["channel_id"] = message.text if message.text else str(message.forward_from_chat.id)
        ADMIN_STATES[user_id]["state"] = "wait_thumb_course"
        await message.reply_text("🖼 Ab Course ka **Thumbnail (Photo)** bhejein:")
        return

    if state == "wait_thumb_course" and message.photo:
        await database.add_item(state_data["course_name"], state_data["parent_id"], "course", {"channel_id": state_data["channel_id"], "thumb_id": message.photo.file_id})
        del ADMIN_STATES[user_id]
        btn = [[InlineKeyboardButton("Proceed to Course", callback_data=f"nav_course_{state_data['parent_id']}")]]
        await message.reply_text(f"✅ Course completely saved!", reply_markup=InlineKeyboardMarkup(btn))
        return

    # File Uploading Logic
    if state == "uploading_files" and (message.video or message.document):
        topic_id = state_data["topic_id"]
        file_type = "video" if message.video else "pdf"
        
        if "channel_id" not in state_data:
            channel_id = await database.get_course_channel_id(topic_id)
            if not channel_id:
                return await message.reply_text("❌ Course Dump Channel nahi mila.")
            ADMIN_STATES[user_id]["channel_id"] = int(channel_id)
            
        try:
            backup_msg = await message.copy(config.BACKUP_CHANNEL_ID)
            main_msg = await message.copy(ADMIN_STATES[user_id]["channel_id"])
            url = await database.save_file(topic_id, file_type, main_msg.id, backup_msg.id)
            await message.reply_text(f"✅ **Saved!** 🔗 `{url}`", quote=True)
        except Exception as e:
            await message.reply_text(f"❌ Upload Error: {e}")

# --- 4. 🆕 UPGRADED MANAGE COMMAND (Edit, Navigate, Delete) ---
@app.on_callback_query(filters.regex("^manage_root$"))
async def manage_root(client, callback_query):
    coachings = await database.get_items("root", "coaching")
    buttons = [[InlineKeyboardButton(f"🏫 {c['name']}", callback_data=f"man_act_{c['_id']}")] for c in coachings]
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start_menu")])
    await callback_query.message.edit_text("⚙️ **Manage Data (Root)**\nKis Coaching ko manage/edit karna hai?", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^man_nav_(.*)_(.*)$"))
async def manage_nav(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    
    items = await database.get_items(parent_id, item_type)
    buttons = [[InlineKeyboardButton(f"📂 {item['name']}", callback_data=f"man_act_{item['_id']}")] for item in items]
    
    parent_item = await database.get_item_by_id(parent_id)
    back_btn = f"man_act_{parent_id}" if parent_item and parent_item.get("parent_id") != "root" else "manage_root"
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=back_btn)])
    
    await callback_query.message.edit_text(f"⚙️ **Select {HIERARCHY[item_type]['title']} to Manage:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^man_act_(.*)$"))
async def manage_action(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    if not item:
        return await callback_query.answer("Item not found!", show_alert=True)
        
    item_type = item['type']
    next_type = HIERARCHY[item_type]["next"]
    
    buttons = [[InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_name_{item_id}")]]
    
    if next_type and next_type != "upload":
        buttons.append([InlineKeyboardButton(f"📂 Manage Inside ({HIERARCHY[next_type]['title']}s)", callback_data=f"man_nav_{next_type}_{item_id}")])
        
    buttons.append([InlineKeyboardButton("🗑 Delete", callback_data=f"delete_item_{item_id}")])
    
    back_cb = "manage_root" if item.get("parent_id") == "root" else f"man_nav_{item_type}_{item['parent_id']}"
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=back_cb)])
    
    await callback_query.message.edit_text(f"⚙️ **Action Menu:** `{item['name']}`\nKya karna chahte hain?", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^edit_name_(.*)$"))
async def ask_edit_name(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    ADMIN_STATES[callback_query.from_user.id] = {"state": "wait_edit_name", "item_id": item_id}
    await callback_query.message.reply_text(f"✍️ **{item['name']}** ka naya naam type karke bhejein:")

@app.on_callback_query(filters.regex(r"^delete_item_(.*)$"))
async def delete_item_cb(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    back_cb = "manage_root" if item.get("parent_id") == "root" else f"man_nav_{item['type']}_{item['parent_id']}"
    
    await database.delete_item(item_id)
    await callback_query.answer("✅ Item Deleted!", show_alert=True)
    
    # Refreshing page back to parent
    callback_query.matches = [type('obj', (object,), {'group': lambda self, x: back_cb.split('_')[-2] if x==1 else back_cb.split('_')[-1]})()]
    if back_cb == "manage_root":
        await manage_root(client, callback_query)
    else:
        await manage_nav(client, callback_query)

if __name__ == "__main__":
    from keep_alive import keep_alive
    keep_alive()
    print("🚀 Premium Storage Bot Started...")
    app.run()

import string
import random
import asyncio
import time
import datetime
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait, MessageNotModified

import config
import database as db
from keep_alive import keep_alive

app = Client(
    "StorageBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

ADMIN_STATES = {}
FAILED_UPLOADS = {}
BOT_START_TIME = time.time()

LEVELS = {
    "root": "coaching",
    "coaching": "course",
    "course": "subject",
    "subject": "teacher",
    "teacher": "topic",
    "topic": "file" 
}

def generate_hash():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_uptime():
    seconds = int(time.time() - BOT_START_TIME)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

async def is_admin(_, __, message: Message):
    return message.from_user and message.from_user.id in config.ADMINS
admin_filter = filters.create(is_admin)

# ==========================================
# 0. BACKUP COMMAND (/backup) 📦
# ==========================================
@app.on_message(filters.command("backup") & admin_filter)
async def backup_db(client, message):
    status = await message.reply_text("🔄 **Database Backup generating...**")
    try:
        json_data = await db.export_db_json()
        filename = f"StorageBot_Backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json_data)
            
        await message.reply_document(
            document=filename,
            caption="📦 **MongoDB Complete Backup**\n\nYeh aapke pure Storage Bot ka data hai. Ise hamesha safe rakhein!"
        )
        os.remove(filename)
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Backup Failed: {e}")

# ==========================================
# 1. MAIN DASHBOARD (/start)
# ==========================================
@app.on_message(filters.command("start") & admin_filter)
async def start_cmd(client, message):
    if message.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[message.from_user.id]

    welcome_text = f"""╔══════════════════════════╗
🚀 WELCOME TO STORAGE BOT
╚══════════════════════════╝

👋 नमस्कार {message.from_user.first_name}!
आपका स्वागत है हमारे Advanced Storage System में।

✨ OUR FEATURES
📁 Unlimited File Management
🎬 Video & Audio Storage
📚 PDF & Document Storage
🔍 Instant File Search
🔐 Secure Cloud Storage

💡 /backup - Download Database Data
━━━━━━━━━━━━━━━━━━━━"""

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_add_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="nav_manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ])
    await message.reply_text(welcome_text, reply_markup=markup)

# ==========================================
# 2. LIVE STATS 
# ==========================================
@app.on_callback_query(filters.regex("^stats$") & admin_filter)
async def show_stats(client, callback_query):
    await callback_query.answer() 
    start_time = time.time()
    stats = await db.get_stats() # LIVE FETCH FROM DB
    response_time = int((time.time() - start_time) * 1000)
    
    current_date = datetime.datetime.now().strftime("%d %B %Y")
    last_updated = datetime.datetime.now().strftime("%I:%M:%S %p")
    
    stats_text = f"""╭━━━━━━━━━━━━━━━━━━━━━━━╮
💎 STORAGE BOT
📊 LIVE BOT STATISTICS
╰━━━━━━━━━━━━━━━━━━━━━━━╯

┏━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🟢 STATUS : "ONLINE"
┃  ⚡ SYSTEM : "OPERATIONAL"
┃  🗄️ DATABASE : "CONNECTED"
┗━━━━━━━━━━━━━━━━━━━━━━━┛

📦 STORAGE STATISTICS
➤ 🌐 Total Channels   : "{stats['total_channels']}"
➤ 📚 Total Courses    : "{stats['total_courses']}"
➤ 🎬 Total Videos     : "{stats['total_videos']}"
➤ 📄 Total PDFs       : "{stats['total_pdfs']}"

━━━━━━━━━━━━━━━━━━━━━━━
🆕 TODAY'S UPLOAD REPORT
➤ 📥 New Files Today  : "{stats['today_new_files']}"
➤ 📅 Date             : "{current_date}"

━━━━━━━━━━━━━━━━━━━━━━━
⚙️ SERVER INFORMATION
➤ ⏱️ Uptime           : "{get_uptime()}"
➤ 🚀 Response Time    : "{response_time} ms"
➤ 🔄 Last Pinned At   : "{last_updated}"
━━━━━━━━━━━━━━━━━━━━━━━"""

    try:
        await callback_query.message.edit_text(stats_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="nav_manage_root")]]))
    except MessageNotModified:
        pass

# ==========================================
# 3. HIERARCHY NAVIGATION (Strict Separations)
# ==========================================
async def render_nav_menu(client, message_obj, mode, node_id):
    current_node = await db.get_node(node_id)
    node_type = current_node['type']
    
    if node_type == "topic":
        if mode == "add":
            ADMIN_STATES[message_obj.chat.id] = {"state": "UPLOAD_MODE", "topic_id": str(current_node['_id']), "bot_msg_id": message_obj.id}
            text = f"📂 **Topic:** {current_node['name']}\n\n📤 **UPLOAD MODE ACTIVATED!**\nSend Videos/PDFs here. They will be dual-backed up automatically."
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"nav_add_{current_node['parent']}")]])
            await message_obj.edit_text(text, reply_markup=markup)
        else:
            files = await db.get_files(str(current_node['_id']))
            text = f"📂 **Topic Files:** {current_node['name']}\nSelect a file below to manage/delete."
            buttons = []
            for f in files:
                fname = f.get('file_name', 'Unknown')
                if len(fname) > 25: fname = fname[:22] + "..."
                buttons.append([InlineKeyboardButton(f"📄 [{f.get('index_id', '00')}] {fname}", callback_data=f"fileopt_{f['_id']}_{current_node['_id']}")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"nav_manage_{current_node['parent']}")])
            await message_obj.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    child_type = LEVELS[node_type]
    children = await db.get_nodes(node_id)
    
    action_word = "Add Data into" if mode == "add" else "Manage Data inside"
    text = f"📂 **{action_word}:** {current_node['name'].upper()}\n⬇️ Select an option."
    
    buttons = []
    
    if mode == "add":
        # PURE ADD MODE - NO EDIT/DELETE OPTIONS HERE
        for child in children:
            buttons.append([InlineKeyboardButton(f"📁 {child['name']} ➔", callback_data=f"nav_add_{child['_id']}")])
        buttons.append([InlineKeyboardButton(f"➕ Add New {child_type.capitalize()}", callback_data=f"add_{node_id}")])
    else:
        # PURE MANAGE MODE - NAVIGATE INSIDE, EDIT, DELETE
        for child in children:
            buttons.append([InlineKeyboardButton(f"📁 {child['name']} ➔", callback_data=f"nav_manage_{child['_id']}")])
            
        if node_id != "root":
            buttons.append([InlineKeyboardButton(f"✏️ Edit '{current_node['name']}'", callback_data=f"edit_{node_id}")])
            buttons.append([InlineKeyboardButton(f"🗑 Delete Entire Category", callback_data=f"del_{node_id}")])
            
    if node_id != "root":
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"nav_{mode}_{current_node['parent']}")])
    else:
        buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data=f"main_menu")])
        
    await message_obj.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^main_menu$") & admin_filter)
async def main_menu_handler(client, callback_query):
    await callback_query.answer()
    await start_cmd(client, callback_query.message)

@app.on_callback_query(filters.regex("^nav_(add|manage)_(.*)") & admin_filter)
async def navigate_tree(client, callback_query):
    await callback_query.answer()
    mode = callback_query.matches[0].group(1)
    node_id = callback_query.matches[0].group(2)
    await render_nav_menu(client, callback_query.message, mode, node_id)

# ==========================================
# 4. FILE MANAGER OPTIONS
# ==========================================
@app.on_callback_query(filters.regex("^fileopt_(.*)_(.*)") & admin_filter)
async def file_options(client, callback_query):
    await callback_query.answer()
    file_id = callback_query.matches[0].group(1)
    topic_id = callback_query.matches[0].group(2)
    f = await db.get_file(file_id)
    
    if not f: 
        return await callback_query.answer("File not found in DB!", show_alert=True)
    
    text = f"⚙️ **Manage File:**\n\n📄 **Name:** {f.get('file_name', 'Unknown')}\n🔖 **Index:** {f.get('index_id', '00')}\n🔗 **URL:** {f.get('custom_url')}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete File Record", callback_data=f"delfile_{file_id}_{topic_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"nav_manage_{topic_id}")]
    ])
    await callback_query.message.edit_text(text, reply_markup=markup)

@app.on_callback_query(filters.regex("^delfile_(.*)_(.*)") & admin_filter)
async def delete_file_handler(client, callback_query):
    file_id = callback_query.matches[0].group(1)
    topic_id = callback_query.matches[0].group(2)
    await db.delete_file(file_id)
    await callback_query.answer("File Deleted from DataBase!", show_alert=True)
    await render_nav_menu(client, callback_query.message, "manage", topic_id)

# ==========================================
# 5. ADDING DATA (Triggering States)
# ==========================================
@app.on_callback_query(filters.regex("^add_(.*)") & admin_filter)
async def add_trigger(client, callback_query):
    await callback_query.answer()
    parent_id = callback_query.matches[0].group(1)
    parent_node = await db.get_node(parent_id)
    child_type = LEVELS[parent_node['type']]
    
    ADMIN_STATES[callback_query.from_user.id] = {
        "state": "ADD_COURSE_NAME" if child_type == "course" else f"ADD_{child_type.upper()}",
        "parent_id": parent_id,
        "bot_msg_id": callback_query.message.id,
        "data": {}
    }
    
    text = "📝 Enter Course Name:" if child_type == "course" else f"📝 Enter Name for new {child_type.capitalize()}:"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"nav_add_{parent_id}")]])
    await callback_query.message.edit_text(text, reply_markup=markup)

# ==========================================
# 6. CORE UPLOAD LOGIC & RETRY SYSTEM
# ==========================================
async def process_file_upload(client, file_message, topic_id, status_msg):
    file_type = "video" if file_message.video else "pdf"
    file_name = file_message.video.file_name if (file_message.video and file_message.video.file_name) else (file_message.document.file_name if file_message.document and file_message.document.file_name else "Unknown_File")

    try:
        topic = await db.get_node(topic_id)
        teacher = await db.get_node(topic['parent'])
        subject = await db.get_node(teacher['parent'])
        course_id = subject['parent']
    except Exception:
        return await status_msg.edit_text("❌ Database Hierarchy Error!")

    index_id = await db.get_next_index(course_id)
    custom_hash = generate_hash() 
    url_path = "watch" if file_type == "video" else "pdf"
    custom_url = f"{config.DOMAIN_NAME}/{url_path}/{custom_hash}"
    
    custom_caption = f"""🎓 {file_name}
🔖 Index ID : "{index_id}"
📚 Subject : "{subject['name']}"
🎯 Topic : "{topic['name']}"
👨‍🏫 Teacher : "{teacher['name']}"
📂 File Type : "{file_type.upper()}"
━━━━━━━━━━━━━━━━━━
💎 ENJOYS GUYS ⚡"""

    try:
        backup_msg = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                backup_msg = await file_message.copy(config.BACKUP_CHANNEL_ID, caption=custom_caption)
                break
            except FloodWait as e:
                await status_msg.edit_text(f"⏳ Rate Limit. Waiting {e.value}s...")
                await asyncio.sleep(e.value + 1)
        
        dump_channel_id = await db.get_course_dump_channel(topic_id)
        main_msg_id = None
        
        if dump_channel_id:
            clean_dump_id = int(dump_channel_id)
            for attempt in range(max_retries):
                try:
                    dump_msg = await file_message.copy(clean_dump_id, caption=custom_caption)
                    main_msg_id = dump_msg.id
                    break
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    fail_id = generate_hash()
                    FAILED_UPLOADS[fail_id] = {"chat_id": file_message.chat.id, "message_id": file_message.id, "topic_id": topic_id}
                    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry Upload", callback_data=f"retry_{fail_id}")]])
                    return await status_msg.edit_text(f"⚠️ Dump Copy Failed!\nError: {e}", reply_markup=btn)
        
        if backup_msg:
            await db.add_file(topic_id, file_type, custom_hash, custom_url, main_msg_id, backup_msg.id, index_id, file_name)
            await status_msg.edit_text(f"✅ **Uploaded! (Index: {index_id})**\n\n🔗 **Link:** `{custom_url}`")
        else:
            await status_msg.edit_text("❌ Upload failed.")
            
    except Exception as e:
        fail_id = generate_hash()
        FAILED_UPLOADS[fail_id] = {"chat_id": file_message.chat.id, "message_id": file_message.id, "topic_id": topic_id}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry Upload", callback_data=f"retry_{fail_id}")]])
        await status_msg.edit_text(f"❌ Critical Error: {e}", reply_markup=btn)

@app.on_callback_query(filters.regex("^retry_(.*)") & admin_filter)
async def retry_upload_handler(client, callback_query):
    await callback_query.answer()
    fail_id = callback_query.matches[0].group(1)
    if fail_id not in FAILED_UPLOADS:
        return await callback_query.answer("Retry session expired!", show_alert=True)
    
    data = FAILED_UPLOADS[fail_id]
    await callback_query.message.edit_text("🔄 Retrying Upload...")
    try:
        original_msg = await client.get_messages(data["chat_id"], data["message_id"])
        await process_file_upload(client, original_msg, data["topic_id"], callback_query.message)
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Retry failed: {e}")

# ==========================================
# 7. HANDLING ADMIN INPUTS & MESSAGES
# ==========================================
@app.on_message(filters.private & admin_filter & ~filters.command(["start", "backup"]))
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_STATES: return 
    
    state_data = ADMIN_STATES[user_id]
    current_state = state_data.get("state")
    
    if current_state != "UPLOAD_MODE":
        await message.delete() 
        try:
            bot_msg = await client.get_messages(message.chat.id, state_data['bot_msg_id'])
        except Exception:
            bot_msg = await message.reply_text("🔄 Processing...")
            state_data['bot_msg_id'] = bot_msg.id
    
    if current_state == "ADD_COURSE_NAME":
        if not message.text: return await bot_msg.edit_text("❌ Send text only!")
        state_data['data']['name'] = message.text
        state_data['state'] = "ADD_COURSE_DUMP"
        await bot_msg.edit_text("📥 Excellent! Now send the **Dump Channel ID** (e.g. -100123456789).")
        
    elif current_state == "ADD_COURSE_DUMP":
        if not message.text: return await bot_msg.edit_text("❌ Send text only!")
        state_data['data']['dump_channel'] = int(message.text)
        state_data['state'] = "ADD_COURSE_THUMB"
        await bot_msg.edit_text("🖼 Now send the **Thumbnail Image** (Photo).")
        
    elif current_state == "ADD_COURSE_THUMB":
        if not message.photo: return await bot_msg.edit_text("❌ Send a photo only!")
        c_data = state_data['data']
        parent_id = state_data['parent_id']
        await db.add_node(c_data['name'], "course", parent_id, extra={"dump_channel": c_data['dump_channel'], "thumb": message.photo.file_id})
        
        await bot_msg.edit_text("✅ Course created successfully!")
        await asyncio.sleep(1)
        await render_nav_menu(client, bot_msg, "add", parent_id)

    elif current_state.startswith("ADD_"):
        if not message.text: return await bot_msg.edit_text("❌ Send text only!")
        node_type = current_state.split("_")[1].lower()
        parent_id = state_data['parent_id']
        await db.add_node(message.text, node_type, parent_id)
        
        await bot_msg.edit_text(f"✅ {node_type.capitalize()} created!")
        await asyncio.sleep(1)
        await render_nav_menu(client, bot_msg, "add", parent_id)
        
    elif current_state == "EDIT_NAME":
        if not message.text: return await bot_msg.edit_text("❌ Send text only!")
        node_id = state_data['node_id']
        parent_id = state_data['parent_id']
        await db.update_node_name(node_id, message.text)
        
        await bot_msg.edit_text("✅ Name updated successfully!")
        await asyncio.sleep(1)
        await render_nav_menu(client, bot_msg, "manage", parent_id)

    elif current_state == "UPLOAD_MODE":
        if not (message.video or message.document):
            return await message.reply_text("❌ Send a valid Video or PDF document!")
        status_msg = await message.reply_text("🔄 Processing and Uploading...")
        await process_file_upload(client, message, state_data['topic_id'], status_msg)

# ==========================================
# 8. EDIT / DELETE CALLBACKS
# ==========================================
@app.on_callback_query(filters.regex("^(edit|del)_(.*)") & admin_filter)
async def edit_delete_handler(client, callback_query):
    action = callback_query.matches[0].group(1)
    node_id = callback_query.matches[0].group(2)
    node = await db.get_node(node_id)
    
    if action == "edit":
        await callback_query.answer()
        ADMIN_STATES[callback_query.from_user.id] = {"state": "EDIT_NAME", "node_id": node_id, "parent_id": node['parent'], "bot_msg_id": callback_query.message.id}
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"nav_manage_{node['parent']}")]] )
        await callback_query.message.edit_text("📝 Send the new name:", reply_markup=markup)
        
    elif action == "del":
        parent_id = node['parent']
        await callback_query.answer("🧹 Pura data root saaf ho raha hai...", show_alert=False)
        # BHAi YAHAN PAR JADOO CHALEGA (Bulk Deletion Engine)
        await db.delete_node(node_id) 
        await render_nav_menu(client, callback_query.message, "manage", parent_id)

if __name__ == "__main__":
    print("Starting Web Server...")
    keep_alive()
    print("Starting Telegram Bot...")
    app.run()

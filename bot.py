import string
import random
import asyncio
import time
import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait

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
यहाँ आप अपनी जरूरी Files, Videos, PDFs और Documents को सुरक्षित तरीके से Store और Manage कर सकते हैं।

✨ OUR FEATURES
📁 Unlimited File Management
🎬 Video & Audio Storage
📚 PDF & Document Storage
🔍 Instant File Search
📥 Easy File Access
🔐 Secure Cloud Storage
⚡ Fast & Easy Navigation

━━━━━━━━━━━━━━━━━━━━
💡 Your Files, Your Storage!
❤️ Thank You For Using Our Storage Bot."""

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_add_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="nav_manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ])
    await message.reply_text(welcome_text, reply_markup=markup)

# ==========================================
# 2. STATS 
# ==========================================
@app.on_callback_query(filters.regex("^stats$") & admin_filter)
async def show_stats(client, callback_query):
    start_time = time.time()
    stats = await db.get_stats()
    response_time = int((time.time() - start_time) * 1000)
    
    current_date = datetime.datetime.now().strftime("%d %B %Y")
    last_updated = datetime.datetime.now().strftime("%I:%M %p")
    
    stats_text = f"""╭━━━━━━━━━━━━━━━━━━━━━━━╮
💎 STORAGE BOT
📊 BOT STATISTICS
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
➤ 🔄 Last Updated     : "{last_updated}"

━━━━━━━━━━━━━━━━━━━━━━━

📈 STORAGE ACTIVITY

📡 Channels  ▰▰▰▰▰▰▰▰▰
📚 Courses   ▰▰▰▰▰▰▰▰▰
🎬 Videos    ▰▰▰▰▰▰▰▰▰
📄 Documents ▰▰▰▰▰▰▰▰▰

━━━━━━━━━━━━━━━━━━━━━━━
✨ Every File. Every Course. One Storage.
❤️ POWERED BY STORAGE BOT
🛡️ Secure • Fast • Organized"""

    await callback_query.message.edit_text(stats_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="nav_manage_root")]]))

# ==========================================
# 3. HIERARCHY NAVIGATION (Add vs Manage)
# ==========================================
async def render_nav_menu(client, message_obj, mode, node_id):
    current_node = await db.get_node(node_id)
    node_type = current_node['type']
    
    if node_type == "topic":
        ADMIN_STATES[message_obj.chat.id] = {"state": "UPLOAD_MODE", "topic_id": str(current_node['_id'])}
        text = f"📂 **Topic:** {current_node['name']}\n\n📤 **UPLOAD MODE ACTIVATED!**\nSend Videos/PDFs here. They will be dual-backed up automatically."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"nav_{mode}_{current_node['parent']}")]])
        if isinstance(message_obj, Message):
            await message_obj.reply_text(text, reply_markup=markup)
        else:
            await message_obj.edit_text(text, reply_markup=markup)
        return

    child_type = LEVELS[node_type]
    children = await db.get_nodes(node_id)
    
    action_word = "Add Data into" if mode == "add" else "Manage"
    text = f"📂 **{action_word}:** {current_node['name'].upper()}\n⬇️ Select a {child_type.capitalize()}."
    
    buttons = []
    
    if mode == "add":
        for child in children:
            buttons.append([InlineKeyboardButton(f"📁 {child['name']} ➔", callback_data=f"nav_add_{child['_id']}")])
        buttons.append([InlineKeyboardButton(f"➕ Add New {child_type.capitalize()}", callback_data=f"add_{node_id}")])
    else:
        for child in children:
            buttons.append([InlineKeyboardButton(f"⚙️ {child['name']}", callback_data=f"opt_{child['_id']}")])
            
    if node_id != "root":
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"nav_{mode}_{current_node['parent']}")])
        
    markup = InlineKeyboardMarkup(buttons)
    if isinstance(message_obj, Message):
        await message_obj.reply_text(text, reply_markup=markup)
    else:
        await message_obj.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex("^nav_(add|manage)_(.*)") & admin_filter)
async def navigate_tree(client, callback_query):
    mode = callback_query.matches[0].group(1)
    node_id = callback_query.matches[0].group(2)
    await render_nav_menu(client, callback_query.message, mode, node_id)

@app.on_callback_query(filters.regex("^opt_(.*)") & admin_filter)
async def node_options(client, callback_query):
    node_id = callback_query.matches[0].group(1)
    node = await db.get_node(node_id)
    
    text = f"⚙️ **Manage:** {node['name']} ({node['type'].capitalize()})"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Open Inside", callback_data=f"nav_manage_{node_id}")],
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_{node_id}"), InlineKeyboardButton("🗑 Delete", callback_data=f"del_{node_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"nav_manage_{node['parent']}")]
    ])
    await callback_query.message.edit_text(text, reply_markup=markup)

# ==========================================
# 4. ADDING DATA (Triggering States)
# ==========================================
@app.on_callback_query(filters.regex("^add_(.*)") & admin_filter)
async def add_trigger(client, callback_query):
    parent_id = callback_query.matches[0].group(1)
    parent_node = await db.get_node(parent_id)
    child_type = LEVELS[parent_node['type']]
    
    if child_type == "course":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "ADD_COURSE_NAME", "parent_id": parent_id, "data": {}}
        await callback_query.message.reply_text("📝 Enter Course Name:")
    else:
        ADMIN_STATES[callback_query.from_user.id] = {"state": f"ADD_{child_type.upper()}", "parent_id": parent_id}
        await callback_query.message.reply_text(f"📝 Enter Name for new {child_type.capitalize()}:")
    await callback_query.answer()

# ==========================================
# 5. CORE UPLOAD LOGIC & RETRY SYSTEM
# ==========================================
async def process_file_upload(client, file_message, topic_id, status_msg):
    file_type = "video" if file_message.video else "pdf"
    file_name = "Unknown_File"
    if file_message.video and file_message.video.file_name:
        file_name = file_message.video.file_name
    elif file_message.document and file_message.document.file_name:
        file_name = file_message.document.file_name

    # Fetch DB Hierarchy for Custom Caption
    try:
        topic = await db.get_node(topic_id)
        teacher = await db.get_node(topic['parent'])
        subject = await db.get_node(teacher['parent'])
    except Exception as e:
        return await status_msg.edit_text("❌ Database Hierarchy Error!")

    custom_hash = generate_hash()
    url_path = "watch" if file_type == "video" else "pdf"
    custom_url = f"{config.DOMAIN_NAME}/{url_path}/{custom_hash}"
    
    # NEW CUSTOM CAPTION
    custom_caption = f"""🎓 {file_name}
🔖 Index ID : "{custom_hash}"
📚 Subject : "{subject['name']}"
🎯 Topic : "{topic['name']}"
👨‍🏫 Teacher : "{teacher['name']}"
📂 File Type : "{file_type.upper()}"
━━━━━━━━━━━━━━━━━━
💎 ENJOYS GUYS ⚡"""

    try:
        backup_msg = None
        max_retries = 3
        
        # 1. Forward to Backup
        for attempt in range(max_retries):
            try:
                backup_msg = await file_message.copy(config.BACKUP_CHANNEL_ID, caption=custom_caption)
                break
            except FloodWait as e:
                await status_msg.edit_text(f"⏳ Telegram Rate Limit. Auto-waiting {e.value} seconds...")
                await asyncio.sleep(e.value + 1)
        
        # 2. Forward to Dump Channel
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
                    # RETRY GENERATOR ON FAIL
                    fail_id = generate_hash()
                    FAILED_UPLOADS[fail_id] = {"chat_id": file_message.chat.id, "message_id": file_message.id, "topic_id": topic_id}
                    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry Upload", callback_data=f"retry_{fail_id}")]])
                    return await status_msg.edit_text(f"⚠️ Dump Channel Copy Failed!\nError: {e}\nCheck admin rights in `{clean_dump_id}`.", reply_markup=btn)
        
        # 3. Database Entry
        if backup_msg:
            await db.add_file(topic_id, file_type, custom_hash, custom_url, main_msg_id, backup_msg_id)
            await status_msg.edit_text(f"✅ **Uploaded successfully!**\n\n🔗 **Link:** `{custom_url}`\n📝 **Hash:** `{custom_hash}`")
        else:
            await status_msg.edit_text("❌ Upload failed. Could not send to Backup Channel.")
            
    except Exception as e:
        fail_id = generate_hash()
        FAILED_UPLOADS[fail_id] = {"chat_id": file_message.chat.id, "message_id": file_message.id, "topic_id": topic_id}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry Upload", callback_data=f"retry_{fail_id}")]])
        await status_msg.edit_text(f"❌ Critical Error: {e}", reply_markup=btn)

@app.on_callback_query(filters.regex("^retry_(.*)") & admin_filter)
async def retry_upload_handler(client, callback_query):
    fail_id = callback_query.matches[0].group(1)
    if fail_id not in FAILED_UPLOADS:
        return await callback_query.answer("Retry session expired! Send file again.", show_alert=True)
    
    data = FAILED_UPLOADS[fail_id]
    await callback_query.message.edit_text("🔄 Retrying Upload...")
    try:
        original_msg = await client.get_messages(data["chat_id"], data["message_id"])
        await process_file_upload(client, original_msg, data["topic_id"], callback_query.message)
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Retry completely failed: {e}")

# ==========================================
# 6. HANDLING ADMIN INPUTS (Continuous Flow FSM)
# ==========================================
@app.on_message(filters.private & admin_filter & ~filters.command("start"))
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_STATES:
        return 
    
    state_data = ADMIN_STATES[user_id]
    current_state = state_data.get("state")
    
    if current_state == "ADD_COURSE_NAME":
        if not message.text: return await message.reply("❌ Send text only!")
        state_data['data']['name'] = message.text
        state_data['state'] = "ADD_COURSE_DUMP"
        await message.reply_text("📥 Excellent! Now send the **Dump Channel ID** (e.g. -100123456789).")
        
    elif current_state == "ADD_COURSE_DUMP":
        if not message.text: return await message.reply("❌ Send text only!")
        state_data['data']['dump_channel'] = int(message.text)
        state_data['state'] = "ADD_COURSE_THUMB"
        await message.reply_text("🖼 Now send the **Thumbnail Image** (Photo).")
        
    elif current_state == "ADD_COURSE_THUMB":
        if not message.photo: return await message.reply("❌ Send a photo only!")
        c_data = state_data['data']
        parent_id = state_data['parent_id']
        await db.add_node(c_data['name'], "course", parent_id, extra={"dump_channel": c_data['dump_channel'], "thumb": message.photo.file_id})
        
        del ADMIN_STATES[user_id]
        await message.reply_text("✅ Course created successfully!")
        await render_nav_menu(client, message, "add", parent_id) # Continuous flow

    elif current_state.startswith("ADD_"):
        if not message.text: return await message.reply("❌ Send text only!")
        node_type = current_state.split("_")[1].lower()
        parent_id = state_data['parent_id']
        await db.add_node(message.text, node_type, parent_id)
        
        del ADMIN_STATES[user_id]
        await message.reply_text(f"✅ {node_type.capitalize()} '{message.text}' created!")
        await render_nav_menu(client, message, "add", parent_id) # Continuous flow
        
    elif current_state == "EDIT_NAME":
        if not message.text: return await message.reply("❌ Send text only!")
        node_id = state_data['node_id']
        parent_id = state_data['parent_id']
        await db.update_node_name(node_id, message.text)
        
        del ADMIN_STATES[user_id]
        await message.reply_text("✅ Name updated successfully!")
        await render_nav_menu(client, message, "manage", parent_id)

    elif current_state == "UPLOAD_MODE":
        if not (message.video or message.document):
            return await message.reply_text("❌ Send a valid Video or PDF document!")
        
        status_msg = await message.reply_text("🔄 Processing and Uploading...")
        await process_file_upload(client, message, state_data['topic_id'], status_msg)

# ==========================================
# 7. EDIT / DELETE CALLBACKS
# ==========================================
@app.on_callback_query(filters.regex("^(edit|del)_(.*)") & admin_filter)
async def edit_delete_handler(client, callback_query):
    action = callback_query.matches[0].group(1)
    node_id = callback_query.matches[0].group(2)
    node = await db.get_node(node_id)
    
    if action == "edit":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "EDIT_NAME", "node_id": node_id, "parent_id": node['parent']}
        await callback_query.message.reply_text("📝 Send the new name:")
        await callback_query.answer()
        
    elif action == "del":
        parent_id = node['parent']
        await db.delete_node(node_id)
        await callback_query.answer("🗑 Node Deleted!", show_alert=True)
        await render_nav_menu(client, callback_query.message, "manage", parent_id)

if __name__ == "__main__":
    print("Starting Web Server...")
    keep_alive()
    print("Starting Telegram Bot...")
    app.run()

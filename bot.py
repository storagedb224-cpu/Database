import string
import random
import asyncio
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

# Admin Dictionary for State Management (FSM)
ADMIN_STATES = {}

# Node hierarchy levels
LEVELS = {
    "root": "coaching",
    "coaching": "course",
    "course": "subject",
    "subject": "teacher",
    "teacher": "topic",
    "topic": "file" # Topic ke andar files hoti hain
}

def generate_hash():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# --- AUTH CHECK ---
async def is_admin(_, __, message: Message):
    return message.from_user and message.from_user.id in config.ADMINS
admin_filter = filters.create(is_admin)

# ==========================================
# 1. MAIN DASHBOARD (/start)
# ==========================================
@app.on_message(filters.command("start") & admin_filter)
async def start_cmd(client, message):
    # Reset any stuck state
    if message.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[message.from_user.id]

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Data (Tree Mode)", callback_data="nav_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="nav_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ])
    await message.reply_text("🚀 **Premium Storage Bot - Master Dashboard**\nSelect an option below:", reply_markup=markup)

# ==========================================
# 2. STATS 
# ==========================================
@app.on_callback_query(filters.regex("^stats$") & admin_filter)
async def show_stats(client, callback_query):
    stats = await db.get_stats()
    text = "📊 **Live MongoDB Stats:**\n\n"
    for k, v in stats.items():
        text += f"• {k}: `{v}`\n"
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="nav_root")]]))

# ==========================================
# 3. HIERARCHY NAVIGATION (The Engine)
# ==========================================
@app.on_callback_query(filters.regex("^nav_(.*)") & admin_filter)
async def navigate_tree(client, callback_query):
    node_id = callback_query.data.split("_")[1]
    
    current_node = await db.get_node(node_id)
    if not current_node:
        return await callback_query.answer("Node not found!", show_alert=True)
    
    node_type = current_node['type']
    
    if node_type == "topic":
        # Topic open kiya hai -> Upload mode me daalo
        ADMIN_STATES[callback_query.from_user.id] = {"state": "UPLOAD_MODE", "topic_id": str(current_node['_id'])}
        text = f"📂 **Topic:** {current_node['name']}\n\n📤 **UPLOAD MODE ACTIVATED!**\nSend Videos/PDFs here. They will be dual-backed up automatically."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"nav_{current_node['parent']}")]])
        await callback_query.message.edit_text(text, reply_markup=markup)
        return

    child_type = LEVELS[node_type]
    children = await db.get_nodes(node_id)
    
    text = f"📂 **Current Location:** {current_node['name'].upper()}\n⬇️ Select a {child_type.capitalize()} or Add New."
    
    buttons = []
    for child in children:
        buttons.append([InlineKeyboardButton(f"📁 {child['name']}", callback_data=f"opt_{child['_id']}")])
    
    buttons.append([InlineKeyboardButton(f"➕ Add {child_type.capitalize()}", callback_data=f"add_{node_id}")])
    
    if node_id != "root":
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"nav_{current_node['parent']}")])
        
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# Options for a specific Node (Manage Inside, Edit Name, Delete)
@app.on_callback_query(filters.regex("^opt_(.*)") & admin_filter)
async def node_options(client, callback_query):
    node_id = callback_query.data.split("_")[1]
    node = await db.get_node(node_id)
    
    text = f"⚙️ **Manage:** {node['name']} ({node['type'].capitalize()})"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Manage Inside", callback_data=f"nav_{node_id}")],
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_{node_id}"), InlineKeyboardButton("🗑 Delete", callback_data=f"del_{node_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"nav_{node['parent']}")]
    ])
    await callback_query.message.edit_text(text, reply_markup=markup)

# ==========================================
# 4. ADDING DATA (Triggering States)
# ==========================================
@app.on_callback_query(filters.regex("^add_(.*)") & admin_filter)
async def add_trigger(client, callback_query):
    parent_id = callback_query.data.split("_")[1]
    parent_node = await db.get_node(parent_id)
    child_type = LEVELS[parent_node['type']]
    
    # Advanced logic for Course (Requires Name -> Dump ID -> Thumb)
    if child_type == "course":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "ADD_COURSE_NAME", "parent_id": parent_id, "data": {}}
        await callback_query.message.reply_text("📝 Enter Course Name:")
    else:
        ADMIN_STATES[callback_query.from_user.id] = {"state": f"ADD_{child_type.upper()}", "parent_id": parent_id}
        await callback_query.message.reply_text(f"📝 Enter Name for new {child_type.capitalize()}:")
    await callback_query.answer()

# ==========================================
# 5. HANDLING ADMIN TEXT/MEDIA INPUTS (FSM)
# ==========================================
@app.on_message(filters.private & admin_filter & ~filters.command("start"))
async def handle_inputs(client, message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_STATES:
        return # Agar koi state nahi hai to bot ignore karega
    
    state_data = ADMIN_STATES[user_id]
    current_state = state_data.get("state")
    
    # --- COURSE CREATION FSM ---
    if current_state == "ADD_COURSE_NAME":
        if not message.text: return await message.reply("❌ Send text only!")
        state_data['data']['name'] = message.text
        state_data['state'] = "ADD_COURSE_DUMP"
        await message.reply_text("📥 Excellent! Now send the **Dump Channel ID** (e.g. -100123456789) for this course.")
        
    elif current_state == "ADD_COURSE_DUMP":
        if not message.text: return await message.reply("❌ Send text only!")
        state_data['data']['dump_channel'] = int(message.text)
        state_data['state'] = "ADD_COURSE_THUMB"
        await message.reply_text("🖼 Now send the **Thumbnail Image** (Photo) for this course.")
        
    elif current_state == "ADD_COURSE_THUMB":
        if not message.photo: return await message.reply("❌ Send a photo only!")
        state_data['data']['thumb'] = message.photo.file_id
        
        # Save complete course to DB
        parent_id = state_data['parent_id']
        c_data = state_data['data']
        await db.add_node(c_data['name'], "course", parent_id, extra={"dump_channel": c_data['dump_channel'], "thumb": c_data['thumb']})
        
        del ADMIN_STATES[user_id]
        await message.reply_text("✅ Course created successfully! Send /start to navigate.")

    # --- NORMAL NODE CREATION (Coaching, Subject, Teacher, Topic) ---
    elif current_state.startswith("ADD_"):
        if not message.text: return await message.reply("❌ Send text only!")
        node_type = current_state.split("_")[1].lower()
        await db.add_node(message.text, node_type, state_data['parent_id'])
        del ADMIN_STATES[user_id]
        await message.reply_text(f"✅ {node_type.capitalize()} '{message.text}' created! Send /start to manage.")
        
    # --- EDIT NODE NAME ---
    elif current_state == "EDIT_NAME":
        if not message.text: return await message.reply("❌ Send text only!")
        node_id = state_data['node_id']
        await db.update_node_name(node_id, message.text)
        del ADMIN_STATES[user_id]
        await message.reply_text("✅ Name updated successfully! Send /start.")

    # --- 📤 THE CORE ENGINE: UPLOAD MODE (Dual Storage) ---
    elif current_state == "UPLOAD_MODE":
        if not (message.video or message.document):
            return await message.reply_text("❌ Send a valid Video or PDF document!")
            
        topic_id = state_data['topic_id']
        file_type = "video" if message.video else "pdf"
        
        # Original file ka naam extract karna
        file_name = "Unknown_File"
        if message.video and message.video.file_name:
            file_name = message.video.file_name
        elif message.document and message.document.file_name:
            file_name = message.document.file_name

        status_msg = await message.reply_text("🔄 Processing and Uploading... Please wait.")
        
        # Action: Generate Hash and URL
        custom_hash = generate_hash()
        url_path = "watch" if file_type == "video" else "pdf"
        custom_url = f"{config.DOMAIN_NAME}/{url_path}/{custom_hash}"
        
        # --- BADIYA CUSTOM CAPTION ---
        custom_caption = (
            f"**📁 Name:** `{file_name}`\n"
            f"**🗂 Type:** `{file_type.capitalize()}`\n\n"
            f"**🔗 Watch/Download Link:** {custom_url}\n"
            f"**🔑 File Hash:** `{custom_hash}`\n\n"
            f"⚡️ *Provided by Premium Storage*"
        )
        
        try:
            # Action 1: Universal Backup Channel (With Auto-Retry for Rate Limits)
            backup_msg = None
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    # Naya caption pass kiya jaa raha hai (purana auto remove ho jayega)
                    backup_msg = await message.copy(
                        config.BACKUP_CHANNEL_ID,
                        caption=custom_caption 
                    )
                    break
                except FloodWait as e:
                    await status_msg.edit_text(f"⏳ Telegram Rate Limit. Auto-waiting {e.value} seconds...")
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    raise e
            
            # Action 1.5: Course Dump Channel
            dump_channel_id = await db.get_course_dump_channel(topic_id)
            main_msg_id = None
            
            if dump_channel_id:
                # String ID ko integer me convert karke send karna ensure kar rahe hain
                clean_dump_id = int(dump_channel_id)
                for attempt in range(max_retries):
                    try:
                        dump_msg = await message.copy(
                            clean_dump_id,
                            caption=custom_caption
                        )
                        main_msg_id = dump_msg.id
                        break
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                    except Exception as e:
                        await message.reply_text(f"⚠️ Warning: Dump channel me copy nahi hua.\nKripya check karein ki kya Bot us channel ({clean_dump_id}) me ADMIN hai?\nError: {e}")
                        break
            
            # Action 2: Save to DB
            if backup_msg:
                await db.add_file(
                    topic_id=topic_id,
                    file_type=file_type,
                    custom_hash=custom_hash,
                    custom_url=custom_url,
                    main_msg_id=main_msg_id,
                    backup_msg_id=backup_msg.id
                )
                # Reply to Admin
                await status_msg.edit_text(f"✅ **Uploaded successfully to both channels!**\n\n🔗 **Link:** `{custom_url}`\n📝 **Hash:** `{custom_hash}`")
            else:
                await status_msg.edit_text("❌ Upload failed. Could not send to Backup Channel.")
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Critical Upload Error: {e}")

# ==========================================
# 6. EDIT / DELETE CALLBACKS
# ==========================================
@app.on_callback_query(filters.regex("^(edit|del)_(.*)") & admin_filter)
async def edit_delete_handler(client, callback_query):
    action, node_id = callback_query.data.split("_")
    
    if action == "edit":
        ADMIN_STATES[callback_query.from_user.id] = {"state": "EDIT_NAME", "node_id": node_id}
        await callback_query.message.reply_text("📝 Send the new name:")
        await callback_query.answer()
        
    elif action == "del":
        node = await db.get_node(node_id)
        await db.delete_node(node_id)
        await callback_query.answer("🗑 Node Deleted!", show_alert=True)
        # Go back to parent
        await navigate_tree(client, callback_query) # Simulating a back press 

# --- RUN BOT ---
if __name__ == "__main__":
    print("Starting Web Server...")
    keep_alive()
    print("Starting Telegram Bot...")
    app.run()

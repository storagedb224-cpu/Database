from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import config
from utils import ADMIN_STATES, HIERARCHY, is_admin

@Client.on_message((filters.text | filters.photo | filters.document | filters.video) & filters.private)
@is_admin
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_STATES:
        return
    state_data = ADMIN_STATES[user_id]
    state = state_data.get("state")
    
    if state == "wait_edit_name" and message.text:
        item_id = state_data["item_id"]
        new_name = message.text
        await database.update_item_name(item_id, new_name)
        del ADMIN_STATES[user_id]
        btn = [[InlineKeyboardButton("🔙 Back to Action Menu", callback_data=f"man_act_{item_id}")]]
        await message.reply_text(f"✅ Naam badalkar **{new_name}** ho gaya hai!", reply_markup=InlineKeyboardMarkup(btn))
        return

    if state and state.startswith("wait_name_") and message.text:
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

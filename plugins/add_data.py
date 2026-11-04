from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
from utils import ADMIN_STATES, HIERARCHY

@Client.on_callback_query(filters.regex(r"^nav_(.*)_(.*)$"))
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

@Client.on_callback_query(filters.regex(r"^add_(.*)_(.*)$"))
async def ask_new_item(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    ADMIN_STATES[callback_query.from_user.id] = {"state": f"wait_name_{item_type}", "parent_id": parent_id}
    await callback_query.message.reply_text(f"✍️ Naye **{HIERARCHY[item_type]['title']}** ka naam type karke bhejein:")

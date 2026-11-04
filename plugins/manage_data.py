from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
from utils import ADMIN_STATES, HIERARCHY

@Client.on_callback_query(filters.regex("^manage_root$"))
async def manage_root(client, callback_query):
    coachings = await database.get_items("root", "coaching")
    buttons = [[InlineKeyboardButton(f"🏫 {c['name']}", callback_data=f"man_act_{c['_id']}")] for c in coachings]
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start_menu")])
    await callback_query.message.edit_text("⚙️ **Manage Data (Root)**\nKis Coaching ko manage/edit karna hai?", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^man_nav_(.*)_(.*)$"))
async def manage_nav(client, callback_query):
    item_type = callback_query.matches[0].group(1)
    parent_id = callback_query.matches[0].group(2)
    items = await database.get_items(parent_id, item_type)
    buttons = [[InlineKeyboardButton(f"📂 {item['name']}", callback_data=f"man_act_{item['_id']}")] for item in items]
    
    parent_item = await database.get_item_by_id(parent_id)
    back_btn = f"man_act_{parent_id}" if parent_item and parent_item.get("parent_id") != "root" else "manage_root"
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=back_btn)])
    await callback_query.message.edit_text(f"⚙️ **Select {HIERARCHY[item_type]['title']} to Manage:**", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^man_act_(.*)$"))
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

@Client.on_callback_query(filters.regex(r"^edit_name_(.*)$"))
async def ask_edit_name(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    ADMIN_STATES[callback_query.from_user.id] = {"state": "wait_edit_name", "item_id": item_id}
    await callback_query.message.reply_text(f"✍️ **{item['name']}** ka naya naam type karke bhejein:")

@Client.on_callback_query(filters.regex(r"^delete_item_(.*)$"))
async def delete_item_cb(client, callback_query):
    item_id = callback_query.matches[0].group(1)
    item = await database.get_item_by_id(item_id)
    back_cb = "manage_root" if item.get("parent_id") == "root" else f"man_nav_{item['type']}_{item['parent_id']}"
    
    await database.delete_item(item_id)
    await callback_query.answer("✅ Item Deleted!", show_alert=True)
    
    # Page Refresh Trick
    callback_query.matches = [type('obj', (object,), {'group': lambda self, x: back_cb.split('_')[-2] if x==1 else back_cb.split('_')[-1]})()]
    if back_cb == "manage_root":
        await manage_root(client, callback_query)
    else:
        await manage_nav(client, callback_query)

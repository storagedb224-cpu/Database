from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
from utils import ADMIN_STATES, admin_filter  # 🆕 admin_filter इम्पोर्ट किया

# 🆕 @is_admin हटाकर admin_filter को लाइन में ही जोड़ दिया
@Client.on_message(filters.command("start") & filters.private & admin_filter)
async def start_cmd(client, message):
    if message.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[message.from_user.id]
        
    buttons = [
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_coaching_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ]
    await message.reply_text("👑 **Admin Dashboard**\nSwagat hai! Apna option chunein:", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^start_menu$"))
async def start_menu_cb(client, callback_query):
    if callback_query.from_user.id in ADMIN_STATES:
        del ADMIN_STATES[callback_query.from_user.id]
    buttons = [
        [InlineKeyboardButton("➕ Add Course / Data", callback_data="nav_coaching_root")],
        [InlineKeyboardButton("⚙️ Manage Data", callback_data="manage_root")],
        [InlineKeyboardButton("📊 Premium Stats", callback_data="stats")]
    ]
    await callback_query.message.edit_text("👑 **Admin Dashboard**\nChunein aapko kya karna hai:", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^stats$"))
async def show_stats(client, callback_query):
    coaching, course, videos, pdfs = await database.get_stats()
    text = f"📊 **DATABASE STATISTICS** 📊\n━━━━━━━━━━━━━━━━━━━━\n🏫 Total Coachings: `{coaching}`\n📚 Total Courses: `{course}`\n🎥 Total Videos: `{videos}`\n📕 Total PDFs: `{pdfs}`\n📦 Total Media: `{videos + pdfs}`\n━━━━━━━━━━━━━━━━━━━━"
    btn = [[InlineKeyboardButton("🔙 Back", callback_data="start_menu")]]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btn))

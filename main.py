import asyncio
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client
import config
from keep_alive import keep_alive

# plugins=dict(root="plugins") lagane se ye apne aap saari files utha lega
app = Client(
    "StorageBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=dict(root="plugins") 
)

if __name__ == "__main__":
    keep_alive()
    print("🚀 Modular Storage Bot Started Successfully...")
    app.run()

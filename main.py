import logging
import os

# यह हमें बताएगा कि बॉट के अंदर क्या चल रहा है
logging.basicConfig(level=logging.INFO)

import asyncio
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client
import config
from keep_alive import keep_alive

# 💡 स्मार्ट प्लगइन खोजक (Smart Plugin Finder)
# अगर 'plugins' फोल्डर गिटहब पर नहीं है, तो यह बाहर (Root) से फाइलें उठा लेगा!
plugin_folder = "plugins" if os.path.exists("plugins") else "."

app = Client(
    "StorageBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=dict(root=plugin_folder) 
)

if __name__ == "__main__":
    keep_alive()
    print(f"🚀 Bot Started! Plugins loaded from: '{plugin_folder}'")
    app.run()

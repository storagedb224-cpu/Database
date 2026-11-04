from motor.motor_asyncio import AsyncIOMotorClient
import config
import string
import random

# MongoDB कनेक्शन
client = AsyncIOMotorClient(config.MONGO_URI)
db = client["CourseStorageDB"]

# कलेक्शन्स (Collections)
tree_col = db["course_tree"]  # कोचिंग, कोर्स, सब्जेक्ट के नाम के लिए
files_col = db["files_data"]  # फाइल्स के लिंक्स और ID के लिए

async def get_items(parent_id, category_type):
    # डेटाबेस से बटन बनाने के लिए लिस्ट निकालना
    cursor = tree_col.find({"parent_id": parent_id, "type": category_type})
    return await cursor.to_list(length=100)

async def add_item(name, parent_id, category_type):
    # नया नाम (कोचिंग, कोर्स आदि) जोड़ना
    item = {"name": name, "parent_id": parent_id, "type": category_type}
    result = await tree_col.insert_one(item)
    return str(result.inserted_id)

def generate_custom_id():
    # यूनिक कस्टम ID (जैसे A1B2C) बनाना
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

async def save_file_data(file_type, file_id, msg_id, backup_msg_id, tree_path):
    # फाइल को मोंगो डीबी में सेव करना
    custom_hash = generate_custom_id()
    custom_url = f"{config.DOMAIN_NAME}/{'watch' if file_type == 'video' else 'pdf'}/{custom_hash}"
    
    data = {
        "custom_hash": custom_hash,
        "custom_url": custom_url,
        "main_msg_id": msg_id,
        "backup_msg_id": backup_msg_id,
        "tree_path": tree_path, # इसमें कोचिंग से लेकर टॉपिक तक की IDs होंगी
        "file_type": file_type
    }
    await files_col.insert_one(data)
    return custom_url

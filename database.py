from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
import config
import string
import random

# MongoDB Connection
client = AsyncIOMotorClient(config.MONGO_URI)
db = client["StorageBotDB"]
tree_col = db["tree_data"]  
files_col = db["files_data"]  

async def get_items(parent_id, item_type):
    cursor = tree_col.find({"parent_id": str(parent_id), "type": item_type})
    return await cursor.to_list(length=1000)

async def get_item_by_id(item_id):
    return await tree_col.find_one({"_id": ObjectId(item_id)})

async def add_item(name, parent_id, item_type, extra_data=None):
    doc = {"name": name, "parent_id": str(parent_id), "type": item_type}
    if extra_data:
        doc.update(extra_data)
    res = await tree_col.insert_one(doc)
    return str(res.inserted_id)

async def delete_item(item_id):
    await tree_col.delete_one({"_id": ObjectId(item_id)})

async def get_stats():
    coaching_count = await tree_col.count_documents({"type": "coaching"})
    course_count = await tree_col.count_documents({"type": "course"})
    videos_count = await files_col.count_documents({"file_type": "video"})
    pdfs_count = await files_col.count_documents({"file_type": "pdf"})
    return coaching_count, course_count, videos_count, pdfs_count

def generate_custom_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

async def get_course_channel_id(topic_id):
    try:
        topic = await tree_col.find_one({"_id": ObjectId(topic_id)})
        teacher = await tree_col.find_one({"_id": ObjectId(topic["parent_id"])})
        subject = await tree_col.find_one({"_id": ObjectId(teacher["parent_id"])})
        course = await tree_col.find_one({"_id": ObjectId(subject["parent_id"])})
        return course.get("channel_id")
    except Exception as e:
        print(f"Channel dhundhne me error: {e}")
        return None

async def save_file(topic_id, file_type, main_msg_id, backup_msg_id):
    custom_hash = generate_custom_id()
    folder = "watch" if file_type == "video" else "pdf"
    custom_url = f"{config.DOMAIN_NAME}/{folder}/{custom_hash}"
    
    doc = {
        "custom_hash": custom_hash,
        "custom_url": custom_url,
        "topic_id": str(topic_id),
        "file_type": file_type,
        "main_msg_id": main_msg_id,
        "backup_msg_id": backup_msg_id
    }
    await files_col.insert_one(doc)
    return custom_url

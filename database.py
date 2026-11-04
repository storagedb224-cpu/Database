from motor.motor_asyncio import AsyncIOMotorClient
import config
from bson.objectid import ObjectId

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
    # Aage chal kar isme child items delete karne ka logic bhi add kar sakte hain

async def get_stats():
    coaching_count = await tree_col.count_documents({"type": "coaching"})
    course_count = await tree_col.count_documents({"type": "course"})
    
    videos_count = await files_col.count_documents({"file_type": "video"})
    pdfs_count = await files_col.count_documents({"file_type": "pdf"})
    
    return coaching_count, course_count, videos_count, pdfs_count

async def save_file(topic_id, file_type, msg_id):
    doc = {
        "topic_id": str(topic_id),
        "file_type": file_type,
        "msg_id": msg_id
    }
    await files_col.insert_one(doc)

from motor.motor_asyncio import AsyncIOMotorClient
import config
from bson import ObjectId

client = AsyncIOMotorClient(config.MONGO_URI)
db = client['PremiumStorageBot']
nodes_col = db['nodes'] # Coaching, Course, Subject, etc.
files_col = db['files'] # Videos and PDFs

async def add_node(name, node_type, parent_id, extra=None):
    doc = {
        "name": name,
        "type": node_type,
        "parent": parent_id,
        "extra": extra or {}
    }
    result = await nodes_col.insert_one(doc)
    return str(result.inserted_id)

async def get_nodes(parent_id):
    cursor = nodes_col.find({"parent": parent_id})
    return await cursor.to_list(length=1000)

async def get_node(node_id):
    if node_id == "root": return {"_id": "root", "name": "Root", "type": "root"}
    return await nodes_col.find_one({"_id": ObjectId(node_id)})

async def update_node_name(node_id, new_name):
    await nodes_col.update_one({"_id": ObjectId(node_id)}, {"$set": {"name": new_name}})

async def delete_node(node_id):
    # Note: Advanced cascading delete can be implemented here later
    await nodes_col.delete_one({"_id": ObjectId(node_id)})

async def add_file(topic_id, file_type, custom_hash, custom_url, main_msg_id, backup_msg_id):
    doc = {
        "topic_id": str(topic_id),
        "file_type": file_type,
        "custom_hash": custom_hash,
        "custom_url": custom_url,
        "main_msg_id": main_msg_id,
        "backup_msg_id": backup_msg_id
    }
    await files_col.insert_one(doc)

async def get_stats():
    stats = {
        "Coachings": await nodes_col.count_documents({"type": "coaching"}),
        "Courses": await nodes_col.count_documents({"type": "course"}),
        "Topics": await nodes_col.count_documents({"type": "topic"}),
        "Files (Videos/PDFs)": await files_col.count_documents({})
    }
    return stats

# Helper to trace back to Course Level
async def get_course_dump_channel(topic_id):
    try:
        topic = await get_node(topic_id)
        teacher = await get_node(topic['parent'])
        subject = await get_node(teacher['parent'])
        course = await get_node(subject['parent'])
        return course['extra'].get('dump_channel')
    except Exception as e:
        return None

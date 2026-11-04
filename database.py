from motor.motor_asyncio import AsyncIOMotorClient
import config
from bson import ObjectId
import datetime

client = AsyncIOMotorClient(config.MONGO_URI)
db = client['PremiumStorageBot']
nodes_col = db['nodes']
files_col = db['files']

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
    await nodes_col.delete_one({"_id": ObjectId(node_id)})

async def add_file(topic_id, file_type, custom_hash, custom_url, main_msg_id, backup_msg_id, index_id):
    doc = {
        "topic_id": str(topic_id),
        "file_type": file_type,
        "custom_hash": custom_hash,
        "index_id": index_id,
        "custom_url": custom_url,
        "main_msg_id": main_msg_id,
        "backup_msg_id": backup_msg_id,
        "created_at": datetime.datetime.utcnow()
    }
    await files_col.insert_one(doc)

async def get_stats():
    now = datetime.datetime.utcnow()
    today_start = datetime.datetime(now.year, now.month, now.day)
    
    stats = {
        "total_channels": await nodes_col.count_documents({"type": "coaching"}),
        "total_courses": await nodes_col.count_documents({"type": "course"}),
        "total_videos": await files_col.count_documents({"file_type": "video"}),
        "total_pdfs": await files_col.count_documents({"file_type": "pdf"}),
        "today_new_files": await files_col.count_documents({"created_at": {"$gte": today_start}})
    }
    return stats

# Traceback to find Course ID for Auto-Index Generation
async def get_course_id(topic_id):
    try:
        topic = await get_node(topic_id)
        teacher = await get_node(topic['parent'])
        subject = await get_node(teacher['parent'])
        course = await get_node(subject['parent'])
        return str(course['_id'])
    except Exception as e:
        return None

async def get_course_dump_channel(topic_id):
    try:
        course_id = await get_course_id(topic_id)
        if course_id:
            course = await get_node(course_id)
            return course['extra'].get('dump_channel')
        return None
    except Exception:
        return None

# Generate Sequential 01, 02, 03... per course
async def get_next_index(course_id):
    if not course_id: return "01"
    course = await get_node(course_id)
    extra = course.get('extra', {})
    
    current_index = extra.get('last_index', 0)
    next_index = current_index + 1
    
    extra['last_index'] = next_index
    await nodes_col.update_one(
        {"_id": ObjectId(course_id)}, 
        {"$set": {"extra": extra}}
    )
    return f"{next_index:02d}" # Automatically adds 0 (e.g., 01, 02, 15, 100)

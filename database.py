import json
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from bson import ObjectId
import config

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

async def get_all_descendants(node_id):
    descendants = []
    children = await get_nodes(str(node_id))
    for child in children:
        descendants.append(child)
        descendants.extend(await get_all_descendants(str(child['_id'])))
    return descendants

async def delete_node(node_id):
    node = await get_node(node_id)
    if not node: return
    
    descendants = await get_all_descendants(str(node_id))
    all_node_ids = [ObjectId(node_id)] + [child['_id'] for child in descendants]
    
    topic_ids = [str(node_id)] + [str(child['_id']) for child in descendants if child['type'] == 'topic']
    if topic_ids:
        await files_col.delete_many({"topic_id": {"$in": topic_ids}})
        
    await nodes_col.delete_many({"_id": {"$in": all_node_ids}})

async def add_file(topic_id, file_type, custom_hash, custom_url, main_msg_id, backup_msg_id, index_id, file_name):
    doc = {
        "topic_id": str(topic_id),
        "file_type": file_type,
        "custom_hash": custom_hash,
        "index_id": index_id,
        "file_name": file_name,
        "custom_url": custom_url,
        "main_msg_id": main_msg_id,
        "backup_msg_id": backup_msg_id,
        "created_at": datetime.datetime.utcnow()
    }
    await files_col.insert_one(doc)

# 🟢 FILES WILL ALWAYS SORT BY INDEX_ID (001, 002...)
async def get_files(topic_id):
    cursor = files_col.find({"topic_id": str(topic_id)}).collation({"locale": "en", "numericOrdering": True}).sort("index_id", 1)
    return await cursor.to_list(length=1000)

async def get_file(file_id):
    return await files_col.find_one({"_id": ObjectId(file_id)})

async def delete_file(file_id):
    await files_col.delete_one({"_id": ObjectId(file_id)})

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

async def get_course_id(topic_id):
    try:
        topic = await get_node(topic_id)
        teacher = await get_node(topic['parent'])
        subject = await get_node(teacher['parent'])
        course = await get_node(subject['parent'])
        return str(course['_id'])
    except Exception:
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

async def get_next_index(course_id):
    if not course_id: return "001"
    result = await nodes_col.find_one_and_update(
        {"_id": ObjectId(course_id)},
        {"$inc": {"extra.last_index": 1}},
        return_document=ReturnDocument.AFTER
    )
    if not result: return "001"
    next_index = result.get("extra", {}).get("last_index", 1)
    return f"{next_index:03d}" 

# 🟢 AUTO FIX INDEX COMMAND LOGIC (/fixindex)
async def fix_all_indexes():
    courses = await nodes_col.find({"type": "course"}).to_list(length=None)
    for course in courses:
        descendants = await get_all_descendants(str(course['_id']))
        topic_ids = [str(child['_id']) for child in descendants if child['type'] == 'topic']
        
        if not topic_ids: continue
        
        # Files ko original time ke hisaab se sort karke uthayega
        files = await files_col.find({"topic_id": {"$in": topic_ids}}).sort("created_at", 1).to_list(length=None)
        
        counter = 1
        for f in files:
            new_idx = f"{counter:03d}"
            await files_col.update_one({"_id": f['_id']}, {"$set": {"index_id": new_idx}})
            counter += 1
            
        extra = course.get('extra', {})
        extra['last_index'] = counter - 1
        await nodes_col.update_one({"_id": course['_id']}, {"$set": {"extra": extra}})

class MongoEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId): return str(obj)
        if isinstance(obj, datetime.datetime): return obj.isoformat()
        return super().default(obj)

async def export_db_json():
    nodes = await nodes_col.find({}).to_list(length=None)
    files = await files_col.find({}).to_list(length=None)
    return json.dumps({"nodes": nodes, "files": files}, cls=MongoEncoder, indent=4)

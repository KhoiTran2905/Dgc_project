 
from pymongo import MongoClient

try:
    client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    client.server_info()  # Lệnh này sẽ lỗi nếu MongoDB không chạy
    print("✓ MongoDB connected successfully!")
    print(f"  Databases: {client.list_database_names()}")
except Exception as e:
    print(f"✗ Connection failed: {e}")
    print("  → Check if MongoDB service is running (Step 1)")
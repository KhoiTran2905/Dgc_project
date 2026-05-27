from pymongo import MongoClient
import time

class DGCDatabase:
    def __init__(self, uri="mongodb://localhost:27017", db_name="dgc_db"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.objects = self.db["objects"]
        self.refs = self.db["refs"]
        self.events = self.db["events"]
        self._setup_indexes()
        print(f"[DB] Connected → {db_name}")

    def _setup_indexes(self):
        self.objects.create_index("site_id")
        self.objects.create_index("deleted")
        self.refs.create_index("alive")
        self.refs.create_index([("alive", 1), ("lease_expiry", 1)])
        self.events.create_index("timestamp")
        self.events.create_index("event_type")

    # ── Objects ──────────────────────────────────────────

    def save_object(self, obj):
        self.objects.replace_one({"_id": obj.obj_id}, obj.to_dict(), upsert=True)

    def get_all_objects(self, site_id=None):
        query = {"site_id": site_id} if site_id else {}
        return list(self.objects.find(query))

    def count_collected(self):
        return self.objects.count_documents({"deleted": True})

    def count_leaked(self):
        # Còn sống nhưng rc=0 và local_rc=0 → không ai giữ mà chưa bị xóa
        return self.objects.count_documents({"deleted": False, "total_rc": 0})

    # ── Refs ─────────────────────────────────────────────

    def save_ref(self, ref):
        self.refs.replace_one({"_id": ref.ref_id}, ref.to_dict(), upsert=True)

    def get_expired_refs(self):
        # Tìm refs còn alive nhưng lease đã hết hạn
        now = time.time()
        return list(self.refs.find({"alive": True, "lease_expiry": {"$lt": now}}))

    def mark_ref_expired(self, ref_id: str):
        self.refs.update_one(
            {"_id": ref_id},
            {"$set": {"alive": False, "expired_at": time.time()}}
        )

    def get_active_ref_count(self):
        return self.refs.count_documents({"alive": True})

    # ── Events ───────────────────────────────────────────

    def log_event(self, event):
        self.events.insert_one(event.to_dict())

    def get_events_by_type(self, event_type: str):
        return list(self.events.find({"event_type": event_type}))

    # ── Analytics (dùng trong báo cáo) ───────────────────

    def get_summary(self):
        pipeline = [
            {"$group": {
                "_id": "$deleted",
                "count": {"$sum": 1},
                "avg_rc": {"$avg": "$total_rc"}
            }}
        ]
        return list(self.objects.aggregate(pipeline))

    def get_event_counts(self):
        pipeline = [
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return list(self.events.aggregate(pipeline))

    # ── Utility ──────────────────────────────────────────

    def clear_all(self):
        self.objects.drop()
        self.refs.drop()
        self.events.drop()
        self._setup_indexes()
        print("[DB] Cleared all collections")
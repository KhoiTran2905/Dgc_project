"""
Site B REST API — chạy lệnh: uvicorn api:app --reload --port 8000
Sau đó mở browser: http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import time

from dgc.database import DGCDatabase
from dgc.site_b import SiteB

# ── Khởi động app ─────────────────────────────────────────────────────────────
db = DGCDatabase()
site_b = SiteB(db, lease_duration=10.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tạo sẵn 5 objects khi server khởi động
    db.clear_all()
    for i in range(1, 6):
        site_b.create_object(f"B{i}")
    print("[API] Site B started — 5 objects created")
    yield
    site_b.stop()
    print("[API] Site B stopped")

app = FastAPI(
    title="Distributed GC — Site B API",
    description="REST API cho hệ thống Distributed Garbage Collection",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request/Response models ────────────────────────────────────────────────────

class AddRefRequest(BaseModel):
    ref_id: str
    from_site: str
    from_obj: str
    to_obj: str

class CreateObjectRequest(BaseModel):
    obj_id: str

# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    """Kiểm tra server có chạy không."""
    return {
        "message": "Site B DGC API đang chạy",
        "docs": "http://localhost:8000/docs"
    }


@app.get("/objects", tags=["Objects"])
def get_objects():
    """
    Lấy danh sách tất cả objects và trạng thái RC.
    Dùng để monitor hệ thống.
    """
    with site_b.lock:
        result = {}
        for obj_id, obj in site_b.objects.items():
            active_refs = [r for r in site_b.refs.values()
                          if r.to_obj == obj_id and r.alive]
            result[obj_id] = {
                "obj_id": obj_id,
                "rc": obj.rc,
                "local_rc": obj.local_rc,
                "total_rc": obj.total_rc,
                "deleted": obj.deleted,
                "active_refs": len(active_refs),
                "status": "deleted" if obj.deleted else
                          "alive" if obj.total_rc > 0 else "candidate"
            }
    return result


@app.post("/objects", tags=["Objects"])
def create_object(req: CreateObjectRequest):
    """Tạo object mới ở Site B."""
    with site_b.lock:
        if req.obj_id in site_b.objects:
            raise HTTPException(400, f"Object '{req.obj_id}' đã tồn tại")
    obj = site_b.create_object(req.obj_id)
    return {"message": f"Object '{req.obj_id}' created", "total_rc": obj.total_rc}


@app.get("/objects/{obj_id}", tags=["Objects"])
def get_object(obj_id: str):
    """Lấy thông tin 1 object cụ thể."""
    with site_b.lock:
        obj = site_b.objects.get(obj_id)
    if not obj:
        raise HTTPException(404, f"Object '{obj_id}' không tồn tại")
    return {
        "obj_id": obj.obj_id,
        "rc": obj.rc,
        "local_rc": obj.local_rc,
        "total_rc": obj.total_rc,
        "deleted": obj.deleted,
    }


@app.post("/refs", tags=["References"])
def add_ref(req: AddRefRequest):
    """
    Site A đăng ký giữ reference đến object của Site B.
    Tạo lease 10 giây — Site A phải renew trước khi hết hạn.
    """
    ok = site_b.add_remote_ref(
        req.ref_id, req.from_site, req.from_obj, req.to_obj
    )
    if not ok:
        raise HTTPException(404,
            f"Object '{req.to_obj}' không tồn tại hoặc đã bị deleted")
    with site_b.lock:
        obj = site_b.objects.get(req.to_obj)
    return {
        "ref_id": req.ref_id,
        "from": f"{req.from_site}:{req.from_obj}",
        "to": req.to_obj,
        "lease_duration": site_b.lease_duration,
        "total_rc_of_object": obj.total_rc if obj else 0,
        "message": f"Ref registered. Renew trước {site_b.lease_duration}s!"
    }


@app.put("/refs/{ref_id}/renew", tags=["References"])
def renew_lease(ref_id: str):
    """
    Site A gia hạn lease — heartbeat.
    Phải gọi mỗi 3 giây để tránh bị coi là crashed.
    """
    ok = site_b.renew_lease(ref_id)
    if not ok:
        raise HTTPException(404,
            f"Ref '{ref_id}' không tồn tại hoặc đã expired")
    with site_b.lock:
        ref = site_b.refs.get(ref_id)
    return {
        "ref_id": ref_id,
        "renewed": True,
        "new_expiry": ref.lease_expiry if ref else None,
        "expires_in": f"{site_b.lease_duration}s"
    }


@app.delete("/refs/{ref_id}", tags=["References"])
def remove_ref(ref_id: str):
    """
    Site A chủ động thả reference — happy path.
    Không cần chờ lease timeout.
    """
    ok = site_b.remove_remote_ref(ref_id)
    if not ok:
        raise HTTPException(404, f"Ref '{ref_id}' không tồn tại")
    return {"ref_id": ref_id, "released": True, "message": "Ref removed"}


@app.get("/refs", tags=["References"])
def get_refs():
    """Xem tất cả refs hiện tại (alive và expired)."""
    with site_b.lock:
        result = []
        for ref in site_b.refs.values():
            result.append({
                "ref_id": ref.ref_id,
                "from": f"{ref.from_site}:{ref.from_obj}",
                "to_obj": ref.to_obj,
                "alive": ref.alive,
                "expires_in_seconds": round(
                    max(0, ref.lease_expiry - time.time()), 1
                ),
            })
    return result


@app.get("/stats", tags=["Monitor"])
def get_stats():
    """
    Thống kê tổng quan — dùng để viết báo cáo và monitor.
    """
    with site_b.lock:
        objs = list(site_b.objects.values())
        refs = list(site_b.refs.values())

    alive   = [o for o in objs if not o.deleted]
    deleted = [o for o in objs if o.deleted]
    active_refs  = [r for r in refs if r.alive]
    expired_refs = [r for r in refs if not r.alive]

    return {
        "objects": {
            "total":   len(objs),
            "alive":   len(alive),
            "deleted": len(deleted),
        },
        "refs": {
            "active":  len(active_refs),
            "expired": len(expired_refs),
        },
        "gc": {
            "collected": site_b.stats["collected"],
            "leaked":    site_b.stats["leaked"],
            "false_deletes": site_b.stats["false_deletes"],
        },
        "lease_duration": site_b.lease_duration,
    }


@app.get("/events", tags=["Monitor"])
def get_events(limit: int = 20):
    """Xem event log gần nhất từ MongoDB."""
    events = db.get_events_by_type.__func__ and \
             list(db.events.find().sort("timestamp", -1).limit(limit))
    return {"events": events, "total": db.events.count_documents({})}
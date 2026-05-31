# api/site_a_server.py
"""
Site A chạy như 1 server độc lập trên port 8001.
Khi tắt terminal này = Site A crash thật sự.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import threading
import time
import uuid
import httpx
import logging

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("SiteA-Server")

SITE_B_URL = "http://localhost:8000"
RENEW_INTERVAL = 3.0
LEASE_DURATION = 10.0

# ── State của Site A ───────────────────────────────────────────────────────────
class SiteAState:
    def __init__(self):
        self.held_refs: dict = {}   # ref_id → to_obj
        self.refs_lock = threading.Lock()
        self.lagging = False        # Giả lập lag mạng
        self.renew_timer = None
        self.client = httpx.Client(base_url=SITE_B_URL, timeout=5.0)
        self._start_renew_loop()

    def _start_renew_loop(self):
        def loop():
            while True:
                time.sleep(RENEW_INTERVAL)
                if self.lagging:
                    logger.warning("⚠ Site A đang LAG — bỏ qua renew!")
                    continue
                with self.refs_lock:
                    ref_ids = list(self.held_refs.keys())
                for ref_id in ref_ids:
                    try:
                        resp = self.client.put(f"/refs/{ref_id}/renew")
                        if resp.status_code == 200:
                            logger.debug(f"Renewed {ref_id}")
                        else:
                            logger.warning(f"Renew failed {ref_id}: {resp.status_code}")
                    except Exception as e:
                        logger.error(f"Renew error {ref_id}: {e}")

        t = threading.Thread(target=loop, daemon=True, name="SiteA-Renewer")
        t.start()

site_a = SiteAState()

# ── FastAPI app ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Site A server started on :8001")
    yield
    logger.info("Site A server stopping...")

app = FastAPI(
    title="Site A Server",
    description="Site A độc lập — tắt terminal này để simulate crash",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ─────────────────────────────────────────────────────────────────────
class GrabRefRequest(BaseModel):
    from_obj: str
    to_obj: str

# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/status", tags=["Info"])
def status():
    """Trạng thái Site A — dashboard ping endpoint này để biết A còn sống không."""
    with site_a.refs_lock:
        refs = dict(site_a.held_refs)
    return {
        "alive": True,
        "lagging": site_a.lagging,
        "held_refs": len(refs),
        "refs": refs,
    }


@app.post("/grab", tags=["Actions"])
def grab_ref(req: GrabRefRequest):
    """
    Site A grab reference đến object ở Site B.
    Tự động gọi POST /refs trên Site B.
    """
    ref_id = "ref-" + str(uuid.uuid4())[:6]
    try:
        resp = site_a.client.post(f"{SITE_B_URL}/refs", json={
            "ref_id": ref_id,
            "from_site": "A",
            "from_obj": req.from_obj,
            "to_obj": req.to_obj,
        })
        if resp.status_code == 200:
            with site_a.refs_lock:
                site_a.held_refs[ref_id] = req.to_obj
            logger.info(f"Grabbed {ref_id}: {req.from_obj}→{req.to_obj}")
            return {"ref_id": ref_id, "from": req.from_obj, "to": req.to_obj}
        raise HTTPException(400, f"Site B rejected: {resp.json()}")
    except httpx.ConnectError:
        raise HTTPException(503, "Không kết nối được Site B")


@app.delete("/release/{ref_id}", tags=["Actions"])
def release_ref(ref_id: str):
    """Site A chủ động release reference."""
    with site_a.refs_lock:
        if ref_id not in site_a.held_refs:
            raise HTTPException(404, f"Ref '{ref_id}' không tồn tại")
        to_obj = site_a.held_refs.pop(ref_id)

    try:
        site_a.client.delete(f"{SITE_B_URL}/refs/{ref_id}")
    except Exception as e:
        logger.error(f"Release error: {e}")

    logger.info(f"Released {ref_id}→{to_obj}")
    return {"ref_id": ref_id, "released": True}


@app.post("/lag/start", tags=["Simulate"])
def start_lag():
    """
    Bắt đầu giả lập lag mạng.
    Site A ngừng renew lease → sau 10s Site B sẽ coi A là dead.
    """
    site_a.lagging = True
    logger.warning("⚠ LAG STARTED — heartbeat stopped")
    return {"lagging": True, "message": "Site A đang lag — lease sẽ expire sau 10s"}


@app.post("/lag/stop", tags=["Simulate"])
def stop_lag():
    """Dừng lag — Site A renew lại bình thường."""
    site_a.lagging = False
    logger.info("Lag stopped — heartbeat resumed")
    return {"lagging": False, "message": "Lag dừng — heartbeat tiếp tục"}
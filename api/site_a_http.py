"""
Phiên bản Site A dùng HTTP thay vì direct call.
Dùng cùng interface với site_a.py để dễ swap.
"""
import time
import threading
import logging
import uuid
import httpx

logger = logging.getLogger("SiteA-HTTP")

RENEW_INTERVAL = 3.0
SITE_B_URL = "http://localhost:8000"


class SiteAHttp:
    """Giống SiteA nhưng giao tiếp với Site B qua REST API."""

    def __init__(self, site_id: str):
        self.site_id = site_id
        self.client = httpx.Client(base_url=SITE_B_URL, timeout=5.0)
        self.alive = True
        self.held_refs: dict = {}
        self.refs_lock = threading.Lock()
        self._renewer = threading.Thread(
            target=self._renew_loop, daemon=True,
            name=f"{site_id}-Heartbeat-HTTP"
        )
        self._renewer.start()
        logger.info(f"[{self.site_id}] Started → Site B at {SITE_B_URL}")

    def grab_ref(self, from_obj: str, to_obj: str):
        if not self.alive:
            return None
        ref_id = str(uuid.uuid4())[:8]
        try:
            resp = self.client.post("/refs", json={
                "ref_id": ref_id,
                "from_site": self.site_id,
                "from_obj": from_obj,
                "to_obj": to_obj,
            })
            if resp.status_code == 200:
                with self.refs_lock:
                    self.held_refs[ref_id] = to_obj
                logger.info(f"[{self.site_id}] Grabbed '{ref_id}': {from_obj}→{to_obj}")
                return ref_id
            logger.warning(f"grab_ref failed: {resp.json()}")
            return None
        except Exception as e:
            logger.error(f"HTTP error grab_ref: {e}")
            return None

    def release_ref(self, ref_id: str):
        with self.refs_lock:
            to_obj = self.held_refs.pop(ref_id, None)
        if to_obj is None:
            return False
        try:
            resp = self.client.delete(f"/refs/{ref_id}")
            logger.info(f"[{self.site_id}] Released '{ref_id}'→{to_obj}")
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"HTTP error release_ref: {e}")
            return False

    def crash(self):
        self.alive = False
        with self.refs_lock:
            abandoned = len(self.held_refs)
        logger.error(f"[{self.site_id}] ⚡ CRASHED — {abandoned} refs abandoned")

    def _renew_loop(self):
        while True:
            time.sleep(RENEW_INTERVAL)
            if not self.alive:
                continue
            with self.refs_lock:
                ref_ids = list(self.held_refs.keys())
            for ref_id in ref_ids:
                try:
                    self.client.put(f"/refs/{ref_id}/renew")
                except Exception as e:
                    logger.warning(f"Renew failed for '{ref_id}': {e}")
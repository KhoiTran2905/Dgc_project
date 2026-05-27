import time
import threading
import logging
import uuid

logger = logging.getLogger("SiteA")

RENEW_INTERVAL = 3.0


class SiteA:
    def __init__(self, site_id: str, site_b):
        self.site_id = site_id
        self.site_b = site_b
        self.alive = True
        self.held_refs: dict = {}   # ref_id → to_obj
        self._renewer = threading.Thread(
            target=self._renew_loop, daemon=True,
            name=f"{site_id}-Heartbeat"
        )
        self._renewer.start()
        logger.info(f"SiteA '{site_id}' started")

    def grab_ref(self, from_obj: str, to_obj: str):
        if not self.alive:
            return None
        ref_id = str(uuid.uuid4())[:8]
        ok = self.site_b.add_remote_ref(ref_id, self.site_id, from_obj, to_obj)
        if ok:
            self.held_refs[ref_id] = to_obj
            logger.info(f"[{self.site_id}] Grabbed '{ref_id}': {from_obj}→{to_obj}")
            return ref_id
        return None

    def release_ref(self, ref_id: str):
        if ref_id in self.held_refs:
            to_obj = self.held_refs.pop(ref_id)
            self.site_b.remove_remote_ref(ref_id)
            logger.info(f"[{self.site_id}] Released '{ref_id}'→{to_obj}")

    def crash(self):
        self.alive = False
        logger.error(
            f"[{self.site_id}] ⚡ CRASHED — "
            f"{len(self.held_refs)} refs abandoned"
        )

    def _renew_loop(self):
        while True:
            time.sleep(RENEW_INTERVAL)
            if not self.alive:
                continue
            for ref_id in list(self.held_refs.keys()):
                self.site_b.renew_lease(ref_id)
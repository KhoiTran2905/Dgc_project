import logging
import threading
import time
import uuid

logger = logging.getLogger("SiteA")

RENEW_INTERVAL = 3.0


class SiteA:
    def __init__(self, site_id: str, site_b):
        self.site_id = site_id
        self.site_b = site_b
        self.alive = True
        self.held_refs: dict = {}
        self.refs_lock = threading.Lock()
        self._renewer = threading.Thread(
            target=self._renew_loop,
            daemon=True,
            name=f"{site_id}-Heartbeat",
        )
        self._renewer.start()
        logger.info(f"SiteA '{site_id}' started")

    def grab_ref(self, from_obj: str, to_obj: str):
        if not self.alive:
            return None

        ref_id = str(uuid.uuid4())[:8]
        ok = self.site_b.add_remote_ref(ref_id, self.site_id, from_obj, to_obj)
        if not ok:
            return None

        with self.refs_lock:
            self.held_refs[ref_id] = to_obj

        logger.info(f"[{self.site_id}] Grabbed '{ref_id}': {from_obj}->{to_obj}")
        return ref_id

    def release_ref(self, ref_id: str):
        with self.refs_lock:
            to_obj = self.held_refs.pop(ref_id, None)

        if to_obj is None:
            return False

        removed = self.site_b.remove_remote_ref(ref_id)
        logger.info(f"[{self.site_id}] Released '{ref_id}'->{to_obj}")
        return removed

    def crash(self):
        self.alive = False
        with self.refs_lock:
            abandoned = len(self.held_refs)
        logger.error(f"[{self.site_id}] CRASHED - {abandoned} refs abandoned")

    def _renew_loop(self):
        while True:
            time.sleep(RENEW_INTERVAL)
            if not self.alive:
                continue

            with self.refs_lock:
                ref_ids = list(self.held_refs.keys())

            for ref_id in ref_ids:
                self.site_b.renew_lease(ref_id)

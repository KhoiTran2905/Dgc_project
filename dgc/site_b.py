import logging
import threading
import time

from .database import DGCDatabase
from .types import DGCObject, GCEvent, LeaseRef

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SiteB")

GC_SCAN_INTERVAL = 2.0


class SiteB:
    def __init__(self, db: DGCDatabase, lease_duration: float = 10.0):
        self.db = db
        self.lease_duration = lease_duration
        self.objects: dict = {}
        self.refs: dict = {}
        self.lock = threading.RLock()
        self.stats = {"collected": 0, "leaked": 0, "false_deletes": 0}
        self._running = True
        self._gc_thread = threading.Thread(
            target=self._gc_daemon, daemon=True, name="GC-Daemon"
        )
        self._gc_thread.start()
        logger.info(f"SiteB started | lease={lease_duration}s")

    def create_object(self, obj_id: str):
        with self.lock:
            obj = DGCObject(obj_id=obj_id, site_id="B")
            self.objects[obj_id] = obj
            self.db.save_object(obj)
            self._log("object_created", obj_id, "Created", obj.total_rc)
        return obj

    def release_local_ref(self, obj_id: str):
        with self.lock:
            obj = self.objects.get(obj_id)
            if not obj or obj.deleted:
                return
            obj.local_rc = max(0, obj.local_rc - 1)
            self.db.save_object(obj)
            logger.info(f"Local ref released on '{obj_id}' (local_rc={obj.local_rc})")
            self._try_collect(obj_id)

    def add_remote_ref(
        self, ref_id: str, from_site: str, from_obj: str, to_obj: str
    ) -> bool:
        with self.lock:
            existing_ref = self.refs.get(ref_id)
            if existing_ref and existing_ref.alive:
                existing_ref.renew()
                self.db.save_ref(existing_ref)
                logger.info(f"Ref '{ref_id}' already alive; lease renewed")
                return True

            obj = self.objects.get(to_obj)
            if not obj or obj.deleted:
                logger.warning(f"add_remote_ref FAILED: '{to_obj}' not found/deleted")
                return False

            ref = LeaseRef(from_site, from_obj, "B", to_obj, self.lease_duration)
            ref.ref_id = ref_id
            self.refs[ref_id] = ref
            obj.rc += 1

            self.db.save_ref(ref)
            self.db.save_object(obj)
            self._log("ref_added", to_obj, f"From {from_site}:{from_obj}", obj.total_rc)
            logger.info(f"Ref '{ref_id}': {from_site}:{from_obj}->{to_obj} (rc={obj.rc})")
            return True

    def renew_lease(self, ref_id: str) -> bool:
        with self.lock:
            ref = self.refs.get(ref_id)
            if not ref or not ref.alive:
                return False
            ref.renew()
            self.db.save_ref(ref)
            return True

    def remove_remote_ref(self, ref_id: str) -> bool:
        with self.lock:
            ref = self.refs.get(ref_id)
            if not ref or not ref.alive:
                return False

            ref.expire()
            obj = self.objects.get(ref.to_obj)
            if obj and not obj.deleted:
                obj.rc = max(0, obj.rc - 1)
                self.db.save_object(obj)
                self._log(
                    "ref_removed",
                    ref.to_obj,
                    f"Explicit by {ref.from_site}",
                    obj.total_rc,
                )
                logger.info(f"Ref '{ref_id}' removed (rc of {ref.to_obj}={obj.rc})")
                self._try_collect(ref.to_obj)

            self.db.save_ref(ref)
            self.db.mark_ref_expired(ref_id)
            return True

    def _try_collect(self, obj_id: str):
        obj = self.objects.get(obj_id)
        if not obj or obj.deleted:
            return
        if obj.can_be_deleted:
            obj.deleted = True
            obj.deleted_at = time.time()
            self.db.save_object(obj)
            self._log("object_collected", obj_id, "RC=0", 0)
            self.stats["collected"] += 1
            logger.info(f"'{obj_id}' COLLECTED")

    def _gc_daemon(self):
        logger.info("GC daemon running...")
        while self._running:
            time.sleep(GC_SCAN_INTERVAL)
            expired_count = self.collect_expired_refs()
            if expired_count:
                logger.warning(f"GC: {expired_count} expired lease(s) collected")

    def collect_expired_refs(self) -> int:
        with self.lock:
            return self._collect_expired_refs_locked()

    def _collect_expired_refs_locked(self) -> int:
        now = time.time()
        expired_count = 0

        for ref_id, ref in list(self.refs.items()):
            if not ref.alive or now <= ref.lease_expiry:
                continue

            ref.expire(now)
            expired_count += 1

            obj = self.objects.get(ref.to_obj)
            if obj and not obj.deleted:
                obj.rc = max(0, obj.rc - 1)
                self.db.save_object(obj)
                self._log(
                    "ref_expired",
                    ref.to_obj,
                    f"Lease timeout from {ref.from_site}",
                    obj.total_rc,
                )
                logger.warning(
                    f"Lease expired: {ref.from_site}->{ref.to_obj} "
                    f"(total_rc now {obj.total_rc})"
                )
                self._try_collect(ref.to_obj)

            self.db.save_ref(ref)
            self.db.mark_ref_expired(ref_id)

        return expired_count

    def _log(self, event_type, obj_id, reason, rc):
        self.db.log_event(GCEvent(event_type, obj_id, "B", reason, rc))

    def stop(self):
        self._running = False

    def print_status(self):
        print("\n" + "=" * 55)
        print("  SITE B - OBJECT STATUS")
        print("=" * 55)
        with self.lock:
            for obj_id in sorted(self.objects):
                obj = self.objects[obj_id]
                active = [
                    ref for ref in self.refs.values()
                    if ref.to_obj == obj_id and ref.alive
                ]
                status = "DELETED" if obj.deleted else "ALIVE  "
                print(
                    f"  {obj_id}: {status} | "
                    f"rc={obj.rc} local={obj.local_rc} "
                    f"total={obj.total_rc} | refs={len(active)}"
                )
        print(f"\n  Collected: {self.stats['collected']}")
        print("=" * 55)

import time
import uuid

class DGCObject:
    def __init__(self, obj_id: str, site_id: str):
        self.obj_id = obj_id
        self.site_id = site_id
        self.rc = 0
        self.local_rc = 1
        self.deleted = False
        self.created_at = time.time()
        self.deleted_at = None

    @property
    def total_rc(self):
        return self.rc + self.local_rc

    @property
    def can_be_deleted(self):
        return self.total_rc == 0 and not self.deleted

    def to_dict(self):
        return {
            "_id": self.obj_id,
            "obj_id": self.obj_id,
            "site_id": self.site_id,
            "rc": self.rc,
            "local_rc": self.local_rc,
            "total_rc": self.total_rc,
            "deleted": self.deleted,
            "created_at": self.created_at,
            "deleted_at": self.deleted_at,
        }


class LeaseRef:
    def __init__(self, from_site: str, from_obj: str,
                 to_site: str, to_obj: str, lease_duration: float = 10.0):
        self.ref_id = str(uuid.uuid4())[:8]
        self.from_site = from_site
        self.from_obj = from_obj
        self.to_site = to_site
        self.to_obj = to_obj
        self.lease_duration = lease_duration
        self.lease_expiry = time.time() + lease_duration
        self.alive = True
        self.created_at = time.time()
        self.expired_at = None

    def renew(self):
        self.lease_expiry = time.time() + self.lease_duration

    def is_expired(self):
        return time.time() > self.lease_expiry

    def to_dict(self):
        return {
            "_id": self.ref_id,
            "ref_id": self.ref_id,
            "from_site": self.from_site,
            "from_obj": self.from_obj,
            "to_site": self.to_site,
            "to_obj": self.to_obj,
            "lease_duration": self.lease_duration,
            "lease_expiry": self.lease_expiry,
            "alive": self.alive,
            "created_at": self.created_at,
            "expired_at": self.expired_at,
        }


class GCEvent:
    def __init__(self, event_type: str, obj_id: str,
                 site_id: str, reason: str, rc_at_event: int):
        self.event_type = event_type
        self.obj_id = obj_id
        self.site_id = site_id
        self.reason = reason
        self.rc_at_event = rc_at_event
        self.timestamp = time.time()

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "obj_id": self.obj_id,
            "site_id": self.site_id,
            "reason": self.reason,
            "rc_at_event": self.rc_at_event,
            "timestamp": self.timestamp,
        }
import time

from dgc.site_b import SiteB


class InMemoryDGCDB:
    def __init__(self):
        self.objects = {}
        self.refs = {}
        self.events = []

    def save_object(self, obj):
        self.objects[obj.obj_id] = obj.to_dict()

    def save_ref(self, ref):
        self.refs[ref.ref_id] = ref.to_dict()

    def mark_ref_expired(self, ref_id: str):
        ref = self.refs.get(ref_id)
        if ref:
            ref["alive"] = False
            ref["expired_at"] = time.time()

    def log_event(self, event):
        self.events.append(event.to_dict())

    def get_expired_refs(self):
        raise AssertionError("SiteB must not use stale DB snapshots for GC decisions")

    def count_leaked(self):
        return sum(
            1
            for obj in self.objects.values()
            if not obj["deleted"] and obj["total_rc"] == 0
        )


def make_site_b(lease_duration=10.0):
    return SiteB(InMemoryDGCDB(), lease_duration=lease_duration)


def test_add_and_remove_remote_ref_are_idempotent():
    site_b = make_site_b()
    try:
        site_b.create_object("B1")

        assert site_b.add_remote_ref("ref-1", "A", "A1", "B1") is True
        assert site_b.add_remote_ref("ref-1", "A", "A1", "B1") is True

        obj = site_b.objects["B1"]
        ref = site_b.refs["ref-1"]
        assert obj.rc == 1
        assert ref.alive is True

        assert site_b.remove_remote_ref("ref-1") is True
        assert site_b.remove_remote_ref("ref-1") is False
        assert site_b.remove_remote_ref("missing-ref") is False

        assert obj.rc == 0
        assert ref.alive is False
        assert ref.expired_at is not None
    finally:
        site_b.stop()


def test_late_heartbeat_before_gc_scan_prevents_false_deletion():
    site_b = make_site_b(lease_duration=30.0)
    try:
        site_b.create_object("B1")
        site_b.add_remote_ref("lag-ref", "A", "A1", "B1")
        site_b.release_local_ref("B1")

        ref = site_b.refs["lag-ref"]
        ref.lease_expiry = time.time() - 1.0
        site_b.db.save_ref(ref)

        assert site_b.renew_lease("lag-ref") is True
        expired_count = site_b.collect_expired_refs()

        obj = site_b.objects["B1"]
        assert expired_count == 0
        assert ref.alive is True
        assert obj.deleted is False
        assert obj.rc == 1
        assert site_b.stats["false_deletes"] == 0
    finally:
        site_b.stop()


def test_crashed_site_reference_is_collected_after_lease_expiry():
    site_b = make_site_b(lease_duration=10.0)
    try:
        site_b.create_object("B1")
        site_b.add_remote_ref("crash-ref", "A", "A1", "B1")
        site_b.release_local_ref("B1")

        ref = site_b.refs["crash-ref"]
        ref.lease_expiry = time.time() - 1.0
        expired_count = site_b.collect_expired_refs()

        obj = site_b.objects["B1"]
        assert expired_count == 1
        assert ref.alive is False
        assert ref.expired_at is not None
        assert obj.rc == 0
        assert obj.local_rc == 0
        assert obj.deleted is True
        assert site_b.db.count_leaked() == 0
    finally:
        site_b.stop()

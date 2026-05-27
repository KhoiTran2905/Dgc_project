"""
Demo Multiple Sites:
  Site A và Site C cùng giữ refs đến objects ở Site B.
  Site A crash → B1 vẫn phải sống vì C còn giữ.
  Site C crash → B1 mới được collect.
"""
import time, sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dgc.database import DGCDatabase
from dgc.site_b import SiteB
from dgc.site_a import SiteA

logging.getLogger("SiteB").setLevel(logging.WARNING)
logging.getLogger("SiteA").setLevel(logging.WARNING)


def demo_multi_site():
    print("="*60)
    print("MULTIPLE SITES — A và C cùng giữ refs đến B")
    print("="*60)

    db = DGCDatabase(db_name="dgc_multisite")
    db.clear_all()

    site_b = SiteB(db, lease_duration=10.0)
    site_a = SiteA("A", site_b)   # Site A
    site_c = SiteA("C", site_b)   # Site C — thêm 1 site nữa

    # Tạo objects
    for i in range(1, 5):
        site_b.create_object(f"B{i}")

    # A và C cùng giữ B1
    ref_a_b1 = site_a.grab_ref("A1", "B1")
    ref_c_b1 = site_c.grab_ref("C1", "B1")   # B1 có RC=2

    # Chỉ A giữ B2, chỉ C giữ B3
    ref_a_b2 = site_a.grab_ref("A1", "B2")
    ref_c_b3 = site_c.grab_ref("C1", "B3")

    # Release local refs
    for i in range(1, 5):
        site_b.release_local_ref(f"B{i}")
    time.sleep(0.3)

    print("\n[STATE] Ban đầu — A và C cùng active:")
    site_b.print_status()

    # Site A crash
    print("\n[ACTION] Site A CRASH!")
    print("  B1 vẫn phải sống (C còn giữ)")
    print("  B2 phải bị collect (chỉ A giữ)")
    site_a.crash()

    print(f"  Chờ lease expire (10s)...")
    for i in range(13, 0, -1):
        print(f"\r  {i}s...", end="", flush=True)
        time.sleep(1)
    print()

    print("\n[STATE] Sau khi Site A crash:")
    site_b.print_status()

    with site_b.lock:
        b1 = site_b.objects.get("B1")
        b2 = site_b.objects.get("B2")
        print(f"\n  B1 deleted={b1.deleted} (expect: False — C còn giữ)")
        print(f"  B2 deleted={b2.deleted} (expect: True  — chỉ A giữ)")

    # Site C crash
    print("\n[ACTION] Site C CRASH!")
    print("  B1 và B3 phải bị collect")
    site_c.crash()

    print(f"  Chờ lease expire (10s)...")
    for i in range(13, 0, -1):
        print(f"\r  {i}s...", end="", flush=True)
        time.sleep(1)
    print()

    print("\n[STATE] Sau khi Site C crash:")
    site_b.print_status()

    site_b.stop()
    db.client.drop_database("dgc_multisite")


def experiment_multi_site_metrics():
    """
    Đo metric: với N sites, crash từng site một.
    Kiểm tra không có false deletion nào xảy ra.
    """
    print("\n" + "="*60)
    print("EXPERIMENT: Multiple Sites — False Deletion Test")
    print("="*60)

    results = []
    for n_sites in [2, 3, 4, 5]:
        db = DGCDatabase(db_name=f"dgc_ms_{n_sites}")
        db.clear_all()
        site_b = SiteB(db, lease_duration=8.0)

        # Tạo N sites
        sites = [SiteA(f"S{i}", site_b) for i in range(n_sites)]

        # Tạo 1 object được giữ bởi TẤT CẢ sites
        site_b.create_object("SharedObj")
        refs = []
        for i, site in enumerate(sites):
            ref_id = site.grab_ref(f"S{i}obj", "SharedObj")
            if ref_id:
                refs.append((site, ref_id))
        site_b.release_local_ref("SharedObj")
        time.sleep(0.2)

        false_deletes = 0

        # Crash từng site một, chờ lease expire
        for idx, (site, ref_id) in enumerate(refs[:-1]):
            site.crash()
            time.sleep(10)  # Chờ lease expire

            # Kiểm tra SharedObj vẫn còn sống
            with site_b.lock:
                obj = site_b.objects.get("SharedObj")
                if obj and obj.deleted:
                    false_deletes += 1
                    print(f"  ✗ FALSE DELETE after site {idx} crash!")

        # Crash site cuối → lúc này mới được collect
        refs[-1][0].crash()
        time.sleep(12)

        with site_b.lock:
            obj = site_b.objects.get("SharedObj")
            final_deleted = obj.deleted if obj else False

        result = {
            "n_sites": n_sites,
            "false_deletes": false_deletes,
            "final_collected": final_deleted,
        }
        results.append(result)

        print(f"  Sites={n_sites}: false_delete={false_deletes}, "
              f"final_collected={final_deleted}")

        site_b.stop()
        db.client.drop_database(f"dgc_ms_{n_sites}")

    print("\n  SUMMARY:")
    print(f"  {'Sites':<8} {'False Delete':<15} {'Final Collected'}")
    print("  " + "-"*35)
    for r in results:
        ok = "✓" if r['final_collected'] and r['false_deletes'] == 0 else "✗"
        print(f"  {r['n_sites']:<8} {r['false_deletes']:<15} {r['final_collected']} {ok}")


if __name__ == "__main__":
    demo_multi_site()
    experiment_multi_site_metrics()
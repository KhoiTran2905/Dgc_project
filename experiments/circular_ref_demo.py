"""
Demo Circular Reference Problem trong DGC.

Tình huống:
  B1 → B2 → B1 (vòng tròn)
  Không ai từ bên ngoài giữ B1 hay B2 nữa
  → RC của cả 2 vẫn = 1 mãi mãi
  → Memory leak vĩnh viễn, GC không thể phát hiện
"""
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dgc.database import DGCDatabase
from dgc.site_b import SiteB
from dgc.site_a import SiteA


def demo_circular_leak():
    print("="*60)
    print("CIRCULAR REFERENCE — Memory Leak Demo")
    print("="*60)

    db = DGCDatabase(db_name="dgc_circular")
    db.clear_all()
    site_b = SiteB(db, lease_duration=10.0)
    site_a = SiteA("A", site_b)

    # Tạo 4 objects
    for i in range(1, 5):
        site_b.create_object(f"B{i}")

    # Site A giữ B1 và B3
    ref_b1 = site_a.grab_ref("A1", "B1")
    ref_b3 = site_a.grab_ref("A1", "B3")

    # Tạo circular: B1 ↔ B2
    # Dùng add_remote_ref trực tiếp để simulate B1 giữ B2 và ngược lại
    site_b.add_remote_ref("circ-1", "B1", "B1obj", "B2")  # B1 → B2
    site_b.add_remote_ref("circ-2", "B2", "B2obj", "B1")  # B2 → B1

    # Release local refs của tất cả objects
    for i in range(1, 5):
        site_b.release_local_ref(f"B{i}")
    time.sleep(0.3)

    print("\n[STATE] Sau khi tạo circular B1↔B2:")
    site_b.print_status()

    # Site A release refs đến B1 và B3
    print("\n[ACTION] Site A release refs đến B1 và B3...")
    site_a.release_ref(ref_b1)
    site_a.release_ref(ref_b3)
    time.sleep(0.5)

    print("\n[STATE] Sau khi Site A release:")
    print("  B1: vẫn RC=1 (B2 giữ) → LEAK")
    print("  B2: vẫn RC=1 (B1 giữ) → LEAK")
    print("  B3: RC=0, local=0 → đã được collect")
    print("  B4: RC=0, local=0 → đã được collect")
    site_b.print_status()

    # Chờ 15s — GC daemon có detect được không?
    print("\n[WAIT] Chờ 15s — GC daemon có phát hiện circular leak không?")
    time.sleep(15)

    print("\n[STATE] Sau 15s chờ GC:")
    site_b.print_status()

    # Đếm leaked
    with site_b.lock:
        leaked = [o for o in site_b.objects.values()
                  if not o.deleted and o.total_rc > 0]

    print(f"\n[RESULT] Leaked objects: {len(leaked)}")
    for obj in leaked:
        print(f"  {obj.obj_id}: RC={obj.total_rc} — LEAKED (circular ref)")

    print("\n[CONCLUSION]")
    print("  Reference Counting KHÔNG thể giải quyết circular reference.")
    print("  Cần dùng Mark-and-Sweep hoặc Tracing GC để xử lý.")
    print("  Đây là trade-off của thuật toán lease-based DGC.")

    site_b.stop()
    db.client.drop_database("dgc_circular")


def demo_circular_vs_normal():
    """So sánh normal GC vs circular để thấy rõ sự khác biệt."""
    print("\n" + "="*60)
    print("SO SÁNH: Normal GC vs Circular Reference")
    print("="*60)

    # Normal case
    db1 = DGCDatabase(db_name="dgc_normal_case")
    db1.clear_all()
    b1 = SiteB(db1, lease_duration=5.0)
    a1 = SiteA("A", b1)

    b1.create_object("N1")
    b1.create_object("N2")
    r1 = a1.grab_ref("A1", "N1")
    r2 = a1.grab_ref("A1", "N2")
    b1.release_local_ref("N1")
    b1.release_local_ref("N2")
    time.sleep(0.2)
    a1.release_ref(r1)
    a1.release_ref(r2)
    time.sleep(0.5)

    normal_leaked = sum(1 for o in b1.objects.values()
                        if not o.deleted and o.total_rc == 0)
    normal_collected = sum(1 for o in b1.objects.values() if o.deleted)
    print(f"\n  Normal case:   collected={normal_collected}, leaked={normal_leaked}")
    b1.stop()
    db1.client.drop_database("dgc_normal_case")

    # Circular case
    db2 = DGCDatabase(db_name="dgc_circular_case")
    db2.clear_all()
    b2 = SiteB(db2, lease_duration=5.0)

    b2.create_object("C1")
    b2.create_object("C2")
    b2.add_remote_ref("c-ref-1", "C1", "C1obj", "C2")
    b2.add_remote_ref("c-ref-2", "C2", "C2obj", "C1")
    b2.release_local_ref("C1")
    b2.release_local_ref("C2")
    time.sleep(8)  # Chờ GC scan nhiều lần

    circ_leaked = sum(1 for o in b2.objects.values()
                      if not o.deleted)
    circ_collected = sum(1 for o in b2.objects.values() if o.deleted)
    print(f"  Circular case: collected={circ_collected}, "
          f"leaked={circ_leaked} ← KHÔNG THỂ COLLECT")

    print(f"\n  → Circular reference gây leak {circ_leaked} objects")
    print(f"     mà standard RC-based GC KHÔNG phát hiện được.")

    b2.stop()
    db2.client.drop_database("dgc_circular_case")


if __name__ == "__main__":
    import logging
    logging.getLogger("SiteB").setLevel(logging.WARNING)
    logging.getLogger("SiteA").setLevel(logging.WARNING)

    demo_circular_leak()
    demo_circular_vs_normal()
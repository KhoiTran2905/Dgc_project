# demo_graph.py
"""
Chạy file này để xem graph visualization trực quan.
Hiển thị 3 snapshot: trước crash, ngay sau crash, sau lease expire.
"""
import time
import os
from dgc.database import DGCDatabase
from dgc.site_b import SiteB
from dgc.site_a import SiteA
from dgc.types import DGCObject
from graph.visualizer import draw_graph, draw_experiment_chart

os.makedirs("output", exist_ok=True)


def make_a_objects(site_a):
    """Tạo fake DGCObject cho Site A để vẽ graph."""
    return {
        f"A{i}": DGCObject(f"A{i}", "A")
        for i in range(1, 4)
    }


def snapshot(site_a_objs, site_b, title, save_path):
    with site_b.lock:
        all_objs = {**site_a_objs, **site_b.objects}
        all_refs = dict(site_b.refs)
    draw_graph(all_objs, all_refs, title=title, save_path=save_path)


def main():
    db = DGCDatabase()
    db.clear_all()

    site_b = SiteB(db, lease_duration=10.0)
    site_a = SiteA("A", site_b)
    a_objs = make_a_objects(site_a)

    # Tạo objects
    for i in range(1, 7):
        site_b.create_object(f"B{i}")

    # Grab refs TRƯỚC
    ref1 = site_a.grab_ref("A1", "B1")
    ref2 = site_a.grab_ref("A1", "B2")
    ref3 = site_a.grab_ref("A2", "B3")
    ref4 = site_a.grab_ref("A2", "B4")

    # Release local refs SAU — để objects chỉ sống nhờ remote refs
    for i in range(1, 7):
        site_b.release_local_ref(f"B{i}")
    time.sleep(0.5)   # Chờ GC collect B5, B6 ngay

    # ── Snapshot 1: Hệ thống đang hoạt động bình thường ──
    print("\n[1] Snapshot: System running normally...")
    snapshot(a_objs, site_b,
             title="State 1: System Running — Site A holds refs to B1-B4",
             save_path="output/state1_running.png")

    # Site A release 1 ref
    site_a.release_ref(ref1)
    time.sleep(0.3)

    # ── Snapshot 2: Sau khi release B1 ──
    print("[2] Snapshot: After Site A releases ref to B1...")
    snapshot(a_objs, site_b,
             title="State 2: After explicit release of B1",
             save_path="output/state2_release.png")

    # Crash
    print("[3] Site A crashes! Waiting for lease to expire...")
    site_a.crash()

    for i in range(13, 0, -1):
        print(f"\r    {i}s...", end="", flush=True)
        time.sleep(1)
    print()

    # ── Snapshot 3: Sau khi crash và GC chạy ──
    print("[4] Snapshot: After crash + GC collected...")
    snapshot(a_objs, site_b,
             title="State 3: After Site A crash — GC collected B2,B3,B4",
             save_path="output/state3_after_gc.png")

    # ── Vẽ chart experiment ──
    print("\n[5] Drawing experiment chart...")
    sample_results = [
        {"lease_duration": 5,  "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
        {"lease_duration": 8,  "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
        {"lease_duration": 10, "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
        {"lease_duration": 15, "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
        {"lease_duration": 20, "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
        {"lease_duration": 30, "leaked": 0, "false_deletes": 0, "correctly_collected": 10},
    ]
    draw_experiment_chart(
        sample_results,
        x_key="lease_duration",
        x_label="Lease Duration (seconds)",
        title="Experiment 1: Effect of Lease Duration on GC Correctness",
        save_path="output/chart_exp1.png"
    )

    site_b.stop()
    print("\n✓ Done! Check folder 'output/' for all saved images.")


if __name__ == "__main__":
    main()
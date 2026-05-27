import time
import logging
from dgc.database import DGCDatabase
from dgc.site_b import SiteB
from dgc.site_a import SiteA

def main():
    print("\n" + "="*55)
    print("  DISTRIBUTED GC SIMULATION")
    print("="*55)

    db = DGCDatabase()
    db.clear_all()

    site_b = SiteB(db, lease_duration=10.0)
    site_a = SiteA("A", site_b)

    # Tao 5 objects o Site B
    print("\n[1] Creating 5 objects at Site B...")
    for i in range(1, 6):
        site_b.create_object(f"B{i}")
    site_b.print_status()

    # Site A grab refs
    print("\n[2] Site A grabs references to B1, B2, B3...")
    ref1 = site_a.grab_ref("A1", "B1")
    ref2 = site_a.grab_ref("A1", "B2")
    ref3 = site_a.grab_ref("A2", "B3")
    time.sleep(0.5)
    site_b.print_status()

    # Happy path: B4, B5 khong co ref → local=0 → collect
    print("\n[3] Releasing local refs on B4, B5 (no remote refs)...")
    site_b.release_local_ref("B4")
    site_b.release_local_ref("B5")
    time.sleep(0.5)
    site_b.print_status()

    # Site A release ref1 (B1)
    print("\n[4] Site A explicitly releases ref to B1...")
    site_a.release_ref(ref1)
    time.sleep(0.5)
    site_b.print_status()

    # CRASH
    print("\n[5] ⚡ Site A CRASHES! (B2, B3 still held)")
    print("    Waiting 13s for lease to expire...\n")
    site_a.crash()
    for i in range(13, 0, -1):
        print(f"\r    {i}s remaining...", end="", flush=True)
        time.sleep(1)
    print("\n")

    # Ket qua sau crash
    print("[6] After lease expiry — GC results:")
    site_b.print_status()

    # MongoDB stats
    print("\n[MONGODB STATS]")
    print(f"  Collected: {db.count_collected()}")
    print(f"  Leaked:    {db.count_leaked()}")
    print(f"  Summary:   {db.get_summary()}")
    print(f"  Events:    {db.get_event_counts()}")

    site_b.stop()
    print("\n✓ Done! Open MongoDB Compass to see the data.")

if __name__ == "__main__":
    main()
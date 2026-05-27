import time
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dgc.database import DGCDatabase
from dgc.site_b import SiteB
from dgc.site_a import SiteA


def run_one_scenario(lease_duration, crash_after, n_objects, n_refs, db_name=None):
    if db_name is None:
        db_name = f"dgc_exp_{int(time.time()*1000)}"

    db = DGCDatabase(db_name=db_name)
    db.clear_all()

    site_b = SiteB(db, lease_duration=lease_duration)
    site_a = SiteA("A", site_b)

    # Tạo objects — local_rc=1 mặc định
    for i in range(n_objects):
        site_b.create_object(f"B{i}")

    # Site A grab refs TRƯỚC khi release local
    refs_grabbed = []
    objs_with_remote_ref = set()
    for i in range(n_refs):
        target = f"B{random.randint(0, n_objects - 1)}"
        ref_id = site_a.grab_ref(f"A{i}", target)
        if ref_id:
            refs_grabbed.append(ref_id)
            objs_with_remote_ref.add(target)

    # Sau khi grab xong, release local ref của TẤT CẢ objects
    # → objects chỉ còn tồn tại nhờ remote refs từ Site A
    for i in range(n_objects):
        site_b.release_local_ref(f"B{i}")

    # Chờ GC daemon quét xong objects không có ref nào
    time.sleep(0.5)

    # Crash Site A
    time.sleep(crash_after)
    site_a.crash()

    # Chờ lease expire + buffer
    time.sleep(lease_duration + 4.0)

    # Đánh giá
    leaked = 0
    false_deletes = 0
    correctly_collected = 0

    with site_b.lock:
        for obj_id, obj in site_b.objects.items():
            has_remote_ref = obj_id in objs_with_remote_ref

            if has_remote_ref:
                # Được giữ bởi Site A → phải bị collect sau crash + lease expire
                if obj.deleted:
                    correctly_collected += 1
                else:
                    leaked += 1
            else:
                # Không có remote ref, local đã release → phải bị collect ngay
                if obj.deleted:
                    correctly_collected += 1
                else:
                    leaked += 1

    result = {
        "lease_duration": lease_duration,
        "crash_after": crash_after,
        "n_objects": n_objects,
        "n_refs": n_refs,
        "leaked": leaked,
        "false_deletes": false_deletes,
        "correctly_collected": correctly_collected,
        "total_events": db.get_event_counts(),
    }

    site_b.stop()
    db.client.drop_database(db_name)
    return result


def print_table(headers, rows):
    widths = [max(len(str(r[i])) for r in rows + [headers])
              for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 2 * len(widths)))
    for row in rows:
        print(fmt.format(*row))


# ── Thí nghiệm 1: Lease duration ──────────────────────────────────────────────

def experiment_1():
    print("\n" + "="*60)
    print("EXPERIMENT 1: Lease Duration Impact")
    print("Fix: crash_after=2s | n_objects=10 | n_refs=5")
    print("Thay đổi: lease_duration từ 5s đến 30s")
    print("="*60)

    rows = []
    for lease in [5, 8, 10, 15, 20, 30]:
        print(f"  Running lease={lease}s ...", end=" ", flush=True)
        r = run_one_scenario(
            lease_duration=lease,
            crash_after=2.0,
            n_objects=10,
            n_refs=5
        )
        row = (lease, r["leaked"], r["false_deletes"], r["correctly_collected"])
        rows.append(row)
        print(f"leaked={r['leaked']} false={r['false_deletes']} collected={r['correctly_collected']}")

    print()
    print_table(["Lease(s)", "Leaked", "False Delete", "Collected"], rows)
    return rows


# ── Thí nghiệm 2: Crash timing ────────────────────────────────────────────────

def experiment_2():
    print("\n" + "="*60)
    print("EXPERIMENT 2: Crash Timing Impact")
    print("Fix: lease=10s | n_objects=10 | n_refs=5")
    print("Thay đổi: crash_after từ 0s đến 12s")
    print("="*60)

    rows = []
    for crash_t in [0, 1, 3, 5, 8, 12]:
        print(f"  Running crash_after={crash_t}s ...", end=" ", flush=True)
        r = run_one_scenario(
            lease_duration=10.0,
            crash_after=crash_t,
            n_objects=10,
            n_refs=5
        )
        row = (crash_t, r["leaked"], r["false_deletes"], r["correctly_collected"])
        rows.append(row)
        print(f"leaked={r['leaked']} false={r['false_deletes']} collected={r['correctly_collected']}")

    print()
    print_table(["Crash at(s)", "Leaked", "False Delete", "Collected"], rows)
    return rows


# ── Thí nghiệm 3: Scale ───────────────────────────────────────────────────────

def experiment_3():
    print("\n" + "="*60)
    print("EXPERIMENT 3: Scale Impact")
    print("Fix: lease=10s | crash_after=2s")
    print("Thay đổi: số objects và refs tăng dần")
    print("="*60)

    configs = [(5,2), (10,5), (20,10), (50,20), (100,40)]
    rows = []
    for n_obj, n_ref in configs:
        print(f"  Running objects={n_obj} refs={n_ref} ...", end=" ", flush=True)
        r = run_one_scenario(
            lease_duration=10.0,
            crash_after=2.0,
            n_objects=n_obj,
            n_refs=n_ref
        )
        row = (n_obj, n_ref, r["leaked"], r["false_deletes"], r["correctly_collected"])
        rows.append(row)
        print(f"leaked={r['leaked']} false={r['false_deletes']} collected={r['correctly_collected']}")

    print()
    print_table(["Objects", "Refs", "Leaked", "False Delete", "Collected"], rows)
    return rows


# ── Thí nghiệm 4: Stress test ─────────────────────────────────────────────────

def experiment_4(n_runs=20):
    print("\n" + "="*60)
    print(f"EXPERIMENT 4: Stress Test ({n_runs} runs, random params)")
    print("="*60)

    total_leaked = 0
    total_false = 0
    total_collected = 0
    runs_with_leak = 0
    runs_with_false = 0

    for i in range(n_runs):
        lease  = random.uniform(8, 15)
        crash  = random.uniform(0, 5)
        n_obj  = random.randint(5, 15)
        n_ref  = random.randint(2, 8)
        r = run_one_scenario(lease, crash, n_obj, n_ref)

        total_leaked    += r["leaked"]
        total_false     += r["false_deletes"]
        total_collected += r["correctly_collected"]
        if r["leaked"] > 0:       runs_with_leak  += 1
        if r["false_deletes"] > 0: runs_with_false += 1

        print(f"\r  Progress: {i+1}/{n_runs} | "
              f"leaks so far: {runs_with_leak} | "
              f"false_del: {runs_with_false}", end="", flush=True)

    print(f"\n\n  ── STRESS TEST RESULTS ──")
    print(f"  Total runs:         {n_runs}")
    print(f"  Leak rate:          {runs_with_leak/n_runs:.1%}  ({runs_with_leak}/{n_runs})")
    print(f"  False delete rate:  {runs_with_false/n_runs:.1%}  ({runs_with_false}/{n_runs})")
    print(f"  Avg leaked/run:     {total_leaked/n_runs:.2f}")
    print(f"  Avg collected/run:  {total_collected/n_runs:.2f}")

    return {
        "n_runs": n_runs,
        "leak_rate": runs_with_leak / n_runs,
        "false_delete_rate": runs_with_false / n_runs,
        "avg_leaked": total_leaked / n_runs,
        "avg_collected": total_collected / n_runs,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    # Tắt log INFO khi chạy experiment cho đỡ rối
    logging.getLogger("SiteB").setLevel(logging.WARNING)
    logging.getLogger("SiteA").setLevel(logging.WARNING)
    logging.getLogger("DB").setLevel(logging.WARNING)

    print("DGC Experiments — bắt đầu chạy")
    print("Lưu ý: mỗi scenario chờ lease expire nên sẽ mất vài phút\n")

    r1 = experiment_1()
    r2 = experiment_2()
    r3 = experiment_3()
    r4 = experiment_4(n_runs=20)

    print("\n\n✓ Tất cả thí nghiệm hoàn thành!")
    print("  Copy các bảng số liệu trên vào báo cáo.")
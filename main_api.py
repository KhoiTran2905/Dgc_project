# main_api.py
import time
import logging
from api.site_a_http import SiteAHttp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    print("\n" + "="*50)
    print("  TEST REST API — Site A → HTTP → Site B")
    print("="*50)

    site_a = SiteAHttp("A")

    print("\n[1] Grab refs...")
    ref1 = site_a.grab_ref("A1", "B1")
    ref2 = site_a.grab_ref("A1", "B2")
    ref3 = site_a.grab_ref("A2", "B3")
    time.sleep(1)

    print("\n[2] Release ref đến B1...")
    site_a.release_ref(ref1)
    time.sleep(1)

    print("\n[3] Crash Site A — chờ 13s...")
    site_a.crash()
    for i in range(13, 0, -1):
        print(f"\r    {i}s...", end="", flush=True)
        time.sleep(1)

    print("\n\n✓ Xem kết quả tại:")
    print("  http://localhost:8000/objects")
    print("  http://localhost:8000/stats")
    print("  http://localhost:8000/docs")

if __name__ == "__main__":
    main()
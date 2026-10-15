import threading
import time
import requests

host = "http://localhost:8001"
urls = ['/block', '/nonblock', '/thread']

def get(url):
    t1 = time.time()
    r = requests.get(host + url)
    print(f"{url}: {time.time() - t1:.2f} s -> {r.json()}")

for u in urls:
    threads = [threading.Thread(target=get, args=(u,)) for _ in range(3)]
    t1 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()  # chờ cả 3 request xong, giống `wait` trong bash
    print(f"Tổng thời gian {u}: {time.time() - t1:.2f} s\n")


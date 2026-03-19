#!/usr/bin/env python3
"""
Safe CPU + Memory stress for a pod
- Memory: 50% of available memory (within cgroup limits)
- CPU: ~50% per core
- Duration configurable
"""

import threading
import time
import os

# ===== CONFIGURATION =====
CPU_LOAD = 0.5    # CPU load per core (0.0 to 1.0)
DURATION = 60     # Duration in seconds
MEMORY_FRACTION = 0.5  # Fraction of available memory to allocate
# =========================

# Determine safe memory limit (cgroup v1 and v2)
def get_memory_limit_bytes():
    try:
        # cgroup v1
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            limit = int(f.read().strip())
            # if unlimited, return physical memory
            if limit > 1 << 60:
                limit = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
            return limit
    except FileNotFoundError:
        # cgroup v2
        try:
            with open("/sys/fs/cgroup/memory.max") as f:
                limit = f.read().strip()
                if limit == "max":
                    limit = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
                else:
                    limit = int(limit)
                return limit
        except Exception:
            # fallback to physical memory
            return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')

# Allocate memory safely
mem_limit = get_memory_limit_bytes()
mem_to_allocate = int(mem_limit * MEMORY_FRACTION)
print(f"Allocating {mem_to_allocate / (1024*1024):.1f} MB of memory (50% of limit)...")
memory_block = bytearray(mem_to_allocate)
print("Memory allocated.")

# CPU worker
def cpu_worker(load: float):
    interval = 0.1
    while True:
        start = time.time()
        while (time.time() - start) < load * interval:
            pass
        time.sleep(interval * (1 - load))

# Start CPU threads
threads = []
for _ in range(os.cpu_count()):
    t = threading.Thread(target=cpu_worker, args=(CPU_LOAD,))
    t.daemon = True
    t.start()
    threads.append(t)

# Run
print(f"Stressing CPU and memory for {DURATION} seconds...")
time.sleep(DURATION)
print("Stress finished.")


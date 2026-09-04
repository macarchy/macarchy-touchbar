import sys
import time


def log(*a):
    print(f"[macarchy-touchbar {time.strftime('%H:%M:%S')}]", *a, file=sys.stderr, flush=True)

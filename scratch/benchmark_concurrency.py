"""
benchmark_concurrency.py — Hardware Concurrency & Memory Benchmark for LearnForge on Jetson Orin.
Simulates dual-stream concurrent requests to Ollama (Flashcards + Quiz) to measure latency and VRAM/RAM overhead.

Usage:
  python scratch/benchmark_concurrency.py
"""
import time
import requests
import json
from concurrent.futures import ThreadPoolExecutor

OLLAMA_URL = "http://localhost:11434/api/generate"
TEST_PROMPT = """You are an expert tutor. Given this text excerpt:
"Stack memory allocation is handled automatically by the CPU architecture using the stack pointer register. It is extremely fast with LIFO ordering."
Generate 3 active recall flashcards in JSON format with question, answer, type, and hint."""

def run_single_request(thread_id: int):
    start = time.time()
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": "llama3.2:1b",
                "prompt": f"[Thread {thread_id}] {TEST_PROMPT}",
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 4096,
                }
            },
            timeout=30.0
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            print(f"[Thread {thread_id}] Success in {elapsed:.2f}s | Response length: {len(resp.json().get('response', ''))} chars")
            return elapsed, True
        else:
            print(f"[Thread {thread_id}] HTTP {resp.status_code} in {elapsed:.2f}s")
            return elapsed, False
    except Exception as e:
        elapsed = time.time() - start
        print(f"[Thread {thread_id}] Error: {e} in {elapsed:.2f}s")
        return elapsed, False

def benchmark_concurrency(num_workers: int = 2):
    print("=" * 60)
    print(f"Starting LearnForge Concurrency Benchmark ({num_workers} parallel requests)...")
    print("Check memory on Jetson in another terminal with: sudo tegrastats | grep -i ram")
    print("=" * 60)

    start_total = time.time()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(run_single_request, i+1) for i in range(num_workers)]
        results = [f.result() for f in futures]

    total_time = time.time() - start_total
    success_count = sum(1 for _, ok in results if ok)
    avg_latency = sum(t for t, _ in results) / len(results) if results else 0

    print("=" * 60)
    print(f"Benchmark Complete:")
    print(f"  Total Wall-Clock Time: {total_time:.2f}s")
    print(f"  Average Request Time : {avg_latency:.2f}s")
    print(f"  Success Rate         : {success_count}/{num_workers} ({success_count/num_workers*100:.0f}%)")
    print("=" * 60)

if __name__ == "__main__":
    benchmark_concurrency(num_workers=2)

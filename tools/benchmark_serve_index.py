import asyncio
import time
from httpx import AsyncClient, ASGITransport
from app.server import app

async def run_benchmark(n_requests=2000, concurrency=50):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Warmup
        for _ in range(10):
            await client.get("/")

        start = time.perf_counter()
        sem = asyncio.Semaphore(concurrency)

        async def worker():
            async with sem:
                resp = await client.get("/")
                assert resp.status_code == 200

        tasks = [worker() for _ in range(n_requests)]
        await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - start
        rps = n_requests / elapsed
        avg_latency_ms = (elapsed / n_requests) * 1000
        print(f"Completed {n_requests} requests in {elapsed:.4f}s ({rps:.2f} req/s, avg latency {avg_latency_ms:.3f}ms)")
        return rps

if __name__ == "__main__":
    asyncio.run(run_benchmark())

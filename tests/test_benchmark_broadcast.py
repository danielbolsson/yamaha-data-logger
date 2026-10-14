import time
import asyncio
import pytest


class MockWebSocket:
    def __init__(self, client_id: int, delay: float = 0.001, fail: bool = False):
        self.client_id = client_id
        self.delay = delay
        self.fail = fail
        self.received = []

    async def send_text(self, text: str):
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError(f"Client {self.client_id} connection reset")
        self.received.append(text)


async def sequential_broadcast(websockets: set, message: str):
    disconnected_clients = set()
    for ws in list(websockets):
        try:
            await ws.send_text(message)
        except Exception:
            disconnected_clients.add(ws)

    for dead_ws in disconnected_clients:
        websockets.discard(dead_ws)


async def concurrent_broadcast(websockets: set, message: str):
    if not websockets:
        return

    clients = list(websockets)

    async def send_to_client(ws):
        try:
            await ws.send_text(message)
            return None
        except Exception:
            return ws

    results = await asyncio.gather(*[send_to_client(ws) for ws in clients], return_exceptions=True)

    for res in results:
        if res and not isinstance(res, Exception):
            websockets.discard(res)


@pytest.mark.anyio
async def test_broadcast_performance_benchmark():
    num_clients = 50
    delay_per_client = 0.001  # 1ms simulated network latency
    payload = '{"rpm": 3000, "status": "ok"}'

    # Sequential test setup
    seq_sockets = {MockWebSocket(i, delay=delay_per_client, fail=(i % 10 == 0)) for i in range(num_clients)}
    start_seq = time.perf_counter()
    await sequential_broadcast(seq_sockets, payload)
    seq_duration = time.perf_counter() - start_seq

    # Concurrent test setup
    conc_sockets = {MockWebSocket(i, delay=delay_per_client, fail=(i % 10 == 0)) for i in range(num_clients)}
    start_conc = time.perf_counter()
    await concurrent_broadcast(conc_sockets, payload)
    conc_duration = time.perf_counter() - start_conc

    # Disconnected cleanup verification: 5 failed out of 50 (0, 10, 20, 30, 40)
    assert len(seq_sockets) == 45
    assert len(conc_sockets) == 45

    speedup_pct = ((seq_duration - conc_duration) / seq_duration) * 100
    speedup_factor = seq_duration / conc_duration if conc_duration > 0 else 0

    print(f"\n--- Broadcast Benchmark ({num_clients} clients, {delay_per_client * 1000:.1f}ms latency/client) ---")
    print(f"Sequential Broadcast Time: {seq_duration * 1000:.2f} ms")
    print(f"Concurrent Broadcast Time: {conc_duration * 1000:.2f} ms")
    print(f"Latency Reduction:         {speedup_pct:.2f}% ({speedup_factor:.1f}x faster)")

    assert conc_duration < seq_duration


if __name__ == "__main__":
    asyncio.run(test_broadcast_performance_benchmark())

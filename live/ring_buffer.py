"""
live/ring_buffer.py — Thread-safe circular (ring) audio buffer for Phase 5 live pipeline.

Design:
- Fixed-capacity circular buffer backed by a pre-allocated numpy array.
- Single-producer / single-consumer (SPSC) design: sounddevice callback writes,
  inference thread reads. Uses a threading.Condition for blocking consumer.
- Capacity is set in samples at construction time. Overflow drops oldest samples
  (never blocks the audio callback — a late callback is worse than a dropped chunk).
- No dynamic allocation in the hot path.

Usage (producer / audio callback side):
    rb = RingBuffer(capacity_samples=96000, channels=1)
    rb.write(chunk_float32_ndarray)   # called from sounddevice callback

Usage (consumer / inference side):
    chunk = rb.read(chunk_size=4800, timeout=0.5)
    if chunk is not None:
        # process chunk...

Self-test:
    python live/ring_buffer.py
"""

import threading
import numpy as np
from typing import Optional


class RingBuffer:
    """
    Thread-safe circular audio buffer.

    Parameters
    ----------
    capacity_samples : int
        Maximum number of audio samples to store. Should be a multiple of
        chunk_samples for clean alignment, but is not required.
    channels : int
        Number of audio channels. Mono = 1.
    dtype : np.dtype
        Sample dtype. float32 by default (matches sounddevice and DeepFilterNet).
    """

    def __init__(self, capacity_samples: int, channels: int = 1, dtype=np.float32):
        if capacity_samples <= 0:
            raise ValueError(f"capacity_samples must be > 0, got {capacity_samples}")
        if channels <= 0:
            raise ValueError(f"channels must be > 0, got {channels}")

        self._capacity = capacity_samples
        self._channels = channels
        self._dtype = dtype

        # Pre-allocate storage: shape (capacity, channels)
        self._buf = np.zeros((capacity_samples, channels), dtype=dtype)
        self._write_pos = 0   # next slot to write into (exclusive)
        self._read_pos = 0    # next slot to read from (inclusive)
        self._available = 0   # number of valid samples currently stored

        # One lock + condition covers both read and write paths.
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

        # Overflow counter — incremented when write drops oldest samples.
        self.overflow_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, data: np.ndarray) -> None:
        """
        Write audio data into the ring buffer.

        Parameters
        ----------
        data : np.ndarray
            Shape (n_samples,) for mono or (n_samples, channels) for multi-channel.
            Will be cast to self._dtype automatically.

        Notes
        -----
        Called from the sounddevice audio callback.  NEVER blocks; if there is
        insufficient space, the oldest data is silently discarded (overflow) and
        the overflow_count counter is incremented.
        """
        data = np.asarray(data, dtype=self._dtype)
        if data.ndim == 1:
            data = data[:, np.newaxis]   # (n,) → (n, 1)
        if data.shape[1] != self._channels:
            raise ValueError(
                f"Channel mismatch: buffer has {self._channels} ch, "
                f"data has {data.shape[1]} ch"
            )

        n = data.shape[0]
        if n == 0:
            return
        if n > self._capacity:
            # Write only the most recent capacity samples.
            data = data[-self._capacity:]
            n = self._capacity

        with self._not_empty:
            free = self._capacity - self._available
            if n > free:
                # Drop oldest samples to make room (overflow).
                drop = n - free
                self._read_pos = (self._read_pos + drop) % self._capacity
                self._available -= drop
                self.overflow_count += 1

            # Write in one or two memcpy segments (handles wrap-around).
            space_to_end = self._capacity - self._write_pos
            if n <= space_to_end:
                self._buf[self._write_pos:self._write_pos + n] = data
            else:
                # Split across the end-of-buffer wrap.
                self._buf[self._write_pos:] = data[:space_to_end]
                self._buf[:n - space_to_end] = data[space_to_end:]

            self._write_pos = (self._write_pos + n) % self._capacity
            self._available += n
            self._not_empty.notify()

    def read(self, n_samples: int, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Read exactly n_samples from the ring buffer, blocking until available.

        Parameters
        ----------
        n_samples : int
            Number of samples to read.
        timeout : float
            Maximum seconds to wait for data. Returns None on timeout.

        Returns
        -------
        np.ndarray or None
            Shape (n_samples, channels), dtype=self._dtype, or None on timeout.
        """
        with self._not_empty:
            if not self._not_empty.wait_for(
                lambda: self._available >= n_samples, timeout=timeout
            ):
                return None  # Timed out.

            out = np.empty((n_samples, self._channels), dtype=self._dtype)
            space_to_end = self._capacity - self._read_pos
            if n_samples <= space_to_end:
                out[:] = self._buf[self._read_pos:self._read_pos + n_samples]
            else:
                out[:space_to_end] = self._buf[self._read_pos:]
                out[space_to_end:] = self._buf[:n_samples - space_to_end]

            self._read_pos = (self._read_pos + n_samples) % self._capacity
            self._available -= n_samples
            return out

    @property
    def available(self) -> int:
        """Number of samples currently available to read."""
        with self._lock:
            return self._available

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def channels(self) -> int:
        return self._channels

    def clear(self) -> None:
        """Discard all buffered data (e.g. after a pipeline reset)."""
        with self._not_empty:
            self._write_pos = 0
            self._read_pos = 0
            self._available = 0
            self._buf[:] = 0.0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    import sys

    print("RingBuffer self-test — start")

    # --- Test 1: basic write / read roundtrip ---
    rb = RingBuffer(capacity_samples=1024, channels=1)
    chunk = np.random.randn(256).astype(np.float32)
    rb.write(chunk)
    out = rb.read(256, timeout=0.5)
    assert out is not None, "read returned None"
    assert out.shape == (256, 1), f"shape mismatch: {out.shape}"
    np.testing.assert_allclose(out[:, 0], chunk, atol=1e-6)
    print("  [PASS] test 1: basic write/read roundtrip")

    # --- Test 2: wrap-around ---
    rb2 = RingBuffer(capacity_samples=100, channels=1)
    a = np.ones(80, dtype=np.float32) * 1.0
    b = np.ones(80, dtype=np.float32) * 2.0
    rb2.write(a)
    rb2.read(80, timeout=0.2)   # consume a
    rb2.write(b)                # this wraps around the internal buffer
    out2 = rb2.read(80, timeout=0.2)
    assert out2 is not None
    np.testing.assert_allclose(out2[:, 0], b, atol=1e-6)
    print("  [PASS] test 2: wrap-around write/read")

    # --- Test 3: overflow drops oldest ---
    rb3 = RingBuffer(capacity_samples=100, channels=1)
    old = np.zeros(80, dtype=np.float32)
    new_data = np.ones(80, dtype=np.float32) * 9.0
    rb3.write(old)
    rb3.write(new_data)   # should overflow, drop 60 oldest samples of `old`
    assert rb3.overflow_count == 1, f"overflow_count={rb3.overflow_count}"
    assert rb3.available == 100, f"available={rb3.available}"
    print(f"  [PASS] test 3: overflow drops oldest (overflow_count={rb3.overflow_count})")

    # --- Test 4: multi-channel ---
    rb4 = RingBuffer(capacity_samples=200, channels=2)
    stereo = np.random.randn(100, 2).astype(np.float32)
    rb4.write(stereo)
    out4 = rb4.read(100, timeout=0.2)
    assert out4.shape == (100, 2)
    np.testing.assert_allclose(out4, stereo, atol=1e-6)
    print("  [PASS] test 4: multi-channel roundtrip")

    # --- Test 5: threaded producer-consumer ---
    rb5 = RingBuffer(capacity_samples=48000 * 2, channels=1)
    reference = np.arange(4800, dtype=np.float32)
    received = []

    def producer():
        for _ in range(10):
            rb5.write(reference.copy())

    def consumer():
        for _ in range(10):
            chunk = rb5.read(4800, timeout=1.0)
            assert chunk is not None
            received.append(chunk.copy())

    t_prod = threading.Thread(target=producer)
    t_cons = threading.Thread(target=consumer)
    t_cons.start()
    t_prod.start()
    t_prod.join()
    t_cons.join()
    assert len(received) == 10
    for c in received:
        np.testing.assert_allclose(c[:, 0], reference, atol=1e-6)
    print("  [PASS] test 5: threaded producer-consumer (10 chunks)")

    # --- Test 6: timeout returns None ---
    rb6 = RingBuffer(capacity_samples=1000, channels=1)
    result = rb6.read(500, timeout=0.05)
    assert result is None, f"expected None on timeout, got {result}"
    print("  [PASS] test 6: timeout returns None")

    print("RingBuffer self-test — ALL PASSED")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())

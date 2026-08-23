import time
import torch

@torch.jit.script
def nlms_jit(d: torch.Tensor, x: torch.Tensor, L: int = 64, mu: float = 0.1, eps: float = 1e-6) -> torch.Tensor:
    N = d.shape[0]
    w = torch.zeros(L, dtype=torch.float32)
    e = torch.zeros(N, dtype=torch.float32)
    x_pad = torch.nn.functional.pad(x, (L - 1, 0))
    
    # We can do tap extraction inside the loop efficiently
    for n in range(N):
        # Slice taps from padded x
        x_n = x_pad[n : n + L].flip(0)
        y = torch.dot(w, x_n)
        err = d[n] - y
        e[n] = err
        pwr = torch.dot(x_n, x_n)
        w = w + (mu / (pwr + eps)) * err * x_n
    return e

if __name__ == "__main__":
    N = 144000
    d_t = torch.randn(N, dtype=torch.float32)
    x_t = torch.randn(N, dtype=torch.float32)

    # Warmup / compile JIT
    _ = nlms_jit(d_t[:1000], x_t[:1000])

    t0 = time.time()
    e_out = nlms_jit(d_t, x_t)
    elapsed = time.time() - t0
    print(f"PyTorch JIT compiled: {N} samples in {elapsed:.4f}s ({N/elapsed:.0f} samples/sec)")
    print(f"Extrapolated for 300 files: {elapsed * 300:.2f}s")

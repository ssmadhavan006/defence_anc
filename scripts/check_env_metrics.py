import sys
import torch

print("=== ENVIRONMENT & METRIC LIBRARIES CHECK ===")
cuda_available = torch.cuda.is_available()
print(f"PyTorch CUDA Available: {cuda_available}")
if cuda_available:
    print(f"Device Count: {torch.cuda.device_count()}")
    print(f"Device Name: {torch.cuda.get_device_name(0)}")

print("\n--- Inspecting PESQ Library ---")
try:
    import pesq
    print(f"pesq version / module: {pesq.__file__}")
    print(f"pesq functions/constants: {dir(pesq)}")

    # Test signature or help on pesq.pesq
    from pesq import pesq, pesq_batch
    import inspect
    print(f"pesq.pesq signature: {inspect.signature(pesq)}")
    print(f"pesq.pesq docstring excerpt:\n{pesq.__doc__[:300] if pesq.__doc__ else 'No docstring'}")
except Exception as e:
    print(f"pesq inspection error: {e}")

print("\n--- Inspecting PySTOI Library ---")
try:
    import pystoi
    print(f"pystoi version / module: {pystoi.__file__}")
    from pystoi import stoi
    import inspect
    print(f"pystoi.stoi signature: {inspect.signature(stoi)}")
    print(f"pystoi.stoi docstring excerpt:\n{stoi.__doc__[:300] if stoi.__doc__ else 'No docstring'}")
except Exception as e:
    print(f"pystoi inspection error: {e}")

print("\n--- Inspecting matplotlib / seaborn / pandas for charts ---")
for pkg in ["matplotlib", "seaborn", "pandas"]:
    try:
        mod = __import__(pkg)
        print(f"  {pkg}: installed ({mod.__file__})")
    except ImportError:
        print(f"  {pkg}: NOT INSTALLED")

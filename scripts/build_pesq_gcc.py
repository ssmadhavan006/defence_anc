import glob
import os
import sys
import sysconfig
import subprocess
import shutil
import urllib.request
import tarfile
import numpy as np


def _find_gcc() -> str:
    """
    Locate a usable gcc.exe. Checks PATH first, then falls back to scanning
    common WinGet/Chocolatey install locations. Deliberately does not
    hardcode a specific Windows user profile -- a prior version of this
    script hardcoded `C:/Users/Admin/...`, which only worked on the machine
    it was written on.
    """
    on_path = shutil.which("gcc")
    if on_path:
        return on_path

    search_roots = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
        "C:/ProgramData/chocolatey/lib",
        "C:/msys64",
        "C:/mingw64",
    ]
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        matches = glob.glob(os.path.join(root, "**", "gcc.exe"), recursive=True)
        if matches:
            return matches[0]

    raise FileNotFoundError(
        "No gcc.exe found on PATH or in common install locations. "
        "Install a MinGW-w64 toolchain first, e.g.: "
        "winget install --id BrechtSanders.WinLibs.POSIX.UCRT"
    )


def build_pesq_with_gcc():
    print("=== Building pesq with GCC ===")
    
    # 1. Download pesq source tar.gz from PyPI
    url = "https://github.com/ludlows/python-pesq/archive/refs/tags/v0.0.4.zip"
    build_dir = "results/pesq_build"
    zip_path = os.path.join(build_dir, "python-pesq-0.0.4.zip")

    os.makedirs(build_dir, exist_ok=True)
    if not os.path.exists(zip_path):
        print(f"Downloading {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
            out.write(resp.read())

    import zipfile
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(path=build_dir)

    pesq_src = os.path.join(build_dir, "PESQ-0.0.4", "pesq")
    print(f"PESQ source extracted to: {pesq_src}")

    # 2. Check if cython is installed
    try:
        import Cython
    except ImportError:
        print("Installing cython...")
        subprocess.run(["uv", "add", "cython"], check=True)

    # 3. Cythonize cypesq.pyx -> cypesq.c
    pyx_path = os.path.join(pesq_src, "cypesq.pyx")
    c_out = os.path.join(pesq_src, "cypesq.c")
    
    cmd_cython = ["uv", "run", "cython", "-3", pyx_path, "-o", c_out]
    print(f"Running: {' '.join(cmd_cython)}")
    subprocess.run(cmd_cython, check=True)

    gcc_bin = _find_gcc()
    print(f"Using gcc: {gcc_bin}")

    # Python include and DLL path for Windows
    py_include = os.path.join(sys.base_prefix, "include")
    py_libs = os.path.join(sys.base_prefix, "libs")
    numpy_include = np.get_include()

    c_files = [
        c_out,
        os.path.join(pesq_src, "dsp.c"),
        os.path.join(pesq_src, "pesqdsp.c"),
        os.path.join(pesq_src, "pesqmod.c"),
    ]
    site_pesq_dir = os.path.join(sys.prefix, "Lib", "site-packages", "pesq")
    os.makedirs(site_pesq_dir, exist_ok=True)

    # Build the .pyd filename from this interpreter's actual ABI tag
    # (e.g. cp311-win_amd64), instead of a hardcoded cp39 that only matches
    # a Python 3.9 environment.
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")  # e.g. ".cp311-win_amd64.pyd"
    pyd_out = os.path.join(site_pesq_dir, f"cypesq{ext_suffix}")

    version_tag = f"{sys.version_info.major}{sys.version_info.minor}"
    py_dll = os.path.join(sys.base_prefix, f"python{version_tag}.dll")
    if not os.path.exists(py_dll):
        raise FileNotFoundError(f"Expected Python DLL not found: {py_dll}")

    cmd_gcc = [
        gcc_bin, "-O3", "-shared",
        "-DMS_WIN64", "-DSIZEOF_VOID_P=8",
        "-I", pesq_src,
        "-I", py_include,
        "-I", numpy_include,
        py_dll,
        "-o", pyd_out,
    ] + c_files

    print(f"\nCompiling PESQ C extension with GCC:\n  {' '.join(cmd_gcc)}")
    res = subprocess.run(cmd_gcc, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"GCC Compilation stdout:\n{res.stdout}")
        print(f"GCC Compilation stderr:\n{res.stderr}")
        res.check_returncode()

    print(f"\nSuccessfully compiled PESQ C extension to: {pyd_out}")

    # 6. Copy pesq python package to site-packages
    site_pesq_dir = os.path.join(sys.prefix, "Lib", "site-packages", "pesq")
    os.makedirs(site_pesq_dir, exist_ok=True)
    shutil.copy(os.path.join(pesq_src, "__init__.py"), site_pesq_dir)
    shutil.copy(os.path.join(pesq_src, "_pesq.py"), site_pesq_dir)

    print("Successfully installed pesq package into virtualenv!")

if __name__ == "__main__":
    build_pesq_with_gcc()

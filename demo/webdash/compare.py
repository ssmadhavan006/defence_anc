"""
demo/webdash/compare.py — Dashboard Mode 3: classical-vs-AI method comparison.

Serves the judge a mixture picker and, for any mixture, all conditions side
by side (noisy input, each classical baseline, DeepFilterNet3) with their
AUDITED metrics straight from results/eval_raw.csv -- the same numbers
results/final/target_compliance.md reports. No runtime DSP, no new inference:
every WAV this module serves already exists on disk from the offline eval
run (eval/run_eval.py). This is what makes Mode 3 low-risk (see the
dashboard plan's D6): the classical-vs-AI story is told with numbers that
were already independently verified, not computed live under demo pressure.

Security note: mixture_id and method are user-supplied URL path segments.
They are used ONLY as dictionary keys into an index built at startup from
eval_raw.csv (a file this project generates, not user input) -- never
concatenated into a filesystem path. An unrecognised key is a 404, not a
path traversal opportunity.

Mounted at /compare by demo/webdash/app.py's make_app(compare_app=...).

Self-test (Mode A, no server):
    python demo/webdash/compare.py --self-test
    SKIPs if results/eval_raw.csv doesn't exist yet -- run the reproduction
    steps in docs/corpus_redefinition_v2.md §8 first.
"""

import argparse
import csv
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

DEFAULT_EVAL_RAW = os.path.join(_REPO_ROOT, "results", "eval_raw.csv")

# Preference order for "our model" -- prefer the deployed/tuned config
# (atten_lim_db=30, see config/audio_config.yaml) over the untuned default,
# falling back if a given mixture only has the untuned row.
_OUR_MODEL_PREFERENCE = ("deepfilternet_tuned", "deepfilternet")
_CLASSICAL_METHODS = ("noisy", "nlms", "spectral_subtraction", "wiener")

_METRIC_FIELDS = ("pesq_wb", "stoi", "si_snr", "delta_si_snr")


def _to_float_or_none(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_index(eval_raw_path: str = DEFAULT_EVAL_RAW) -> dict:
    """
    Parse eval_raw.csv into {mixture_id: {category, subtype, snr_db, methods:
    {method: {metrics..., output_path, clean_ref_path}}}}. Raises
    FileNotFoundError if eval_raw_path doesn't exist -- callers decide
    whether that's a SKIP (self-test) or a startup warning (make_compare_app).
    """
    if not os.path.exists(eval_raw_path):
        raise FileNotFoundError(eval_raw_path)

    index: dict = {}
    with open(eval_raw_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mid = row["mixture_id"]
            entry = index.setdefault(mid, {
                "category": row["category"],
                "subtype": row["subtype"],
                "snr_db": _to_float_or_none(row["snr_db"]),
                "methods": {},
            })
            method_row = {
                field: _to_float_or_none(row.get(field)) for field in _METRIC_FIELDS
            }
            method_row["output_path"] = os.path.normpath(row["output_path"])
            entry["methods"][row["method"]] = method_row
            # clean_ref_path is identical across every method row for a given
            # mixture_id -- stash it once at the mixture level too.
            entry.setdefault("clean_ref_path", os.path.normpath(row["clean_ref_path"]))

    return index


def _our_model_method(entry_methods: dict) -> str:
    for name in _OUR_MODEL_PREFERENCE:
        if name in entry_methods:
            return name
    # Fall back to any method not in the classical set (defensive -- should
    # not happen once the reproduction steps have been run in full).
    for name in entry_methods:
        if name not in _CLASSICAL_METHODS:
            return name
    return _OUR_MODEL_PREFERENCE[0]


def make_compare_app(eval_raw_path: str = DEFAULT_EVAL_RAW) -> "FastAPI":
    if not _FASTAPI_OK:
        raise ImportError("fastapi is required. Install: pip install fastapi uvicorn[standard]")

    index = build_index(eval_raw_path)   # raises FileNotFoundError if missing -- caller's problem
    app = FastAPI(title="PS26052 Comparison Mode", docs_url=None, redoc_url=None)

    @app.get("/mixtures")
    async def list_mixtures(category: str = None, subtype: str = None):
        out = []
        for mid, entry in index.items():
            if category and entry["category"] != category:
                continue
            if subtype and entry["subtype"] != subtype:
                continue
            out.append({
                "mixture_id": mid,
                "category": entry["category"],
                "subtype": entry["subtype"],
                "snr_db": entry["snr_db"],
                "our_model_method": _our_model_method(entry["methods"]),
            })
        out.sort(key=lambda r: (r["category"], r["subtype"], r["snr_db"], r["mixture_id"]))
        return {"count": len(out), "mixtures": out}

    @app.get("/metrics/{mixture_id}")
    async def metrics(mixture_id: str):
        entry = index.get(mixture_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown mixture_id {mixture_id!r}")
        our_model = _our_model_method(entry["methods"])
        methods_out = {}
        for name, m in entry["methods"].items():
            methods_out[name] = {k: m[k] for k in _METRIC_FIELDS}
        return {
            "mixture_id": mixture_id,
            "category": entry["category"],
            "subtype": entry["subtype"],
            "snr_db": entry["snr_db"],
            "our_model_method": our_model,
            "methods": methods_out,
        }

    @app.get("/audio/{mixture_id}/{method}")
    async def audio(mixture_id: str, method: str):
        entry = index.get(mixture_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown mixture_id {mixture_id!r}")
        if method == "clean":
            path = entry["clean_ref_path"]
        else:
            m = entry["methods"].get(method)
            if m is None:
                raise HTTPException(status_code=404,
                                     detail=f"no {method!r} output for mixture_id {mixture_id!r}")
            path = m["output_path"]
        abs_path = os.path.join(_REPO_ROOT, path) if not os.path.isabs(path) else path
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail=f"audio file missing on disk: {path}")
        return FileResponse(abs_path, media_type="audio/wav")

    return app


# ---------------------------------------------------------------------------
# Self-test (Mode A -- no server, SKIPs if eval_raw.csv is absent)
# ---------------------------------------------------------------------------
def _self_test():
    print("demo/webdash/compare.py self-test -- start")

    if not _FASTAPI_OK:
        print("[SKIP] fastapi not installed")
        sys.exit(0)

    try:
        from starlette.testclient import TestClient
    except ImportError:
        print("[SKIP] starlette.testclient not available (install httpx)")
        sys.exit(0)

    if not os.path.exists(DEFAULT_EVAL_RAW):
        print(f"[SKIP] {DEFAULT_EVAL_RAW} not found -- run the reproduction steps in "
              f"docs/corpus_redefinition_v2.md section 8 first.")
        sys.exit(0)

    index = build_index()
    assert len(index) > 0, "eval_raw.csv parsed to zero mixtures"
    n_methods = {len(e["methods"]) for e in index.values()}
    print(f"  [PASS] test 1: indexed {len(index)} mixtures, "
          f"{sorted(n_methods)} method(s) per mixture")

    # Every mixture must expose an "our model" method distinct from the
    # classical baselines -- this is the whole point of comparison mode.
    for mid, entry in index.items():
        m = _our_model_method(entry["methods"])
        assert m not in _CLASSICAL_METHODS, f"{mid}: resolved our-model method {m!r} is classical"
    print("  [PASS] test 2: every mixture resolves to a non-classical 'our model' method")

    app = make_compare_app()
    client = TestClient(app, raise_server_exceptions=True)

    r = client.get("/mixtures")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(index)
    sample_mid = body["mixtures"][0]["mixture_id"]
    print(f"  [PASS] test 3: /mixtures lists all {body['count']} mixtures "
          f"(sample: {sample_mid!r})")

    r = client.get("/metrics/" + sample_mid)
    assert r.status_code == 200
    m = r.json()
    assert "noisy" in m["methods"], "every mixture must have a 'noisy' (no processing) row"
    assert m["methods"][m["our_model_method"]]["si_snr"] is not None
    print(f"  [PASS] test 4: /metrics/{sample_mid} returns audited per-method metrics "
          f"(our_model_method={m['our_model_method']!r})")

    r = client.get("/audio/" + sample_mid + "/noisy")
    assert r.status_code == 200, f"expected 200 serving real audio, got {r.status_code}"
    assert r.headers["content-type"] == "audio/wav"
    print("  [PASS] test 5: /audio serves an existing WAV with the right content-type")

    r = client.get("/audio/" + sample_mid + "/not_a_real_method")
    assert r.status_code == 404
    r = client.get("/metrics/not_a_real_mixture_id")
    assert r.status_code == 404
    print("  [PASS] test 6: unknown method/mixture_id -> 404, not a path-traversal or crash")

    print("demo/webdash/compare.py self-test -- ALL PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    else:
        print("This module is a library. Use --self-test or import make_compare_app.")

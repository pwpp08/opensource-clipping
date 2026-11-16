import importlib.util
import os

# Compatibility guard: older PyAV builds lack `metadata_errors` in av.open()
try:
    import av as _av
    if not getattr(_av.open, "_is_compat_wrapped", False):
        _orig_av_open = _av.open
        def _compat_av_open(*args, **kwargs):
            try:
                return _orig_av_open(*args, **kwargs)
            except TypeError as _err:
                if "metadata_errors" in str(_err) and "metadata_errors" in kwargs:
                    kwargs.pop("metadata_errors", None)
                    return _orig_av_open(*args, **kwargs)
                raise
        _compat_av_open._is_compat_wrapped = True
        _av.open = _compat_av_open
except Exception:
    pass

_LOADED_INTERNAL_MODULES = {}

def _iter_internal_modules():
    pkg_dir = os.path.dirname(__file__)
    preferred = ["utils.py", "helpers.py", "ffmpeg_utils.py", "broll.py", "renderer.py"]
    others = sorted(
        f for f in os.listdir(pkg_dir)
        if f.endswith(".py") and f not in preferred and f not in ("__init__.py", "api.py", "server.py", "main.py")
    )
    for fname in preferred + others:
        fpath = os.path.join(pkg_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if fname not in _LOADED_INTERNAL_MODULES:
            mod_name = f"clipping_studio_internal_{fname[:-3]}"
            spec = importlib.util.spec_from_file_location(mod_name, fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _LOADED_INTERNAL_MODULES[fname] = mod
        yield _LOADED_INTERNAL_MODULES[fname]

def __getattr__(name: str):
    for mod in _iter_internal_modules():
        if hasattr(mod, name):
            val = getattr(mod, name)
            globals()[name] = val
            return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

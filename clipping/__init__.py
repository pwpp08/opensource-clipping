# clipping — AI Auto-Clipper & Teaser Generator

import inspect as _inspect
try:
    import av as _av
    if "metadata_errors" not in _inspect.signature(_av.open).parameters:
        _orig_av_open = _av.open
        def _compat_av_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _orig_av_open(*args, **kwargs)
        _av.open = _compat_av_open
except Exception:
    pass

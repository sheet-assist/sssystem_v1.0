# Monkeypatch: fix BaseContext.__copy__ bug that raises AttributeError
# (copy(super()) doesn't work reliably across Python/Django versions).
# Patch applied at project import time so Django test client can copy template
# contexts during tests without error.
try:
    from django.template.context import BaseContext

    def _safe_basecontext_copy(self):
        """Return a shallow copy of BaseContext with copied `dicts` list.

        This avoids calling copy(super()) which can fail on some Python/Django
        combinations (observed as "super object has no attribute 'dicts'").
        """
        duplicate = object.__new__(self.__class__)
        # copy existing attributes, but ensure `dicts` is a shallow copy
        for k, v in getattr(self, "__dict__", {}).items():
            if k == "dicts":
                continue
            setattr(duplicate, k, v)
        duplicate.dicts = list(self.dicts)
        return duplicate

    BaseContext.__copy__ = _safe_basecontext_copy
except Exception:
    # If Django isn't available yet (or BaseContext can't be imported),
    # silently continue — Django will import this file again at runtime.
    pass

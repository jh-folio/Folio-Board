"""Bound regenerable macro responses; the observation ledger is never pruned."""
import re
import time
from pathlib import Path

_OWNED=re.compile(r'(fred|ecos)_macro_[A-Za-z_]+_[a-f0-9]{24}\.json')


def prune_owned_cache(root:Path,*,budget_bytes=128*1024*1024,now=None):
    root=Path(root).resolve()
    if not root.is_dir():return 0
    clock=time.time() if now is None else now
    candidates=[]
    try:paths=list(root.iterdir())
    except OSError:return 0
    for path in paths:
        if not _OWNED.fullmatch(path.name) or path.is_symlink() or not path.is_file() or path.resolve().parent!=root:continue
        try:stat=path.stat()
        except OSError:continue
        candidates.append((stat.st_mtime,stat.st_size,path))
    total=sum(size for _,size,_ in candidates);removed=0
    for modified,size,path in sorted(candidates):
        # Fresh responses may be in use. A large initial collection can temporarily
        # exceed the cap; the next collection removes expired oldest pages first.
        if clock-modified<=3600:continue
        if total<=budget_bytes and clock-modified<=7*86400:continue
        try:path.unlink()
        except OSError:continue
        total-=size;removed+=1
    return removed

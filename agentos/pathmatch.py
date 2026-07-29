import fnmatch


def matches(path, pattern):
    if fnmatch.fnmatch(path, pattern):
        return True
    if fnmatch.fnmatch(path, pattern.rstrip("/") + "/*"):
        return True
    return any(fnmatch.fnmatch(seg, pattern) for seg in path.split("/"))

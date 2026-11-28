import functools

# HEADER note

# DOC1 Adds one.
# DOC2 Never fails.
@functools.lru_cache
def documented(x):
    return x + 1

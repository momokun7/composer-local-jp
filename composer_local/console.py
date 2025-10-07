from functools import lru_cache

from rich import console


@lru_cache(maxsize=None)
def get_console() -> console.Console:
    return console.Console()

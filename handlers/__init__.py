
# — или сразу сделать удобный экспорт:
from .registration import register_handlers   as registration_handlers
from .topics       import register_handlers   as topics_handlers
from .search       import register_handlers   as search_handlers
from .misc         import register_handlers   as misc_handlers

__all__ = [
    "registration_handlers",
    "topics_handlers",
    "search_handlers",
    "misc_handlers",
]

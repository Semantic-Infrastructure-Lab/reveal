"""JSON utilities for reveal."""

import json
from datetime import datetime, date


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and date objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def safe_json_dumps(obj, **kwargs):
    """Safely dump JSON with support for datetime/date objects."""
    kwargs.setdefault('cls', DateTimeEncoder)
    kwargs.setdefault('indent', 2)
    return json.dumps(obj, **kwargs)

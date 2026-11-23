"""The two retiring request spellings reveal's own text must not teach (D20; BACK-2716, BACK-2713).

COMMAND_MODEL rule 2: an analysis-only scheme names a path and selects an analysis, so its request is taught as
``reveal NOUN TARGET --flags``; a URI query option (``?key=``) is taught as the noun's flag. Shared by the RETIREMENTS
replacement check (``test_retirement_replacements_back2716.py``) and the first-screen teaching check
(``test_teaching_one_spelling_back2713.py``).
"""
import re

from reveal.adapters.registry import get_adapter_class, list_supported_schemes
from reveal.cli.invocation import RETIREMENTS

# The adapters declare it (``ANALYSIS_ONLY``); a retired twin (architecture, stats) is one with its own scheme row.
ANALYSIS_ONLY = tuple(sorted(
    scheme for scheme in list_supported_schemes()
    if getattr(get_adapter_class(scheme), 'ANALYSIS_ONLY', False) and f'scheme:{scheme}' not in RETIREMENTS))
ANALYSIS_URI = re.compile(r'\b(?:' + '|'.join(ANALYSIS_ONLY) + r')://')
QUERY_OPTION = re.compile(r'(?<![\w/])[?&][A-Za-z_][\w-]*')

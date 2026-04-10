"""Parser for cPanel AutoSSL NDJSON log files.

Log location: /var/cpanel/logs/autossl/TIMESTAMP/
Each run directory contains:
    json      - newline-delimited JSON log records
    txt       - human-readable text version
    provider  - symlink to provider name (e.g. LetsEncrypt)
    upid      - symlink to unique process ID
    username  - symlink to '*' (all users) or a specific username

JSON record format:
    {"timestamp": "...", "contents": "...", "indent": 0-3,
     "type": "out|error|success", "pid": int, "partial": 0}

NOTE: cPanel uses Unicode curly quotes in log contents:
    " (U+201C) and " (U+201D) for double quotes
    ' (U+2019) for apostrophes

Log structure — two phases:

  Phase 1: Analyzing
    indent=0  Top-level ("Analyzing 4 users …")
    indent=1  Per-user ("Analyzing "USERNAME"'s domains …")
    indent=2  Per-domain ("Analyzing "domain.com" (website) …")
    indent=3  Domain details (TLS Status, Defect, Certificate expiry, Impediment)

  Phase 2: DCV (Domain Control Validation)
    indent=0  Per-user ("Processing "USERNAME"'s local DCV results …")
    indent=1  Per-domain ("Analyzing "domain.com"'s DCV results …")
    indent=2  Per-domain detail ("Impediment: CODE: description")
"""

import json
import os
import re
from typing import Any, Dict, List

AUTOSSL_LOG_DIR = "/var/cpanel/logs/autossl"

# cPanel uses Unicode curly quotes: \u201c (") and \u201d ("), \u2019 (')
_LQ = '\u201c'   # left double quote "
_RQ = '\u201d'   # right double quote "
_AP = '\u2019'   # curly apostrophe '

_RE_USER_ANALYZING = re.compile(
    rf'Analyzing [{_LQ}"](.+?)[{_RQ}"][{_AP}\']s\s+domains'
)
_RE_USER_DCV = re.compile(
    rf'Processing [{_LQ}"](.+?)[{_RQ}"][{_AP}\']s\s+(?:local )?DCV results'
)
_RE_USER_COMPLETE = re.compile(
    rf'The system has completed [{_LQ}"](.+?)[{_RQ}"][{_AP}\']s\s+AutoSSL check'
)
_RE_DOMAIN = re.compile(
    rf'Analyzing [{_LQ}"](.+?)[{_RQ}"]\s*\(website\)'
)
_RE_DOMAIN_DCV = re.compile(
    rf'Analyzing [{_LQ}"](.+?)[{_RQ}"][{_AP}\']s\s+DCV results'
)
_RE_EXPIRY_DAYS = re.compile(r'\(([+-]?\d+\.?\d*)\s+days?\s+(from now|ago)\)')
_RE_DEFECT = re.compile(r'^Defect:\s+(.+)')
_RE_IMPEDIMENT = re.compile(r'^Impediment:\s+(\w+):\s*(.+)')
_RE_OPENSSL_CODE = re.compile(r'\(0:\d+:(\w+)\)')

# Short display codes for impediments — shared with renderer so JSON `detail` matches text output
IMPEDIMENT_SHORT = {
    'TOTAL_DCV_FAILURE': 'DCV:TOTAL',
    'NO_UNSECURED_DOMAIN_PASSED_DCV': 'DCV:PARTIAL',
}


def list_runs(log_dir: str = AUTOSSL_LOG_DIR) -> List[str]:
    """Return list of run timestamps, newest first."""
    if not os.path.isdir(log_dir):
        return []
    entries = [
        name for name in os.listdir(log_dir)
        if os.path.isdir(os.path.join(log_dir, name))
    ]
    entries.sort(reverse=True)
    return entries


def get_run_metadata(timestamp: str, log_dir: str = AUTOSSL_LOG_DIR) -> Dict[str, str]:
    """Load provider, upid, and username from symlinks in run directory."""
    run_dir = os.path.join(log_dir, timestamp)
    meta: Dict[str, str] = {'provider': 'unknown', 'upid': 'unknown', 'username': '*'}
    for key in ('provider', 'upid', 'username'):
        path = os.path.join(run_dir, key)
        if os.path.islink(path):
            meta[key] = os.readlink(path)
    return meta


def _new_domain_entry(domain: str) -> Dict[str, Any]:
    return {
        'domain': domain,
        'tls_status': None,       # 'ok' | 'incomplete' | 'defective'
        'cert_expiry_raw': None,  # raw string from log
        'cert_expiry_days': None, # float, negative = already expired
        'defects': [],            # list of full defect strings
        'impediments': [],        # list of {code, detail}
        'user_excluded': False,
    }


def _extract_defect_code(defect_str: str) -> str:
    """Extract compact OpenSSL error code from verbose defect string.

    e.g. '...verification (0:18:DEPTH_ZERO_SELF_SIGNED_CERT).'
         → 'DEPTH_ZERO_SELF_SIGNED_CERT'
    """
    m = _RE_OPENSSL_CODE.search(defect_str)
    return m.group(1) if m else defect_str[:60]


_STATUS_ORDER: Dict[str, int] = {'defective': 0, 'incomplete': 1, 'ok': 2}


def _process_indent0(contents: str, state: Dict[str, Any], users: Dict[str, Any]) -> None:
    """DCV phase start: 'Processing "USERNAME"'s local DCV results …'"""
    m = _RE_USER_DCV.search(contents)
    if m:
        state['current_user'] = m.group(1)
        state['phase'] = 'dcv'
        users.setdefault(state['current_user'], {'domains': {}})
        state['current_domain'] = None


def _process_indent1(contents: str, state: Dict[str, Any], users: Dict[str, Any]) -> None:
    """Per-user analyzing or per-domain DCV tracking."""
    if state['phase'] == 'analyzing':
        m = _RE_USER_ANALYZING.search(contents)
        if m:
            state['current_user'] = m.group(1)
            users.setdefault(state['current_user'], {'domains': {}})
            state['current_domain'] = None
        elif _RE_USER_COMPLETE.search(contents):
            state['current_domain'] = None
    elif state['phase'] == 'dcv' and state['current_user'] is not None:
        m = _RE_DOMAIN_DCV.search(contents)
        if m:
            state['current_domain'] = m.group(1)


def _process_indent2(contents: str, state: Dict[str, Any], users: Dict[str, Any]) -> None:
    """Domain detection (analyzing) or DCV impediments (dcv phase)."""
    current_user = state['current_user']
    if state['phase'] == 'analyzing' and current_user is not None:
        m = _RE_DOMAIN.search(contents)
        if m:
            state['current_domain'] = m.group(1)
            users[current_user]['domains'].setdefault(
                state['current_domain'], _new_domain_entry(state['current_domain'])
            )
    elif state['phase'] == 'dcv' and current_user is not None and state['current_domain'] is not None:
        if contents.startswith('Impediment:'):
            entry = users[current_user]['domains'].setdefault(
                state['current_domain'], _new_domain_entry(state['current_domain'])
            )
            m = _RE_IMPEDIMENT.match(contents)
            if m:
                entry['impediments'].append({'code': m.group(1), 'detail': m.group(2).rstrip('.')})


def _process_indent3(contents: str, rtype: str, state: Dict[str, Any], users: Dict[str, Any]) -> None:
    """Domain detail fields: TLS status, expiry, defects, impediments."""
    current_user = state['current_user']
    current_domain = state['current_domain']
    if state['phase'] != 'analyzing' or current_user is None or current_domain is None:
        return
    entry = users[current_user]['domains'].get(current_domain)
    if entry is None:
        return

    if 'TLS Status:' in contents:
        entry['tls_status'] = 'ok' if rtype == 'success' else ('defective' if rtype == 'error' else 'incomplete')
    elif 'Certificate expiry:' in contents:
        entry['cert_expiry_raw'] = contents
        m = _RE_EXPIRY_DAYS.search(contents)
        if m:
            days = float(m.group(1))
            entry['cert_expiry_days'] = -days if m.group(2) == 'ago' else days
    elif contents.startswith('Defect:'):
        m = _RE_DEFECT.match(contents)
        if m:
            entry['defects'].append(m.group(1))
    elif 'User-excluded' in contents:
        entry['user_excluded'] = True
    elif contents.startswith('Impediment:'):
        # Some impediments appear at indent=3 during analyzing phase
        m = _RE_IMPEDIMENT.match(contents)
        if m:
            entry['impediments'].append({'code': m.group(1), 'detail': m.group(2).rstrip('.')})


def _parse_log_lines(json_path: str) -> tuple:
    """Read the NDJSON log file, return (users dict, run_start, run_end)."""
    users: Dict[str, Dict[str, Any]] = {}
    state: Dict[str, Any] = {
        'current_user': None,
        'current_domain': None,
        'phase': 'analyzing',
        'run_start': None,
        'run_end': None,
    }
    _dispatch = {0: _process_indent0, 1: _process_indent1, 2: _process_indent2}

    with open(json_path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = rec.get('timestamp', '')
            if state['run_start'] is None:
                state['run_start'] = ts
            state['run_end'] = ts

            indent = rec.get('indent', 0)
            contents = rec.get('contents', '')

            if indent in _dispatch:
                _dispatch[indent](contents, state, users)
            elif indent == 3:
                _process_indent3(contents, rec.get('type', 'out'), state, users)

    return users, state['run_start'], state['run_end']


def _build_user_list(users: Dict[str, Any]) -> tuple:
    """Build sorted per-user domain lists and compute overall summary. Returns (user_list, overall)."""
    overall: Dict[str, int] = {}
    user_list = []

    for uname, udata in users.items():
        domains_list = sorted(
            udata['domains'].values(),
            key=lambda d: (_STATUS_ORDER.get(d.get('tls_status') or 'unknown', 3), d['domain']),
        )
        for d in domains_list:
            d['defect_codes'] = [_extract_defect_code(x) for x in d['defects']]
            # Synthesize detail: mirrors text renderer column so JSON has same info density
            parts = list(d['defect_codes'][:2])
            for imp in d.get('impediments', [])[:1]:
                parts.append(IMPEDIMENT_SHORT.get(imp['code'], imp['code']))
            d['detail'] = ', '.join(parts)

        user_summary: Dict[str, int] = {}
        for d in domains_list:
            status = d.get('tls_status') or ('dcv_failed' if d.get('impediments') else 'unknown')
            user_summary[status] = user_summary.get(status, 0) + 1
            overall[status] = overall.get(status, 0) + 1

        user_list.append({
            'username': uname,
            'domain_count': len(domains_list),
            'summary': user_summary,
            'domains': domains_list,
        })

    return user_list, overall


def parse_run(timestamp: str, log_dir: str = AUTOSSL_LOG_DIR) -> Dict[str, Any]:
    """Parse the NDJSON log for an autossl run.

    Returns a structured dict:
    {
        'type': 'autossl_run',
        'run_timestamp': str,
        'provider': str,
        'summary': {'ok': N, 'incomplete': N, 'defective': N, ...},
        'users': [
            {
                'username': str,
                'domain_count': int,
                'summary': {'ok': N, ...},
                'domains': [
                    {
                        'domain': str,
                        'tls_status': str,       # ok / incomplete / defective
                        'cert_expiry_days': float,  # negative = expired
                        'defects': [str, ...],
                        'defect_codes': [str, ...], # compact codes
                        'impediments': [{'code': str, 'detail': str}, ...],
                    }
                ],
            }
        ],
    }
    """
    run_dir = os.path.join(log_dir, timestamp)
    json_path = os.path.join(run_dir, 'json')
    meta = get_run_metadata(timestamp, log_dir)

    try:
        users, run_start, run_end = _parse_log_lines(json_path)
    except OSError as exc:
        return {
            'contract_version': '1.0',
            'type': 'autossl_run',
            'error': str(exc),
            'run_timestamp': timestamp,
            'log_dir': run_dir,
        }

    user_list, overall = _build_user_list(users)

    return {
        'contract_version': '1.0',
        'type': 'autossl_run',
        'run_timestamp': timestamp,
        'run_start': run_start,
        'run_end': run_end,
        'provider': meta.get('provider', 'unknown'),
        'upid': meta.get('upid', 'unknown'),
        'global_run': meta.get('username', '*') == '*',
        'log_dir': run_dir,
        'user_count': len(user_list),
        'domain_count': sum(u['domain_count'] for u in user_list),
        'summary': overall,
        'users': user_list,
    }

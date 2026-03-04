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
from typing import Any, Dict, List, Optional

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

    # username → {domains: {domain_name: entry}}
    users: Dict[str, Dict[str, Any]] = {}
    current_user: Optional[str] = None
    current_domain: Optional[str] = None
    phase = 'analyzing'  # 'analyzing' | 'dcv'
    run_start: Optional[str] = None
    run_end: Optional[str] = None

    try:
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
                indent = rec.get('indent', 0)
                contents = rec.get('contents', '')
                rtype = rec.get('type', 'out')

                if run_start is None:
                    run_start = ts
                run_end = ts

                if indent == 0:
                    # DCV phase: "Processing "USERNAME"'s local DCV results …"
                    m = _RE_USER_DCV.search(contents)
                    if m:
                        current_user = m.group(1)
                        phase = 'dcv'
                        users.setdefault(current_user, {'domains': {}})
                        current_domain = None

                elif indent == 1:
                    if phase == 'analyzing':
                        m = _RE_USER_ANALYZING.search(contents)
                        if m:
                            current_user = m.group(1)
                            users.setdefault(current_user, {'domains': {}})
                            current_domain = None
                        elif _RE_USER_COMPLETE.search(contents):
                            # end of user's analyzing section
                            current_domain = None

                    elif phase == 'dcv' and current_user is not None:
                        m = _RE_DOMAIN_DCV.search(contents)
                        if m:
                            current_domain = m.group(1)

                elif indent == 2:
                    if phase == 'analyzing' and current_user is not None:
                        m = _RE_DOMAIN.search(contents)
                        if m:
                            current_domain = m.group(1)
                            users[current_user]['domains'].setdefault(
                                current_domain, _new_domain_entry(current_domain)
                            )

                    elif phase == 'dcv' and current_user is not None and current_domain is not None:
                        if contents.startswith('Impediment:'):
                            entry = users[current_user]['domains'].setdefault(
                                current_domain, _new_domain_entry(current_domain)
                            )
                            m = _RE_IMPEDIMENT.match(contents)
                            if m:
                                entry['impediments'].append({
                                    'code': m.group(1),
                                    'detail': m.group(2).rstrip('.'),
                                })

                elif indent == 3:
                    if phase == 'analyzing' and current_user is not None and current_domain is not None:
                        entry = users[current_user]['domains'].get(current_domain)
                        if entry is None:
                            continue

                        if 'TLS Status:' in contents:
                            if rtype == 'success':
                                entry['tls_status'] = 'ok'
                            elif rtype == 'error':
                                entry['tls_status'] = 'defective'
                            else:
                                entry['tls_status'] = 'incomplete'

                        elif 'Certificate expiry:' in contents:
                            entry['cert_expiry_raw'] = contents
                            m2 = _RE_EXPIRY_DAYS.search(contents)
                            if m2:
                                days = float(m2.group(1))
                                if m2.group(2) == 'ago':
                                    days = -days
                                entry['cert_expiry_days'] = days

                        elif contents.startswith('Defect:'):
                            m3 = _RE_DEFECT.match(contents)
                            if m3:
                                entry['defects'].append(m3.group(1))

                        elif 'User-excluded' in contents:
                            entry['user_excluded'] = True

                        elif contents.startswith('Impediment:'):
                            # Some impediments appear at indent=3 during analyzing phase
                            m4 = _RE_IMPEDIMENT.match(contents)
                            if m4:
                                entry['impediments'].append({
                                    'code': m4.group(1),
                                    'detail': m4.group(2).rstrip('.'),
                                })

    except OSError as exc:
        return {
            'contract_version': '1.0',
            'type': 'autossl_run',
            'error': str(exc),
            'run_timestamp': timestamp,
            'log_dir': run_dir,
        }

    # Build per-user sorted domain lists and overall summary
    _STATUS_ORDER = {'defective': 0, 'incomplete': 1, 'ok': 2}
    overall: Dict[str, int] = {}
    user_list = []

    for uname, udata in users.items():
        domains_list = sorted(
            udata['domains'].values(),
            key=lambda d: (
                _STATUS_ORDER.get(d.get('tls_status') or 'unknown', 3),
                d['domain'],
            ),
        )
        # Annotate with compact defect codes
        for d in domains_list:
            d['defect_codes'] = [_extract_defect_code(x) for x in d['defects']]

        user_summary: Dict[str, int] = {}
        for d in domains_list:
            status = d.get('tls_status') or (
                'dcv_failed' if d.get('impediments') else 'unknown'
            )
            user_summary[status] = user_summary.get(status, 0) + 1
            overall[status] = overall.get(status, 0) + 1

        user_list.append({
            'username': uname,
            'domain_count': len(domains_list),
            'summary': user_summary,
            'domains': domains_list,
        })

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

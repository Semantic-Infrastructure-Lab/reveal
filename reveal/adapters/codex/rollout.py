"""Codex rollout source identity and loss policy shared by direct and search views."""

ROLLOUT_RULE = 'Consumed nonblank JSONL lines before Codex normalization and view-specific processing; object decoding does not validate every payload'


def unavailable_rollout(raw):
    return {'candidate_records': 0, 'analyzed_records': 0, 'failed_records': 0, 'first_failed_line': None,
            'source': raw if isinstance(raw, str) else '', 'opened': False, 'decision': 'unavailable',
            'recovered_records': 0, 'failures': [{'phase': 'selection', 'cause': 'UnavailableRolloutPath',
                                                'message': 'Selected session has no usable rollout path'}],
            'count_rule': ROLLOUT_RULE}


def rollout_lost(proof):
    return bool(proof.get('failed_records') or proof.get('recovered_records') or proof.get('failures'))

"""Text and grep bodies for schema-validation batches."""


def schema_batch_text(result: dict, format: str = 'text') -> str:
    if result.get('error'):
        return ''  # the shared emission boundary reports the failed result
    lines = []
    for row in result['results']:
        path = row['source']
        if row['status'] == 'error':
            lines.append(f"{path}: Error: {row['error']}")
        elif format != 'grep':
            verdict = 'No issues found' if row['status'] == 'valid' else f"Found {row['total']} issue(s)"
            lines.append(f"{path}: {verdict}")
        for error in row.get('errors', []):
            lines.append(f"  Rule {error['rule']} failed: {error['error']}")
        for detection in row.get('detections', []):
            lines.append(f"{path}:{detection['line']}:{detection['column']}:"
                         f"{detection['rule_code']}:{detection['message']}")
            if format != 'grep' and detection.get('suggestion'):
                lines.append(f"  {detection['suggestion']}")
    return '\n'.join(lines)

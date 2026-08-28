"""Tests for reveal.utils.severity (BACK-1205)."""

import unittest

from reveal.utils.severity import SEVERITY_ORDER, filter_by_severity


class TestFilterBySeverity(unittest.TestCase):
    def setUp(self):
        self.items = [
            {'name': 'a', 'severity': 'low'},
            {'name': 'b', 'severity': 'medium'},
            {'name': 'c', 'severity': 'high'},
            {'name': 'd', 'severity': 'critical'},
        ]

    def test_no_severity_returns_all_unchanged(self):
        self.assertEqual(filter_by_severity(self.items, None), self.items)
        self.assertEqual(filter_by_severity(self.items, ''), self.items)

    def test_filters_to_minimum_threshold(self):
        result = filter_by_severity(self.items, 'high')
        self.assertEqual([i['name'] for i in result], ['c', 'd'])

    def test_lowest_threshold_keeps_everything(self):
        result = filter_by_severity(self.items, 'low')
        self.assertEqual(len(result), 4)

    def test_critical_threshold_keeps_only_critical(self):
        result = filter_by_severity(self.items, 'critical')
        self.assertEqual([i['name'] for i in result], ['d'])

    def test_case_insensitive(self):
        result = filter_by_severity(self.items, 'HIGH')
        self.assertEqual([i['name'] for i in result], ['c', 'd'])

    def test_unrecognized_severity_is_a_noop(self):
        result = filter_by_severity(self.items, 'nonsense')
        self.assertEqual(result, self.items)

    def test_custom_key(self):
        items = [{'level': 'low'}, {'level': 'critical'}]
        result = filter_by_severity(items, 'high', key='level')
        self.assertEqual(result, [{'level': 'critical'}])

    def test_missing_or_unrecognized_item_severity_is_dropped(self):
        items = [{'name': 'no-sev'}, {'name': 'bad-sev', 'severity': 'urgent'}, {'name': 'ok', 'severity': 'high'}]
        result = filter_by_severity(items, 'low')
        self.assertEqual([i['name'] for i in result], ['ok'])

    def test_order_constant_matches_file_checker(self):
        # Keep in sync with cli/file_checker.py's _SEVERITY_ORDER (BACK-1205 shares
        # the same vocabulary between the lint path and the network-adapter checks).
        self.assertEqual(SEVERITY_ORDER, ['low', 'medium', 'high', 'critical'])


if __name__ == '__main__':
    unittest.main()

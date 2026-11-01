"""終了した機能のAPIを閉じ、通常の入力検査を残す。"""
import unittest
from solver.service import dispatch
from solver.tests.test_night_fairness import six_staff

class RetiredAutoTests(unittest.TestCase):
    def test_auto_creation_and_validation_are_rejected(self):
        raw = six_staff()
        for action in (None, 'validate'):
            payload = {'input': raw, 'mode': 'auto'}
            if action:
                payload['action'] = action
            result = dispatch(payload)
            self.assertEqual(result['status'], 'INVALID_INPUT')
            self.assertIn('終了', result['errors'][0])

    def test_normal_validation_is_still_available(self):
        result = dispatch({'input': six_staff(), 'action': 'validate', 'assignments': {}})
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['validationErrors'][0]['code'], 'structure')

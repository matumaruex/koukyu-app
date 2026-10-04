import unittest
from copy import deepcopy
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


class StaffingRequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = roomy_fixture()
        cls.raw.update(requiredStaff=[5, 2, 6], maxReducedSundays=0, dailyRequiredStaff={'5': [2, 5, 3]})
        cls.result = solve(cls.raw, seconds=10, optimize=False)
        assert cls.result['status'] in ('FEASIBLE', 'OPTIMAL'), cls.result
        cls.table = cls.result['assignments']

    def test_custom_counts_are_generated_and_independently_checked(self):
        self.assertEqual(validate(self.raw, self.table), [])
        p = deepcopy(self.raw)
        p['dailyRequiredStaff']['5'] = [0, 40, 0]
        errors = validate(p, self.table)
        error = next(e for e in errors if e['code'] == 'coverage' and e['day'] == 5)
        self.assertEqual(error['required'], 40)
        self.assertEqual(error['time'], 600)
        self.assertLess(error['actual'], 40)
        self.assertEqual(solve(p, seconds=5)['status'], 'INFEASIBLE')

    def test_legacy_defaults_are_preserved(self):
        p = normalize(roomy_fixture())
        self.assertEqual(p['requiredStaff'], [4, 4, 4])
        self.assertEqual(p['maxReducedSundays'], 3)
        self.assertEqual(p['dailyRequiredStaff'], {})

    def test_sunday_override_is_exact_and_does_not_use_relaxation(self):
        from datetime import timedelta
        p = normalize(self.raw)
        sunday = next(d for d in range(1, p['days'] + 1) if (p['start'] + timedelta(days=d-1)).weekday() == 6)
        raw = deepcopy(self.raw)
        raw['maxReducedSundays'] = 5
        # One daytime worker and a recovery suffice for the morning; explicit
        # requests for two noon workers must still fail, even on Sunday.
        table = deepcopy(self.table)
        for row in table.values():
            row[str(sunday)] = 'off'
        table['s0'][str(sunday)] = 'early'
        raw['requiredStaff'] = [0, 2, 0]
        errors = validate(raw, table)
        self.assertFalse(any(e['code'] == 'coverage' and e['day'] == sunday for e in errors))
        raw['dailyRequiredStaff'] = {str(sunday): [0, 2, 0]}
        errors = validate(raw, table)
        self.assertTrue(any(e['code'] == 'coverage' and e['day'] == sunday and e['required'] == 2 for e in errors))
        raw['dailyRequiredStaff'] = {}
        raw['maxReducedSundays'] = 0
        errors = validate(raw, table)
        self.assertTrue(any(e['code'] == 'coverage' and e['day'] == sunday for e in errors))

    def test_invalid_counts_and_days_are_rejected(self):
        variants = [{'requiredStaff': x} for x in (None, '4', [4, 4], [True, 4, 4], [-1, 4, 4], [41, 4, 4], [4.0, 4, 4])]
        variants += [{'maxReducedSundays': x} for x in (-1, 6, True, '3')]
        variants += [{'dailyRequiredStaff': x} for x in (None, [], {'0':[4,4,4]}, {'29':[4,4,4]}, {'5':[4,4]}, {'1':[4,4,4], '01':[4,4,4]})]
        for changes in variants:
            p = deepcopy(self.raw)
            p.update(changes)
            self.assertEqual(solve(p)['status'], 'INVALID_INPUT', changes)


if __name__ == '__main__':
    unittest.main()

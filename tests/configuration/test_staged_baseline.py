"""Source-only staged suite boundary checks; no native execution claim."""
import unittest
from evals.experiments.staged_baseline.cases import load_cases, revision_inputs, identification_input


class StagedBoundaryTests(unittest.TestCase):
    def test_projection_has_one_revision_and_no_operator_labels(self):
        for case in load_cases():
            for revision in case['revisions']:
                projected = revision_inputs(case, revision)
                self.assertNotIn('revisions', projected)
                self.assertNotIn('native_qualification', projected)
                self.assertIsNone(projected['environment']['baseline_test'])
                self.assertEqual(projected['source_files'], case['revisions'][revision]['source_files'])
                self.assertEqual(len(projected['environment']['approved_test_paths']), 2)
                projected['source_files'][0]['content'] = 'changed'
                self.assertNotEqual(case['revisions'][revision]['source_files'][0]['content'], 'changed')

    def test_identification_never_sees_property_or_test_identity(self):
        for case in load_cases():
            projected = identification_input(case, 'reported')
            self.assertEqual(set(projected), {'fixture_id', 'issue', 'scope', 'source_files'})
            for citation in case['revisions']['reported']['citations']:
                source = next(s for s in projected['source_files'] if s['path'] == citation['path'])
                self.assertEqual('\n'.join(source['content'].splitlines()[citation['start_line']-1:citation['end_line']]), citation['quote'])

    def test_native_stage_contract_projections_keep_operator_labels_separate(self):
        from evals.experiments.staged_baseline.cases import planning_cases, validity_cases
        plans = planning_cases()
        self.assertEqual({inputs.environment.framework for _, inputs, _ in plans},
                         {'pytest', 'Jest', 'Minitest', 'Test::More', 'JUnit 5'})
        for _, inputs, oracle in plans:
            baseline = inputs.environment.baseline_test
            self.assertIn(baseline.path, {source.path for source in inputs.source_files})
            self.assertNotIn(baseline.path, inputs.environment.approved_test_paths)
            self.assertEqual(oracle.status, 'ready')
        for _, inputs, expected in validity_cases():
            self.assertTrue(expected)
            self.assertFalse({'result', 'receipt', 'review'} & {item.kind for item in inputs.items})

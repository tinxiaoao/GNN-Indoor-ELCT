"""Mechanism fixtures only: not building generalization or recovery-rate data."""
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import numpy as np
from geo_elct import correction_v2 as v2
from geo_elct.__main__ import main


def internal():
    wall = np.full((30, 40), 3, np.uint8)
    wall[10:13] = 2; wall[13:] = 4
    return wall, np.zeros_like(wall)


class OpeningMechanisms(unittest.TestCase):
    def run_fixture(self, wall, icon):
        return v2.repair_opening_components(icon, wall)

    def actions(self, records):return [r['action'] for r in records]

    def test_supported_boundary_window(self):
        wall, icon = internal();wall[:10] = 3;wall[:3] = 2
        icon[:3, 10:20] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(icon, result))
        self.assertEqual(self.actions(records), ['keep_valid'])
        self.assertEqual(summary['unresolved_component_count'], 0)
        self.assertIn('image_exit', records[0]['domains_before']['evidence_counts'])

    def test_near_border_without_wall_or_room_support_is_not_valid(self):
        wall = np.zeros((30, 40), np.uint8);icon = np.zeros_like(wall);icon[:3, 10:20] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(icon, result))
        self.assertEqual(self.actions(records), ['keep_unresolved'])
        self.assertEqual(summary['unresolved_component_count'], 1)

    def test_label_zero_enclosed_cavity_is_not_outside(self):
        wall, icon = internal();wall[7:10, 6:27] = 0;icon[10:13, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(summary['unresolved_component_count'], 1)
        self.assertNotIn('outside', records[0]['domains_before']['signature'])
        self.assertTrue(np.array_equal(result, icon))

    def test_original_internal_valid(self):
        wall, icon = internal();icon[10:13, 10:22] = 2
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(self.actions(records), ['keep_valid'])
        self.assertTrue(np.array_equal(result, icon))

    def test_exterior_lip_is_distinct_from_overlap_acceptance(self):
        wall, icon = internal();wall[:10] = 0;icon[9:13, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(records[0]['reason'], 'inplace_rectangular_exterior_face_lip')
        self.assertLess(records[0]['wall_overlap_before'], .995)
        self.assertTrue(np.array_equal(result, icon))
        self.assertEqual(v2.CONFIG['opening']['min_wall_overlap_fraction'], .995)
        self.assertNotIn('min_component_fill_fraction', v2.CONFIG['opening'])

    def test_internal_room_overhang_does_not_use_exterior_lip(self):
        wall, icon = internal();icon[11:14, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(self.actions(records), ['move'])
        self.assertEqual(records[0]['shift_dy_dx'], [-1, 0])
        self.assertEqual(records[0]['wall_overlap_after'], 1)
        expected = np.zeros_like(icon);expected[10:13, 10:22] = 1
        self.assertTrue(np.array_equal(result, expected))

    def test_exterior_shift_leaving_uncovered_opposite_wall_face_is_not_kept_valid(self):
        wall, icon = internal();wall[:10] = 0;icon[9:12, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(self.actions(records), ['move'])
        self.assertEqual(records[0]['shift_dy_dx'], [1, 0])
        expected = np.zeros_like(icon);expected[10:13, 10:22] = 1
        self.assertTrue(np.array_equal(result, expected))

    def test_no_candidate_keeps_unresolved(self):
        wall, icon = internal();icon[20:23, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(records[0]['reason'], 'no_legal_shift')
        self.assertEqual(summary['erased_component_count'], 0)
        self.assertTrue(np.array_equal(result, icon))

    def test_tied_best_candidates_keep_original(self):
        wall = np.full((30, 40), 3, np.uint8);wall[8:10] = 2;wall[10:12] = 4;wall[12:14] = 2;wall[14:] = 5
        icon = np.zeros_like(wall);icon[10:12, 10:22] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(records[0]['reason'], 'tied_best_shifts')
        self.assertEqual(sorted(records[0]['tied_best_shifts']), [[-2, 0], [2, 0]])
        self.assertTrue(np.array_equal(result, icon))

    def test_internal_band_completion(self):
        wall, icon = internal();icon[10:13, 10:15] = 1;icon[10:13, 17:23] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(summary['merged_pairs'], 1)
        self.assertEqual(records[0]['action'], 'complete')
        self.assertEqual(records[0]['area_change_px'], 6)
        expected = np.zeros_like(icon);expected[10:13, 10:23] = 1
        self.assertTrue(np.array_equal(result, expected))

    def test_other_type_collision_not_overwritten(self):
        wall, icon = internal();icon[10:13, 10:15] = 1;icon[10:13, 17:23] = 1;icon[10:13, 15:17] = 2
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(summary['merged_pairs'], 0)
        self.assertTrue(np.array_equal(result, icon))
        self.assertGreater(summary['unresolved_event_count'], 0)

    def test_split_band_with_fragment_aspect_ratio_inversion(self):
        wall = np.full((30, 40), 3, np.uint8);wall[:, 10:15] = 2;wall[:, 15:] = 0
        icon = np.zeros_like(wall);icon[8:12, 10:15] = 1;icon[13:17, 10:15] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertEqual(summary['merged_pairs'], 1)
        expected = np.zeros_like(icon);expected[8:17, 10:15] = 1
        self.assertTrue(np.array_equal(result, expected))
        self.assertEqual(records[0]['domains_before']['orientation'], 'vertical')
        self.assertEqual(records[0]['domains_before']['orientation_source'], 'aligned_completion_pair')

    def test_multi_domain_and_corner_ambiguity(self):
        wall, icon = internal();wall[:10, 17:] = 5;icon[10:13, 10:24] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(result, icon))
        self.assertEqual(self.actions(records), ['keep_unresolved'])
        self.assertGreaterEqual(len(records[0]['domains_before']['signature']), 3)

    def test_square_orientation_ambiguous(self):
        wall, icon = internal();icon[10:13, 12:15] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(result, icon))
        self.assertTrue(records[0]['domains_before']['square_orientation_ambiguous'])
        self.assertEqual(summary['unresolved_component_count'], 1)

    def test_small_isolated_speck_erased_with_evidence(self):
        wall, icon = internal();icon[22:24, 12:14] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertFalse(np.any(result))
        self.assertEqual(self.actions(records), ['erase'])
        self.assertEqual(records[0]['area_change_px'], -4)
        self.assertEqual(records[0]['domains_after']['signature'], [])
        self.assertEqual(records[0]['domains_after']['status'], 'component_erased')

    def test_small_real_opening_not_deleted_by_area(self):
        wall, icon = internal();wall[11:] = 4;icon[10:11, 12:16] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(result, icon))
        self.assertEqual(self.actions(records), ['keep_valid'])

    def test_multiple_completion_partners_ambiguous(self):
        wall, icon = internal();icon[10:13, 5:10] = 1;icon[10:13, 12:17] = 1;icon[10:13, 19:24] = 1
        result, summary, records = self.run_fixture(wall, icon)
        self.assertTrue(np.array_equal(result, icon))
        self.assertEqual(summary['merged_pairs'], 0)
        self.assertIn('multiple_completion_partners', [r['reason'] for r in records])

    def test_new_mode_is_explicit_and_default_unchanged(self):
        with patch('geo_elct.__main__.extract', return_value={}) as run, redirect_stdout(io.StringIO()):
            main(['extract','--wall','a','--icon','b','--out','c','--mode','correction_v2'])
        self.assertEqual(run.call_args.kwargs['mode'], 'correction_v2')

    def diagnostic_fixture(self, summary, stats):
        base = Path(os.environ.get('GEO_ELCT_TEST_TMP', Path(__file__).resolve().parents[1]/'runs')).resolve()
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix='v2_diagnostic_', dir=base)
        self.assertTrue(Path(temp.name).resolve().is_relative_to(base))
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)
        (path/'room_stats.json').write_text(json.dumps(stats), encoding='utf-8')
        return v2.runtime_diagnostics(path, {'module_summaries': {'door_window_component_repair_v2': summary}}, {'passed': True})

    def test_unresolved_cannot_be_hidden_by_internal_graph_pass(self):
        wall, icon = internal();icon[20:23, 10:22] = 1
        _, summary, _ = self.run_fixture(wall, icon)
        report = self.diagnostic_fixture(summary, {})
        self.assertTrue(report['internal_graph_existing_report_passed'])
        self.assertTrue(report['manual_review_required'])
        self.assertFalse(report['all_implemented_checks_passed'])
        self.assertFalse(report['em_ready'])

    def test_external_anomaly_prevents_success(self):
        wall, icon = internal();icon[10:13, 10:22] = 1
        _, summary, _ = self.run_fixture(wall, icon)
        report = self.diagnostic_fixture(summary, {'1': {'walls': [['horizontal', 3, 5]], 'openings': []}})
        self.assertEqual(report['exported_external_wall_segment_count'], 1)
        self.assertEqual(len(report['external_export_anomalies']), 1)
        self.assertTrue(report['manual_review_required'])
        self.assertFalse(report['all_implemented_checks_passed'])


if __name__ == '__main__':unittest.main()

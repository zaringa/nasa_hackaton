import sys
import types
import unittest
from unittest.mock import Mock, patch
import ast
import io
from pathlib import Path

import numpy as np

import mini_model as model
import verify_formulas as audit


class AuditTests(unittest.TestCase):
    def test_coordinate_axes_and_basis_example(self):
        for phi, lam, expected in [(0, 0, [3, 0, 0]),
                                    (0, np.pi/2, [0, 3, 0]),
                                    (np.pi/2, 0, [0, 0, 3])]:
            np.testing.assert_allclose(model.spherical_position(3, phi, lam), expected, atol=1e-15)
        basis = model.local_basis(np.pi/6, 0)
        np.testing.assert_allclose(basis[:, 1], [-0.5, 0, np.sqrt(3)/2], atol=1e-15)
        np.testing.assert_allclose(basis[:, 2], [np.sqrt(3)/2, 0, 0.5], atol=1e-15)

    def test_basis_identities_on_many_sites(self):
        for phi in np.linspace(-np.pi/2, np.pi/2, 11):
            for lam in np.linspace(-np.pi, np.pi, 9):
                basis = model.local_basis(phi, lam)
                np.testing.assert_allclose(basis.T @ basis, np.eye(3), atol=1e-15)
                np.testing.assert_allclose(np.linalg.inv(basis), basis.T, atol=1e-15)
                np.testing.assert_allclose(np.cross(basis[:, 0], basis[:, 1]), basis[:, 2], atol=1e-15)

    def test_local_projections_and_origin_subtraction(self):
        basis = model.local_basis(0.7, -1.2)
        vector = np.array([2., -3., 4.])
        projections = [sum(vector[i]*basis[i, axis] for i in range(3)) for axis in range(3)]
        np.testing.assert_allclose(model.global_to_local(vector, basis), projections)
        np.testing.assert_allclose(model.local_to_global(projections, basis), vector)
        np.testing.assert_array_equal(model.observer_to_body([10, 20, 30], [1, 2, 3]), [9, 18, 27])

    def test_terrain_derivatives_against_finite_differences(self):
        phi, lam, step = 0.4, 0.8, 1e-6
        radius = lambda p, l: 10 + 0.2*p - 0.3*l
        point = lambda p, l: model.spherical_position(radius(p, l), p, l)
        analytic = model.terrain_derivatives(radius(phi, lam), 0.2, -0.3, phi, lam)
        numerical_phi = (point(phi+step, lam)-point(phi-step, lam))/(2*step)
        numerical_lam = (point(phi, lam+step)-point(phi, lam-step))/(2*step)
        np.testing.assert_allclose(analytic, [numerical_phi, numerical_lam], atol=2e-9)

    def test_first_order_longitude_increment(self):
        radius, phi, lam = 10., 0.3, 0.4
        derivative = model.position_derivatives(radius, phi, lam)[2]
        errors = []
        for step in [0.01, 0.005]:
            actual = model.spherical_position(radius, phi, lam+step)-model.spherical_position(radius, phi, lam)
            errors.append(np.linalg.norm(actual-step*derivative))
        self.assertAlmostEqual(errors[0]/errors[1], 4, delta=0.001)

    def test_azimuth_convention_and_component_reconstruction(self):
        for expected, vector in [(0, [0, 1, 0]), (90, [1, 0, 0]),
                                  (180, [0, -1, 0]), (270, [-1, 0, 0])]:
            azimuth, elevation = model.azimuth_elevation(vector, np.eye(3))
            self.assertAlmostEqual(model.radians_to_degrees(azimuth), expected)
            self.assertEqual(elevation, 0)
        for angle in np.linspace(0, 2*np.pi, 13):
            east, north = model.horizontal_components(2, angle)
            np.testing.assert_allclose([east, north], [2*np.sin(angle), 2*np.cos(angle)])
            azimuth, elevation = model.azimuth_elevation([east, north, 1], np.eye(3))
            self.assertAlmostEqual(np.tan(elevation), 0.5)

    def test_great_circle_and_clearance(self):
        basis = model.local_basis(0.4, 0.5)
        psi, azimuth = 0.03, 1.4
        direction = model.great_circle_direction(psi, azimuth, basis)
        self.assertAlmostEqual(np.linalg.norm(direction), 1)
        self.assertAlmostEqual(np.arccos(direction @ basis[:, 2]), psi)
        horizon = lambda azimuth: np.zeros_like(azimuth)+0.1
        self.assertAlmostEqual(model.angular_clearance(1, 0.3, horizon), 0.2)
        self.assertTrue(model.point_visibility_indicator(0.2))
        self.assertFalse(model.point_visibility_indicator(0))

    def test_small_angle_curvature_and_flat_comparison(self):
        for psi in [1e-3, 5e-4]:
            self.assertLess(abs(np.sin(psi)-psi), psi**3/5)
            self.assertLess(abs(np.cos(psi)-(1-psi**2/2)), psi**4/20)
        radius = 1_737_400.
        exact = model.terrain_elevation_angle(radius+1000, radius+2, 20_000/radius)
        approximate = model.approximate_terrain_elevation(1000, 0, 2, 20_000, radius)
        flat = np.arctan2(998, 20_000)
        self.assertAlmostEqual(model.radians_to_degrees(flat), 2.856695, delta=0.00001)
        self.assertLess(abs(approximate-exact), abs(flat-exact))

    def test_ground_level_horizon_is_a_supremum(self):
        psi = np.array([0.1, 0.01, 0.001])
        exact = model.terrain_elevation_angle(10, 10, psi)
        np.testing.assert_allclose(exact, model.ground_level_sphere_elevation(psi), atol=1e-13)
        self.assertTrue(np.all(exact < 0))
        self.assertEqual(model.smooth_sphere_horizon(10, 0), 0)
        self.assertLess(abs(exact[-1]), abs(exact[0]))

    def test_nonzero_dem_sphere_and_height_sensitivity(self):
        radius, ground, height = 1_737_400., 1000., 2.
        surface = radius+ground
        expected = -np.arccos(surface/(surface+height))
        self.assertEqual(model.smooth_sphere_horizon(surface, height), expected)
        terrain_radius, observer_radius, psi, step = 10.5, 10.1, 0.03, 1e-5
        numerical = (model.terrain_elevation_angle(terrain_radius, observer_radius+step, psi)
                     - model.terrain_elevation_angle(terrain_radius, observer_radius-step, psi))/(2*step)
        self.assertAlmostEqual(model.observer_height_sensitivity(terrain_radius, observer_radius, psi),
                               numerical, delta=1e-9)

    def test_coverage_bound_against_line_segment_occlusion(self):
        inner, outer, observer_radius = 10., 10.5, 10.2
        cutoff, distance = model.terrain_coverage_limit(inner, outer, observer_radius, 10)
        self.assertAlmostEqual(distance, 10*cutoff)
        observer = np.array([observer_radius, 0.])
        for angle in np.linspace(cutoff+1e-4, np.pi, 101):
            point = outer*np.array([np.cos(angle), np.sin(angle)])
            segment = point-observer
            parameter = np.clip(-observer @ segment/(segment @ segment), 0, 1)
            nearest_radius = np.linalg.norm(observer+parameter*segment)
            self.assertLess(nearest_radius, inner)

    def test_feature_width_and_uncertainty(self):
        self.assertAlmostEqual(model.feature_angular_width(20, 20_000), 0.001)
        self.assertAlmostEqual(model.radians_to_degrees(model.feature_angular_width(20, 20_000)),
                               0.0572957795)
        self.assertEqual(model.elevation_uncertainty(1, 1000), 0.001)
        self.assertEqual(model.transition_time_uncertainty(0.01, -0.001), 10)
        self.assertEqual(model.transition_time_uncertainty(0.01, 0), np.inf)

    def test_angular_disc_geometry_and_area_derivative(self):
        angular = model.angular_radius(700_000, [150_000_000, 0, 0])
        self.assertAlmostEqual(model.radians_to_degrees(angular), 0.2673813, delta=0.000001)
        radius, step = 0.1, 1e-7
        for y in np.linspace(-0.08, 0.08, 9):
            derivative = (model.disc_area_antiderivative(y+step, radius)
                          - model.disc_area_antiderivative(y-step, radius))/(2*step)
            self.assertAlmostEqual(derivative, model.disc_strip_width(y, radius), delta=1e-10)
        for theta in np.linspace(-1, 1, 9):
            y, dy = radius*np.sin(theta), radius*np.cos(theta)
            self.assertAlmostEqual(model.disc_strip_width(y, radius)*dy,
                                   radius**2*(1+np.cos(2*theta)))

    def test_disc_sample_coordinates_and_weighted_areas(self):
        count, radius = 2000, 0.01
        rays = model.disc_sample_directions([0, 0, 1], radius, count)
        projected = rays[:, :2]/rays[:, 2, None]/np.tan(radius)
        radial_squared = np.sum(projected**2, axis=1)
        np.testing.assert_allclose(radial_squared, (np.arange(count)+0.5)/count, atol=1e-15)
        np.testing.assert_allclose(np.linalg.norm(rays, axis=1), 1, atol=1e-15)
        self.assertAlmostEqual(model.weighted_visible_fraction([True, False, True], [1, 2, 3]), 4/6)

    def test_occultation_against_ray_sphere_intersection(self):
        centre, radius = np.array([10., 0., 0.]), 1.
        rays = model.unit_vector([[1, 0, 0], [1, 0.05, 0], [1, 0.2, 0], [-1, 0, 0]])
        projection = rays @ centre
        discriminant = projection**2 - (centre @ centre-radius**2)
        independent_blocked = (projection > 0) & (discriminant >= 0)
        np.testing.assert_array_equal(~model.earth_open_mask(rays, centre, radius), independent_blocked)

    def test_continuous_root_and_step_boundary_are_different(self):
        self.assertAlmostEqual(model.refine_transition(lambda time: 3*time-2, 0, 1, 1e-8), 2/3, delta=1e-8)
        self.assertAlmostEqual(model.refine_state_transition(lambda time: time >= 0.7, 0, 1, 1e-8),
                               0.7, delta=1e-8)
        hidden_window = lambda time: 1-(time-5)**2
        self.assertEqual(model.windows_from_samples([0, 10], [hidden_window(0), hidden_window(10)]), [])
        actual_start = model.refine_transition(hidden_window, 0, 5, 1e-8)
        actual_end = model.refine_transition(hidden_window, 5, 10, 1e-8)
        np.testing.assert_allclose([actual_start, actual_end], [4, 6], atol=1e-8)

    def test_taylor_error_and_event_sensitivity(self):
        root = 2.
        for delta in [0.01, -0.01]:
            actual = (root+delta)**2-4
            linear = 2*root*delta
            self.assertAlmostEqual(actual-linear, delta**2)
        angular_error, rate = 0.002, 0.0004
        shift = model.transition_time_uncertainty(angular_error, rate)
        self.assertAlmostEqual(rate*shift, angular_error)

    def test_duration_integral_and_joint_intersection(self):
        np.testing.assert_array_equal(model.darkness_indicator([0, 0.5, 1]), [True, False, False])
        first, second = [(0, 2), (4, 7)], [(1, 5)]
        self.assertEqual(model.total_duration(first), 5)
        self.assertEqual(model.longest_duration(first), 3)
        self.assertEqual(model.total_duration(model.intersect_windows(first, second)), 2)
        self.assertEqual(model.longest_duration(model.complement_windows(first, 0, 8)), 2)
        edges = np.array([0, 1, 2, 4, 5, 7, 8])
        middle = (edges[:-1]+edges[1:])/2
        visible = lambda windows: np.array([any(a <= t < b for a, b in windows) for t in middle])
        joint = model.joint_indicator(visible(first), visible(second))
        self.assertEqual(model.time_integral(edges, joint, method='interval'), 2)

    def test_exact_two_full_hours_plus_one_half_visible_hour(self):
        edges = [0, 7200, 10800]
        equivalent = model.equivalent_full_disc_time(edges, [1, 0.5], method='interval')
        self.assertEqual(equivalent, 9000)
        self.assertEqual(equivalent/3600, 2.5)
        self.assertEqual(model.mean_disc_fraction(edges, [1, 0.5], method='interval'), 2.5/3)
        energy = model.electrical_energy(edges, [2, 1], method='interval')
        self.assertEqual(energy, {'joules': 18000, 'watt_hours': 5})

    def test_trapezoid_exactness_and_quadratic_convergence(self):
        times = np.array([0., 0.1, 0.4, 1.])
        self.assertAlmostEqual(model.time_integral(times, 3*times+2), 3.5)
        errors = []
        for intervals in [10, 20]:
            times = np.linspace(0, 1, intervals+1)
            errors.append(model.time_integral(times, times**2)-1/3)
        self.assertAlmostEqual(errors[0]/errors[1], 4)

    def test_spice_wrapper_units_without_claiming_ephemeris_accuracy(self):
        stub = types.ModuleType('spiceypy')
        stub.spkcpo = Mock(return_value=(np.array([1., 2., 3., 0, 0, 0]), 0.1))
        with patch.dict(sys.modules, {'spiceypy': stub}):
            vector = model.body_vector_from_spice('SUN', 12., [1000, 2000, 3000], 'MOON_ME_DE421')
        np.testing.assert_array_equal(vector, [1000, 2000, 3000])
        np.testing.assert_array_equal(stub.spkcpo.call_args.kwargs['obspos'], [1, 2, 3])
        self.assertEqual(stub.spkcpo.call_args.kwargs['abcorr'], 'CN+S')


class AuditStructureTests(unittest.TestCase):
    def document(self):
        return audit.parse_document('<a id="eq-001"></a>\n\n$$\nx=1\n$$\n\n'
                                    '<a id="eq-002"></a>\n\n$$\ny=2\n$$\n')

    def specifications(self):
        return audit.parse_specifications('001-002|Direct|Example|calculate|m:test_example|')

    def sources(self):
        root = Path(__file__).resolve().parent
        implementation = audit.SourceFile(root / 'mini_model.py',
                                          (audit.SourceSymbol('calculate', 'calculate', 1),))
        tests = audit.SourceFile(root / 'test_mini_model.py',
                                 (audit.SourceSymbol('test_example', 'Examples.test_example', 1),))
        return audit.AuditSources(implementation, {'m': tests})

    def test_equation_document_is_read_independently_of_registry_size(self):
        document = self.document()
        self.assertEqual(document.numbers, (1, 2))
        self.assertEqual(document.anchors, (1, 2))
        self.assertEqual(document.expressions, ('x=1', 'y=2'))
        audit.validate_document(document, self.specifications(), document.digest)

    def test_registry_produces_named_records(self):
        specification = self.specifications()[0]
        self.assertEqual(specification.numbers, (1, 2))
        self.assertEqual(specification.functions, ('calculate',))
        self.assertEqual(specification.evidence.source, 'm')
        self.assertEqual(specification.evidence.function, 'test_example')

    def test_invalid_registry_rows_are_reported_with_context(self):
        for line in ['invalid', '002-001|Direct|Example|calculate|m:test_example|',
                     '001|Unknown|Example|calculate|m:test_example|']:
            with self.subTest(line=line), self.assertRaisesRegex(audit.ValidationError, 'row 1'):
                audit.parse_specifications(line)

    def test_changed_equations_require_review(self):
        with self.assertRaisesRegex(audit.ValidationError, 'equations changed'):
            audit.validate_document(self.document(), self.specifications(), '0'*64)

    def test_duplicate_and_missing_mappings_are_rejected(self):
        specification = self.specifications()[0]
        with self.assertRaisesRegex(audit.ValidationError, 'Duplicate'):
            audit.validate_document(self.document(), (specification, specification), self.document().digest)
        missing = audit.parse_specifications('001|Direct|Example|calculate|m:test_example|')
        with self.assertRaisesRegex(audit.ValidationError, 'mappings differ'):
            audit.validate_document(self.document(), missing, self.document().digest)

    def test_anchor_order_and_duplicates_are_rejected(self):
        document = self.document()
        invalid = audit.EquationDocument(document.expressions, (2, 1), document.digest)
        with self.assertRaisesRegex(audit.ValidationError, 'anchors'):
            audit.validate_document(invalid, self.specifications(), document.digest)

    def test_references_resolve_to_named_source_records(self):
        sources = self.sources()
        audit.validate_references(self.specifications(), sources)
        symbol = sources.tests['m'].find('Examples.test_example')
        self.assertEqual(symbol.name, 'test_example')

    def test_missing_implementation_and_unknown_test_source_are_rejected(self):
        sources = self.sources()
        missing = audit.parse_specifications('001|Direct|Example|absent|m:test_example|')
        with self.assertRaisesRegex(audit.ValidationError, 'absent'):
            audit.validate_references(missing, sources)
        unknown = audit.parse_specifications('001|Direct|Example|calculate|unknown:test_example|')
        with self.assertRaisesRegex(audit.ValidationError, 'Unknown test source'):
            audit.validate_references(unknown, sources)

    def test_ambiguous_method_names_require_qualification(self):
        source = audit.SourceFile(Path('example.py'), (
            audit.SourceSymbol('check', 'First.check', 1), audit.SourceSymbol('check', 'Second.check', 5),
        ))
        with self.assertRaisesRegex(audit.AuditError, 'found 2'):
            source.find('check')
        self.assertEqual(source.find('Second.check').line, 5)

    def test_source_index_preserves_class_qualification(self):
        tree = ast.parse('class First:\n    def check(self):\n        return True\n')
        symbols = audit.source_symbols(tree.body)
        self.assertEqual(symbols[0].qualified_name, 'First.check')
        self.assertEqual(symbols[0].line, 2)

    def test_failed_test_results_are_library_errors(self):
        execution = audit.TestExecution(1, False, 'test failure details', frozenset())
        with self.assertRaisesRegex(audit.AuditError, 'test failure details'):
            audit.validate_execution(execution, self.sources().implementation)

    def test_uncalled_functions_are_rejected(self):
        execution = audit.TestExecution(1, True, '', frozenset())
        with self.assertRaisesRegex(audit.ValidationError, 'calculate'):
            audit.validate_execution(execution, self.sources().implementation)

    def test_standard_trace_is_restored_after_test_execution(self):
        previous = sys.gettrace()
        suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        execution = audit.execute_suite(suite, self.sources().implementation)
        self.assertTrue(execution.successful)
        self.assertIs(sys.gettrace(), previous)

    def test_standard_trace_is_restored_after_runner_failure(self):
        previous = sys.gettrace()
        with patch('unittest.TextTestRunner.run', side_effect=RuntimeError('runner failed')):
            with self.assertRaisesRegex(RuntimeError, 'runner failed'):
                audit.execute_suite(unittest.TestSuite(), self.sources().implementation)
        self.assertIs(sys.gettrace(), previous)

    def test_report_rendering_is_pure_and_uses_resolved_source_links(self):
        sources = self.sources()
        result = audit.VerificationResult(Path(__file__).resolve().parent, self.document(),
                                          self.specifications(), sources,
                                          audit.TestExecution(1, True, '', frozenset({'calculate'})))
        report = audit.render_report(result)
        self.assertIn('[E001](README.md#eq-001)', report)
        self.assertIn('[E002](README.md#eq-002)', report)
        self.assertIn('[calculate](mini_model.py#L1)', report)
        self.assertIn('[test_example](test_mini_model.py#L1)', report)
        self.assertNotIn('{{equation_count}}', report)

    def test_command_line_reports_errors_without_exiting_from_library(self):
        error = io.StringIO()
        with patch('verify_formulas.verify', side_effect=audit.ValidationError(['invalid mapping'])):
            with patch('sys.stderr', error):
                self.assertEqual(audit.main(['--check']), 1)
        self.assertIn('invalid mapping', error.getvalue())


if __name__ == '__main__':
    unittest.main()

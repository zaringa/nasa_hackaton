import unittest

import numpy as np

import mini_model as model


class FormulaTests(unittest.TestCase):
    def test_spherical_coordinates_and_observer(self):
        position = model.observer_position(1_737_400, 1000, 2, 0, 0)
        np.testing.assert_allclose(position, [1_738_402, 0, 0])
        radius, latitude, longitude = model.spherical_coordinates(position)
        np.testing.assert_allclose([radius, latitude, longitude], [1_738_402, 0, 0])
        np.testing.assert_allclose(model.degrees_to_radians([0, 90, 180]), [0, np.pi/2, np.pi])
        np.testing.assert_allclose(model.radians_to_degrees(np.pi), 180)

    def test_basis_and_document_example(self):
        basis = model.local_basis(np.pi/6, 0)
        np.testing.assert_allclose(basis.T @ basis, np.eye(3), atol=1e-15)
        np.testing.assert_allclose(np.cross(basis[:, 0], basis[:, 1]), basis[:, 2])
        vector = np.array([np.sqrt(3)/2, 1, 2.5])
        enu = model.global_to_local(vector, basis)
        np.testing.assert_allclose(enu, [1, np.sqrt(3), 2])
        np.testing.assert_allclose(model.local_to_global(enu, basis), vector)
        azimuth, elevation = model.azimuth_elevation(vector, basis)
        np.testing.assert_allclose(model.radians_to_degrees([azimuth, elevation]), [30, 45])
        self.assertAlmostEqual(elevation, model.elevation_from_sine(vector, basis))

    def test_position_derivatives(self):
        radius, phi, lam, step = 10., 0.4, 0.7, 1e-6
        derivatives = model.position_derivatives(radius, phi, lam)
        inputs = np.array([radius, phi, lam])
        for index, expected in enumerate(derivatives):
            delta = np.eye(3)[index]*step
            numerical = (model.spherical_position(*(inputs+delta))
                         - model.spherical_position(*(inputs-delta)))/(2*step)
            np.testing.assert_allclose(numerical, expected, atol=1e-8)

    def test_vertical_and_zero_directions(self):
        azimuth, elevation = model.azimuth_elevation([0, 0, 1], np.eye(3))
        self.assertTrue(np.isnan(azimuth))
        self.assertAlmostEqual(elevation, np.pi/2)
        horizon = lambda azimuth: np.zeros_like(azimuth)
        self.assertTrue(model.terrain_visibility([0, 0, 1], np.eye(3), horizon))
        self.assertFalse(model.terrain_visibility([0, 0, -1], np.eye(3), horizon))
        with self.assertRaises(ValueError):
            model.azimuth_elevation([0, 0, 0], np.eye(3))

    def test_curvature_and_coverage_examples(self):
        radius = 1_737_400.
        angle = model.terrain_elevation_angle(radius+1000, radius+2, 20_000/radius)
        self.assertAlmostEqual(float(model.radians_to_degrees(angle)), 2.5260574015)
        self.assertAlmostEqual(model.curvature_drop(20_000, radius), 115.1145389663)
        horizon = model.smooth_sphere_horizon(radius, 2)
        self.assertAlmostEqual(float(model.radians_to_degrees(horizon)), -0.0869365719)
        self.assertAlmostEqual(model.smooth_sphere_horizon_distance(radius, 2), 2636.2081354)
        _, distance = model.terrain_coverage_limit(radius, radius+1000, radius+2, radius)
        self.assertAlmostEqual(distance/1000, 61.5695107029)
        np.testing.assert_allclose(model.ground_level_sphere_elevation([0.2, 0.4]), [-0.1, -0.2])

    def test_exact_terrain_matches_vector_geometry(self):
        basis = model.local_basis(-1.4, 0.8)
        observer = 10*basis[:, 2]
        psi, azimuth, terrain_radius = 0.03, 1.2, 10.5
        terrain = terrain_radius*model.great_circle_direction(psi, azimuth, basis)
        measured_azimuth, elevation = model.azimuth_elevation(terrain-observer, basis)
        self.assertAlmostEqual(measured_azimuth, azimuth)
        self.assertAlmostEqual(elevation, model.terrain_elevation_angle(terrain_radius, 10, psi))
        self.assertLess(model.observer_height_sensitivity(terrain_radius, 10, psi), 0)

    def test_sampled_horizon_and_north_wrap(self):
        radius, height = 1_737_400., 2.
        basis = model.local_basis(0, 0)
        tangent = -model.smooth_sphere_horizon(radius, height)
        azimuths = np.arange(4)*np.pi/2
        horizon, profile = model.build_sampled_horizon(
            azimuths, [tangent/2, tangent, 2*tangent], lambda phi, lam: 0,
            radius, (radius+height)*basis[:, 2], basis,
        )
        np.testing.assert_allclose(profile, -tangent, atol=1e-12)
        self.assertAlmostEqual(horizon(-1e-8), horizon(2*np.pi-1e-8))
        self.assertLess(horizon(0), 0)
        with self.assertRaises(ValueError):
            model.make_horizon([0, np.pi], [0, np.nan])

    def test_disc_formula_and_area_integral(self):
        radius = 0.01
        offsets = np.array([-2, -1, -0.5, 0, 0.5, 1, 2])*radius
        expected = [0, 0, 0.1955011095, 0.5, 0.8044988905, 1, 1]
        np.testing.assert_allclose(model.flat_disc_fraction(offsets, radius), expected)
        area = (model.disc_area_antiderivative(radius, radius)
                - model.disc_area_antiderivative(radius/2, radius))
        self.assertAlmostEqual(area, model.flat_disc_visible_area(-radius/2, radius))
        y = np.linspace(radius/2, radius, 100_001)
        numerical = model.time_integral(y, model.disc_strip_width(y, radius))
        self.assertAlmostEqual(numerical, area, places=10)

    def test_disc_samples_converge_to_straight_boundary(self):
        radius = 0.005
        rays = model.disc_sample_directions([0, 1, 0], radius, 20_000)
        np.testing.assert_allclose(np.linalg.norm(rays, axis=1), 1)
        for k in [-0.5, 0, 0.5]:
            horizon = lambda azimuth: np.zeros_like(azimuth)-k*radius
            mask = model.terrain_visibility(rays, np.eye(3), horizon)
            self.assertAlmostEqual(model.weighted_visible_fraction(mask),
                                   model.flat_disc_fraction(k*radius, radius), delta=0.001)

    def test_combined_masks_and_occultation(self):
        first = np.array([True, True, False, False])
        self.assertEqual(model.weighted_visible_fraction(first & first), 0.5)
        self.assertEqual(model.weighted_visible_fraction(first & ~first), 0)
        horizon = lambda azimuth: np.zeros_like(azimuth)
        blocked = model.solar_visibility([0, 100, 100], [0, 1, 1], 0.5, 0.2,
                                          np.eye(3), horizon)
        self.assertEqual(blocked['sun_fraction'], 0)
        self.assertEqual(blocked['terrain_fraction'], 1)
        open_rays = model.earth_open_mask([[1, 0, 0], [0, 1, 0]], [10, 0, 0], 1)
        np.testing.assert_array_equal(open_rays, [False, True])
        self.assertAlmostEqual(model.disc_terrain_fraction([0, 100, 100], 1,
                                                           np.eye(3), horizon), 1)

    def test_panel_power_and_radiance(self):
        self.assertAlmostEqual(model.panel_power(2, 0.3, 1000, 0.5,
                                                 [0, 0, 1], [np.sqrt(3), 0, 1]), 150)
        self.assertEqual(model.panel_power(2, 0.3, 1000, 1, [0, 0, 1], [0, 0, -1]), 0)
        self.assertEqual(model.irradiance_at_distance(1000, 1, 2), 250)
        value = model.panel_power_from_radiance(
            2, 0.3, 1000, [[0, 0, 1], [1, 0, 0]], [True, True], [0.1, 0.1], [0, 0, 1]
        )
        self.assertAlmostEqual(value, 60)

    def test_event_times(self):
        self.assertAlmostEqual(model.linear_transition_time(0, -0.2, 3600, 0.4), 1200)
        root = model.refine_transition(lambda time: time*time-2, 0, 2, 1e-8)
        self.assertAlmostEqual(root, np.sqrt(2), delta=1e-8)
        step = model.refine_state_transition(lambda time: time >= 0.3, 0, 1, 1e-8)
        self.assertAlmostEqual(step, 0.3, delta=1e-8)
        with self.assertRaises(ValueError):
            model.refine_transition(lambda time: time+1, 0, 2, 0.01)

    def test_windows_and_duration(self):
        windows = model.windows_from_samples([0, 1, 2], [-1, 1, -1])
        np.testing.assert_allclose(windows, [[0.5, 1.5]])
        self.assertEqual(model.total_duration(windows), 1)
        self.assertEqual(model.longest_duration(windows), 1)
        self.assertEqual(model.longest_duration([]), 0)
        self.assertEqual(model.complement_windows(windows, 0, 2), [(0, 0.5), (1.5, 2)])
        self.assertEqual(model.intersect_windows([(0, 3), (5, 7)], [(2, 6)]), [(2, 3), (5, 6)])
        self.assertEqual(model.time_to_next_event([0.5, 1.5], 0), 0.5)
        self.assertIsNone(model.time_to_next_event([0.5, 1.5], 2))
        self.assertEqual(model.windows_from_samples([0, 1, 2], [0, 0, 0]), [])
        np.testing.assert_array_equal(model.illumination_indicator([0, 0.1], 0), [False, True])
        np.testing.assert_array_equal(model.joint_indicator([True, False], [True, True]), [1, 0])
        np.testing.assert_array_equal(model.power_indicator([0, 5, 10], 5), [False, True, True])

    def test_integrals_use_elapsed_time(self):
        self.assertEqual(model.time_integral([0, 10, 30], [0, 2, 2]), 50)
        times = [0, 3600, 7200, 10800]
        fraction = [1, 1, 0, 0]
        self.assertEqual(model.equivalent_full_disc_time(times, fraction), 5400)
        self.assertEqual(model.electrical_energy([0, 3600], [2, 2]),
                         {'joules': 7200, 'watt_hours': 2})
        self.assertEqual(model.transition_time_uncertainty(0.01, 0.001), 10)

    def test_complete_calculation_uses_explicit_formulas(self):
        times = np.array([0, 3600, 7200])
        result = model.analyze(
            latitude_deg=0, longitude_deg=0, reference_radius_m=1_737_400,
            ground_elevation_m=0, height_m=2,
            horizon=lambda azimuth: np.zeros_like(azimuth), times_s=times,
            sun_vectors_m=np.tile([1000, 0, 0], (3, 1)),
            earth_vectors_m=np.tile([10, 0, 10], (3, 1)),
            sun_radius_m=1, earth_radius_m=1, panel_area_m2=2, panel_efficiency=0.3,
            panel_normal_enu=[0, 0, 1], irradiance_w_m2=1000,
        )
        self.assertEqual(result['metrics']['sunlight_seconds'], 7200)
        self.assertEqual(result['metrics']['earth_visible_seconds'], 7200)
        self.assertEqual(result['metrics']['joint_seconds'], 7200)
        self.assertEqual(result['metrics']['equivalent_full_disc_seconds'], 7200)
        self.assertEqual(result['metrics']['longest_darkness_seconds'], 0)
        np.testing.assert_allclose(result['power_w'], [600, 600, 600])
        self.assertEqual(result['energy']['watt_hours'], 1200)


if __name__ == '__main__':
    unittest.main()

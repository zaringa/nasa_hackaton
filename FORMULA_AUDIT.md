# Formula implementation audit

All 139 displayed equation blocks in README are individually mapped below to implementation locations and executable evidence. The mapping contains exactly one row per block. 52 tests passed under Python 3.12.3 with NumPy 1.26.4. All 69 top-level implementation functions were called by the tests. Classification counts: Approximation: 7, Definition: 2, Derivation: 13, Direct: 81, Example: 19, Identity: 7, Input: 3, Numerical: 7.

The verifier ran inside a virtual environment: True. Function-call coverage means every function was exercised at least once; it does not mean every branch or every possible input was covered.

This is a correspondence audit with analytical explanations and numerical tests. It is not a machine-checked proof for every possible input. Repeated expressions, intermediate derivation steps, identities, input definitions, and examples are distinguished from executable algorithms. Passing a related test is evidence for the named relation, not a claim that finite tests establish a universal theorem.

## How to reproduce

```sh
source .venv/bin/activate
python -B verify_formulas.py
```

The verifier checks the fingerprint of all 139 formula blocks, requires a unique mapping for every block, confirms the referenced implementation and test functions exist, runs both test suites, and regenerates this report. A changed equation stops verification until the mapping is reviewed.

## Why the main transformations are equivalent

### Coordinate matrices

The document stores a mathematical vector as a column and writes $v_{ENU}=B^{\mathsf T}v_{XYZ}$. NumPy stores a single vector as a one-dimensional array. The code computes its row-vector equivalent, $v_{XYZ}^{\mathsf T}B=(B^{\mathsf T}v_{XYZ})^{\mathsf T}$. Each output entry is therefore the same dot product. Tests check the dot products independently and recover the original vector through the inverse transformation.

### The piecewise circular segment formula

The implementation evaluates the interior formula with $k$ clipped to $[-1,1]$. At $k=-1$, $\arcsin(-1)=-\pi/2$ and the square-root term is zero, so $f=0$. At $k=1$ the result is $f=1$. For $-1<k<1$, clipping leaves $k$ unchanged. This is the same three-case formula in equation 088, within the planar small-disc assumptions. Separate tests differentiate the area antiderivative numerically and compare the strip integral with the closed form.

### Visibility masks

For indicators taking only values zero and one, multiplication equals logical AND. Thus `terrain_mask & earth_mask` represents $M_T M_E$ for each ray. Averaging happens after this intersection. The tests also compare Earth's angular mask with an independent ray-sphere intersection calculation.

### Integrals and their numerical representations

A finite sampled maximum approximates a continuous terrain supremum. Equal-area sums approximate disc integrals. Trapezoids approximate a continuous time integral and are exact only for the chosen piecewise-linear interpolant. The `method="interval"` mode evaluates $\sum_i f_i(t_{i+1}-t_i)$ exactly for supplied piecewise-constant intervals. In the document example, edges `[0, 7200, 10800]` and fractions `[1, 0.5]` return 9000 seconds, or 2.5 hours. Those same edges with powers `[2, 1]` return 18000 J, or 5 Wh.

## Concrete reproduced results

| Calculation | Reproduced result | Evidence |
| --- | --- | --- |
| ENU example | $E=1$, $N=\sqrt3$, $U=2$, $A=30^\circ$, $\varepsilon=45^\circ$ | `test_basis_and_document_example` |
| Smooth lunar sphere at 2 m | $H\approx-0.0869365719^\circ$ | `test_curvature_and_coverage_examples` |
| Offset disc with $k=-0.5$ | $f\approx0.1955011095$ | `test_disc_formula_and_area_integral` |
| Rise from $-0.2^\circ$ to $+0.4^\circ$ over one hour | Crossing after 1200 s or 20 min | `test_event_times` |
| Two hours fully visible plus one hour half visible | $T_{eq}=2.5$ h with interval integration | `test_exact_two_full_hours_plus_one_half_visible_hour` |

## What this does not establish

No actual lunar DEM or SPICE kernel set is supplied. The SPICE test checks wrapper arguments and metre/kilometre conversions using a stub; it does not validate real ephemerides. DEM reading, global elevation bounds, and frame metadata remain external inputs. The finite terrain scan is not a certified adaptive ray tracer. The sampled time workflow can miss an event between matching endpoint states; a test explicitly demonstrates that limitation. No test claims to recover unknown observations.

The combined `analyze` function uses the central-direction power approximation and interpolated window boundaries. The general radiance quadrature and root-refinement functions exist separately; their presence does not mean the combined workflow automatically uses them. The interval integrator requires interval-valued inputs; it does not infer discontinuities from point samples.

## Classification key

| Status | Meaning |
| --- | --- |
| Direct | The algebraic expression or its equivalent finite operation is implemented within its stated model |
| Numerical | A continuous supremum, integral, or root is represented by a finite numerical procedure |
| Approximation | The equation itself uses an approximation such as small angles or local linearization |
| Derivation | An intermediate algebraic or calculus step supporting an implemented expression |
| Identity | A property of the computed values, checked by tests |
| Definition | A coordinate convention or a mathematical object definition |
| Example | Supplied illustrative values and their expected results |
| Input | A datum or bound to be supplied by the caller, not inferred without data |

## Complete equation mapping

| Equation in README | Meaning | Status | Implementation | Executable evidence | Interpretation |
| --- | --- | --- | --- | --- | --- |
| [E001](README.md#eq-001) | Reference sphere radius | Input | [observer_position](mini_model.py#L32) | [test_spherical_coordinates_and_observer](test_mini_model.py#L9) | The dataset radius is supplied by the caller; the numerical value is an example. |
| [E002](README.md#eq-002) | Degrees to radians | Direct | [degrees_to_radians](mini_model.py#L5) | [test_spherical_coordinates_and_observer](test_mini_model.py#L9) |  |
| [E003](README.md#eq-003) | Spherical position components | Direct | [spherical_position](mini_model.py#L28), [radial_direction](mini_model.py#L22) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E004](README.md#eq-004) | Spherical position components | Direct | [spherical_position](mini_model.py#L28), [radial_direction](mini_model.py#L22) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E005](README.md#eq-005) | Spherical position components | Direct | [spherical_position](mini_model.py#L28), [radial_direction](mini_model.py#L22) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E006](README.md#eq-006) | Spherical position components | Direct | [spherical_position](mini_model.py#L28), [radial_direction](mini_model.py#L22) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E007](README.md#eq-007) | Positions on the coordinate axes | Example | [spherical_position](mini_model.py#L28) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E008](README.md#eq-008) | Radial unit vector | Direct | [radial_direction](mini_model.py#L22), [unit_vector](mini_model.py#L13) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E009](README.md#eq-009) | Site ground elevation | Input | [observer_position](mini_model.py#L32), [build_sampled_horizon](mini_model.py#L135) | [test_spherical_coordinates_and_observer](test_mini_model.py#L9) | Ground elevation is supplied; actual DEM reading is an external data input. |
| [E010](README.md#eq-010) | Observer radius and position | Direct | [observer_position](mini_model.py#L32) | [test_spherical_coordinates_and_observer](test_mini_model.py#L9) |  |
| [E011](README.md#eq-011) | Ground elevation plus spacecraft height | Example | [observer_position](mini_model.py#L32) | [test_spherical_coordinates_and_observer](test_mini_model.py#L9) |  |
| [E012](README.md#eq-012) | Terrain point position | Direct | [spherical_position](mini_model.py#L28), [build_sampled_horizon](mini_model.py#L135) | [test_terrain_derivatives_against_finite_differences](test_formula_audit.py#L41) |  |
| [E013](README.md#eq-013) | Radial position derivative | Direct | [position_derivatives](mini_model.py#L56), [local_basis](mini_model.py#L48) | [test_position_derivatives](test_mini_model.py#L29) |  |
| [E014](README.md#eq-014) | Up vector at latitude 30 degrees | Example | [local_basis](mini_model.py#L48) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E015](README.md#eq-015) | First-order longitude increment | Derivation | [position_derivatives](mini_model.py#L56) | [test_first_order_longitude_increment](test_formula_audit.py#L50) | The Taylor step is a derivation; its second-order remainder is checked. |
| [E016](README.md#eq-016) | Longitude derivative | Direct | [position_derivatives](mini_model.py#L56) | [test_position_derivatives](test_mini_model.py#L29) |  |
| [E017](README.md#eq-017) | Normalized east direction | Direct | [local_basis](mini_model.py#L48) | [test_position_derivatives](test_mini_model.py#L29) | The simplified trigonometric result is used directly. |
| [E018](README.md#eq-018) | Latitude derivative | Direct | [position_derivatives](mini_model.py#L56) | [test_position_derivatives](test_mini_model.py#L29) |  |
| [E019](README.md#eq-019) | Normalized north direction | Direct | [local_basis](mini_model.py#L48) | [test_position_derivatives](test_mini_model.py#L29) |  |
| [E020](README.md#eq-020) | North vector at latitude 30 degrees | Example | [local_basis](mini_model.py#L48) | [test_coordinate_axes_and_basis_example](test_formula_audit.py#L16) |  |
| [E021](README.md#eq-021) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E022](README.md#eq-022) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E023](README.md#eq-023) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E024](README.md#eq-024) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E025](README.md#eq-025) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E026](README.md#eq-026) | Unit lengths orthogonality and orientation | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | These are properties of the returned basis, not six separate algorithms. |
| [E027](README.md#eq-027) | Terrain derivative with a variable radius | Direct | [terrain_derivatives](mini_model.py#L61) | [test_terrain_derivatives_against_finite_differences](test_formula_audit.py#L41) |  |
| [E028](README.md#eq-028) | Vector expansion in the local basis | Direct | [local_to_global](mini_model.py#L74) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) |  |
| [E029](README.md#eq-029) | Dot product isolates the east component | Derivation | [global_to_local](mini_model.py#L70) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) | The intermediate cancellation follows from orthonormality. |
| [E030](README.md#eq-030) | Local components as dot products | Direct | [global_to_local](mini_model.py#L70) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) |  |
| [E031](README.md#eq-031) | Basis matrix columns | Definition | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) |  |
| [E032](README.md#eq-032) | ENU to XYZ | Direct | [local_to_global](mini_model.py#L74) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) |  |
| [E033](README.md#eq-033) | XYZ to ENU | Direct | [global_to_local](mini_model.py#L70) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) | NumPy uses row-vector storage; v @ B equals the transpose of B.T @ column_v. |
| [E034](README.md#eq-034) | Inverse equals transpose | Identity | [local_basis](mini_model.py#L48) | [test_basis_identities_on_many_sites](test_formula_audit.py#L25) | An algebraic property; no runtime matrix inversion is needed. |
| [E035](README.md#eq-035) | Observer-relative body vector | Direct | [observer_to_body](mini_model.py#L78) | [test_local_projections_and_origin_subtraction](test_formula_audit.py#L33) |  |
| [E036](README.md#eq-036) | Horizontal vector length | Direct | [azimuth_elevation](mini_model.py#L83) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E037](README.md#eq-037) | Elevation tangent relation | Derivation | [azimuth_elevation](mini_model.py#L83) | [test_azimuth_convention_and_component_reconstruction](test_formula_audit.py#L59) |  |
| [E038](README.md#eq-038) | Elevation using atan2 | Direct | [azimuth_elevation](mini_model.py#L83) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E039](README.md#eq-039) | Equivalent elevation using arcsine | Direct | [elevation_from_sine](mini_model.py#L92) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E040](README.md#eq-040) | Azimuth origin and orientation | Definition | [azimuth_elevation](mini_model.py#L83) | [test_azimuth_convention_and_component_reconstruction](test_formula_audit.py#L59) |  |
| [E041](README.md#eq-041) | Horizontal components from azimuth | Direct | [horizontal_components](mini_model.py#L96) | [test_azimuth_convention_and_component_reconstruction](test_formula_audit.py#L59) |  |
| [E042](README.md#eq-042) | Azimuth using atan2 | Direct | [azimuth_elevation](mini_model.py#L83) | [test_azimuth_convention_and_component_reconstruction](test_formula_audit.py#L59) |  |
| [E043](README.md#eq-043) | Numerical ENU basis | Example | [local_basis](mini_model.py#L48) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E044](README.md#eq-044) | Illustrative input vector | Example | [global_to_local](mini_model.py#L70) | [test_basis_and_document_example](test_mini_model.py#L17) | A test fixture, not an observation or a function to calculate that vector. |
| [E045](README.md#eq-045) | Projected vector and its angles | Example | [global_to_local](mini_model.py#L70), [azimuth_elevation](mini_model.py#L83) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E046](README.md#eq-046) | Projected vector and its angles | Example | [global_to_local](mini_model.py#L70), [azimuth_elevation](mini_model.py#L83) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E047](README.md#eq-047) | Projected vector and its angles | Example | [global_to_local](mini_model.py#L70), [azimuth_elevation](mini_model.py#L83) | [test_basis_and_document_example](test_mini_model.py#L17) |  |
| [E048](README.md#eq-048) | Continuous terrain supremum | Numerical | [build_sampled_horizon](mini_model.py#L135), [make_horizon](mini_model.py#L121) | [test_sampled_horizon_and_north_wrap](test_mini_model.py#L71) | A maximum over finite terrain samples followed by periodic interpolation approximates the supremum. |
| [E049](README.md#eq-049) | Angular clearance above terrain | Direct | [angular_clearance](mini_model.py#L154) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E050](README.md#eq-050) | Horizontal direction and great-circle direction | Direct | [great_circle_direction](mini_model.py#L101) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E051](README.md#eq-051) | Horizontal direction and great-circle direction | Direct | [great_circle_direction](mini_model.py#L101) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E052](README.md#eq-052) | Terrain radius from reference radius and elevation | Direct | [build_sampled_horizon](mini_model.py#L135) | [test_sampled_horizon_and_north_wrap](test_mini_model.py#L71) |  |
| [E053](README.md#eq-053) | Terrain vector components and exact elevation angle | Direct | [great_circle_direction](mini_model.py#L101), [terrain_elevation_angle](mini_model.py#L108) | [test_exact_terrain_matches_vector_geometry](test_mini_model.py#L61) |  |
| [E054](README.md#eq-054) | Terrain vector components and exact elevation angle | Direct | [great_circle_direction](mini_model.py#L101), [terrain_elevation_angle](mini_model.py#L108) | [test_exact_terrain_matches_vector_geometry](test_mini_model.py#L61) |  |
| [E055](README.md#eq-055) | Terrain vector components and exact elevation angle | Direct | [great_circle_direction](mini_model.py#L101), [terrain_elevation_angle](mini_model.py#L108) | [test_exact_terrain_matches_vector_geometry](test_mini_model.py#L61) |  |
| [E056](README.md#eq-056) | Horizon as the supremum along a direction | Numerical | [build_sampled_horizon](mini_model.py#L135) | [test_sampled_horizon_and_north_wrap](test_mini_model.py#L71) | Finite scan samples do not guarantee detection of every intervening ridge. |
| [E057](README.md#eq-057) | Small-angle sine and cosine expansions | Derivation | [approximate_terrain_elevation](mini_model.py#L170) | [test_small_angle_curvature_and_flat_comparison](test_formula_audit.py#L82) | The truncated expansions justify the approximation; the exact path uses NumPy sine and cosine. |
| [E058](README.md#eq-058) | Terrain elevation with curvature drop | Approximation | [approximate_terrain_elevation](mini_model.py#L170), [curvature_drop](mini_model.py#L166) | [test_small_angle_curvature_and_flat_comparison](test_formula_audit.py#L82) | Requires small central angles and elevations small relative to the reference radius. |
| [E059](README.md#eq-059) | Terrain elevation with curvature drop | Approximation | [approximate_terrain_elevation](mini_model.py#L170), [curvature_drop](mini_model.py#L166) | [test_small_angle_curvature_and_flat_comparison](test_formula_audit.py#L82) | Requires small central angles and elevations small relative to the reference radius. |
| [E060](README.md#eq-060) | Flat-surface summit elevation comparison | Example | [approximate_terrain_elevation](mini_model.py#L170) | [test_small_angle_curvature_and_flat_comparison](test_formula_audit.py#L82) | The flat comparison is an example evaluated with atan2 in the test; the related runtime function includes curvature. |
| [E061](README.md#eq-061) | Spherical summit angle and curvature drop | Example | [terrain_elevation_angle](mini_model.py#L108), [curvature_drop](mini_model.py#L166) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E062](README.md#eq-062) | Spherical summit angle and curvature drop | Example | [terrain_elevation_angle](mini_model.py#L108), [curvature_drop](mini_model.py#L166) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E063](README.md#eq-063) | Tangent triangle horizon angle | Derivation | [smooth_sphere_horizon](mini_model.py#L176) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E064](README.md#eq-064) | Negative smooth-sphere horizon | Direct | [smooth_sphere_horizon](mini_model.py#L176) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E065](README.md#eq-065) | Lunar horizon and horizon distance at 2 m | Example | [smooth_sphere_horizon](mini_model.py#L176), [smooth_sphere_horizon_distance](mini_model.py#L182) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E066](README.md#eq-066) | Ground-level sphere elevation and limiting supremum | Direct | [ground_level_sphere_elevation](mini_model.py#L186) | [test_ground_level_horizon_is_a_supremum](test_formula_audit.py#L93) | The sampled maximum at h=0 can be negative although the continuous supremum is zero. |
| [E067](README.md#eq-067) | Global minimum and maximum terrain radii | Input | [terrain_coverage_limit](mini_model.py#L191) | [test_coverage_bound_against_line_segment_occlusion](test_formula_audit.py#L112) | Actual guaranteed global bounds must come from the surface model. |
| [E068](README.md#eq-068) | Two tangent angles and sufficient terrain coverage | Direct | [terrain_coverage_limit](mini_model.py#L191) | [test_coverage_bound_against_line_segment_occlusion](test_formula_audit.py#L112) | The segment test independently checks inner-sphere obstruction beyond the computed bound. |
| [E069](README.md#eq-069) | Two tangent angles and sufficient terrain coverage | Direct | [terrain_coverage_limit](mini_model.py#L191) | [test_coverage_bound_against_line_segment_occlusion](test_formula_audit.py#L112) | The segment test independently checks inner-sphere obstruction beyond the computed bound. |
| [E070](README.md#eq-070) | Two tangent angles and sufficient terrain coverage | Direct | [terrain_coverage_limit](mini_model.py#L191) | [test_coverage_bound_against_line_segment_occlusion](test_formula_audit.py#L112) | The segment test independently checks inner-sphere obstruction beyond the computed bound. |
| [E071](README.md#eq-071) | Illustrative global radius bounds | Example | [terrain_coverage_limit](mini_model.py#L191) | [test_curvature_and_coverage_examples](test_mini_model.py#L49) |  |
| [E072](README.md#eq-072) | Feature angular width | Approximation | [feature_angular_width](mini_model.py#L200) | [test_feature_width_and_uncertainty](test_formula_audit.py#L124) | Uses the small-angle width divided by distance approximation. |
| [E073](README.md#eq-073) | Body distance and angular radius | Direct | [angular_radius](mini_model.py#L219) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E074](README.md#eq-074) | Body distance and angular radius | Direct | [angular_radius](mini_model.py#L219) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E075](README.md#eq-075) | Body distance and angular radius | Direct | [angular_radius](mini_model.py#L219) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E076](README.md#eq-076) | Illustrative solar angular radius | Example | [angular_radius](mini_model.py#L219) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E077](README.md#eq-077) | Centre clearance above a straight boundary | Direct | [angular_clearance](mini_model.py#L154) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E078](README.md#eq-078) | Fully blocked partially visible and fully visible cases | Direct | [flat_disc_fraction](mini_model.py#L238) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) | Exact within the adopted planar small-disc model. |
| [E079](README.md#eq-079) | Planar circular domain and strip endpoints | Derivation | [disc_strip_width](mini_model.py#L227), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | The circle is a model definition and the square-root endpoints lead to the strip width. |
| [E080](README.md#eq-080) | Planar circular domain and strip endpoints | Derivation | [disc_strip_width](mini_model.py#L227), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | The circle is a model definition and the square-root endpoints lead to the strip width. |
| [E081](README.md#eq-081) | Circular strip width and area element | Direct | [disc_strip_width](mini_model.py#L227) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E082](README.md#eq-082) | Visible circular area from its antiderivative | Direct | [flat_disc_visible_area](mini_model.py#L245), [disc_area_antiderivative](mini_model.py#L231) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) | The planar integral is evaluated in closed form. |
| [E083](README.md#eq-083) | Trigonometric substitution in the area integral | Derivation | [disc_area_antiderivative](mini_model.py#L231) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) | The substitution is a derivation step, not an additional runtime algorithm. |
| [E084](README.md#eq-084) | Trigonometric substitution in the area integral | Derivation | [disc_area_antiderivative](mini_model.py#L231) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) | The substitution is a derivation step, not an additional runtime algorithm. |
| [E085](README.md#eq-085) | Area antiderivative and its lower-limit evaluation | Direct | [disc_area_antiderivative](mini_model.py#L231) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E086](README.md#eq-086) | Area antiderivative and its lower-limit evaluation | Direct | [disc_area_antiderivative](mini_model.py#L231) | [test_angular_disc_geometry_and_area_derivative](test_formula_audit.py#L132) |  |
| [E087](README.md#eq-087) | Normalized clearance and circular-segment fraction | Direct | [flat_disc_fraction](mini_model.py#L238) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) | Clipping k to [-1,1] is algebraically equivalent to the three cases. |
| [E088](README.md#eq-088) | Normalized clearance and circular-segment fraction | Direct | [flat_disc_fraction](mini_model.py#L238) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) | Clipping k to [-1,1] is algebraically equivalent to the three cases. |
| [E089](README.md#eq-089) | Half and offset disc fractions | Example | [flat_disc_fraction](mini_model.py#L238) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) |  |
| [E090](README.md#eq-090) | Half and offset disc fractions | Example | [flat_disc_fraction](mini_model.py#L238) | [test_disc_formula_and_area_integral](test_mini_model.py#L86) |  |
| [E091](README.md#eq-091) | Terrain ray mask | Direct | [terrain_visibility](mini_model.py#L158) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E092](README.md#eq-092) | Visible-area integral for uneven terrain | Numerical | [disc_terrain_fraction](mini_model.py#L273), [weighted_visible_fraction](mini_model.py#L265) | [test_disc_samples_converge_to_straight_boundary](test_mini_model.py#L98) | Finite equal-area samples approximate the integral; a straight-boundary analytic result is checked. |
| [E093](README.md#eq-093) | Weighted and equal-weight visible sums | Direct | [weighted_visible_fraction](mini_model.py#L265) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) |  |
| [E094](README.md#eq-094) | Weighted and equal-weight visible sums | Direct | [weighted_visible_fraction](mini_model.py#L265) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) |  |
| [E095](README.md#eq-095) | Square-root radius law for equal-area samples | Direct | [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) |  |
| [E096](README.md#eq-096) | Disc basis coordinates and normalized ray directions | Direct | [unit_vector](mini_model.py#L13), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | Directions use the stated planar tangent projection and small-disc area interpretation. |
| [E097](README.md#eq-097) | Disc basis coordinates and normalized ray directions | Direct | [unit_vector](mini_model.py#L13), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | Directions use the stated planar tangent projection and small-disc area interpretation. |
| [E098](README.md#eq-098) | Disc basis coordinates and normalized ray directions | Direct | [unit_vector](mini_model.py#L13), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | Directions use the stated planar tangent projection and small-disc area interpretation. |
| [E099](README.md#eq-099) | Disc basis coordinates and normalized ray directions | Direct | [unit_vector](mini_model.py#L13), [disc_sample_directions](mini_model.py#L250) | [test_disc_sample_coordinates_and_weighted_areas](test_formula_audit.py#L145) | Directions use the stated planar tangent projection and small-disc area interpretation. |
| [E100](README.md#eq-100) | Earth angular radius and centre direction | Direct | [angular_radius](mini_model.py#L219), [earth_open_mask](mini_model.py#L280) | [test_occultation_against_ray_sphere_intersection](test_formula_audit.py#L154) |  |
| [E101](README.md#eq-101) | Angular Earth obstruction and open-ray mask | Direct | [earth_open_mask](mini_model.py#L280) | [test_occultation_against_ray_sphere_intersection](test_formula_audit.py#L154) | The forward ray is also required to intersect a nearer occulting body. |
| [E102](README.md#eq-102) | Angular Earth obstruction and open-ray mask | Direct | [earth_open_mask](mini_model.py#L280) | [test_occultation_against_ray_sphere_intersection](test_formula_audit.py#L154) | The forward ray is also required to intersect a nearer occulting body. |
| [E103](README.md#eq-103) | Angular Earth obstruction and open-ray mask | Direct | [earth_open_mask](mini_model.py#L280) | [test_occultation_against_ray_sphere_intersection](test_formula_audit.py#L154) | The forward ray is also required to intersect a nearer occulting body. |
| [E104](README.md#eq-104) | Terrain and Earth mask intersection | Direct | [solar_visibility](mini_model.py#L286) | [test_combined_masks_and_occultation](test_mini_model.py#L108) |  |
| [E105](README.md#eq-105) | Mean of the combined ray masks | Direct | [solar_visibility](mini_model.py#L286), [weighted_visible_fraction](mini_model.py#L265) | [test_combined_masks_and_occultation](test_mini_model.py#L108) | This finite sum is direct; its approximation to the continuous disc remains numerical. |
| [E106](README.md#eq-106) | Earth centre clearance and visibility indicator | Direct | [solar_visibility](mini_model.py#L286), [point_visibility_indicator](mini_model.py#L351) | [test_great_circle_and_clearance](test_formula_audit.py#L71) |  |
| [E107](README.md#eq-107) | Incidence cosine and projected panel area | Direct | [effective_panel_area](mini_model.py#L320) | [test_panel_power_and_radiance](test_mini_model.py#L122) | The implementation clips a negative projected area to zero for a single-sided panel. |
| [E108](README.md#eq-108) | Incidence cosine and projected panel area | Direct | [effective_panel_area](mini_model.py#L320) | [test_panel_power_and_radiance](test_mini_model.py#L122) | The implementation clips a negative projected area to zero for a single-sided panel. |
| [E109](README.md#eq-109) | Power using the solar centre direction | Approximation | [panel_power](mini_model.py#L325) | [test_panel_power_and_radiance](test_mini_model.py#L122) | Assumes negligible incidence variation over a small uniform-brightness disc. |
| [E110](README.md#eq-110) | Inverse-square irradiance scaling | Direct | [irradiance_at_distance](mini_model.py#L316) | [test_panel_power_and_radiance](test_mini_model.py#L122) |  |
| [E111](README.md#eq-111) | Radiance integral for panel power | Numerical | [panel_power_from_radiance](mini_model.py#L331) | [test_panel_power_and_radiance](test_mini_model.py#L122) | The caller supplies radiance and solid-angle quadrature weights; analyze uses the centre-direction approximation. |
| [E112](README.md#eq-112) | Zero of the continuous clearance function | Numerical | [angular_clearance](mini_model.py#L154), [refine_transition](mini_model.py#L372) | [test_event_times](test_mini_model.py#L132) | Bisection refines an already bracketed root; it does not detect all roots by itself. |
| [E113](README.md#eq-113) | Illumination threshold margin and state | Direct | [illumination_indicator](mini_model.py#L340), [windows_from_samples](mini_model.py#L442) | [test_windows_and_duration](test_mini_model.py#L141) | A zero threshold uses strictly positive light to exclude complete darkness. |
| [E114](README.md#eq-114) | Solving the linear margin interpolation for time | Derivation | [linear_transition_time](mini_model.py#L366) | [test_event_times](test_mini_model.py#L132) | These are algebraic steps leading to the same interpolated crossing time. |
| [E115](README.md#eq-115) | Solving the linear margin interpolation for time | Derivation | [linear_transition_time](mini_model.py#L366) | [test_event_times](test_mini_model.py#L132) | These are algebraic steps leading to the same interpolated crossing time. |
| [E116](README.md#eq-116) | Solving the linear margin interpolation for time | Derivation | [linear_transition_time](mini_model.py#L366) | [test_event_times](test_mini_model.py#L132) | These are algebraic steps leading to the same interpolated crossing time. |
| [E117](README.md#eq-117) | Interpolated crossing time | Approximation | [linear_transition_time](mini_model.py#L366) | [test_event_times](test_mini_model.py#L132) | Exact for the chosen linear interpolant, approximate for a nonlinear physical trajectory. |
| [E118](README.md#eq-118) | Twenty-minute crossing example | Example | [linear_transition_time](mini_model.py#L366) | [test_event_times](test_mini_model.py#L132) |  |
| [E119](README.md#eq-119) | First-order expansion near an event | Derivation | [transition_time_uncertainty](mini_model.py#L544) | [test_taylor_error_and_event_sensitivity](test_formula_audit.py#L172) |  |
| [E120](README.md#eq-120) | Event timing uncertainty from angular uncertainty | Approximation | [transition_time_uncertainty](mini_model.py#L544) | [test_feature_width_and_uncertainty](test_formula_audit.py#L124) | A local first-order sensitivity estimate, with infinite sensitivity at zero rate. |
| [E121](README.md#eq-121) | State duration integral over known windows | Direct | [total_duration](mini_model.py#L469) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) | Exact for the supplied windows; sampled estimates of the window boundaries have separate errors. |
| [E122](README.md#eq-122) | Sum of window lengths | Direct | [total_duration](mini_model.py#L469), [window_durations](mini_model.py#L465) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) |  |
| [E123](README.md#eq-123) | Fraction of analysis time with suitable light | Direct | [analyze](mini_model.py#L551) | [test_complete_calculation_uses_explicit_formulas](test_mini_model.py#L165) |  |
| [E124](README.md#eq-124) | Earth state duration integral over known windows | Direct | [total_duration](mini_model.py#L469) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) |  |
| [E125](README.md#eq-125) | Longest suitable window and longest interruption | Direct | [longest_duration](mini_model.py#L473), [complement_windows](mini_model.py#L477) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) |  |
| [E126](README.md#eq-126) | Longest suitable window and longest interruption | Direct | [longest_duration](mini_model.py#L473), [complement_windows](mini_model.py#L477) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) |  |
| [E127](README.md#eq-127) | Equivalent full-disc time integral | Numerical | [equivalent_full_disc_time](mini_model.py#L531), [time_integral](mini_model.py#L514) | [test_exact_two_full_hours_plus_one_half_visible_hour](test_formula_audit.py#L195) | Trapezoids approximate sampled functions; interval mode is exact for supplied piecewise-constant intervals. |
| [E128](README.md#eq-128) | Two fully visible hours and one half-visible hour | Example | [equivalent_full_disc_time](mini_model.py#L531) | [test_exact_two_full_hours_plus_one_half_visible_hour](test_formula_audit.py#L195) | Interval mode returns exactly 9000 seconds or 2.5 hours. |
| [E129](README.md#eq-129) | Mean visible fraction | Direct | [mean_disc_fraction](mini_model.py#L535) | [test_exact_two_full_hours_plus_one_half_visible_hour](test_formula_audit.py#L195) | The mean inherits the accuracy of the chosen integration method. |
| [E130](README.md#eq-130) | Electrical energy integral | Numerical | [electrical_energy](mini_model.py#L539), [time_integral](mini_model.py#L514) | [test_exact_two_full_hours_plus_one_half_visible_hour](test_formula_audit.py#L195) | Trapezoids or exact integration of supplied piecewise-constant powers. |
| [E131](README.md#eq-131) | Watt-hour to joule conversion | Direct | [electrical_energy](mini_model.py#L539) | [test_integrals_use_elapsed_time](test_mini_model.py#L156) |  |
| [E132](README.md#eq-132) | Trapezoidal integration sum | Direct | [time_integral](mini_model.py#L514) | [test_trapezoid_exactness_and_quadratic_convergence](test_formula_audit.py#L204) | The finite sum is direct; it approximates an unknown continuous power curve. |
| [E133](README.md#eq-133) | Joint state indicator | Direct | [joint_indicator](mini_model.py#L361) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) |  |
| [E134](README.md#eq-134) | Joint duration from interval intersection | Direct | [intersect_windows](mini_model.py#L493), [total_duration](mini_model.py#L469) | [test_duration_integral_and_joint_intersection](test_formula_audit.py#L182) | Exact for the supplied window sets. |
| [E135](README.md#eq-135) | Intersection length of two windows | Direct | [intersect_windows](mini_model.py#L493) | [test_windows_and_duration](test_mini_model.py#L141) |  |
| [E136](README.md#eq-136) | Time remaining until the next actual event | Direct | [time_to_next_event](mini_model.py#L508) | [test_windows_and_duration](test_mini_model.py#L141) | Event times exclude boundaries caused only by the end of the analysis period. |
| [E137](README.md#eq-137) | Smooth-sphere horizon with nonzero DEM elevation | Direct | [smooth_sphere_horizon](mini_model.py#L176) | [test_nonzero_dem_sphere_and_height_sensitivity](test_formula_audit.py#L101) |  |
| [E138](README.md#eq-138) | Terrain angle derivative with observer height | Direct | [observer_height_sensitivity](mini_model.py#L114) | [test_nonzero_dem_sphere_and_height_sensitivity](test_formula_audit.py#L101) |  |
| [E139](README.md#eq-139) | Elevation uncertainty from terrain height uncertainty | Approximation | [elevation_uncertainty](mini_model.py#L204) | [test_feature_width_and_uncertainty](test_formula_audit.py#L124) | Uses small angles and a small height-to-distance ratio. |

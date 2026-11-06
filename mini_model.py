import numpy as np


# Block 1: Units and input vectors
def degrees_to_radians(angle_deg):
    return np.asarray(angle_deg, dtype=float) * np.pi / 180.0


def radians_to_degrees(angle_rad):
    return np.asarray(angle_rad, dtype=float) * 180.0 / np.pi


def unit_vector(vector):
    vector = np.asarray(vector, dtype=float)
    length = np.linalg.norm(vector, axis=-1, keepdims=True)
    if np.any(length == 0) or not np.all(np.isfinite(vector)):
        raise ValueError("A direction requires a finite nonzero vector.")
    return vector / length


# Block 2: Spherical coordinates and observer position
def radial_direction(latitude_rad, longitude_rad):
    phi, lam = np.broadcast_arrays(latitude_rad, longitude_rad)
    return np.stack((np.cos(phi) * np.cos(lam),
                     np.cos(phi) * np.sin(lam), np.sin(phi)), axis=-1)


def spherical_position(radius_m, latitude_rad, longitude_rad):
    return np.asarray(radius_m)[..., None] * radial_direction(latitude_rad, longitude_rad)


def observer_position(reference_radius_m, ground_elevation_m, height_m,
                      latitude_rad, longitude_rad):
    if reference_radius_m <= 0 or height_m < 0:
        raise ValueError("The reference radius must be positive and height nonnegative.")
    radius = reference_radius_m + ground_elevation_m + height_m
    if radius <= 0:
        raise ValueError("The observer radius must be positive.")
    return spherical_position(radius, latitude_rad, longitude_rad)


def spherical_coordinates(position_m):
    x, y, z = np.moveaxis(np.asarray(position_m, dtype=float), -1, 0)
    return np.sqrt(x*x + y*y + z*z), np.arctan2(z, np.hypot(x, y)), np.arctan2(y, x)


# Block 3: Position derivatives and the local ENU basis
def local_basis(latitude_rad, longitude_rad):
    phi, lam = latitude_rad, longitude_rad
    east = np.array([-np.sin(lam), np.cos(lam), 0.0])
    north = np.array([-np.sin(phi)*np.cos(lam), -np.sin(phi)*np.sin(lam), np.cos(phi)])
    up = radial_direction(phi, lam)
    return np.column_stack((east, north, up))


def position_derivatives(radius_m, latitude_rad, longitude_rad):
    east, north, up = local_basis(latitude_rad, longitude_rad).T
    return up, radius_m*north, radius_m*np.cos(latitude_rad)*east


def terrain_derivatives(radius_m, radial_slope_phi, radial_slope_lambda,
                        latitude_rad, longitude_rad):
    east, north, up = local_basis(latitude_rad, longitude_rad).T
    derivative_phi = radial_slope_phi*up + radius_m*north
    derivative_lambda = radial_slope_lambda*up + radius_m*np.cos(latitude_rad)*east
    return derivative_phi, derivative_lambda


# Block 4: Global and local coordinate transformations
def global_to_local(vector, basis):
    return np.asarray(vector, dtype=float) @ np.asarray(basis)


def local_to_global(enu, basis):
    return np.asarray(enu, dtype=float) @ np.asarray(basis).T


def observer_to_body(body_position_m, observer_position_m):
    return np.asarray(body_position_m) - np.asarray(observer_position_m)


# Block 5: Azimuth, elevation, and horizontal components
def azimuth_elevation(vector, basis):
    east, north, up = np.moveaxis(global_to_local(vector, basis), -1, 0)
    horizontal = np.hypot(east, north)
    if np.any(np.hypot(horizontal, up) == 0):
        raise ValueError("A zero vector has no azimuth or elevation.")
    azimuth = np.where(horizontal == 0, np.nan, np.arctan2(east, north) % (2*np.pi))
    return azimuth, np.arctan2(up, horizontal)


def elevation_from_sine(vector, basis):
    return np.arcsin(np.clip(global_to_local(unit_vector(vector), basis)[..., 2], -1, 1))


def horizontal_components(horizontal_length, azimuth_rad):
    return horizontal_length*np.sin(azimuth_rad), horizontal_length*np.cos(azimuth_rad)


# Block 6: Great-circle terrain directions and exact elevation angles
def great_circle_direction(central_angle_rad, azimuth_rad, basis):
    east, north, up = np.asarray(basis).T
    psi = np.asarray(central_angle_rad)
    horizontal = np.cos(azimuth_rad)*north + np.sin(azimuth_rad)*east
    return np.cos(psi)[..., None]*up + np.sin(psi)[..., None]*horizontal


def terrain_elevation_angle(terrain_radius_m, observer_radius_m, central_angle_rad):
    vertical = terrain_radius_m*np.cos(central_angle_rad) - observer_radius_m
    horizontal = terrain_radius_m*np.sin(central_angle_rad)
    return np.arctan2(vertical, horizontal)


def observer_height_sensitivity(terrain_radius_m, observer_radius_m, central_angle_rad):
    horizontal = terrain_radius_m*np.sin(central_angle_rad)
    vertical = terrain_radius_m*np.cos(central_angle_rad) - observer_radius_m
    return -horizontal / (vertical**2 + horizontal**2)


# Block 7: Sampled terrain horizon and angular clearance
def make_horizon(azimuth_rad, elevation_rad):
    azimuth = np.asarray(azimuth_rad, dtype=float) % (2*np.pi)
    elevation = np.asarray(elevation_rad, dtype=float)
    if azimuth.ndim != 1 or elevation.shape != azimuth.shape or len(azimuth) < 2:
        raise ValueError("A horizon needs matching one-dimensional arrays with at least two samples.")
    if not np.all(np.isfinite(azimuth)) or not np.all(np.isfinite(elevation)):
        raise ValueError("Missing horizon samples must not be replaced with zero.")
    order = np.argsort(azimuth)
    azimuth, elevation = azimuth[order], elevation[order]
    if np.any(np.diff(azimuth) <= 0):
        raise ValueError("Azimuth samples must be distinct modulo 2 pi.")
    return lambda angle: np.interp(angle, azimuth, elevation, period=2*np.pi)


def build_sampled_horizon(azimuth_rad, central_angles_rad, elevation_at,
                          reference_radius_m, observer_m, basis):
    psi = np.asarray(central_angles_rad, dtype=float)
    if psi.ndim != 1 or psi.size == 0 or np.any((psi <= 0) | (psi >= np.pi)):
        raise ValueError("Terrain scan angles must lie strictly between zero and pi.")
    observer_radius = np.linalg.norm(observer_m)
    profile = []
    for azimuth in azimuth_rad:
        direction = great_circle_direction(psi, azimuth, basis)
        _, latitude, longitude = spherical_coordinates(direction)
        elevation = np.array([elevation_at(phi, lam) for phi, lam in zip(latitude, longitude)])
        if not np.all(np.isfinite(elevation)):
            raise ValueError("The DEM does not cover the requested terrain scan.")
        radius = reference_radius_m + elevation
        profile.append(np.max(terrain_elevation_angle(radius, observer_radius, psi)))
    profile = np.asarray(profile)
    return make_horizon(azimuth_rad, profile), profile


def angular_clearance(azimuth_rad, elevation_rad, horizon):
    return np.asarray(elevation_rad) - horizon(azimuth_rad)


def terrain_visibility(directions, basis, horizon):
    azimuth, elevation = azimuth_elevation(directions, basis)
    vertical = np.isnan(azimuth)
    clearance = angular_clearance(np.where(vertical, 0.0, azimuth), elevation, horizon)
    return np.where(vertical, elevation > 0, clearance > 0)


# Block 8: Curvature approximation and the smooth-sphere horizon
def curvature_drop(distance_m, reference_radius_m):
    return np.asarray(distance_m)**2 / (2*reference_radius_m)


def approximate_terrain_elevation(elevation_m, ground_elevation_m, height_m,
                                  distance_m, reference_radius_m):
    vertical = elevation_m - ground_elevation_m - height_m
    return np.arctan2(vertical - curvature_drop(distance_m, reference_radius_m), distance_m)


def smooth_sphere_horizon(surface_radius_m, height_m):
    if surface_radius_m <= 0 or height_m < 0:
        raise ValueError("The surface radius must be positive and height nonnegative.")
    return -np.arccos(surface_radius_m / (surface_radius_m + height_m))


def smooth_sphere_horizon_distance(surface_radius_m, height_m):
    return -surface_radius_m*smooth_sphere_horizon(surface_radius_m, height_m)


def ground_level_sphere_elevation(central_angle_rad):
    return -np.asarray(central_angle_rad)/2


# Block 9: Terrain coverage, feature width, and angular uncertainty
def terrain_coverage_limit(inner_radius_m, outer_radius_m, observer_radius_m,
                           reference_radius_m):
    if not 0 < inner_radius_m <= min(outer_radius_m, observer_radius_m):
        raise ValueError("The inner sphere must fit inside the model and observer radius.")
    angle = (np.arccos(inner_radius_m/observer_radius_m)
             + np.arccos(inner_radius_m/outer_radius_m))
    return angle, reference_radius_m*angle


def feature_angular_width(width_m, distance_m):
    return np.asarray(width_m)/np.asarray(distance_m)


def elevation_uncertainty(height_uncertainty_m, distance_m):
    return np.asarray(height_uncertainty_m)/np.asarray(distance_m)


# Block 10: Optional SPICE input and angular body radii
def body_vector_from_spice(target, et, observer_m, frame):
    import spiceypy as spice

    state, _ = spice.spkcpo(
        target=target, et=et, outref=frame, refloc="OBSERVER", abcorr="CN+S",
        obspos=np.asarray(observer_m)/1000.0, obsctr="MOON", obsref=frame,
    )
    return np.asarray(state[:3])*1000.0


def angular_radius(body_radius_m, observer_to_centre_m):
    distance = np.linalg.norm(observer_to_centre_m, axis=-1)
    if body_radius_m <= 0 or np.any(distance <= body_radius_m):
        raise ValueError("The observer must be outside a body with positive radius.")
    return np.arcsin(body_radius_m/distance)


# Block 11: Circular strips, their antiderivative, and the visible disc fraction
def disc_strip_width(y_rad, radius_rad):
    return 2*np.sqrt(np.maximum(0.0, radius_rad**2 - np.asarray(y_rad)**2))


def disc_area_antiderivative(y_rad, radius_rad):
    if radius_rad <= 0:
        raise ValueError("The disc radius must be positive.")
    y = np.clip(y_rad, -radius_rad, radius_rad)
    return y*np.sqrt(np.maximum(0.0, radius_rad**2-y**2)) + radius_rad**2*np.arcsin(y/radius_rad)


def flat_disc_fraction(clearance_rad, radius_rad):
    if radius_rad <= 0:
        raise ValueError("The disc radius must be positive.")
    k = np.clip(np.asarray(clearance_rad)/radius_rad, -1.0, 1.0)
    return 0.5 + (np.arcsin(k) + k*np.sqrt(1-k*k))/np.pi


def flat_disc_visible_area(clearance_rad, radius_rad):
    return np.pi*radius_rad**2*flat_disc_fraction(clearance_rad, radius_rad)


# Block 12: Equal-area disc samples and individual ray directions
def disc_sample_directions(centre_vector, radius_rad, sample_count):
    if sample_count < 1 or not 0 < radius_rad < np.pi/2:
        raise ValueError("Use a positive sample count and a disc radius between zero and pi/2.")
    centre = unit_vector(centre_vector)
    auxiliary = np.eye(3)[np.argmin(np.abs(centre))]
    first = unit_vector(np.cross(auxiliary, centre))
    second = np.cross(centre, first)
    index = np.arange(sample_count)
    sample_radius = np.sqrt((index+0.5)/sample_count)
    angle = index*np.pi*(3-np.sqrt(5))
    x, y = sample_radius*np.cos(angle), sample_radius*np.sin(angle)
    rays = centre + np.tan(radius_rad)*(x[:, None]*first + y[:, None]*second)
    return unit_vector(rays)


def weighted_visible_fraction(mask, area_weights=None):
    mask = np.asarray(mask, dtype=float)
    weights = np.ones_like(mask) if area_weights is None else np.asarray(area_weights, dtype=float)
    if mask.size == 0 or weights.shape != mask.shape or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Visibility needs matching nonnegative weights with a positive total.")
    return np.sum(weights*mask)/np.sum(weights)


def disc_terrain_fraction(body_vector_m, body_radius_m, basis, horizon, sample_count=1024):
    radius = angular_radius(body_radius_m, body_vector_m)
    rays = disc_sample_directions(body_vector_m, radius, sample_count)
    return weighted_visible_fraction(terrain_visibility(rays, basis, horizon))


# Block 13: Earth occultation and combined solar visibility
def earth_open_mask(solar_rays, earth_vector_m, earth_radius_m):
    earth_direction = unit_vector(earth_vector_m)
    earth_radius_rad = angular_radius(earth_radius_m, earth_vector_m)
    return unit_vector(solar_rays) @ earth_direction < np.cos(earth_radius_rad)


def solar_visibility(sun_vector_m, earth_vector_m, sun_radius_m, earth_radius_m,
                     basis, horizon, sample_count=1024):
    sun_radius_rad = angular_radius(sun_radius_m, sun_vector_m)
    rays = disc_sample_directions(sun_vector_m, sun_radius_rad, sample_count)
    terrain_mask = terrain_visibility(rays, basis, horizon)
    earth_mask = earth_open_mask(rays, earth_vector_m, earth_radius_m)
    if np.linalg.norm(earth_vector_m) >= np.linalg.norm(sun_vector_m):
        earth_mask = np.ones(sample_count, dtype=bool)
    combined_mask = terrain_mask & earth_mask
    sun_azimuth, sun_elevation = azimuth_elevation(sun_vector_m, basis)
    earth_azimuth, earth_elevation = azimuth_elevation(earth_vector_m, basis)
    sun_clearance = angular_clearance(np.nan_to_num(sun_azimuth), sun_elevation, horizon)
    earth_clearance = angular_clearance(np.nan_to_num(earth_azimuth), earth_elevation, horizon)
    return {
        "sun_azimuth_rad": sun_azimuth,
        "sun_elevation_rad": sun_elevation,
        "sun_clearance_rad": sun_clearance,
        "sun_radius_rad": sun_radius_rad,
        "earth_azimuth_rad": earth_azimuth,
        "earth_elevation_rad": earth_elevation,
        "earth_clearance_rad": earth_clearance,
        "earth_center_visible": bool(terrain_visibility(earth_vector_m, basis, horizon)),
        "terrain_fraction": weighted_visible_fraction(terrain_mask),
        "sun_fraction": weighted_visible_fraction(combined_mask),
        "rays": rays,
        "open_mask": combined_mask,
    }


# Block 14: Irradiance, effective panel area, and electrical power
def irradiance_at_distance(reference_irradiance_w_m2, reference_distance_m, distance_m):
    return reference_irradiance_w_m2*(reference_distance_m/np.asarray(distance_m))**2


def effective_panel_area(area_m2, panel_normal, sun_direction):
    cosine = np.sum(unit_vector(panel_normal)*unit_vector(sun_direction), axis=-1)
    return area_m2*np.maximum(0.0, cosine)


def panel_power(area_m2, efficiency, irradiance_w_m2, visible_fraction,
                panel_normal, sun_direction):
    return (efficiency*irradiance_w_m2*visible_fraction
            * effective_panel_area(area_m2, panel_normal, sun_direction))


def panel_power_from_radiance(area_m2, efficiency, radiance_w_m2_sr, rays,
                               open_mask, solid_angle_weights_sr, panel_normal):
    incidence = np.maximum(0.0, unit_vector(rays) @ unit_vector(panel_normal))
    return efficiency*area_m2*np.sum(
        np.asarray(radiance_w_m2_sr)*open_mask*incidence*solid_angle_weights_sr
    )


# Block 15: Illumination, darkness, and point visibility indicators
def illumination_indicator(visible_fraction, minimum_fraction):
    if not 0 <= minimum_fraction <= 1:
        raise ValueError("The illumination threshold must be between zero and one.")
    fraction = np.asarray(visible_fraction)
    return fraction > 0 if minimum_fraction == 0 else fraction >= minimum_fraction


def darkness_indicator(visible_fraction):
    return np.asarray(visible_fraction) == 0


def point_visibility_indicator(clearance_rad):
    return np.asarray(clearance_rad) > 0


def power_indicator(power_w, minimum_power_w):
    if minimum_power_w <= 0:
        raise ValueError("The required power must be positive.")
    return np.asarray(power_w) >= minimum_power_w


def joint_indicator(illumination, earth_visible):
    return np.asarray(illumination, dtype=int)*np.asarray(earth_visible, dtype=int)


# Block 16: Linear event times and transition refinement
def linear_transition_time(time_0, value_0, time_1, value_1):
    if time_1 <= time_0 or value_0 == value_1 or value_0*value_1 > 0:
        raise ValueError("A transition needs increasing times and values bracketing zero.")
    return time_0 - value_0*(time_1-time_0)/(value_1-value_0)


def refine_transition(value_at, time_0, time_1, tolerance_s):
    if tolerance_s <= 0 or time_1 <= time_0:
        raise ValueError("Time bounds and the refinement tolerance must be positive.")
    value_0, value_1 = value_at(time_0), value_at(time_1)
    if not np.isfinite(value_0 + value_1) or value_0*value_1 > 0:
        raise ValueError("Finite endpoint values must bracket zero.")
    if value_0 == 0:
        return time_0
    if value_1 == 0:
        return time_1
    while time_1-time_0 > tolerance_s:
        middle = (time_0+time_1)/2
        if middle == time_0 or middle == time_1:
            break
        value = value_at(middle)
        if not np.isfinite(value):
            raise ValueError("The transition function must remain finite.")
        if value == 0:
            return middle
        if (value > 0) == (value_0 > 0):
            time_0, value_0 = middle, value
        else:
            time_1 = middle
    return (time_0+time_1)/2


def refine_state_transition(state_at, time_0, time_1, tolerance_s):
    if tolerance_s <= 0 or time_1 <= time_0:
        raise ValueError("Time bounds and the refinement tolerance must be positive.")
    initial = bool(state_at(time_0))
    if initial == bool(state_at(time_1)):
        raise ValueError("The endpoint states must differ.")
    while time_1-time_0 > tolerance_s:
        middle = (time_0+time_1)/2
        if middle == time_0 or middle == time_1:
            break
        if bool(state_at(middle)) == initial:
            time_0 = middle
        else:
            time_1 = middle
    return (time_0+time_1)/2


# Block 17: Continuous windows from sampled threshold crossings
def checked_time_series(times_s, values):
    times = np.asarray(times_s, dtype=float)
    values = np.asarray(values, dtype=float)
    if times.ndim != 1 or times.size < 2 or values.shape != times.shape:
        raise ValueError("Use matching one-dimensional arrays with at least two times.")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise ValueError("Time series must contain finite values.")
    if np.any(np.diff(times) <= 0):
        raise ValueError("Sample times must be strictly increasing.")
    return times, values


def merge_windows(windows):
    merged = []
    for start, end in sorted(windows):
        if not np.isfinite(start + end) or end < start:
            raise ValueError("Window bounds must be finite and ordered.")
        if end == start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def windows_from_samples(times_s, values, threshold=0.0, inclusive=False):
    times, values = checked_time_series(times_s, values)
    margin = values-threshold
    active = margin >= 0 if inclusive else margin > 0
    start = times[0] if active[0] else None
    windows = []
    for index in range(len(times)-1):
        if active[index] == active[index+1]:
            continue
        crossing = linear_transition_time(
            times[index], margin[index], times[index+1], margin[index+1]
        )
        if active[index+1]:
            start = crossing
        else:
            windows.append((start, crossing))
            start = None
    if active[-1]:
        windows.append((start, times[-1]))
    return merge_windows(windows)


# Block 18: Durations, interruptions, window intersections, and next events
def window_durations(windows):
    return np.array([end-start for start, end in merge_windows(windows)])


def total_duration(windows):
    return float(window_durations(windows).sum())


def longest_duration(windows):
    return float(np.max(window_durations(windows), initial=0.0))


def complement_windows(windows, period_start, period_end):
    if period_end <= period_start:
        raise ValueError("The analysis period must have positive duration.")
    cursor, gaps = period_start, []
    for start, end in merge_windows(windows):
        start, end = max(start, period_start), min(end, period_end)
        if end <= start:
            continue
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < period_end:
        gaps.append((cursor, period_end))
    return gaps


def intersect_windows(first, second):
    first, second = merge_windows(first), merge_windows(second)
    result, i, j = [], 0, 0
    while i < len(first) and j < len(second):
        start = max(first[i][0], second[j][0])
        end = min(first[i][1], second[j][1])
        if end > start:
            result.append((start, end))
        if first[i][1] <= second[j][1]:
            i += 1
        else:
            j += 1
    return result


def time_to_next_event(event_times_s, current_time_s):
    events = [t for t in event_times_s if t > current_time_s]
    return min(events)-current_time_s if events else None


# Block 19: Time integrals, energy, mean visibility, and timing uncertainty
def time_integral(times_s, values, *, method="trapezoid"):
    if method == "interval":
        edges = np.asarray(times_s, dtype=float)
        intervals = np.asarray(values, dtype=float)
        if edges.ndim != 1 or len(edges) < 2 or intervals.shape != (len(edges)-1,):
            raise ValueError("Interval integration needs N+1 time edges and N interval values.")
        if not np.all(np.isfinite(edges)) or not np.all(np.isfinite(intervals)):
            raise ValueError("Interval data must be finite.")
        if np.any(np.diff(edges) <= 0):
            raise ValueError("Interval edges must be strictly increasing.")
        return float(np.sum(intervals*np.diff(edges)))
    if method != "trapezoid":
        raise ValueError("The integration method must be trapezoid or interval.")
    times, values = checked_time_series(times_s, values)
    return float(np.sum((values[:-1]+values[1:])*np.diff(times)/2))


def equivalent_full_disc_time(times_s, visible_fraction, *, method="trapezoid"):
    return time_integral(times_s, visible_fraction, method=method)


def mean_disc_fraction(times_s, visible_fraction, *, method="trapezoid"):
    return equivalent_full_disc_time(times_s, visible_fraction, method=method)/(times_s[-1]-times_s[0])


def electrical_energy(times_s, power_w, *, method="trapezoid"):
    joules = time_integral(times_s, power_w, method=method)
    return {"joules": joules, "watt_hours": joules/3600.0}


def transition_time_uncertainty(angular_error_rad, angular_rate_rad_s):
    if angular_rate_rad_s == 0:
        return np.inf
    return abs(angular_error_rad/angular_rate_rad_s)


# Block 20: Complete calculation from future input arrays
def analyze(*, latitude_deg, longitude_deg, reference_radius_m, ground_elevation_m,
            height_m, horizon, times_s, sun_vectors_m, earth_vectors_m,
            sun_radius_m, earth_radius_m, minimum_sun_fraction=0.8,
            disc_samples=1024, panel_area_m2=None, panel_efficiency=None,
            panel_normal_enu=None, irradiance_w_m2=None):
    times, _ = checked_time_series(times_s, np.zeros_like(times_s))
    sun_vectors = np.asarray(sun_vectors_m, dtype=float)
    earth_vectors = np.asarray(earth_vectors_m, dtype=float)
    if sun_vectors.shape != (len(times), 3) or earth_vectors.shape != sun_vectors.shape:
        raise ValueError("Body vectors must have shape (number of times, 3).")
    illumination_indicator(0.0, minimum_sun_fraction)
    latitude, longitude = degrees_to_radians([latitude_deg, longitude_deg])
    basis = local_basis(latitude, longitude)
    observer = observer_position(reference_radius_m, ground_elevation_m, height_m,
                                 latitude, longitude)
    states = [solar_visibility(sun, earth, sun_radius_m, earth_radius_m,
                               basis, horizon, disc_samples)
              for sun, earth in zip(sun_vectors, earth_vectors)]
    fractions = np.array([state["sun_fraction"] for state in states])
    earth_clearance = np.array([state["earth_clearance_rad"] for state in states])
    sun_windows = windows_from_samples(times, fractions, minimum_sun_fraction,
                                       inclusive=minimum_sun_fraction > 0)
    earth_windows = windows_from_samples(times, earth_clearance)
    joint_windows = intersect_windows(sun_windows, earth_windows)
    sun_gaps = complement_windows(sun_windows, times[0], times[-1])
    earth_gaps = complement_windows(earth_windows, times[0], times[-1])
    dark_windows = windows_from_samples(times, -fractions, inclusive=True)
    metrics = {
        "sunlight_seconds": total_duration(sun_windows),
        "sunlight_time_fraction": total_duration(sun_windows)/(times[-1]-times[0]),
        "longest_sunlight_seconds": longest_duration(sun_windows),
        "longest_insufficient_light_seconds": longest_duration(sun_gaps),
        "longest_darkness_seconds": longest_duration(dark_windows),
        "earth_visible_seconds": total_duration(earth_windows),
        "longest_earth_gap_seconds": longest_duration(earth_gaps),
        "joint_seconds": total_duration(joint_windows),
        "equivalent_full_disc_seconds": equivalent_full_disc_time(times, fractions),
        "mean_sun_fraction": mean_disc_fraction(times, fractions),
    }
    panel_inputs = (panel_area_m2, panel_efficiency, panel_normal_enu, irradiance_w_m2)
    power = energy = None
    if any(value is not None for value in panel_inputs):
        if any(value is None for value in panel_inputs):
            raise ValueError("Power needs panel area, efficiency, normal, and irradiance.")
        if panel_area_m2 <= 0 or not 0 <= panel_efficiency <= 1:
            raise ValueError("Panel area must be positive and efficiency between zero and one.")
        normal = local_to_global(unit_vector(panel_normal_enu), basis)
        irradiance = np.broadcast_to(np.asarray(irradiance_w_m2), times.shape)
        if np.any(irradiance < 0) or not np.all(np.isfinite(irradiance)):
            raise ValueError("Irradiance must be finite and nonnegative.")
        power = panel_power(panel_area_m2, panel_efficiency, irradiance, fractions,
                            normal, sun_vectors)
        energy = electrical_energy(times, power)
    return {
        "observer_m": observer, "basis": basis, "times_s": times,
        "states": states, "sun_windows": sun_windows, "earth_windows": earth_windows,
        "joint_windows": joint_windows, "dark_windows": dark_windows,
        "sun_gaps": sun_gaps, "earth_gaps": earth_gaps,
        "metrics": metrics, "power_w": power, "energy": energy,
    }

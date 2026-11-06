from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import platform
import re
import sys
import trace
from typing import Mapping
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parent
EXPECTED_FORMULA_DIGEST = "7b6e79527f3c394774865a97d643d260c5bdefd39482f35b7e5f168865868ea4"
TEST_FILES = {"m": "test_mini_model.py", "a": "test_formula_audit.py"}


# Block 1: Named audit records and errors
class AuditError(Exception):
    pass


class ValidationError(AuditError):
    def __init__(self, problems: list[str]):
        self.problems = tuple(problems)
        super().__init__("\n".join(problems))


@dataclass(frozen=True, slots=True)
class EquationDocument:
    expressions: tuple[str, ...]
    anchors: tuple[int, ...]
    digest: str

    @property
    def numbers(self) -> tuple[int, ...]:
        return tuple(range(1, len(self.expressions) + 1))


@dataclass(frozen=True, slots=True)
class TestReference:
    source: str
    function: str


@dataclass(frozen=True, slots=True)
class FormulaSpecification:
    numbers: tuple[int, ...]
    category: str
    description: str
    functions: tuple[str, ...]
    evidence: TestReference
    notes: str


@dataclass(frozen=True, slots=True)
class SourceSymbol:
    name: str
    qualified_name: str
    line: int


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    symbols: tuple[SourceSymbol, ...]

    def find(self, name: str) -> SourceSymbol:
        matches = [symbol for symbol in self.symbols if name in (symbol.name, symbol.qualified_name)]
        if len(matches) != 1:
            raise AuditError(f"{self.path.name}: expected one definition of {name}, found {len(matches)}.")
        return matches[0]

    @property
    def top_level_functions(self) -> frozenset[str]:
        return frozenset(symbol.name for symbol in self.symbols if symbol.name == symbol.qualified_name)


@dataclass(frozen=True, slots=True)
class AuditSources:
    implementation: SourceFile
    tests: Mapping[str, SourceFile]


@dataclass(frozen=True, slots=True)
class TestExecution:
    tests_run: int
    successful: bool
    output: str
    called_functions: frozenset[str]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    root: Path
    document: EquationDocument
    specifications: tuple[FormulaSpecification, ...]
    sources: AuditSources
    execution: TestExecution


# Block 2: Equation document parsing
def parse_document(markdown: str) -> EquationDocument:
    expressions = tuple(re.findall(r"^\$\$\n(.*?)\n\$\$$", markdown, re.M | re.S))
    anchors = tuple(int(number) for number in re.findall(r'<a id="eq-(\d+)"></a>', markdown))
    digest = hashlib.sha256("\n\n".join(expressions).encode()).hexdigest()
    return EquationDocument(expressions, anchors, digest)


def read_document(path: Path) -> EquationDocument:
    return parse_document(path.read_text(encoding="utf-8"))


# Block 3: Formula registry parsing
def parse_specification(line: str) -> FormulaSpecification:
    fields = line.split("|", 5)
    if len(fields) != 6:
        raise ValueError("A formula specification requires six fields.")
    data = dict(zip(("numbers", "category", "description", "functions", "evidence", "notes"), fields))
    bounds = [int(value) for value in data["numbers"].split("-")]
    if len(bounds) not in (1, 2) or bounds[0] < 1 or bounds[-1] < bounds[0]:
        raise ValueError("Equation numbers must form a positive ordered range.")
    source, function = data["evidence"].split(":", 1)
    if not source or not function or not data["description"]:
        raise ValueError("Descriptions and evidence references must be nonempty.")
    categories = {"Direct", "Numerical", "Approximation", "Derivation", "Identity", "Definition", "Example", "Input"}
    if data["category"] not in categories:
        raise ValueError(f"Unknown formula category: {data['category']}.")
    functions = tuple(data["functions"].split(","))
    if not all(functions):
        raise ValueError("Implementation references must be nonempty.")
    return FormulaSpecification(
        numbers=tuple(range(bounds[0], bounds[-1] + 1)), category=data["category"],
        description=data["description"], functions=functions,
        evidence=TestReference(source, function), notes=data["notes"],
    )


def parse_specifications(text: str) -> tuple[FormulaSpecification, ...]:
    specifications = []
    for number, line in enumerate(text.strip().splitlines(), 1):
        try:
            specifications.append(parse_specification(line))
        except (TypeError, ValueError) as error:
            raise ValidationError([f"Invalid formula registry row {number}: {error}"]) from error
    return tuple(specifications)


# Block 4: Qualified source definitions
def source_symbols(nodes: list[ast.stmt], scope: str = "") -> tuple[SourceSymbol, ...]:
    symbols = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            qualified = f"{scope}.{node.name}" if scope else node.name
            if not isinstance(node, ast.ClassDef):
                symbols.append(SourceSymbol(node.name, qualified, node.lineno))
            symbols.extend(source_symbols(node.body, qualified))
    return tuple(symbols)


def read_source(path: Path) -> SourceFile:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return SourceFile(path.resolve(), source_symbols(tree.body))


def read_sources(root: Path) -> AuditSources:
    implementation = read_source(root / "mini_model.py")
    tests = {key: read_source(root / filename) for key, filename in TEST_FILES.items()}
    return AuditSources(implementation, tests)


# Block 5: Document and reference validation
def validate_document(document: EquationDocument, specifications: tuple[FormulaSpecification, ...],
                      expected_digest: str) -> None:
    mapped = [number for specification in specifications for number in specification.numbers]
    duplicates = sorted(number for number, count in Counter(mapped).items() if count > 1)
    problems = []
    if not document.expressions:
        problems.append("The document contains no displayed equations.")
    if document.digest != expected_digest:
        problems.append("README equations changed; review the formula registry.")
    if set(mapped) != set(document.numbers):
        problems.append(f"Equation mappings differ from the document: {sorted(set(mapped) ^ set(document.numbers))}.")
    if duplicates:
        problems.append(f"Duplicate equation mappings: {duplicates}.")
    if document.anchors != document.numbers:
        problems.append("Equation anchors must be unique and follow the document order.")
    if problems:
        raise ValidationError(problems)


def validate_references(specifications: tuple[FormulaSpecification, ...], sources: AuditSources) -> None:
    problems = []
    for specification in specifications:
        try:
            for function in specification.functions:
                sources.implementation.find(function)
            evidence = specification.evidence
            if evidence.source not in sources.tests:
                raise AuditError(f"Unknown test source: {evidence.source}.")
            sources.tests[evidence.source].find(evidence.function)
        except AuditError as error:
            problems.append(f"Equations {specification.numbers}: {error}")
    if problems:
        raise ValidationError(problems)


# Block 6: Standard-library test execution and call tracing
def execute_suite(suite: unittest.TestSuite, implementation: SourceFile) -> TestExecution:
    output = io.StringIO()
    tracer = trace.Trace(count=False, trace=False, countfuncs=True)
    runner = unittest.TextTestRunner(stream=output, verbosity=2)
    previous_trace = sys.gettrace()
    try:
        result = tracer.runfunc(runner.run, suite)
    finally:
        sys.settrace(previous_trace)
    called = frozenset(name for filename, _, name in tracer.results().calledfuncs
                       if filename == str(implementation.path))
    return TestExecution(result.testsRun, result.wasSuccessful(), output.getvalue(), called)


def run_tests(sources: AuditSources) -> TestExecution:
    modules = [source.path.stem for source in sources.tests.values()]
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    return execute_suite(suite, sources.implementation)


def validate_execution(execution: TestExecution, implementation: SourceFile) -> None:
    if not execution.successful:
        raise AuditError(execution.output)
    missing = implementation.top_level_functions - execution.called_functions
    if missing:
        raise ValidationError([f"Implementation functions were not exercised: {sorted(missing)}."])


# Block 7: Verification orchestration
def verify(root: Path = ROOT) -> VerificationResult:
    root = root.resolve()
    document = read_document(root / "README.md")
    specifications = parse_specifications(SPECIFICATIONS)
    validate_document(document, specifications, EXPECTED_FORMULA_DIGEST)
    sources = read_sources(root)
    validate_references(specifications, sources)
    execution = run_tests(sources)
    validate_execution(execution, sources.implementation)
    return VerificationResult(root, document, specifications, sources, execution)


# Block 8: Report rendering and output
def classification(specifications: tuple[FormulaSpecification, ...]) -> str:
    counts = Counter(specification.category for specification in specifications for _ in specification.numbers)
    return ", ".join(f"{category}: {count}" for category, count in sorted(counts.items()))


def report_context(result: VerificationResult) -> dict[str, str]:
    return {
        "equation_count": str(len(result.document.expressions)),
        "test_count": str(result.execution.tests_run),
        "function_count": str(len(result.sources.implementation.top_level_functions)),
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "in_virtualenv": str(sys.prefix != sys.base_prefix),
        "classification": classification(result.specifications),
    }


def source_link(source: SourceFile, function: str, root: Path) -> str:
    symbol = source.find(function)
    filename = source.path.relative_to(root).as_posix()
    return f"[{symbol.name}]({filename}#L{symbol.line})"


def mapping_row(number: int, specification: FormulaSpecification, result: VerificationResult) -> str:
    implementation = ", ".join(source_link(result.sources.implementation, name, result.root)
                               for name in specification.functions)
    evidence = specification.evidence
    test = source_link(result.sources.tests[evidence.source], evidence.function, result.root)
    cells = (f"[E{number:03d}](README.md#eq-{number:03d})", specification.description,
             specification.category, implementation, test, specification.notes)
    return "| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |"


def render_report(result: VerificationResult) -> str:
    context = report_context(result)
    introduction = re.sub(r"\{\{(\w+)\}\}", lambda match: context[match[1]], REPORT_TEMPLATE)
    heading = ("## Complete equation mapping\n\n"
               "| Equation in README | Meaning | Status | Implementation | Executable evidence | Interpretation |\n"
               "| --- | --- | --- | --- | --- | --- |\n")
    records = {number: specification for specification in result.specifications for number in specification.numbers}
    rows = [mapping_row(number, records[number], result) for number in result.document.numbers]
    return introduction + heading + "\n".join(rows) + "\n"


def write_report(result: VerificationResult) -> Path:
    path = result.root / "FORMULA_AUDIT.md"
    path.write_text(render_report(result), encoding="utf-8")
    return path


# Block 9: Command-line entry point
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the formula registry and its executable evidence.")
    parser.add_argument("--check", action="store_true", help="Verify without rewriting the report.")
    arguments = parser.parse_args(argv)
    try:
        result = verify()
        if not arguments.check:
            write_report(result)
    except (AuditError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"PASS: {len(result.document.expressions)} equation blocks mapped; "
          f"{result.execution.tests_run} tests passed; "
          f"{len(result.sources.implementation.top_level_functions)} functions exercised.")
    print(classification(result.specifications))
    return 0


# Block 10: Reviewed formula registry and report template

SPECIFICATIONS = """
001|Input|Reference sphere radius|observer_position|m:test_spherical_coordinates_and_observer|The dataset radius is supplied by the caller; the numerical value is an example.
002|Direct|Degrees to radians|degrees_to_radians|m:test_spherical_coordinates_and_observer|
003|Direct|Spherical position components|spherical_position,radial_direction|a:test_coordinate_axes_and_basis_example|
004|Direct|Spherical position components|spherical_position,radial_direction|a:test_coordinate_axes_and_basis_example|
005|Direct|Spherical position components|spherical_position,radial_direction|a:test_coordinate_axes_and_basis_example|
006|Direct|Spherical position components|spherical_position,radial_direction|a:test_coordinate_axes_and_basis_example|
007|Example|Positions on the coordinate axes|spherical_position|a:test_coordinate_axes_and_basis_example|
008|Direct|Radial unit vector|radial_direction,unit_vector|a:test_coordinate_axes_and_basis_example|
009|Input|Site ground elevation|observer_position,build_sampled_horizon|m:test_spherical_coordinates_and_observer|Ground elevation is supplied; actual DEM reading is an external data input.
010|Direct|Observer radius and position|observer_position|m:test_spherical_coordinates_and_observer|
011|Example|Ground elevation plus spacecraft height|observer_position|m:test_spherical_coordinates_and_observer|
012|Direct|Terrain point position|spherical_position,build_sampled_horizon|a:test_terrain_derivatives_against_finite_differences|
013|Direct|Radial position derivative|position_derivatives,local_basis|m:test_position_derivatives|
014|Example|Up vector at latitude 30 degrees|local_basis|a:test_coordinate_axes_and_basis_example|
015|Derivation|First-order longitude increment|position_derivatives|a:test_first_order_longitude_increment|The Taylor step is a derivation; its second-order remainder is checked.
016|Derivation|Trigonometric differentiation rules|position_derivatives|a:test_first_order_longitude_increment|Explicit intermediate step restored while comparing the original derivation with the merged document.
017|Direct|Longitude derivative|position_derivatives|m:test_position_derivatives|
018|Derivation|Longitude derivative length before normalization|position_derivatives|m:test_position_derivatives|Explicit intermediate step restored while comparing the original derivation with the merged document.
019|Direct|Normalized east direction|local_basis|m:test_position_derivatives|The simplified trigonometric result is used directly.
020|Example|East direction at the two reference meridians|local_basis|a:test_coordinate_axes_and_basis_example|Explicit intermediate step restored while comparing the original derivation with the merged document.
021|Direct|Latitude derivative|position_derivatives|m:test_position_derivatives|
022|Derivation|Factored latitude derivative|position_derivatives|m:test_position_derivatives|Explicit intermediate step restored while comparing the original derivation with the merged document.
023|Derivation|Latitude derivative length before normalization|position_derivatives|m:test_position_derivatives|Explicit intermediate step restored while comparing the original derivation with the merged document.
024|Direct|Normalized north direction|local_basis|m:test_position_derivatives|
025|Example|North vector at latitude 30 degrees|local_basis|a:test_coordinate_axes_and_basis_example|
026|Identity|Required lengths and mutual orthogonality of ENU|local_basis|a:test_basis_identities_on_many_sites|Explicit intermediate step restored while comparing the original derivation with the merged document.
027|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
028|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
029|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
030|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
031|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
032|Identity|East and up orthogonality|local_basis|a:test_basis_identities_on_many_sites|Explicit intermediate step restored while comparing the original derivation with the merged document.
033|Identity|Unit lengths orthogonality and orientation|local_basis|a:test_basis_identities_on_many_sites|These are properties of the returned basis, not six separate algorithms.
034|Direct|Terrain derivative with a variable radius|terrain_derivatives|a:test_terrain_derivatives_against_finite_differences|
035|Direct|Vector expansion in the local basis|local_to_global|a:test_local_projections_and_origin_subtraction|
036|Derivation|Dot product isolates the east component|global_to_local|a:test_local_projections_and_origin_subtraction|The intermediate cancellation follows from orthonormality.
037|Direct|Local components as dot products|global_to_local|a:test_local_projections_and_origin_subtraction|
038|Definition|Basis matrix columns|local_basis|a:test_basis_identities_on_many_sites|
039|Direct|ENU to XYZ|local_to_global|a:test_local_projections_and_origin_subtraction|
040|Direct|XYZ to ENU|global_to_local|a:test_local_projections_and_origin_subtraction|NumPy uses row-vector storage; v @ B equals the transpose of B.T @ column_v.
041|Identity|Inverse equals transpose|local_basis|a:test_basis_identities_on_many_sites|An algebraic property; no runtime matrix inversion is needed.
042|Direct|Observer-relative body vector|observer_to_body|a:test_local_projections_and_origin_subtraction|
043|Direct|Horizontal vector length|azimuth_elevation|m:test_basis_and_document_example|
044|Derivation|Elevation tangent relation|azimuth_elevation|a:test_azimuth_convention_and_component_reconstruction|
045|Direct|Elevation using atan2|azimuth_elevation|m:test_basis_and_document_example|
046|Derivation|Sine of elevation from vector length|elevation_from_sine|m:test_basis_and_document_example|Explicit intermediate step restored while comparing the original derivation with the merged document.
047|Direct|Equivalent elevation using arcsine|elevation_from_sine|m:test_basis_and_document_example|
048|Definition|Azimuth origin and orientation|azimuth_elevation|a:test_azimuth_convention_and_component_reconstruction|
049|Direct|Horizontal components from azimuth|horizontal_components|a:test_azimuth_convention_and_component_reconstruction|
050|Direct|Azimuth using atan2|azimuth_elevation|a:test_azimuth_convention_and_component_reconstruction|
051|Example|Numerical ENU basis|local_basis|m:test_basis_and_document_example|
052|Example|Illustrative input vector|global_to_local|m:test_basis_and_document_example|A test fixture, not an observation or a function to calculate that vector.
053|Example|Projected vector and its angles|global_to_local,azimuth_elevation|m:test_basis_and_document_example|
054|Example|Projected vector and its angles|global_to_local,azimuth_elevation|m:test_basis_and_document_example|
055|Example|Projected vector and its angles|global_to_local,azimuth_elevation|m:test_basis_and_document_example|
056|Numerical|Continuous terrain supremum|build_sampled_horizon,make_horizon|m:test_sampled_horizon_and_north_wrap|A maximum over finite terrain samples followed by periodic interpolation approximates the supremum.
057|Direct|Angular clearance above terrain|angular_clearance|a:test_great_circle_and_clearance|
058|Direct|Horizontal direction and great-circle direction|great_circle_direction|a:test_great_circle_and_clearance|
059|Direct|Horizontal direction and great-circle direction|great_circle_direction|a:test_great_circle_and_clearance|
060|Direct|Terrain radius from reference radius and elevation|build_sampled_horizon|m:test_sampled_horizon_and_north_wrap|
061|Direct|Terrain vector components and exact elevation angle|great_circle_direction,terrain_elevation_angle|m:test_exact_terrain_matches_vector_geometry|
062|Direct|Terrain vector components and exact elevation angle|great_circle_direction,terrain_elevation_angle|m:test_exact_terrain_matches_vector_geometry|
063|Direct|Terrain vector components and exact elevation angle|great_circle_direction,terrain_elevation_angle|m:test_exact_terrain_matches_vector_geometry|
064|Numerical|Horizon as the supremum along a direction|build_sampled_horizon|m:test_sampled_horizon_and_north_wrap|Finite scan samples do not guarantee detection of every intervening ridge.
065|Derivation|Small-angle sine and cosine expansions|approximate_terrain_elevation|a:test_small_angle_curvature_and_flat_comparison|The truncated expansions justify the approximation; the exact path uses NumPy sine and cosine.
066|Approximation|Terrain elevation with curvature drop|approximate_terrain_elevation,curvature_drop|a:test_small_angle_curvature_and_flat_comparison|Requires small central angles and elevations small relative to the reference radius.
067|Approximation|Terrain elevation with curvature drop|approximate_terrain_elevation,curvature_drop|a:test_small_angle_curvature_and_flat_comparison|Requires small central angles and elevations small relative to the reference radius.
068|Example|Flat-surface summit elevation comparison|approximate_terrain_elevation|a:test_small_angle_curvature_and_flat_comparison|The flat comparison is an example evaluated with atan2 in the test; the related runtime function includes curvature.
069|Example|Spherical summit angle and curvature drop|terrain_elevation_angle,curvature_drop|m:test_curvature_and_coverage_examples|
070|Example|Spherical summit angle and curvature drop|terrain_elevation_angle,curvature_drop|m:test_curvature_and_coverage_examples|
071|Derivation|Tangent triangle horizon angle|smooth_sphere_horizon|m:test_curvature_and_coverage_examples|
072|Direct|Negative smooth-sphere horizon|smooth_sphere_horizon|m:test_curvature_and_coverage_examples|
073|Example|Lunar horizon and horizon distance at 2 m|smooth_sphere_horizon,smooth_sphere_horizon_distance|m:test_curvature_and_coverage_examples|
074|Direct|Ground-level sphere elevation and limiting supremum|ground_level_sphere_elevation|a:test_ground_level_horizon_is_a_supremum|The sampled maximum at h=0 can be negative although the continuous supremum is zero.
075|Identity|Continuous ground-level horizon supremum|ground_level_sphere_elevation,smooth_sphere_horizon|a:test_ground_level_horizon_is_a_supremum|Explicit intermediate step restored while comparing the original derivation with the merged document.
076|Input|Global minimum and maximum terrain radii|terrain_coverage_limit|a:test_coverage_bound_against_line_segment_occlusion|Actual guaranteed global bounds must come from the surface model.
077|Direct|Two tangent angles and sufficient terrain coverage|terrain_coverage_limit|a:test_coverage_bound_against_line_segment_occlusion|The segment test independently checks inner-sphere obstruction beyond the computed bound.
078|Direct|Two tangent angles and sufficient terrain coverage|terrain_coverage_limit|a:test_coverage_bound_against_line_segment_occlusion|The segment test independently checks inner-sphere obstruction beyond the computed bound.
079|Direct|Two tangent angles and sufficient terrain coverage|terrain_coverage_limit|a:test_coverage_bound_against_line_segment_occlusion|The segment test independently checks inner-sphere obstruction beyond the computed bound.
080|Example|Illustrative global radius bounds|terrain_coverage_limit|m:test_curvature_and_coverage_examples|
081|Approximation|Feature angular width|feature_angular_width|a:test_feature_width_and_uncertainty|Uses the small-angle width divided by distance approximation.
082|Direct|Body distance and angular radius|angular_radius|a:test_angular_disc_geometry_and_area_derivative|
083|Direct|Body distance and angular radius|angular_radius|a:test_angular_disc_geometry_and_area_derivative|
084|Direct|Body distance and angular radius|angular_radius|a:test_angular_disc_geometry_and_area_derivative|
085|Example|Illustrative solar angular radius|angular_radius|a:test_angular_disc_geometry_and_area_derivative|
086|Direct|Centre clearance above a straight boundary|angular_clearance|a:test_great_circle_and_clearance|
087|Direct|Fully blocked partially visible and fully visible cases|flat_disc_fraction|m:test_disc_formula_and_area_integral|Exact within the adopted planar small-disc model.
088|Derivation|Planar circular domain and strip endpoints|disc_strip_width,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|The circle is a model definition and the square-root endpoints lead to the strip width.
089|Derivation|Visible side of the straight horizon in disc coordinates|flat_disc_visible_area|m:test_disc_formula_and_area_integral|Explicit intermediate step restored while comparing the original derivation with the merged document.
090|Derivation|Planar circular domain and strip endpoints|disc_strip_width,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|The circle is a model definition and the square-root endpoints lead to the strip width.
091|Direct|Circular strip width and area element|disc_strip_width|a:test_angular_disc_geometry_and_area_derivative|
092|Direct|Visible circular area from its antiderivative|flat_disc_visible_area,disc_area_antiderivative|m:test_disc_formula_and_area_integral|The planar integral is evaluated in closed form.
093|Derivation|Trigonometric substitution in the area integral|disc_area_antiderivative|a:test_angular_disc_geometry_and_area_derivative|The substitution is a derivation step, not an additional runtime algorithm.
094|Derivation|Double-angle identity used in disc integration|disc_area_antiderivative|a:test_angular_disc_geometry_and_area_derivative|Explicit intermediate step restored while comparing the original derivation with the merged document.
095|Derivation|Trigonometric substitution in the area integral|disc_area_antiderivative|a:test_angular_disc_geometry_and_area_derivative|The substitution is a derivation step, not an additional runtime algorithm.
096|Direct|Area antiderivative and its lower-limit evaluation|disc_area_antiderivative|a:test_angular_disc_geometry_and_area_derivative|
097|Direct|Area antiderivative and its lower-limit evaluation|disc_area_antiderivative|a:test_angular_disc_geometry_and_area_derivative|
098|Direct|Visible circular area after substituting integration limits|flat_disc_visible_area,disc_area_antiderivative|m:test_disc_formula_and_area_integral|Explicit intermediate step restored while comparing the original derivation with the merged document.
099|Direct|Normalized clearance and circular-segment fraction|flat_disc_fraction|m:test_disc_formula_and_area_integral|Clipping k to [-1,1] is algebraically equivalent to the three cases.
100|Direct|Normalized clearance and circular-segment fraction|flat_disc_fraction|m:test_disc_formula_and_area_integral|Clipping k to [-1,1] is algebraically equivalent to the three cases.
101|Example|Half and offset disc fractions|flat_disc_fraction|m:test_disc_formula_and_area_integral|
102|Example|Half and offset disc fractions|flat_disc_fraction|m:test_disc_formula_and_area_integral|
103|Direct|Terrain ray mask|terrain_visibility|a:test_great_circle_and_clearance|
104|Numerical|Visible-area integral for uneven terrain|disc_terrain_fraction,weighted_visible_fraction|m:test_disc_samples_converge_to_straight_boundary|Finite equal-area samples approximate the integral; a straight-boundary analytic result is checked.
105|Direct|Weighted and equal-weight visible sums|weighted_visible_fraction|a:test_disc_sample_coordinates_and_weighted_areas|
106|Direct|Weighted and equal-weight visible sums|weighted_visible_fraction|a:test_disc_sample_coordinates_and_weighted_areas|
107|Direct|Square-root radius law for equal-area samples|disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|
108|Direct|Disc basis coordinates and normalized ray directions|unit_vector,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|Directions use the stated planar tangent projection and small-disc area interpretation.
109|Direct|Disc basis coordinates and normalized ray directions|unit_vector,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|Directions use the stated planar tangent projection and small-disc area interpretation.
110|Direct|Disc basis coordinates and normalized ray directions|unit_vector,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|Directions use the stated planar tangent projection and small-disc area interpretation.
111|Direct|Disc basis coordinates and normalized ray directions|unit_vector,disc_sample_directions|a:test_disc_sample_coordinates_and_weighted_areas|Directions use the stated planar tangent projection and small-disc area interpretation.
112|Direct|Earth angular radius and centre direction|angular_radius,earth_open_mask|a:test_occultation_against_ray_sphere_intersection|
113|Direct|Angular Earth obstruction and open-ray mask|earth_open_mask|a:test_occultation_against_ray_sphere_intersection|The forward ray is also required to intersect a nearer occulting body.
114|Direct|Angular Earth obstruction and open-ray mask|earth_open_mask|a:test_occultation_against_ray_sphere_intersection|The forward ray is also required to intersect a nearer occulting body.
115|Direct|Angular Earth obstruction and open-ray mask|earth_open_mask|a:test_occultation_against_ray_sphere_intersection|The forward ray is also required to intersect a nearer occulting body.
116|Direct|Terrain and Earth mask intersection|solar_visibility|m:test_combined_masks_and_occultation|
117|Direct|Mean of the combined ray masks|solar_visibility,weighted_visible_fraction|m:test_combined_masks_and_occultation|This finite sum is direct; its approximation to the continuous disc remains numerical.
118|Direct|Earth centre clearance and visibility indicator|solar_visibility,point_visibility_indicator|a:test_great_circle_and_clearance|
119|Direct|Incidence cosine and projected panel area|effective_panel_area|m:test_panel_power_and_radiance|The implementation clips a negative projected area to zero for a single-sided panel.
120|Direct|Incidence cosine and projected panel area|effective_panel_area|m:test_panel_power_and_radiance|The implementation clips a negative projected area to zero for a single-sided panel.
121|Approximation|Power using the solar centre direction|panel_power|m:test_panel_power_and_radiance|Assumes negligible incidence variation over a small uniform-brightness disc.
122|Direct|Inverse-square irradiance scaling|irradiance_at_distance|m:test_panel_power_and_radiance|
123|Numerical|Radiance integral for panel power|panel_power_from_radiance|m:test_panel_power_and_radiance|The caller supplies radiance and solid-angle quadrature weights; analyze uses the centre-direction approximation.
124|Numerical|Zero of the continuous clearance function|angular_clearance,refine_transition|m:test_event_times|Bisection refines an already bracketed root; it does not detect all roots by itself.
125|Direct|Illumination threshold margin and state|illumination_indicator,windows_from_samples|m:test_windows_and_duration|A zero threshold uses strictly positive light to exclude complete darkness.
126|Definition|Endpoint values of the transition margin|linear_transition_time|m:test_event_times|Explicit intermediate step restored while comparing the original derivation with the merged document.
127|Derivation|Solving the linear margin interpolation for time|linear_transition_time|m:test_event_times|These are algebraic steps leading to the same interpolated crossing time.
128|Derivation|Solving the linear margin interpolation for time|linear_transition_time|m:test_event_times|These are algebraic steps leading to the same interpolated crossing time.
129|Derivation|Solving the linear margin interpolation for time|linear_transition_time|m:test_event_times|These are algebraic steps leading to the same interpolated crossing time.
130|Approximation|Interpolated crossing time|linear_transition_time|m:test_event_times|Exact for the chosen linear interpolant, approximate for a nonlinear physical trajectory.
131|Example|Endpoint values in the twenty-minute event example|linear_transition_time|m:test_event_times|Explicit intermediate step restored while comparing the original derivation with the merged document.
132|Example|Twenty-minute crossing example|linear_transition_time|m:test_event_times|
133|Derivation|First-order expansion near an event|transition_time_uncertainty|a:test_taylor_error_and_event_sensitivity|
134|Approximation|Event timing uncertainty from angular uncertainty|transition_time_uncertainty|a:test_feature_width_and_uncertainty|A local first-order sensitivity estimate, with infinite sensitivity at zero rate.
135|Definition|Indicator of the selected illumination criterion|illumination_indicator,power_indicator|m:test_windows_and_duration|Explicit intermediate step restored while comparing the original derivation with the merged document.
136|Direct|State duration integral over known windows|total_duration|a:test_duration_integral_and_joint_intersection|Exact for the supplied windows; sampled estimates of the window boundaries have separate errors.
137|Direct|Sum of window lengths|total_duration,window_durations|a:test_duration_integral_and_joint_intersection|
138|Direct|Fraction of analysis time with suitable light|analyze|m:test_complete_calculation_uses_explicit_formulas|
139|Direct|Earth state duration integral over known windows|total_duration|a:test_duration_integral_and_joint_intersection|
140|Direct|Longest suitable window and longest interruption|longest_duration,complement_windows|a:test_duration_integral_and_joint_intersection|
141|Direct|Longest suitable window and longest interruption|longest_duration,complement_windows|a:test_duration_integral_and_joint_intersection|
142|Numerical|Equivalent full-disc time integral|equivalent_full_disc_time,time_integral|a:test_exact_two_full_hours_plus_one_half_visible_hour|Trapezoids approximate sampled functions; interval mode is exact for supplied piecewise-constant intervals.
143|Example|Two fully visible hours and one half-visible hour|equivalent_full_disc_time|a:test_exact_two_full_hours_plus_one_half_visible_hour|Interval mode returns exactly 9000 seconds or 2.5 hours.
144|Direct|Mean visible fraction|mean_disc_fraction|a:test_exact_two_full_hours_plus_one_half_visible_hour|The mean inherits the accuracy of the chosen integration method.
145|Numerical|Electrical energy integral|electrical_energy,time_integral|a:test_exact_two_full_hours_plus_one_half_visible_hour|Trapezoids or exact integration of supplied piecewise-constant powers.
146|Direct|Watt-hour to joule conversion|electrical_energy|m:test_integrals_use_elapsed_time|
147|Direct|Trapezoidal integration sum|time_integral|a:test_trapezoid_exactness_and_quadratic_convergence|The finite sum is direct; it approximates an unknown continuous power curve.
148|Direct|Joint state indicator|joint_indicator|a:test_duration_integral_and_joint_intersection|
149|Direct|Joint duration from interval intersection|intersect_windows,total_duration|a:test_duration_integral_and_joint_intersection|Exact for the supplied window sets.
150|Direct|Intersection length of two windows|intersect_windows|m:test_windows_and_duration|
151|Direct|Time remaining until the next actual event|time_to_next_event|m:test_windows_and_duration|Event times exclude boundaries caused only by the end of the analysis period.
152|Direct|Smooth-sphere horizon with nonzero DEM elevation|smooth_sphere_horizon|a:test_nonzero_dem_sphere_and_height_sensitivity|
153|Direct|Terrain angle derivative with observer height|observer_height_sensitivity|a:test_nonzero_dem_sphere_and_height_sensitivity|
154|Approximation|Elevation uncertainty from terrain height uncertainty|elevation_uncertainty|a:test_feature_width_and_uncertainty|Uses small angles and a small height-to-distance ratio.
"""

REPORT_TEMPLATE = r"""# Formula implementation audit

All {{equation_count}} displayed equation blocks in README are individually mapped below to implementation locations and executable evidence. The mapping contains exactly one row per block. {{test_count}} tests passed under Python {{python_version}} with NumPy {{numpy_version}}. All {{function_count}} top-level implementation functions were called by the tests. Classification counts: {{classification}}.

The verifier ran inside a virtual environment: {{in_virtualenv}}. Function-call coverage means every function was exercised at least once; it does not mean every branch or every possible input was covered.

This is a correspondence audit with analytical explanations and numerical tests. It is not a machine-checked proof for every possible input. Repeated expressions, intermediate derivation steps, identities, input definitions, and examples are distinguished from executable algorithms. Passing a related test is evidence for the named relation, not a claim that finite tests establish a universal theorem.

## How to reproduce

```sh
source .venv/bin/activate
python -B verify_formulas.py
```

The verifier checks the fingerprint of all {{equation_count}} formula blocks, requires a unique mapping for every block, confirms the referenced implementation and test functions exist, runs both test suites, and regenerates this report. A changed equation stops verification until the mapping is reviewed.

## Why the main transformations are equivalent

### Coordinate matrices

The document stores a mathematical vector as a column and writes $v_{ENU}=B^{\mathsf T}v_{XYZ}$. NumPy stores a single vector as a one-dimensional array. The code computes its row-vector equivalent, $v_{XYZ}^{\mathsf T}B=(B^{\mathsf T}v_{XYZ})^{\mathsf T}$. Each output entry is therefore the same dot product. Tests check the dot products independently and recover the original vector through the inverse transformation.

### The piecewise circular segment formula

The implementation evaluates the interior formula with $k$ clipped to $[-1,1]$. At $k=-1$, $\arcsin(-1)=-\pi/2$ and the square-root term is zero, so $f=0$. At $k=1$ the result is $f=1$. For $-1<k<1$, clipping leaves $k$ unchanged. This is the same three-case formula in equation 100, within the planar small-disc assumptions. Separate tests differentiate the area antiderivative numerically and compare the strip integral with the closed form.

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

"""


if __name__ == "__main__":
    raise SystemExit(main())

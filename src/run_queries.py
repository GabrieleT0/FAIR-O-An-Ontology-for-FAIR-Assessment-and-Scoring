import argparse
import csv
import importlib.util
import re
from pathlib import Path

from rdflib import Dataset, Graph, URIRef

from build_integrated_graph import (
    DEFAULT_OUTPUT as INTEGRATED_FILE,
    build_integrated_dataset,
    write_integrated_dataset,
)


BASE_DIR = Path(__file__).resolve().parent.parent

ONTOLOGY_FILE = BASE_DIR / "FAIR-O.ttl"
DATA_DIR = BASE_DIR / "data"
QUERY_DIR = BASE_DIR / "queries"
RESULT_DIR = BASE_DIR / "results"
RESULT_DIR.mkdir(exist_ok=True)

VARIABLE_RE = re.compile(r"\?(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
SELECT_RE = re.compile(r"SELECT\s+(?P<select>.*?)\s+WHERE\s*\{", re.IGNORECASE | re.DOTALL)
BINDING_DIRECTIVE_RE = re.compile(r"^\s*#\s*@bind\s+(?P<names>.+)$", re.MULTILINE)


def tool_name_from_folder(folder_path: Path) -> str:
    return folder_path.name.removesuffix("_assessment")


def discover_assessment_files() -> list[Path]:
    return sorted(
        file_path
        for file_path in DATA_DIR.glob("*_assessment/*.ttl")
        if file_path.is_file()
    )


def term_to_csv(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def write_query_results(output_file: Path, variables: list[str], rows: list[list]) -> None:
    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(variables)
        writer.writerows([[term_to_csv(value) for value in row] for row in rows])


def filter_query_paths(query_paths: list[Path], selected_queries: list[str] | None) -> list[Path]:
    if not selected_queries:
        return query_paths

    selected = {query.casefold() for query in selected_queries}
    filtered = [
        query_path for query_path in query_paths
        if query_path.stem.casefold() in selected
        or query_path.stem.split("-")[0].casefold() in selected
    ]
    missing = selected - {
        value
        for query_path in filtered
        for value in (
            query_path.stem.casefold(),
            query_path.stem.split("-")[0].casefold(),
        )
    }
    if missing:
        raise FileNotFoundError(
            "No query file found for: " + ", ".join(sorted(missing))
        )
    return filtered


def query_variables(query_text: str) -> set[str]:
    return {match.group("name") for match in VARIABLE_RE.finditer(query_text)}


def projected_variables(query_text: str) -> set[str]:
    match = SELECT_RE.search(query_text)
    if not match:
        return query_variables(query_text)
    return {
        variable
        for variable in query_variables(match.group("select"))
        if variable != "WHERE"
    }


def bindable_variables(query_text: str) -> set[str]:
    variables = set()
    for match in BINDING_DIRECTIVE_RE.finditer(query_text):
        variables.update(match.group("names").split())
    return variables


def rdflib_bindings(bindings: dict[str, str], query_text: str) -> dict[str, URIRef]:
    variables = bindable_variables(query_text)
    return {
        name: URIRef(value)
        for name, value in bindings.items()
        if name in variables
    }


def oxigraph_bindings(bindings: dict[str, str], query_text: str):
    from pyoxigraph import NamedNode, Variable

    variables = bindable_variables(query_text)
    return {
        Variable(name): NamedNode(value)
        for name, value in bindings.items()
        if name in variables
    }


def run_rdflib_query(graph, query_text: str, bindings: dict[str, str]) -> tuple[list[str], list[list]]:
    query_results = graph.query(
        query_text,
        initBindings=rdflib_bindings(bindings, query_text),
    )
    variables = [str(var) for var in query_results.vars]
    return variables, list(query_results)


def run_oxigraph_query(store, query_text: str, bindings: dict[str, str]) -> tuple[list[str], list[list]]:
    query_results = store.query(
        query_text,
        use_default_graph_as_union=True,
        substitutions=oxigraph_bindings(bindings, query_text),
    )
    variables = [var.value for var in query_results.variables]
    rows = [
        [solution[var] for var in query_results.variables]
        for solution in query_results
    ]
    return variables, rows


def run_queries_for_assessment(
    assessment_file: Path,
    query_paths: list[Path],
    bindings: dict[str, str],
) -> list[list]:
    tool_name = tool_name_from_folder(assessment_file.parent)
    output_dir = RESULT_DIR / tool_name
    output_dir.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    graph.parse(ONTOLOGY_FILE, format="turtle")
    graph.parse(assessment_file, format="turtle")

    summary_rows = []

    for query_path in query_paths:
        print(f"{tool_name}: running {query_path.name}", flush=True)
        query_text = query_path.read_text(encoding="utf-8")
        variables, rows = run_rdflib_query(graph, query_text, bindings)

        output_file = output_dir / query_path.name.replace(".rq", ".csv")
        write_query_results(output_file, variables, rows)

        cq_id = query_path.stem.split("-")[0]
        status = "Answered" if rows else "No results"

        summary_rows.append([
            tool_name,
            assessment_file.relative_to(BASE_DIR),
            cq_id,
            query_path.name,
            len(rows),
            status,
        ])

    summary_file = output_dir / "cq-evaluation-summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Tool",
            "Assessment file",
            "CQ",
            "Query file",
            "Rows returned",
            "Status",
        ])
        writer.writerows(summary_rows)

    print(
        f"{tool_name}: loaded {len(graph)} triples from "
        f"{assessment_file.relative_to(BASE_DIR)}."
    )
    print(f"{tool_name}: saved query results in {output_dir}.")

    return summary_rows


def oxigraph_available() -> bool:
    return importlib.util.find_spec("pyoxigraph") is not None


def resolve_integrated_engine(engine: str) -> str:
    if engine == "auto":
        return "oxigraph" if oxigraph_available() else "rdflib"
    if engine == "oxigraph" and not oxigraph_available():
        raise ImportError(
            "pyoxigraph is not installed. Install it or use --engine rdflib."
        )
    return engine


def load_oxigraph_store(input_file: Path):
    from pyoxigraph import RdfFormat, Store

    store = Store()
    store.load(path=str(input_file), format=RdfFormat.TRIG)
    return store


def load_rdflib_dataset(input_file: Path) -> Dataset:
    dataset = Dataset()
    dataset.parse(input_file, format="trig")
    dataset.default_union = True
    return dataset


def run_integrated_queries(
    query_paths: list[Path],
    rebuild: bool,
    engine: str,
    bindings: dict[str, str],
) -> list[list]:
    output_dir = RESULT_DIR / "integrated"
    output_dir.mkdir(parents=True, exist_ok=True)

    if rebuild or not INTEGRATED_FILE.is_file():
        dataset = build_integrated_dataset()
        write_integrated_dataset(dataset, INTEGRATED_FILE)

    engine = resolve_integrated_engine(engine)
    if engine == "oxigraph":
        graph = load_oxigraph_store(INTEGRATED_FILE)
        graph_size = len(graph)
        query_runner = run_oxigraph_query
    else:
        graph = load_rdflib_dataset(INTEGRATED_FILE)
        graph_size = len(graph)
        query_runner = run_rdflib_query

    summary_rows = []
    for query_path in query_paths:
        print(f"integrated ({engine}): running {query_path.name}", flush=True)
        query_text = query_path.read_text(encoding="utf-8")
        variables, rows = query_runner(graph, query_text, bindings)
        write_query_results(
            output_dir / query_path.name.replace(".rq", ".csv"),
            variables,
            rows,
        )

        cq_id = query_path.stem.split("-")[0]
        summary_rows.append([
            "integrated",
            INTEGRATED_FILE.relative_to(BASE_DIR),
            cq_id,
            query_path.name,
            len(rows),
            "Answered" if rows else "No results",
        ])

    summary_file = output_dir / "cq-evaluation-summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Tool",
            "Assessment file",
            "CQ",
            "Query file",
            "Rows returned",
            "Status",
        ])
        writer.writerows(summary_rows)

    print(f"integrated: loaded {graph_size} triples from {INTEGRATED_FILE.relative_to(BASE_DIR)}.")
    print(f"integrated: saved query results in {output_dir}.")
    return summary_rows


def parse_binding(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "Bindings must use NAME=IRI syntax, for example digitalObject=https://example.org/id"
        )
    name, iri = value.split("=", 1)
    if not name or not iri:
        raise argparse.ArgumentTypeError("Binding name and IRI must be non-empty.")
    return name, iri


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute FAIR-O competency queries.")
    parser.add_argument(
        "--queries",
        nargs="+",
        metavar="CQ",
        help=(
            "Run only selected query IDs or stems, for example: "
            "--queries CQ15 CQ16 CQ17"
        ),
    )
    parser.add_argument(
        "--integrated",
        action="store_true",
        help="Run CQs over the single named-graph RDF dataset.",
    )
    parser.add_argument(
        "--rebuild-integrated",
        action="store_true",
        help="Rebuild the integrated TriG dataset before querying it.",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "rdflib", "oxigraph"),
        default="auto",
        help="SPARQL engine for integrated queries. Default: auto.",
    )
    parser.add_argument(
        "--binding",
        action="append",
        type=parse_binding,
        default=[],
        metavar="NAME=IRI",
        help="Bind a SPARQL variable to an IRI before query execution.",
    )
    parser.add_argument(
        "--object",
        dest="digital_object",
        help="Shortcut for --binding digitalObject=IRI.",
    )
    parser.add_argument(
        "--sub-principle",
        help="Shortcut for --binding subPrinciple=IRI.",
    )
    return parser.parse_args()


def collect_bindings(args: argparse.Namespace) -> dict[str, str]:
    bindings = dict(args.binding)
    if args.digital_object:
        bindings["digitalObject"] = args.digital_object
    if args.sub_principle:
        bindings["subPrinciple"] = args.sub_principle
    return bindings


def main() -> None:
    args = parse_args()
    bindings = collect_bindings(args)
    query_paths = filter_query_paths(sorted(QUERY_DIR.glob("CQ*.rq")), args.queries)

    if not query_paths:
        raise FileNotFoundError(f"No CQ query files found in {QUERY_DIR}.")

    if args.integrated or args.rebuild_integrated:
        run_integrated_queries(
            query_paths,
            rebuild=args.rebuild_integrated,
            engine=args.engine,
            bindings=bindings,
        )
        return

    assessment_files = discover_assessment_files()
    if not assessment_files:
        raise FileNotFoundError(f"No assessment TTL files found in {DATA_DIR}.")

    summary_rows = []
    for assessment_file in assessment_files:
        summary_rows.extend(
            run_queries_for_assessment(assessment_file, query_paths, bindings)
        )

    summary_file = RESULT_DIR / "cq-evaluation-summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Tool",
            "Assessment file",
            "CQ",
            "Query file",
            "Rows returned",
            "Status",
        ])
        writer.writerows(summary_rows)

    print(f"Saved combined summary in {summary_file}.")


if __name__ == "__main__":
    main()

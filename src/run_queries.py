from pathlib import Path
import csv
from rdflib import Graph

BASE_DIR = Path(__file__).resolve().parent.parent

ONTOLOGY_FILE = BASE_DIR / "FAIR-O.ttl"
DATA_DIR = BASE_DIR / "data"
QUERY_DIR = BASE_DIR / "queries"
RESULT_DIR = BASE_DIR / "results"
RESULT_DIR.mkdir(exist_ok=True)


def tool_name_from_folder(folder_path: Path) -> str:
    return folder_path.name.removesuffix("_assessment")


def discover_assessment_files() -> list[Path]:
    return sorted(
        file_path
        for file_path in DATA_DIR.glob("*_assessment/*.ttl")
        if file_path.is_file()
    )


def write_query_results(output_file: Path, variables: list[str], rows: list) -> None:
    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(variables)

        for row in rows:
            writer.writerow([
                str(value) if value is not None else ""
                for value in row
            ])


def run_queries_for_assessment(assessment_file: Path, query_paths: list[Path]) -> list[list]:
    tool_name = tool_name_from_folder(assessment_file.parent)
    output_dir = RESULT_DIR / tool_name
    output_dir.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    graph.parse(ONTOLOGY_FILE, format="turtle")
    graph.parse(assessment_file, format="turtle")

    summary_rows = []

    for query_path in query_paths:
        query = query_path.read_text(encoding="utf-8")
        query_results = graph.query(query)

        variables = [str(var) for var in query_results.vars]
        rows = list(query_results)

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
            status
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
            "Status"
        ])
        writer.writerows(summary_rows)

    print(
        f"{tool_name}: loaded {len(graph)} triples from "
        f"{assessment_file.relative_to(BASE_DIR)}."
    )
    print(f"{tool_name}: saved query results in {output_dir}.")

    return summary_rows


def main() -> None:
    assessment_files = discover_assessment_files()
    query_paths = sorted(QUERY_DIR.glob("CQ*.rq"))

    if not assessment_files:
        raise FileNotFoundError(f"No assessment TTL files found in {DATA_DIR}.")

    if not query_paths:
        raise FileNotFoundError(f"No CQ query files found in {QUERY_DIR}.")

    summary_rows = []

    for assessment_file in assessment_files:
        summary_rows.extend(
            run_queries_for_assessment(assessment_file, query_paths)
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
            "Status"
        ])
        writer.writerows(summary_rows)

    print(f"Saved combined summary in {summary_file}.")


if __name__ == "__main__":
    main()

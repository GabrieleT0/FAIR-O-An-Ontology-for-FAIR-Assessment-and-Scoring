#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from rdflib import Graph
from pyshacl import validate

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA = BASE_DIR / "data" / "KGHeartBeat_assessment" / "kgheartbeat_assessment_fair-o.ttl"
DEFAULT_SHAPES = BASE_DIR / "FAIR-O_shape.ttl"
DEFAULT_ONTOLOGY = BASE_DIR / "FAIR-O.ttl"

FORMAT_BY_SUFFIX = {
    ".ttl": "turtle",
    ".turtle": "turtle",
    ".nt": "nt",
    ".nq": "nquads",
    ".n3": "n3",
    ".rdf": "xml",
    ".owl": "xml",
    ".xml": "xml",
    ".jsonld": "json-ld",
    ".json": "json-ld",
}


def guess_format(path: Path) -> str:
    """Return an rdflib parser format based on a file extension."""
    return FORMAT_BY_SUFFIX.get(path.suffix.lower(), "turtle")


def load_graph(path: Path, label: str) -> Graph:
    if not path.exists():
        raise FileNotFoundError(f"{label} file does not exist: {path}")

    graph = Graph()
    graph.parse(path, format=guess_format(path))
    return graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate FAIR-O RDF data using FAIR-O_shape.ttl SHACL shapes."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help=f"RDF data file to validate. Default: {DEFAULT_DATA}",
    )
    parser.add_argument(
        "--shapes",
        type=Path,
        default=DEFAULT_SHAPES,
        help=f"SHACL shapes file. Default: {DEFAULT_SHAPES}",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=DEFAULT_ONTOLOGY,
        help=f"Ontology graph used for class and inference context. Default: {DEFAULT_ONTOLOGY}",
    )
    parser.add_argument(
        "--no-ontology",
        action="store_true",
        help="Validate without loading an ontology graph.",
    )
    parser.add_argument(
        "--inference",
        choices=("none", "rdfs", "owlrl", "both"),
        default="rdfs",
        help="Inference mode passed to pySHACL. Default: rdfs",
    )
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Enable pySHACL advanced features.",
    )
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="Treat SHACL warning severities as conformant.",
    )
    parser.add_argument(
        "--allow-infos",
        action="store_true",
        help="Treat SHACL info severities as conformant.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the validation report graph.",
    )
    parser.add_argument(
        "--report-format",
        choices=("turtle", "json-ld", "xml", "nt"),
        default="turtle",
        help="Serialization format for --report. Default: turtle",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        data_graph = load_graph(args.data, "Data")
        shapes_graph = load_graph(args.shapes, "Shapes")
        ontology_graph = None

        if not args.no_ontology:
            ontology_graph = load_graph(args.ontology, "Ontology")
    except Exception as exc:
        print(f"Could not load RDF graph: {exc}", file=sys.stderr)
        return 2

    try:
        conforms, report_graph, report_text = validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            ont_graph=ontology_graph,
            inference=args.inference,
            advanced=args.advanced,
            allow_warnings=args.allow_warnings,
            allow_infos=args.allow_infos,
        )
    except Exception as exc:
        print(f"Validation failed to run: {exc}", file=sys.stderr)
        return 2

    print(report_text)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            report_graph.serialize(format=args.report_format),
            encoding="utf-8",
        )
        print(f"Wrote validation report to {args.report}")

    return 0 if conforms else 1


if __name__ == "__main__":
    raise SystemExit(main())

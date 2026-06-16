from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote

from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import DCTERMS


BASE_DIR = Path(__file__).resolve().parent.parent
ONTOLOGY_FILE = BASE_DIR / "FAIR-O.ttl"
DEFAULT_OUTPUT = BASE_DIR / "FAIR-O_data.trig"

FAIRO = "https://w3id.org/fair-o#"
RESOURCE_BASE = "https://w3id.org/fair-o/resource/"
GRAPH_BASE = "https://w3id.org/fair-o/graph/"
WAS_ASSESSED_BY = URIRef(f"{FAIRO}wasAssessedBy")

ASSESSMENT_SOURCES = {
    "fuji": BASE_DIR / "data" / "F-UJI_assessment" / "fuji_assessment_fair-o.ttl",
    "fairchecker": BASE_DIR / "data" / "FAIRChecker_assessment" / "fairchecker_assessment_fair-o.ttl",
    "kgheartbeat": BASE_DIR / "data" / "KGHeartBeat_assessment" / "kgheartbeat_assessment_fair-o.ttl",
}

LOCAL_RESOURCE_BASES = (
    RESOURCE_BASE,
    "https://kgheartbeat.di.unisa.it/fairness-data/",
)


def uri_segment(value: object) -> str:
    return quote(str(value).strip().rstrip("."), safe="")


def normalized_uri(value: URIRef) -> URIRef:
    return URIRef(quote(str(value), safe=":/?#[]@!$&'()*+,;=%"))


def canonical_object_iri(graph: Graph, subject: URIRef) -> URIRef:
    identifier = next(graph.objects(subject, DCTERMS.identifier), None)
    if identifier is not None and str(identifier).strip():
        return URIRef(f"{RESOURCE_BASE}dataset_{uri_segment(identifier)}")

    local_name = str(subject).rstrip("/#").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if local_name.startswith("dataset_"):
        return URIRef(f"{RESOURCE_BASE}{local_name}")
    return URIRef(f"{RESOURCE_BASE}dataset_{uri_segment(subject)}")


def tool_owned_iri(tool_id: str, value: URIRef) -> URIRef:
    text = str(value)
    for base in LOCAL_RESOURCE_BASES:
        if text.startswith(base):
            local_name = text[len(base):]
            return URIRef(f"{RESOURCE_BASE}{tool_id}/{uri_segment(local_name)}")
    return value


def add_assessment_graph(dataset: Dataset, tool_id: str, source_file: Path) -> int:
    source = Graph()
    source.parse(source_file, format="turtle")
    object_map = {
        subject: canonical_object_iri(source, subject)
        for subject in source.subjects(WAS_ASSESSED_BY, None)
        if isinstance(subject, URIRef)
    }
    target = dataset.graph(URIRef(f"{GRAPH_BASE}{tool_id}"))

    def remap(term):
        if not isinstance(term, URIRef):
            return term
        if term in object_map:
            return object_map[term]
        return normalized_uri(tool_owned_iri(tool_id, term))

    for subject, predicate, obj in source:
        target.add((remap(subject), predicate, remap(obj)))
    return len(target)


def build_integrated_dataset() -> Dataset:
    dataset = Dataset()
    dataset.default_union = True
    dataset.graph(URIRef(f"{GRAPH_BASE}ontology")).parse(ONTOLOGY_FILE, format="turtle")

    for tool_id, source_file in ASSESSMENT_SOURCES.items():
        if not source_file.is_file():
            raise FileNotFoundError(f"Assessment graph not found: {source_file}")
        add_assessment_graph(dataset, tool_id, source_file)
    return dataset


def write_integrated_dataset(dataset: Dataset, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    dataset.serialize(destination=output_file, format="trig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one named-graph RDF dataset from all FAIR assessment tools.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output TriG file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_integrated_dataset()
    write_integrated_dataset(dataset, args.output)
    print(f"Integrated RDF dataset written to {args.output}")
    for graph in dataset.graphs():
        print(f"{graph.identifier}: {len(graph)} triples")


if __name__ == "__main__":
    main()

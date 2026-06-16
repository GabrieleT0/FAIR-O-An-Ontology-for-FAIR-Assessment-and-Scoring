from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote


ANALYSIS_DATE_DEFAULT = "2026-04-01"
SOFTWARE_AGENT_ID = "FAIRChecker"
SOFTWARE_AGENT_LABEL = "FAIRChecker"
TOOL_ID = "fairchecker"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

METRIC_SPECS = {
    "score_F1A": {
        "subprinciple": "F1",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker F1A score",
        "description": "FAIRChecker score for the F1A check.",
    },
    "score_F1B": {
        "subprinciple": "F1",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker F1B score",
        "description": "FAIRChecker score for the F1B check.",
    },
    "score_F2A": {
        "subprinciple": "F2",
        "scope": "fairo:MetadataScope",
        "label": "FAIRChecker F2A score",
        "description": "FAIRChecker score for the F2A check.",
    },
    "score_F2B": {
        "subprinciple": "F2",
        "scope": "fairo:MetadataScope",
        "label": "FAIRChecker F2B score",
        "description": "FAIRChecker score for the F2B check.",
    },
    "score_A1.1": {
        "subprinciple": "A1.1",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker A1.1 score",
        "description": "FAIRChecker score for the A1.1 check.",
    },
    "score_A1.2": {
        "subprinciple": "A1.2",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker A1.2 score",
        "description": "FAIRChecker score for the A1.2 check.",
    },
    "score_I1": {
        "subprinciple": "I1",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker I1 score",
        "description": "FAIRChecker score for the I1 check.",
    },
    "score_I2": {
        "subprinciple": "I2",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker I2 score",
        "description": "FAIRChecker score for the I2 check.",
    },
    "score_I3": {
        "subprinciple": "I3",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker I3 score",
        "description": "FAIRChecker score for the I3 check.",
    },
    "score_R1.1": {
        "subprinciple": "R1.1",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker R1.1 score",
        "description": "FAIRChecker score for the R1.1 check.",
    },
    "score_R1.2": {
        "subprinciple": "R1.2",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker R1.2 score",
        "description": "FAIRChecker score for the R1.2 check.",
    },
    "score_R1.3": {
        "subprinciple": "R1.3",
        "scope": "fairo:DataAndMetadata",
        "label": "FAIRChecker R1.3 score",
        "description": "FAIRChecker score for the R1.3 check.",
    },
}

AGGREGATE_SPECS = {
    "total_F": {"predicate": "fairo:fScore", "max_raw": 8},
    "total_A": {"predicate": "fairo:aScore", "max_raw": 4},
    "total_I": {"predicate": "fairo:iScore", "max_raw": 6},
    "total_R": {"predicate": "fairo:rScore", "max_raw": 6},
    "score_total": {"predicate": "fairo:fairScore", "max_raw": 24},
}


@dataclass(frozen=True)
class DatasetRow:
    source_file: str
    row: Dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert FAIRChecker CSV assessments into a FAIR-O Turtle KG.",
    )
    parser.add_argument(
        "--input-folder",
        default=os.path.join(REPO_ROOT, "data", "FAIRChecker_assessment"),
        help="Folder containing FAIRChecker CSV files.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(REPO_ROOT, "results", "fairchecker_assessment_fair-o.ttl"),
        help="Output Turtle file.",
    )
    parser.add_argument(
        "--analysis-date",
        default=ANALYSIS_DATE_DEFAULT,
        help="Assessment analysis date in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def turtle_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def uri_segment(value: object) -> str:
    return quote(str(value).strip().rstrip("."), safe="")


def parse_float(raw: object) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def format_decimal(value: float) -> str:
    return format(value, "g")


def normalize_score(raw_value: float, max_raw: float) -> float:
    return raw_value / max_raw


def test_outcome_from_normalized(value: float) -> str:
    if value >= 1.0:
        return "fairo:Pass"
    if value <= 0.0:
        return "fairo:Fail"
    return "fairo:Indeterminate"


def load_rows(input_folder: str) -> List[DatasetRow]:
    rows: List[DatasetRow] = []
    for filename in sorted(os.listdir(input_folder)):
        if not filename.endswith(".csv"):
            continue
        csv_path = os.path.join(input_folder, filename)
        with open(csv_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(DatasetRow(source_file=filename, row=row))
    if not rows:
        raise ValueError(f"No CSV files found in {input_folder}")
    return rows


def add_prefixes(lines: List[str]) -> None:
    lines.extend(
        [
            "@prefix : <https://w3id.org/fair-o/resource/> .",
            "@prefix fairo: <https://w3id.org/fair-o#> .",
            "@prefix fairVocab: <https://w3id.org/fair/principles/terms/> .",
            "@prefix dct: <http://purl.org/dc/terms/> .",
            "@prefix prov: <http://www.w3.org/ns/prov#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix void: <http://rdfs.org/ns/void#> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "",
        ]
    )


def add_supporting_resources(lines: List[str]) -> None:
    lines.extend(
        [
            ":faircheckerDiscreteScore a fairo:ScoringFunction ;",
            '    rdfs:label "FAIRChecker discrete score normalization" ;',
            '    fairo:formula "normalizedScore = rawScore / 2" ;',
            '    dct:description "Normalizes FAIRChecker sub-principle scores from the native 0..2 scale to the FAIR-O 0..1 range." ;',
            '    fairo:minValue "0"^^xsd:decimal ;',
            '    fairo:maxValue "1"^^xsd:decimal .',
            "",
            ":faircheckerAggregateNormalization a fairo:AggregationMethod ;",
            '    rdfs:label "FAIRChecker aggregate normalization" ;',
            '    fairo:formula "normalizedAggregate = rawAggregate / principleMaximum" ;',
            '    dct:description "Normalizes FAIRChecker principle and overall totals by dividing each raw aggregate by its maximum attainable value." .',
            "",
            f":{SOFTWARE_AGENT_ID} a prov:SoftwareAgent ;",
            f'    rdfs:label "{SOFTWARE_AGENT_LABEL}" .',
            "",
        ]
    )

    for metric_name, spec in METRIC_SPECS.items():
        algorithm_id = f"algorithm_{uri_segment(metric_name)}"
        description = turtle_escape(spec["description"])
        label = turtle_escape(spec["label"])
        lines.extend(
            [
                f":{algorithm_id} a fairo:CalculationAlgorithm ;",
                f'    rdfs:label "{label}" ;',
                f"    fairo:implementedBy :{SOFTWARE_AGENT_ID} ;",
                f"    fairo:appliesScoringFunction :faircheckerDiscreteScore ;",
                f'    fairo:algorithmDescription "{description}" .',
                "",
            ]
        )


def emit_dataset(lines: List[str], dataset_uri: str, dataset_id: str, processed_url: str) -> None:
    lines.append(f":{dataset_uri} a void:Dataset, prov:Entity ;")
    lines.append(f'    dct:title "{turtle_escape(dataset_id)}" ;')
    lines.append(f'    dct:identifier "{turtle_escape(dataset_id)}" ;')
    if processed_url:
        lines.append(f"    dct:source <{processed_url}> ;")
    lines[-1] = lines[-1].rstrip(" ;") + " ."
    lines.append("")


def emit_assessment(
    lines: List[str],
    assessment_uri: str,
    dataset_uri: str,
    analysis_date: str,
    aggregates: Dict[str, float],
) -> None:
    dt = f"{analysis_date}T00:00:00Z"
    lines.extend(
        [
            f":{assessment_uri} a fairo:FAIRAssessment, prov:Activity ;",
            f"    prov:used :{dataset_uri} ;",
            f'    prov:startedAtTime "{dt}"^^xsd:dateTime ;',
            f'    prov:endedAtTime "{dt}"^^xsd:dateTime ;',
            "    fairo:usesAggregationMethod :faircheckerAggregateNormalization .",
            "",
        ]
    )

    aggregate_entries: List[str] = []
    for column, spec in AGGREGATE_SPECS.items():
        raw_value = aggregates.get(column)
        if raw_value is None:
            continue
        normalized = normalize_score(raw_value, spec["max_raw"])
        aggregate_entries.append(
            f'    {spec["predicate"]} "{format_decimal(normalized)}"^^xsd:decimal'
        )

    if aggregate_entries:
        lines.append(f":{assessment_uri}")
        for index, entry in enumerate(aggregate_entries):
            suffix = " ;" if index < len(aggregate_entries) - 1 else " ."
            lines.append(f"{entry}{suffix}")
        lines.append("")


def emit_result(
    lines: List[str],
    result_uri: str,
    metric_name: str,
    raw_value: float,
    source_file: str,
) -> None:
    spec = METRIC_SPECS[metric_name]
    normalized = normalize_score(raw_value, 2)
    evidence = (
        f"Metric {metric_name} from {source_file} returned raw FAIRChecker score "
        f"{format_decimal(raw_value)} on a 0..2 scale; normalized FAIR-O value is "
        f"{format_decimal(normalized)}."
    )
    algorithm_id = f"algorithm_{uri_segment(metric_name)}"

    lines.extend(
        [
            f":{result_uri} a fairo:SubPrincipleResult ;",
            f"    fairo:forSubPrinciple fairVocab:{spec['subprinciple']} ;",
            f"    fairo:assessmentScope {spec['scope']} ;",
            f'    fairo:value "{format_decimal(normalized)}"^^xsd:decimal ;',
            f"    fairo:testResult {test_outcome_from_normalized(normalized)} ;",
            f'    fairo:evidence "{turtle_escape(evidence)}" ;',
            f"    fairo:computedUsing :{algorithm_id} .",
            "",
        ]
    )


def build_graph(rows: Iterable[DatasetRow], analysis_date: str) -> List[str]:
    lines: List[str] = []
    add_prefixes(lines)
    add_supporting_resources(lines)

    for dataset in rows:
        row = dataset.row
        dataset_id = (row.get("id") or "").strip()
        if not dataset_id:
            continue

        processed_url = (row.get("processed_url") or "").strip()
        dataset_uri = f"dataset_{uri_segment(dataset_id)}"
        assessment_uri = (
            f"assessment_{TOOL_ID}_{uri_segment(dataset_id)}_"
            f"{uri_segment(analysis_date)}"
        )

        emit_dataset(lines, dataset_uri, dataset_id, processed_url)

        aggregates = {
            column: parse_float(row.get(column))
            for column in AGGREGATE_SPECS
        }
        emit_assessment(lines, assessment_uri, dataset_uri, analysis_date, aggregates)

        lines.append(f":{dataset_uri} fairo:wasAssessedBy :{assessment_uri} .")
        lines.append("")

        for metric_name in METRIC_SPECS:
            raw_value = parse_float(row.get(metric_name))
            if raw_value is None:
                continue
            result_uri = (
                f"result_{TOOL_ID}_{uri_segment(dataset_id)}_"
                f"{uri_segment(metric_name)}_"
                f"{uri_segment(analysis_date)}"
            )
            emit_result(lines, result_uri, metric_name, raw_value, dataset.source_file)
            lines.append(f":{assessment_uri} fairo:hasSubPrincipleResult :{result_uri} .")
            lines.append("")

    return lines


def write_output(lines: List[str], output_path: str) -> None:
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input_folder)
    lines = build_graph(rows, args.analysis_date)
    write_output(lines, args.output)
    print(f"KG written to: {args.output}")
    print(f"Datasets processed: {sum(1 for row in rows if (row.row.get('id') or '').strip())}")
    print(f"Analysis date: {args.analysis_date}")


if __name__ == "__main__":
    main()

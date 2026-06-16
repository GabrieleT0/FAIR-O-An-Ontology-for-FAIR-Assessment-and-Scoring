from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote


ANALYSIS_DATE_DEFAULT = "2026-04-01"
SOFTWARE_AGENT_ID = "FUJI"
SOFTWARE_AGENT_LABEL = "F-UJI"
TOOL_ID = "fuji"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

SUBPRINCIPLE_SPECS = {
    "score_earned_A1": {
        "subprinciple": "A1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI A1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle A1.",
        "max_raw": 1,
        "evidence_columns": ["FsF_A1_01M_earned", "FsF_A1_02MD_earned"],
    },
    "score_earned_A1_1": {
        "subprinciple": "A1.1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI A1.1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle A1.1.",
        "max_raw": 1,
        "evidence_columns": ["FsF_A1_1_01MD_earned"],
    },
    "score_earned_A1_2": {
        "subprinciple": "A1.2",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI A1.2 score",
        "description": "F-UJI aggregate score for FAIR sub-principle A1.2.",
        "max_raw": 1,
        "evidence_columns": ["FsF_A1_2_01MD_earned"],
    },
    "score_earned_F1": {
        "subprinciple": "F1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI F1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle F1.",
        "max_raw": 1,
        "evidence_columns": ["FsF_F1_01MD_earned", "FsF_F1_02MD_earned"],
    },
    "score_earned_F2": {
        "subprinciple": "F2",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI F2 score",
        "description": "F-UJI aggregate score for FAIR sub-principle F2.",
        "max_raw": 1,
        "evidence_columns": ["FsF_F2_01M_earned"],
    },
    "score_earned_F3": {
        "subprinciple": "F3",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI F3 score",
        "description": "F-UJI aggregate score for FAIR sub-principle F3.",
        "max_raw": 1,
        "evidence_columns": ["FsF_F3_01M_earned"],
    },
    "score_earned_F4": {
        "subprinciple": "F4",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI F4 score",
        "description": "F-UJI aggregate score for FAIR sub-principle F4.",
        "max_raw": 1,
        "evidence_columns": ["FsF_F4_01M_earned"],
    },
    "score_earned_I1": {
        "subprinciple": "I1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI I1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle I1.",
        "max_raw": 2,
        "evidence_columns": ["FsF_I1_01M_earned"],
    },
    "score_earned_I2": {
        "subprinciple": "I2",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI I2 score",
        "description": "F-UJI aggregate score for FAIR sub-principle I2.",
        "max_raw": 2,
        "evidence_columns": ["FsF_I2_01M_earned"],
    },
    "score_earned_I3": {
        "subprinciple": "I3",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI I3 score",
        "description": "F-UJI aggregate score for FAIR sub-principle I3.",
        "max_raw": 1,
        "evidence_columns": ["FsF_I3_01M_earned"],
    },
    "score_earned_R1": {
        "subprinciple": "R1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI R1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle R1.",
        "max_raw": 1,
        "evidence_columns": ["FsF_R1_01M_earned"],
    },
    "score_earned_R1_1": {
        "subprinciple": "R1.1",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI R1.1 score",
        "description": "F-UJI aggregate score for FAIR sub-principle R1.1.",
        "max_raw": 1,
        "evidence_columns": ["FsF_R1_1_01M_earned"],
    },
    "score_earned_R1_2": {
        "subprinciple": "R1.2",
        "scope": "fairo:MetadataScope",
        "label": "F-UJI R1.2 score",
        "description": "F-UJI aggregate score for FAIR sub-principle R1.2.",
        "max_raw": 1,
        "evidence_columns": ["FsF_R1_2_01M_earned"],
    },
    "score_earned_R1_3": {
        "subprinciple": "R1.3",
        "scope": "fairo:DataAndMetadata",
        "label": "F-UJI R1.3 score",
        "description": "F-UJI aggregate score for FAIR sub-principle R1.3.",
        "max_raw": 1,
        "evidence_columns": ["FsF_R1_3_01M_earned", "FsF_R1_3_02D_earned"],
    },
}

AGGREGATE_SPECS = {
    "score_earned_F": {"predicate": "fairo:fScore", "max_raw": 1},
    "score_earned_A": {"predicate": "fairo:aScore", "max_raw": 3},
    "score_earned_I": {"predicate": "fairo:iScore", "max_raw": 4},
    "score_earned_R": {"predicate": "fairo:rScore", "max_raw": 2},
    "score_earned_FAIR": {"predicate": "fairo:fairScore", "max_raw": 10},
}


@dataclass(frozen=True)
class DatasetRow:
    row: Dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert F-UJI CSV assessments into a FAIR-O Turtle KG.",
    )
    parser.add_argument(
        "--input",
        default=os.path.join(REPO_ROOT, "data", "F-UJI_assessment", "results.csv"),
        help="F-UJI CSV export file.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(REPO_ROOT, "results", "fuji_assessment_fair-o.ttl"),
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
    if max_raw <= 0:
        return 0.0
    return raw_value / max_raw


def test_outcome_from_normalized(value: float) -> str:
    if value >= 1.0:
        return "fairo:Pass"
    if value <= 0.0:
        return "fairo:Fail"
    return "fairo:Indeterminate"


def load_rows(input_path: str) -> List[DatasetRow]:
    with open(input_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [DatasetRow(row=row) for row in reader]
    if not rows:
        raise ValueError(f"No rows found in {input_path}")
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
            ":fujiAggregateNormalization a fairo:ScoringFunction ;",
            '    rdfs:label "F-UJI aggregate normalization" ;',
            '    fairo:formula "normalizedScore = rawScore / subPrincipleMaximum" ;',
            '    dct:description "Normalizes F-UJI exported aggregate scores to the FAIR-O 0..1 range using the maximum score exposed by each aggregate metric." ;',
            '    fairo:minValue "0"^^xsd:decimal ;',
            '    fairo:maxValue "1"^^xsd:decimal .',
            "",
            ":fujiAssessmentAggregation a fairo:AggregationMethod ;",
            '    rdfs:label "F-UJI assessment aggregation normalization" ;',
            '    fairo:formula "normalizedAggregate = rawAggregate / principleMaximum" ;',
            '    dct:description "Normalizes F-UJI principle and overall totals using the maxima present in the exported assessment summary." .',
            "",
            f":{SOFTWARE_AGENT_ID} a prov:SoftwareAgent ;",
            f'    rdfs:label "{SOFTWARE_AGENT_LABEL}" .',
            "",
        ]
    )

    for aggregate_column, spec in SUBPRINCIPLE_SPECS.items():
        algorithm_id = f"algorithm_{uri_segment(aggregate_column)}"
        lines.extend(
            [
                f":{algorithm_id} a fairo:CalculationAlgorithm ;",
                f'    rdfs:label "{turtle_escape(spec["label"])}" ;',
                f"    fairo:implementedBy :{SOFTWARE_AGENT_ID} ;",
                "    fairo:appliesScoringFunction :fujiAggregateNormalization ;",
                f'    fairo:algorithmDescription "{turtle_escape(spec["description"])}" .',
                "",
            ]
        )


def emit_dataset(lines: List[str], dataset_uri: str, dataset_id: str, url: str) -> None:
    lines.append(f":{dataset_uri} a void:Dataset, prov:Entity ;")
    lines.append(f'    dct:title "{turtle_escape(dataset_id)}" ;')
    lines.append(f'    dct:identifier "{turtle_escape(dataset_id)}" ;')
    if url:
        lines.append(f"    dct:source <{url}> ;")
    lines[-1] = lines[-1].rstrip(" ;") + " ."
    lines.append("")


def emit_assessment(
    lines: List[str],
    assessment_uri: str,
    dataset_uri: str,
    analysis_date: str,
    aggregates: Dict[str, Optional[float]],
) -> None:
    dt = f"{analysis_date}T00:00:00Z"
    lines.extend(
        [
            f":{assessment_uri} a fairo:FAIRAssessment, prov:Activity ;",
            f"    prov:used :{dataset_uri} ;",
            f'    prov:startedAtTime "{dt}"^^xsd:dateTime ;',
            f'    prov:endedAtTime "{dt}"^^xsd:dateTime ;',
            "    fairo:usesAggregationMethod :fujiAssessmentAggregation .",
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


def build_evidence(row: Dict[str, str], aggregate_column: str, raw_value: float, max_raw: float) -> str:
    detail_parts: List[str] = []
    for column in SUBPRINCIPLE_SPECS[aggregate_column]["evidence_columns"]:
        detail_value = parse_float(row.get(column))
        if detail_value is not None:
            detail_parts.append(f"{column}={format_decimal(detail_value)}")

    detail_suffix = ""
    if detail_parts:
        detail_suffix = " Contributing F-UJI exported checks: " + ", ".join(detail_parts) + "."

    normalized = normalize_score(raw_value, max_raw)
    return (
        f"Aggregate metric {aggregate_column} returned raw F-UJI score "
        f"{format_decimal(raw_value)} with maximum {format_decimal(max_raw)}; "
        f"normalized FAIR-O value is {format_decimal(normalized)}."
        f"{detail_suffix}"
    )


def emit_result(
    lines: List[str],
    result_uri: str,
    aggregate_column: str,
    raw_value: float,
    row: Dict[str, str],
) -> None:
    spec = SUBPRINCIPLE_SPECS[aggregate_column]
    normalized = normalize_score(raw_value, spec["max_raw"])
    evidence = build_evidence(row, aggregate_column, raw_value, spec["max_raw"])
    algorithm_id = f"algorithm_{uri_segment(aggregate_column)}"

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

        url = (row.get("url") or "").strip()
        dataset_uri = f"dataset_{uri_segment(dataset_id)}"
        assessment_uri = (
            f"assessment_{TOOL_ID}_{uri_segment(dataset_id)}_"
            f"{uri_segment(analysis_date)}"
        )

        emit_dataset(lines, dataset_uri, dataset_id, url)

        aggregates = {column: parse_float(row.get(column)) for column in AGGREGATE_SPECS}
        emit_assessment(lines, assessment_uri, dataset_uri, analysis_date, aggregates)

        lines.append(f":{dataset_uri} fairo:wasAssessedBy :{assessment_uri} .")
        lines.append("")

        for aggregate_column in SUBPRINCIPLE_SPECS:
            raw_value = parse_float(row.get(aggregate_column))
            if raw_value is None:
                continue
            result_uri = (
                f"result_{TOOL_ID}_{uri_segment(dataset_id)}_"
                f"{uri_segment(aggregate_column)}_"
                f"{uri_segment(analysis_date)}"
            )
            emit_result(lines, result_uri, aggregate_column, raw_value, row)
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
    rows = load_rows(args.input)
    lines = build_graph(rows, args.analysis_date)
    write_output(lines, args.output)
    print(f"KG written to: {args.output}")
    print(f"Datasets processed: {sum(1 for row in rows if (row.row.get('id') or '').strip())}")
    print(f"Analysis date: {args.analysis_date}")


if __name__ == "__main__":
    main()

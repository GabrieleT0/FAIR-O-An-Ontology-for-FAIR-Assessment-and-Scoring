from __future__ import annotations

import argparse
from datetime import date
import glob
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote
import pandas as pd


ALLOWED_COLUMNS = [
	"F1-M Unique and persistent ID",
	"F1-D URIs dereferenceability",
	"F2a-M - Metadata availability via standard primary sources",
	"F2b-M Metadata availability for all the attributes covered in the FAIR score computation",
	"F3-M Data referrable via a DOI",
	"F4-M Metadata registered in a searchable engine",
	"F score",
	"A1-D Working access point(s)",
	"A1-M Metadata availability via working primary sources",
	"A1.2 Authentication & HTTPS support",
	"A2-M Registered in search engines",
	"A score",
	"R1.1 Machine- or human-readable license retrievable via any primary source",
	"R1.2 Publisher information such as authors-contributors-publishers and sources",
	"R1.3-D Data organized in a standardized way",
	"R1.3-M Metadata are described with VoID/DCAT predicates",
	"R score",
	"I1-D Standard & open representation format",
	"I1-M Metadata are described with VoID/DCAT predicates",
	"I2 Use of FAIR vocabularies",
	"I3-D Degree of connection",
	"I score",
	"FAIR score",
	"KG id",
	"KG name",
	"Description",
	"SPARQL endpoint URL",
	"Dataset URL",
	"License machine redeable (metadata)",
	"URL for download the dataset",
	"External links",
	" Number of triples (metadata)",
	"Number of entities",
	"Vocabularies"
]

AGGREGATE_CODES = {"FAIR", "F", "A", "I", "R"}
SOFTWARE_AGENT_ID = "KGHeartBeat"
SOFTWARE_AGENT_LABEL = "KGHeartBeat"
TOOL_ID = "kgheartbeat"


@dataclass(frozen=True)
class ResultKey:
	"""Key used to deduplicate equivalent SubPrincipleResult resources."""

	metric: str
	subprinciple: str
	scope: str
	value: str


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Convert FAIR assessment CSV snapshots into a Turtle KG.",
	)
	parser.add_argument(
		"--input-folder",
		default="../data",
		help="Folder that contains snapshot CSV files.",
	)
	parser.add_argument(
		"--mapping-json",
		default="../data/fair_mapping.json",
		help="JSON file that maps metric labels to FAIR principle/subprinciple codes.",
	)
	parser.add_argument(
		"--principles-doc",
		default="../data/fair_principle_doc.json",
		help="JSON file with algorithm and scoring function documentation.",
	)
	parser.add_argument(
		"--output",
		default="../data/fair_assessment_kg.ttl",
		help="Path to the output Turtle file.",
	)
	parser.add_argument(
		"--min-snapshot-date",
		default="2025-04-27",
		help="Only process CSV snapshots with date >= this value (YYYY-MM-DD).",
	)
	parser.add_argument(
		"--organize",
		action="store_true",
		help="Organize output TTL by grouping predicates per subject.",
	)
	parser.add_argument(
		"--skip-missing-usecols",
		action="store_true",
		help="Skip CSV snapshots whose columns do not match the expected usecols list.",
	)
	return parser.parse_args()


def load_metric_map(path: str) -> Dict[str, str]:
	with open(path, "r", encoding="utf-8") as handle:
		return json.load(handle)


def load_principles_doc(path: str) -> Dict:
	"""Load scoring functions, algorithms, and aggregation methods."""
	with open(path, "r", encoding="utf-8") as handle:
		return json.load(handle)


def parse_numeric_or_none(raw: object) -> Optional[str]:
	if raw is None:
		return None

	text = str(raw).strip()
	if not text:
		return None

	lowered = text.lower()
	if lowered in {"-", "none", "nan", "null"}:
		return None

	normalized = text.replace(",", ".")
	try:
		number = float(normalized)
	except ValueError:
		return None

	return format(number, "g")


def turtle_escape(text: str) -> str:
	return (
		text.replace("\\", "\\\\")
		.replace('"', '\\"')
		.replace("\n", "\\n")
		.replace("\r", "\\r")
	)


def uri_segment(value: object) -> str:
	# quote() does not encode '.' but Turtle local names cannot end with '.'.
	return quote(str(value).strip().rstrip("."), safe="")


def parse_vocabularies(raw: object) -> List[str]:
	"""Parse the 'Vocabularies' column into a list of URI strings.

	The column stores values like::

		['http://schema.org/', 'http://purl.org/dc/terms/']
	"""
	if raw is None:
		return []
	text = str(raw).strip()
	if not text or text.lower() in {"[]", "nan", "none", "-"}:
		return []
	return re.findall(r"https?://[^\s\]\[\'\"<>]+", text)


def parse_external_links(raw: object) -> List[Tuple[str, int]]:
	"""Parse the 'External links' column into (target_name, count) pairs.

	The column stores values like::

		['Name:getty-aat, value:2930', 'Name:dbpedia, value:2611']
	"""
	if raw is None:
		return []
	text = str(raw).strip()
	if not text or text.lower() in {"[]", "nan", "none", "-"}:
		return []
	results: List[Tuple[str, int]] = []
	for match in re.finditer(r"Name:\s*([^,\]'\"]+?)\s*,\s*value:\s*(\d+)", text):
		name = match.group(1).strip()
		count = int(match.group(2))
		results.append((name, count))
	return results


def extract_http_url(raw: object) -> Optional[str]:
	if raw is None:
		return None

	text = str(raw).strip()
	if not text or text.lower() in {"nan", "none", "-"}:
		return None

	match = re.search(r"https?://[^\s\]\[\'\"<>]+", text)
	if not match:
		return None

	return match.group(0)


def scope_from_source(source: str) -> str:
	if source == "metadata":
		return "fairo:MetadataScope"
	if source == "data":
		return "fairo:DataScope"
	return "fairo:DataAndMetadata"


def source_from_metric(metric_name: str) -> str:
	if re.search(r"(^|[^A-Za-z])M([^A-Za-z]|$)", metric_name):
		return "metadata"
	if re.search(r"(^|[^A-Za-z])D([^A-Za-z]|$)", metric_name):
		return "data"
	return "(meta)data"


def test_outcome_from_value(value: str) -> str:
	"""Return the fairo:TestOutcome individual URI for a numeric score string."""
	try:
		num = float(value)
	except ValueError:
		return "fairo:Indeterminate"
	if num >= 1.0:
		return "fairo:Pass"
	if num <= 0.0:
		return "fairo:Fail"
	return "fairo:Indeterminate"


def stable_result_id(key: ResultKey) -> str:
	base = "|".join([key.metric, key.subprinciple, key.scope, key.value])
	digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
	return f"result_{TOOL_ID}_{digest}"


def extract_snapshot_date(csv_path: str) -> Optional[date]:
	"""Extract YYYY-MM-DD snapshot date from a CSV filename."""
	basename = os.path.splitext(os.path.basename(csv_path))[0]
	match = re.search(r"\d{4}-\d{2}-\d{2}", basename)
	if not match:
		return None

	try:
		return date.fromisoformat(match.group(0))
	except ValueError:
		return None


def build_long_dataframe(
	input_folder: str,
	metric_map: Dict[str, str],
	min_snapshot_date: date,
	skip_missing_usecols: bool = False,
) -> pd.DataFrame:
	frames: List[pd.DataFrame] = []
	mapped_metrics = set(metric_map.keys())

	for csv_path in sorted(glob.glob(os.path.join(input_folder, "*.csv"))):
		if "melted" in csv_path:
			continue

		snapshot_date = extract_snapshot_date(csv_path)
		if snapshot_date is None or snapshot_date < min_snapshot_date:
			continue
		snapshot_date_text = snapshot_date.isoformat()

		try:
			df = pd.read_csv(csv_path, usecols=ALLOWED_COLUMNS)
		except ValueError as exc:
			if skip_missing_usecols and "Usecols do not match columns" in str(exc):
				print(f"Skipping {csv_path}: {exc}")
				continue
			raise
		df.columns = df.columns.str.strip()

		df_long = df.melt(
			id_vars=[
				"KG id",
				"KG name",
				"Description",
				"SPARQL endpoint URL",
				"Dataset URL",
				"License machine redeable (metadata)",
				"URL for download the dataset",
				"External links",
				"Number of triples (metadata)",
				"Number of entities",
				"Vocabularies",
			],
			var_name="metric",
			value_name="metric_value_rml",
		)

		df_long = df_long[df_long["metric"].isin(mapped_metrics)].copy()
		df_long["FAIR subprinciple"] = df_long["metric"].map(metric_map)
		df_long["source"] = df_long["metric"].apply(source_from_metric)
		df_long["Analysis date"] = snapshot_date_text

		frames.append(df_long)

	if not frames:
		raise ValueError(
			f"No input CSV snapshot found under {input_folder} with date >= {min_snapshot_date.isoformat()}"
		)

	return pd.concat(frames, ignore_index=True)


def add_prefixes(lines: List[str]) -> None:
	lines.extend(
		[
			"@prefix : <https://kgheartbeat.di.unisa.it/fairness-data/> .",
			"@prefix fairo: <https://w3id.org/fair-o#> .",
			"@prefix fairVocab: <https://w3id.org/fair/principles/terms/> .",
			"@prefix dct: <http://purl.org/dc/terms/> .",
			"@prefix dcat: <http://www.w3.org/ns/dcat#> .",
			"@prefix prov: <http://www.w3.org/ns/prov#> .",
			"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
			"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
			"@prefix void: <http://rdfs.org/ns/void#> .",
			"",
		]
	)


def add_scoring_functions(lines: List[str], scoring_functions: List[Dict]) -> None:
	"""Emit ScoringFunction resources from principles doc."""
	for sf in scoring_functions:
		sf_id = sf.get("id", "unknownSF")
		label = turtle_escape(sf.get("label", sf_id))
		formula = turtle_escape(sf.get("formula", ""))
		description = turtle_escape(sf.get("description", ""))
		min_value = sf.get("minValue")
		max_value = sf.get("maxValue")

		lines.extend(
			[
				f":{sf_id} a fairo:ScoringFunction ;",
				f'    rdfs:label "{label}" ;',
				f'    fairo:formula "{formula}" ;',
			]
		)

		if description:
			lines.append(f'    dct:description "{description}" ;')

		if min_value is not None:
			lines.append(f'    fairo:minValue "{min_value}"^^xsd:decimal ;')

		if max_value is not None:
			lines.append(f'    fairo:maxValue "{max_value}"^^xsd:decimal ;')

		lines[-1] = lines[-1].rstrip(" ;") + " ."
		lines.append("")


def add_software_agent(lines: List[str]) -> None:
	"""Emit the software agent that implements the FAIR assessment algorithms."""
	lines.extend(
		[
			f":{SOFTWARE_AGENT_ID} a prov:SoftwareAgent ;",
			f'    rdfs:label "{SOFTWARE_AGENT_LABEL}" .',
			"",
		]
	)


def add_algorithms(lines: List[str], algorithms: List[Dict]) -> None:
	"""Emit CalculationAlgorithm resources from principles doc."""
	for alg in algorithms:
		alg_id = alg.get("id", "unknownAlg")
		subprinciple_info = alg.get("implementsSubPrinciple", {})
		notation = subprinciple_info.get("notation", "")
		description = turtle_escape(alg.get("description", ""))
		scoring_func_ref = alg.get("scoringFunction")

		lines.extend(
			[
				f":{alg_id} a fairo:CalculationAlgorithm ;",
				f'    rdfs:label "{notation}" ;',
				f"    fairo:implementedBy :{SOFTWARE_AGENT_ID} ;",
			]
		)

		if description:
			lines.append(f'    fairo:algorithmDescription "{description}" ;')

		if scoring_func_ref:
			lines.append(f"    fairo:appliesScoringFunction :{scoring_func_ref} ;")

		lines[-1] = lines[-1].rstrip(" ;") + " ."
		lines.append("")


def add_aggregation_methods(lines: List[str], aggregation_methods: List[Dict]) -> None:
	"""Emit AggregationMethod resources from principles doc."""
	for agg in aggregation_methods:
		agg_id = agg.get("id", "unknownAgg")
		label = turtle_escape(agg.get("label", agg_id))
		formula = turtle_escape(agg.get("formula", ""))
		description = turtle_escape(agg.get("description", ""))

		lines.extend(
			[
				f":{agg_id} a fairo:AggregationMethod ;",
				f'    rdfs:label "{label}" ;',
				f'    fairo:formula "{formula}" ;',
			]
		)

		if description:
			lines.append(f'    dct:description "{description}" ;')

		lines[-1] = lines[-1].rstrip(" ;") + " ."
		lines.append("")


def append_turtle(lines: List[str], output_path: str) -> None:
	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write("\n".join(lines))
		handle.write("\n")


def find_algorithm_for_metric(metric: str, algorithms: List[Dict]) -> Optional[str]:
	"""Find algorithm ID that implements this metric's subprinciple."""
	for alg in algorithms:
		subprinciple_info = alg.get("implementsSubPrinciple", {})
		notation = subprinciple_info.get("notation", "")
		if notation in metric:
			return alg.get("id")

	# Some KGHeartBeat metric names use a broader principle notation than the
	# documented algorithm (for example, A1-D versus A1.1-D). In those cases,
	# match the descriptive part of the metric instead.
	for alg in algorithms:
		subprinciple_info = alg.get("implementsSubPrinciple", {})
		monitored_aspect = subprinciple_info.get("monitoredAspect", "")
		if monitored_aspect and monitored_aspect.casefold() in metric.casefold():
			return alg.get("id")
	return None


def build_kg(df_long: pd.DataFrame, output_path: str, principles_doc: Dict) -> Tuple[int, int, int]:
	lines: List[str] = []
	add_prefixes(lines)

	scoring_functions = principles_doc.get("scoringFunctions", [])
	aggregation_methods = principles_doc.get("aggregationMethods", [])
	algorithms = principles_doc.get("algorithms", [])

	add_scoring_functions(lines, scoring_functions)
	add_software_agent(lines)
	add_algorithms(lines, algorithms)
	add_aggregation_methods(lines, aggregation_methods)

	created_results: Set[str] = set()
	dedup_index: Dict[ResultKey, str] = {}
	links: Set[Tuple[str, str]] = set()
	dataset_assessment_links: Set[Tuple[str, str]] = set()
	declared_external_datasets: Set[str] = set()

	total_assessments = 0

	for kg_id, dataset_df in df_long.groupby("KG id", sort=True):
		dataset_uri = f"dataset_{uri_segment(kg_id)}"
		sample = dataset_df.iloc[0]

		identifier = extract_http_url(sample.get("KG id", ""))
		title = turtle_escape(str(sample.get("KG name", "")))
		description = turtle_escape(str(sample.get("Description", "")))
		sparql_endpoint = extract_http_url(sample.get("SPARQL endpoint URL", ""))
		dataset_url = extract_http_url(sample.get("Dataset URL", ""))
		download_url = extract_http_url(sample.get("URL for download the dataset", ""))
		license_url = extract_http_url(sample.get("License machine redeable (metadata)", ""))
		triples = parse_numeric_or_none(sample.get("Number of triples (metadata)", None))
		entities = parse_numeric_or_none(sample.get("Number of entities", None))
		

		lines.append(f":{dataset_uri} a void:Dataset, prov:Entity ;")
		lines.append(f'    dct:title "{title}" ;')

		if description and description.lower() not in {"nan", "none"}:
			lines.append(f'    dct:description "{description}" ;')

		if dataset_url:
			lines.append(f"    dcat:landingPage <{dataset_url}> ;")

		if sparql_endpoint:
			lines.append(f"    void:sparqlEndpoint <{sparql_endpoint}> ;")

		if download_url:
			lines.append(f"    void:dataDump <{download_url}> ;")

		if license_url:
			lines.append(f"    dct:license <{license_url}> ;")
		
		if identifier:
			lines.append(f"    dct:identifier <{identifier}> ;")

		if triples:
			lines.append(f"    void:triples {triples} ;")

		if entities:
			lines.append(f"    void:entities {entities} ;")

		lines[-1] = lines[-1].rstrip(" ;") + " ."
		lines.append("")

		# Emit void:vocabulary triples for each vocabulary URI
		for vocab_uri in parse_vocabularies(sample.get("Vocabularies")):
			lines.append(f":{dataset_uri} void:vocabulary <{vocab_uri}> .")
		lines.append("")

		# Emit void:Linkset resources for each external link target
		ext_links = parse_external_links(sample.get("External links"))
		for ext_name, ext_count in ext_links:
			ext_safe = uri_segment(ext_name)
			ext_dataset_uri = f"external_{ext_safe}"
			linkset_uri = f"linkset_{dataset_uri}_to_{ext_safe}"

			# void:subset connects the source dataset to its Linkset
			lines.append(f":{dataset_uri} void:subset :{linkset_uri} .")
			lines.append("")

			lines.append(f":{linkset_uri} a void:Linkset ;")
			lines.append(f"    void:subjectsTarget :{dataset_uri} ;")
			lines.append(f"    void:objectsTarget :{ext_dataset_uri} ;")
			lines.append(f"    void:triples {ext_count} .")
			lines.append("")

			# Declare the external dataset once
			if ext_dataset_uri not in declared_external_datasets:
				declared_external_datasets.add(ext_dataset_uri)
				lines.append(f":{ext_dataset_uri} a void:Dataset ;")
				lines.append(f'    dct:title "{turtle_escape(ext_name)}" .')
				lines.append("")

		for date_text, assessment_df in dataset_df.groupby("Analysis date", sort=True):
			assessment_uri = (
				f"assessment_{TOOL_ID}_{uri_segment(kg_id)}_"
				f"{uri_segment(date_text)}"
			)
			dt = f"{date_text}T00:00:00Z"

			lines.append(f":{assessment_uri} a fairo:FAIRAssessment, prov:Activity ;")
			lines.append(f"    prov:used :{dataset_uri} ;")
			lines.append(f'    prov:startedAtTime "{dt}"^^xsd:dateTime ;')
			lines.append(f'    prov:endedAtTime "{dt}"^^xsd:dateTime .')
			lines.append("")

			dataset_assessment_links.add((dataset_uri, assessment_uri))
			total_assessments += 1

			aggregate_values: Dict[str, str] = {}

			for row in assessment_df.to_dict("records"):
				metric = str(row.get("metric", "")).strip()
				subprinciple = str(row.get("FAIR subprinciple", "")).strip()

				if not metric or not subprinciple:
					continue

				value = parse_numeric_or_none(row.get("metric_value_rml"))
				if value is None:
					continue

				if subprinciple in AGGREGATE_CODES:
					aggregate_values[subprinciple] = value
					continue

				source = str(row.get("source", "(meta)data"))
				scope = scope_from_source(source)

				dedup_key = ResultKey(
					metric=metric,
					subprinciple=subprinciple,
					scope=scope,
					value=value,
				)

				result_uri = dedup_index.get(dedup_key)
				if result_uri is None:
					result_uri = stable_result_id(dedup_key)
					dedup_index[dedup_key] = result_uri

					evidence = turtle_escape(
						f"Metric '{metric}' scored {value} for {subprinciple} ({source})."
					)
					algorithm_id = find_algorithm_for_metric(metric, algorithms)
					outcome = test_outcome_from_value(value)
					lines.append(f":{result_uri} a fairo:SubPrincipleResult ;")
					lines.append(f"    fairo:forSubPrinciple fairVocab:{subprinciple} ;")
					lines.append(f"    fairo:assessmentScope {scope} ;")
					lines.append(f'    fairo:value "{value}"^^xsd:decimal ;')
					lines.append(f"    fairo:testResult {outcome} ;")
					lines.append(f'    fairo:evidence "{evidence}" ;')

					if algorithm_id:
						lines.append(f"    fairo:computedUsing :{algorithm_id} .")
					else:
						lines[-1] = lines[-1].rstrip(" ;") + " ."

					lines.append("")
					created_results.add(result_uri)

				links.add((assessment_uri, result_uri))

			# Add aggregate scores
			score_predicates = {
				"FAIR": "fairo:fairScore",
				"F": "fairo:fScore",
				"A": "fairo:aScore",
				"I": "fairo:iScore",
				"R": "fairo:rScore",
			}

			score_entries = []
			for code, predicate in score_predicates.items():
				value = aggregate_values.get(code)
				if value is not None:
					score_entries.append((predicate, value))

			if score_entries:
				lines.append(f":{assessment_uri}")
				for idx, (predicate, value) in enumerate(score_entries):
					suffix = " ;" if idx < len(score_entries) - 1 else " ."
					lines.append(f'    {predicate} "{value}"^^xsd:decimal{suffix}')
				lines.append("")

			# Add aggregation method
			if aggregation_methods:
				agg_method_id = aggregation_methods[0].get("id", "linearCombination")
				lines.append(f":{assessment_uri} fairo:usesAggregationMethod :{agg_method_id} .")
				lines.append("")

	# Link datasets to assessments
	for dataset_uri, assessment_uri in sorted(dataset_assessment_links):
		lines.append(f":{dataset_uri} fairo:wasAssessedBy :{assessment_uri} .")
		lines.append("")

	# Link assessments to deduplicated results
	for assessment_uri, result_uri in sorted(links):
		lines.append(f":{assessment_uri} fairo:hasSubPrincipleResult :{result_uri} .")
		lines.append("")

	append_turtle(lines, output_path)
	return total_assessments, len(created_results), len(links)


def main() -> None:
	args = parse_args()
	try:
		min_snapshot_date = date.fromisoformat(args.min_snapshot_date)
	except ValueError as exc:
		raise ValueError(
			f"Invalid --min-snapshot-date '{args.min_snapshot_date}'. Expected YYYY-MM-DD."
		) from exc

	metric_map = load_metric_map(args.mapping_json)
	principles_doc = load_principles_doc(args.principles_doc)
	df_long = build_long_dataframe(
		args.input_folder,
		metric_map,
		min_snapshot_date,
		skip_missing_usecols=args.skip_missing_usecols,
	)

	assessments, unique_results, links = build_kg(df_long, args.output, principles_doc)
	print(f"KG written to: {args.output}")
	print(f"Assessments: {assessments}")
	print(f"Unique SubPrincipleResult resources: {unique_results}")
	print(f"Assessment-result links: {links}")
	print(f"Scoring Functions: {len(principles_doc.get('scoringFunctions', []))}")
	print(f"Algorithms: {len(principles_doc.get('algorithms', []))}")
	print(f"Aggregation Methods: {len(principles_doc.get('aggregationMethods', []))}")

	if args.organize:
		print("\nOrganizing Turtle output...")
		import subprocess
		subprocess.run([
			"python3", "organize_ttl.py",
			args.output, args.output
		], cwd=os.path.dirname(os.path.abspath(__file__)))
		print("Turtle output organized by subject!")


if __name__ == "__main__":
	main()

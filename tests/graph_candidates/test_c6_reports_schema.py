import json

from scripts.graph_candidates.c6_common import command_metadata, write_json


def test_json_report_is_valid(tmp_path):
    report_path = tmp_path / "report.json"
    write_json(report_path, {"schema_version": "test", "status": "passed"})
    with report_path.open(encoding="utf-8") as f:
        parsed = json.load(f)
    assert parsed["schema_version"] == "test"
    assert parsed["status"] == "passed"


def test_command_line_metadata_is_reportable(tmp_path):
    metadata = command_metadata(tmp_path / "run_001", "test_stage")
    assert "command_line" in metadata
    assert "working_directory" in metadata
    assert metadata["created_by"]
    assert metadata["run_id"] == "run_001"

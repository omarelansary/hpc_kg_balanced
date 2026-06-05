import json

from scripts.graph_candidates.c6_common import write_json


def test_json_report_is_valid(tmp_path):
    report_path = tmp_path / "report.json"
    write_json(report_path, {"schema_version": "test", "status": "passed"})
    with report_path.open(encoding="utf-8") as f:
        parsed = json.load(f)
    assert parsed["schema_version"] == "test"
    assert parsed["status"] == "passed"


"""Validated fully synthetic skills ledger; only aggregate data leaves HTTP API."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS = {"transport", "assembly", "inspection"}
FIELDS = {"id", "skills", "inspection_training_eligible", "training_hours"}


def validate(records):
    valid, issues, seen = [], [], set()
    if not isinstance(records, list):
        return [], [{"row": 0, "code": "schema", "reason": "records must be a list"}]
    for index, row in enumerate(records, 1):
        code = None
        if not isinstance(row, dict) or set(row) != FIELDS:
            code = "schema"
        elif row["id"] not in ("W01", "W02", "W03", "W04"):
            code = "identifier"
        elif row["id"] in seen:
            code = "duplicate"
        elif not isinstance(row["skills"], dict) or set(row["skills"]) != SKILLS:
            code = "skill_schema"
        elif any(type(x) is not bool for x in row["skills"].values()) or type(row["inspection_training_eligible"]) is not bool:
            code = "qualification_type"
        elif type(row["training_hours"]) is not int or not 0 <= row["training_hours"] <= 40:
            code = "training_hours"
        elif sum(row["skills"].values()) > 1:
            code = "pooled_assignment"
        elif row["inspection_training_eligible"] and (row["skills"]["inspection"] or any(row["skills"].values()) or row["training_hours"] != 8):
            code = "eligibility"
        elif not row["inspection_training_eligible"] and row["training_hours"] != 0:
            code = "eligibility"
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            seen.add(row["id"])
        if code:
            issues.append({"row": index, "code": code, "reason": "합성 스킬 원장 검수 규칙과 맞지 않는 행입니다."})
        else:
            valid.append(row)
    return valid, issues


def load(path=None):
    source = Path(path) if path else ROOT / "data" / "workforce.json"
    raw = source.read_bytes()
    snapshot = json.loads(raw.decode("utf-8"))
    if not isinstance(snapshot, dict) or set(snapshot) != {"synthetic", "snapshot", "records", "assumptions"} or snapshot.get("synthetic") is not True or not isinstance(snapshot["snapshot"], str) or not isinstance(snapshot["assumptions"], str):
        raise ValueError("workforce must be an explicitly synthetic snapshot")
    records, issues = validate(snapshot.get("records"))
    if issues or len(records) != 4 or sum(row["skills"]["transport"] for row in records) != 1 or sum(row["skills"]["assembly"] for row in records) != 1:
        raise ValueError("invalid four-worker synthetic snapshot; simulation was not run")
    before = sum(row["skills"]["inspection"] for row in records)
    participants = [row for row in records if row["inspection_training_eligible"]]
    if before != 1 or len(participants) != 1:
        raise ValueError("snapshot must have one qualified worker and one explicitly eligible idle synthetic worker")
    aggregate = {"synthetic": True, "total_workers": len(records), "qualified_before": before,
                 "qualified_after": before + len(participants), "skill_gap_to_candidate": len(participants),
                 "training_participants": len(participants), "total_training_hours": sum(row["training_hours"] for row in participants),
                 "input_quality": {"passed": len(records), "error_count": len(issues), "issues": issues},
                 "source_json_sha256": hashlib.sha256(raw).hexdigest(),
                 "training_assumptions": "완전 합성 작업자 원장의 교육 적격자1명에게 사전교육8시간 후 검사 자격 취득을 가정. 전체 인원 유지, 실제 교육 효과·개인 평가 판단 아님."}
    return {"snapshot": snapshot, "aggregate": aggregate}

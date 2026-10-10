"""Actual localhost n8n I/O checks; reads only this workflow's execution tables.

The approve/reject POSTs are explicit synthetic test decisions, not real HR approval.
No account, credential, configuration, encryption-key or token tables are read.
"""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit
from datetime import datetime, timezone
import argparse, csv, io, json, platform, sqlite3, time, uuid

APP = 'http://127.0.0.1:8798'
N8N = 'http://127.0.0.1:5697'
WORKFLOW = 'WonikLearningV3Local'
ROOT = Path(__file__).resolve().parents[1]
WAIT = '담당자 결정 대기'
REVIEW = '교육 요청 검토'
DECISION = '명시적 결정 기록'
PLANS = '계획 원장 출력'
CSV = 'CSV 출력'


def http(url, body=None, as_text=False):
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = Request(url, data=payload, headers={'Content-Type': 'application/json'} if payload else {})
    with urlopen(req, timeout=350) as response:
        raw = response.read().decode('utf-8')
        return raw if as_text else json.loads(raw)


def submit(body):
    # n8n healthz can be ready before the published webhook is registered.
    # A 404 has not accepted an execution; retry the same synthetic request only then.
    end = time.monotonic() + 180
    while True:
        try:
            return http(N8N + '/webhook/wonik-learning', body)
        except HTTPError as error:
            if error.code != 404 or time.monotonic() >= end:
                raise
            time.sleep(1)


def unflatten(raw):
    """Decode n8n's flatted.stringify output, preserving table string literals."""
    values = json.loads(raw)
    if not isinstance(values, list):
        return values
    cache = {}

    def entry(index):
        if index in cache:
            return cache[index]
        value = values[index]
        if isinstance(value, dict):
            target = cache[index] = {}
            target.update({key: reference(item) for key, item in value.items()})
            return target
        if isinstance(value, list):
            target = cache[index] = []
            target.extend(reference(item) for item in value)
            return target
        return value

    def reference(value):
        if isinstance(value, str) and value.isdecimal():
            return entry(int(value))
        return value

    return entry(0)


def db_rows(db_path, after):
    with sqlite3.connect('file:' + db_path.resolve().as_posix() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            'select id,status,finished,startedAt,stoppedAt,waitTill from execution_entity '
            'where workflowId=? and id>? order by id', (WORKFLOW, after))]


def execution_data(db_path, execution_id):
    with sqlite3.connect('file:' + db_path.resolve().as_posix() + '?mode=ro', uri=True) as db:
        row = db.execute('select d.data from execution_data d join execution_entity e '
                         'on e.id=d.executionId where e.id=? and e.workflowId=?',
                         (execution_id, WORKFLOW)).fetchone()
        return unflatten(row[0]) if row else None


def until(db_path, after, predicate, timeout=420):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        rows = db_rows(db_path, after)
        if rows:
            assert len(rows) == 1, 'Unexpected concurrent execution in this isolated workflow'
            row = rows[0]
            if row['status'] == 'error':
                raise AssertionError('n8n execution error, ID ' + str(row['id']))
            data = execution_data(db_path, row['id'])
            if data and predicate(row, data):
                return row, data
        time.sleep(0.7)
    raise TimeoutError('n8n did not reach expected execution state')


def runs(data):
    return data['resultData']['runData']


def output(data, node):
    return runs(data)[node][-1]['data']['main'][0][0]['json']


def find_resume(value):
    if isinstance(value, dict):
        if isinstance(value.get('resumeUrl'), str):
            return value['resumeUrl']
        for item in value.values():
            result = find_resume(item)
            if result:
                return result
    elif isinstance(value, list):
        for item in value:
            result = find_resume(item)
            if result:
                return result


def archive(value):
    if isinstance(value, dict):
        return {key: '[runtime resume URL omitted]' if key == 'resumeUrl' else archive(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [archive(item) for item in value]
    return value


def main(db_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline = db_rows(db_path, 0)
    after = max((int(row['id']) for row in baseline), default=0)
    initial = http(APP + '/api/learning/plans')['plans']
    assert initial == [], 'Use a fresh app ledger for this isolated integration check'
    inputs = [
        ('approve_llm', 'llm', 'current', '새 직원이 물건을 넣을 때 바코드를 잘못 읽어요. 무엇부터 익히면 좋을까요?', 'approve'),
        ('reject_rules', 'rules', 'current', '자재 투입 교육을 계획해 주세요.', 'reject'),
        ('blocked_conflict', 'llm', 'conflict', '자재 투입 교육을 계획해 주세요.', None),
    ]
    cases = []
    for name, mode, scope, query, decision in inputs:
        request_id = str(uuid.uuid4())
        body = dict(requestId=request_id, selectedWorkerId='SYN-101', query=query, mode=mode, policyScope=scope)
        before = http(APP + '/api/learning/plans')['plans']
        submit(body)
        waiting = None
        if decision:
            waiting, wait_data = until(db_path, after, lambda row, data: row['status'] == 'waiting' and WAIT in runs(data))
            review = output(wait_data, REVIEW)
            assert review['state'] == 'awaiting_approval' and review['proposal']['id'] == 'C-LOAD'
            assert http(APP + '/api/learning/plans')['plans'] == before, 'Wait must not add a plan'
            resume_url = find_resume(wait_data)
            assert resume_url, 'n8n serialized execution did not contain the generated resume URL'
            target = urlsplit(resume_url)
            assert target.scheme == 'http' and target.hostname == '127.0.0.1' and target.port == 5697
            (out_dir / (name + '-wait.json')).write_text(json.dumps(archive(wait_data), ensure_ascii=False, indent=2), encoding='utf-8')
            http(resume_url, {'action': decision})
        row, data = until(db_path, after, lambda row, data: row['status'] == 'success')
        after = int(row['id'])
        review = output(data, REVIEW)
        plans = http(APP + '/api/learning/plans')['plans']
        own_plans = [plan for plan in plans if plan['requestId'] == request_id]
        checks = {'app_validation_authority': True, 'completed_execution': row['status'] == 'success',
                  'no_qualification_granted': all(plan['qualificationGranted'] is False for plan in plans)}
        transport_metadata = {}
        if decision:
            final = output(data, DECISION)
            expected = 'approved' if decision == 'approve' else 'rejected'
            assert final['review']['state'] == expected
            assert len(own_plans) == (1 if decision == 'approve' else 0)
            assert output(data, PLANS)['plans'] == plans
            text = output(data, CSV)['csv']
            api_text = http(APP + '/api/learning/export.csv', as_text=True)
            # Some HTTP clients remove the UTF-8 BOM; CSV content must still be identical.
            assert text.lstrip('\ufeff') == api_text.lstrip('\ufeff')
            parsed = list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
            assert len(parsed) == len(plans) and len([item for item in parsed if item['requestId'] == request_id]) == len(own_plans)
            csv_path = out_dir / (name + '.csv')
            csv_path.write_text(text, encoding='utf-8', newline='')
            checks.update(wait_observed=True, before_decision_no_new_plan=True, explicit_decision_post=True,
                          plans_json_matches_persisted_ledger=True, csv_matches_api=True, own_plan_rows=len(own_plans))
            transport_metadata = {'csv_bom_preserved': text.startswith('\ufeff'),
                                  'csv_comparison': 'identical content ignoring optional transport BOM'}
        else:
            assert review['state'] == 'blocked' and review['code'] == 'POLICY_CONFLICT'
            assert not any(node in runs(data) for node in (WAIT, DECISION, PLANS, CSV))
            assert plans == before and review['llmStatus'] == 'not_called'
            checks.update(no_wait=True, no_decision=True, no_csv=True, no_plan=True, model_not_called=True)
        trace_path = out_dir / (name + '-execution.json')
        trace_path.write_text(json.dumps(archive(data), ensure_ascii=False, indent=2), encoding='utf-8')
        cases.append({'name': name, 'requestId': request_id, 'executionId': str(row['id']),
                      'status': row['status'], 'decision': decision, 'reviewState': review['state'],
                      'finalState': output(data, DECISION)['review']['state'] if decision else review['state'],
                      'mode': mode, 'query': query, 'courseId': review.get('proposal', {}).get('id') if review.get('proposal') else None,
                      'planCountBefore': len(before), 'planCountAfter': len(plans), 'ownPlanCount': len(own_plans),
                      'review': review, 'plan': own_plans[0] if own_plans else None,
                      'transportMetadata': transport_metadata,
                      'nodeNames': list(runs(data)), 'checks': checks, 'executionMetadata': row,
                      'waitMetadata': waiting, 'tracePath': trace_path.name,
                      'csvPath': csv_path.name if decision else None})
        print(json.dumps({'case': name, 'executionId': str(row['id']), 'status': row['status'], 'ownPlans': len(own_plans)}, ensure_ascii=False), flush=True)
    result = {'passed': True, 'n8nVersion': '2.42.3', 'workflowId': WORKFLOW, 'synthetic': True,
              'date': datetime.now(timezone.utc).isoformat(), 'executionHost': platform.node(),
              'appEndpoint': APP, 'n8nEndpoint': N8N, 'cases': cases,
              'approvalOperator': 'explicit synthetic test POST; not a real HR decision',
              'dataScope': 'only this workflow execution_entity metadata and execution_data',
              'boundary': 'education plan confirmation only; no training completion, qualification, production effect or company deployment'}
    (out_dir / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: 3 actual n8n executions, 1 persisted synthetic education plan; JSON and CSV matched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=ROOT.parents[1] / 'work/wonik-v3-runtime/n8n-state/.n8n/database.sqlite')
    parser.add_argument('--out', type=Path, default=ROOT / 'evidence' / ('n8n-reproduction-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    args = parser.parse_args()
    main(args.db, args.out)

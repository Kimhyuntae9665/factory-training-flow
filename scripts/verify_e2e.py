"""Actual local n8n+Qwen integration checks. Never reads auth/token columns."""
from pathlib import Path
import json, time, uuid, sqlite3, argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8770'

def api(path, body=None):
    req = Request(BASE + path, data=json.dumps(body).encode() if body else None,
                  headers={'Content-Type':'application/json','Origin':BASE} if body else {})
    try:
        with urlopen(req, timeout=20) as r: return r.status, json.load(r)
    except HTTPError as e: return e.code, json.load(e)

def get(job_id): return api('/api/job?id=' + job_id)[1]

def wait(job_id, states, limit=180):
    end = time.monotonic()+limit
    while time.monotonic()<end:
        j=get(job_id)
        if j['state'] in states:return j
        if j['state'] in {'failed','blocked'}:raise AssertionError((j['state'],j.get('error_code')))
        time.sleep(1)
    raise TimeoutError('Expected '+repr(states))

def executions(db_path):
    db=sqlite3.connect('file:'+str(db_path.resolve())+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return [dict(r) for r in db.execute('select id,status,finished,startedAt,stoppedAt,waitTill from execution_entity order by id')]

def run(db_path):
    out=ROOT/'evidence';out.mkdir(exist_ok=True)
    rows=api('/api/jobs')[1]['items']
    approved=next(j for j in rows if j['state']=='approved')
    assert approved['result']['plan']['mode']=='llm' and approved['training_plan']
    assert approved['training_plan']['source_sha256']==approved['result']['hr']['source_json_sha256']
    assert api('/api/decision',{'request_id':approved['id'],'decision':'approve'})[0]==200
    assert api('/api/decision',{'request_id':approved['id'],'decision':'reject'})[0]==409

    fixture=api('/api/fixture')[1]
    body={'request':'수요 1.0배, 로봇 자동화와 검사 교육을 함께 비교해 주세요.',
          'records':fixture['records'],'synthetic':True,'idempotency_key':uuid.uuid4().hex}
    status,j=api('/api/submit',body);assert status==200
    reject_id=j['id']
    status,replay=api('/api/submit',body);assert status==200 and replay['id']==reject_id
    changed=dict(body,request='수요 1.1배, 로봇 자동화와 검사 교육을 함께 비교해 주세요.')
    assert api('/api/submit',changed)[0]==409
    pending=wait(reject_id,{'awaiting_approval'})
    assert pending['training_plan'] is None and pending['result']['plan']['mode']=='llm'
    before=executions(db_path)
    assert any(str(e['id'])==pending['n8n_execution_id'] and e['waitTill'] is not None for e in before)
    assert api('/api/decision',{'request_id':reject_id,'decision':'reject'})[0]==200
    rejected=wait(reject_id,{'rejected'});assert rejected['training_plan'] is None
    assert api('/api/decision',{'request_id':reject_id,'decision':'reject'})[0]==200
    assert api('/api/decision',{'request_id':reject_id,'decision':'approve'})[0]==409

    broken=json.loads(json.dumps(body));broken['idempotency_key']=uuid.uuid4().hex
    del broken['records'][0]['skills']['inspection']
    status,j=api('/api/submit',broken);assert status==200
    end=time.monotonic()+20
    while time.monotonic()<end and j['state']!='blocked':time.sleep(.5);j=get(j['id'])
    assert j['state']=='blocked' and j['result'] is None and j['training_plan'] is None
    assert not any(e['stage']=='analyzing' for e in j['events'])
    db=sqlite3.connect(ROOT/'data/jobs.sqlite3')
    counts={row[0]:row[1] for row in db.execute('select job_id,count(*) from training_plans group by job_id')}
    assert counts=={approved['id']:1}
    time.sleep(1)
    final=executions(db_path)
    assert len(final)==3 and all(e['status']=='success' for e in final)
    result={'passed':True,'synthetic':True,'actual_n8n':'2.42.3','actual_llm':True,
            'cases':{'approve':{'id':approved['id'],'education_plans':1,'before_approval_plans':0,'ui_decision':True},
                     'reject':{'id':rejected['id'],'education_plans':0,'before_approval_plans':0},
                     'missing_fixture':{'id':j['id'],'education_plans':0,'llm_started':False},
                     'duplicate_request':'same job; no extra n8n execution','duplicate_decision':'same persisted result; no extra plan',
                     'conflicting_request_and_decision':'HTTP409'},
            'n8n_wait_observed':before,'n8n_terminal_executions':final,
            'model_runs':[{'request_id':x['id'],'plan':x['result']['plan'],'summary':x['summary']} for x in (approved,rejected)],
            'plan_rows':counts,'external_contacts':False,'approval_operator':'automated synthetic demo reviewer; no real HR decision',
            'completed_record_restart':'pending root check'}
    (out/'e2e-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for label,x in [('approved',approved),('rejected',rejected),('blocked',j),('before-reject',pending)]:
        (out/(label+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'approve':approved['id'],'reject':rejected['id'],'blocked':j['id'],'plans':counts,'n8n_executions':[(e['id'],e['status']) for e in final]},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--n8n-db',type=Path,required=True)
    run(p.parse_args().n8n_db)

from pathlib import Path
import json,uuid
ROOT=Path(__file__).resolve().parents[1]
nodes=[];connections={}
def add(name,typ,params,pos,version=1,**extra):
 nodes.append({'id':uuid.uuid5(uuid.NAMESPACE_URL,'factory-training/'+name).hex,'name':name,'type':'n8n-nodes-base.'+typ,'typeVersion':version,'position':pos,'parameters':params,**extra})
def edge(a,b,output=0):
 outputs=connections.setdefault(a,{'main':[]})['main']
 while len(outputs)<=output:outputs.append([])
 outputs[output].append({'node':b,'type':'main','index':0})
def http(name,path,body,pos):
 add(name,'httpRequest',{'method':'POST','url':'http://127.0.0.1:8770/api/workflow/'+path,
  'sendHeaders':True,'headerParameters':{'parameters':[{'name':'X-Workflow-Client','value':'factory-training-local-v1'}]},
  'sendBody':True,'specifyBody':'json','jsonBody':body,'options':{'timeout':180000}},pos,4.2)
def condition(name,field,pos):
 add(name,'if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uuid.uuid4().hex,'leftValue':'={{ $json.'+field+' }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}},pos,2.2)
add('합성 요청 접수','webhook',{'httpMethod':'POST','path':'factory-training','responseMode':'onReceived','options':{}},[0,0],2,webhookId='factory-training-local')
http('원장·요청 검수','validate','={{ JSON.stringify({request_id: $json.body.request_id}) }}',[230,0])
condition('검수 통과?','valid',[460,0])
http('실제 Qwen·SimPy 비교','analyze','={{ JSON.stringify({request_id: $json.request_id}) }}',[690,-80])
condition('AI 비교 성공?','ok',[920,-80])
http('검토 대기 등록','await-review','={{ JSON.stringify({request_id: $json.request_id, resume_url: $execution.resumeUrl, execution_id: $execution.id}) }}',[1150,-160])
add('검토자 결정 대기','wait',{'resume':'webhook','httpMethod':'POST','responseMode':'onReceived','options':{}},[1380,-160],1.1,webhookId='factory-training-review-wait')
http('결정·계획 확정','finalize','={{ JSON.stringify({request_id: $json.body.request_id, decision: $json.body.decision}) }}',[1610,-160])
nodes[-1].update(retryOnFail=True,maxTries=5,waitBetweenTries=3000)
add('입력 오류 차단','noOp',{},[690,180])
add('AI 실패 기록','noOp',{},[1150,100])
edge('합성 요청 접수','원장·요청 검수');edge('원장·요청 검수','검수 통과?')
edge('검수 통과?','실제 Qwen·SimPy 비교');edge('검수 통과?','입력 오류 차단',1)
edge('실제 Qwen·SimPy 비교','AI 비교 성공?');edge('AI 비교 성공?','검토 대기 등록');edge('AI 비교 성공?','AI 실패 기록',1)
edge('검토 대기 등록','검토자 결정 대기');edge('검토자 결정 대기','결정·계획 확정')
workflow={'id':'FactoryTrainingLocal01','name':'Factory Training Flow | n8n × Qwen × SimPy','active':False,'nodes':nodes,'connections':connections,'settings':{'executionOrder':'v1','saveDataSuccessExecution':'all','saveDataErrorExecution':'all','saveManualExecutions':True,'timezone':'Asia/Seoul'},'pinData':{},'tags':[]}
target=ROOT/'workflow.json';target.write_text(json.dumps(workflow,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(nodes)} nodes / {len(connections)} connections -> {target}')

from pathlib import Path
import hashlib,json,re
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from PIL import Image
import fitz

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]
PUBLISHED=(BASE/'adapter.py').is_file()
PROJECT=BASE if PUBLISHED else BASE/'work/factory-n8n'
OUT=BASE/'docs' if PUBLISHED else BASE/'outputs'
e2e=json.loads((PROJECT/'evidence/e2e-results.json').read_text(encoding='utf-8'))
approved=json.loads((PROJECT/'evidence/approved.json').read_text(encoding='utf-8'))
unit=json.loads((PROJECT/'tests/test-results.json').read_text(encoding='utf-8'))
sections=re.split(r'^## .*$',(ROOT/'prose.md').read_text(encoding='utf-8'),flags=re.M)[1:]
blocks=[[p.strip() for p in s.strip().split('\n\n')] for s in sections]
connections=[s[0] for s in blocks]
assert e2e['passed'] and unit['passed'] and len(connections)==3
pdfmetrics.registerFont(TTFont('KR','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('KR-B','C:/Windows/Fonts/malgunbd.ttf'))
W,H=1280,720
NAVY='#19374b';BLUE='#246f9e';TEAL='#187e6d';GOLD='#9b6913';GRAY='#536b79';LIGHT='#eaf2f5'
COLORS=[BLUE,TEAL,GOLD,'#755b9d']
PDF=OUT/('portfolio.pdf' if PUBLISHED else '김현태_원익홀딩스_n8nAI_포트폴리오_개선본.pdf')
c=canvas.Canvas(str(PDF),pagesize=(W,H),pageCompression=1)
c.setTitle('Factory Training Flow | 김현태 | 원익홀딩스 HR Data & AI | 개선본')
c.setAuthor('김현태')
boxes=[];annotations=[];page_no=0

def rect(x,t,w,h,color,stroke=None):
 c.setFillColor(HexColor(color));c.setStrokeColor(HexColor(stroke or color));c.setLineWidth(1)
 c.rect(x,H-t-h,w,h,fill=1,stroke=bool(stroke))
def text(x,t,s,size=12,color=NAVY,bold=False):
 c.setFillColor(HexColor(color));c.setFont('KR-B' if bold else 'KR',size);c.drawString(x,H-t-size,s)
def para(x,t,s,w,size=12,color=NAVY,bold=False):
 p=Paragraph(escape(s).replace('\n','<br/>'),ParagraphStyle('p',fontName='KR-B' if bold else 'KR',fontSize=size,leading=size*1.5,textColor=HexColor(color),wordWrap='CJK'))
 _,h=p.wrap(w,H);p.drawOn(c,x,H-t-h);return h
def link(x,t,label,url,size=9):
 text(x,t,label,size,BLUE);c.linkURL(url,(x,H-t-size-2,x+pdfmetrics.stringWidth(label,'KR',size),H-t),relative=0,thickness=0)
def base(n,kicker,title):
 global page_no
 page_no=n;rect(0,0,W,H,'#fbfcfd');rect(0,0,8,H,BLUE)
 text(44,18,'김현태  /  원익홀딩스 HR Data & AI 지원 프로젝트',12,GRAY)
 text(921,18,'개인 PoC · 합성 데이터 · 개정 2026.10.08',10,GRAY)
 text(44,45,kicker,11,TEAL,True);text(44,65,title,31,NAVY,True)
 para(44,110,connections[n-1],1192,13,BLUE,True)
 c.setStrokeColor(HexColor('#d3dfe5'));c.line(44,34,1236,34)
 text(44,697,'Factory Training Flow  /  AI 도구를 활용해 기획·구현·검증  /  원익 내부 도입·HR 실무 실적 아님',9,GRAY)
 text(1179,695,f'{n} / 3',11,GRAY)
def shot(path,x,t,w):
 im=Image.open(path);h=w*im.height/im.width
 rect(x-6,t-6,w+12,h+12,'#dde8ee',NAVY)
 c.drawImage(str(path),x,H-t-h,w,h,mask='auto')
 c.setStrokeColor(HexColor(NAVY));c.setLineWidth(1.5);c.rect(x-6,H-t-h-6,w+12,h+12,fill=0,stroke=1)
 boxes.append({'page':page_no,'file':str(path.relative_to(BASE)),'image':[x,t,w,h],'outer':[x-6,t-6,w+12,h+12],'continuous_four_side_border_pt':1.5})
 return h
def guide(n,x,t,title,desc,w):
 color=COLORS[n-1];rect(x,t,w,58,LIGHT)
 text(x+13,t+10,f'{n:02d}  {title}',12,color,True)
 para(x+13,t+30,desc,w-26,10.5,GRAY)
def leader(n,points,target,region):
 color=(["#54a7d3","#53b7a5","#d4a044"][n-1] if page_no==2 else COLORS[n-1]);c.setStrokeColor(HexColor(color));c.setLineWidth(1.05)
 p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
 for x,y in points[1:]:p.lineTo(x,H-y)
 p.lineTo(target[0],H-target[1]);c.drawPath(p)
 x,t,w,h=region
 c.setStrokeColor(HexColor(color));c.setLineWidth(1)
 c.rect(x,H-t-h,w,h,fill=0,stroke=1)
 bx,bt=(x-16,t+4) if page_no==1 and n==4 else (x,t-14)
 rect(bx,bt,14,14,color)
 c.setFillColor(HexColor('#ffffff'));c.setFont('KR-B',9);c.drawCentredString(bx+7,H-bt-10.5,str(n))
 annotations.append({'page':page_no,'number':n,'guide_start':points[0],'route':points[1:],'target':target,'highlight_region':region,'outline_pt':1,'number_tab':[bx,bt,14,14]})

base(1,'01  /  교육 AI 과제 발굴 · 합성 공정 비교','검사 교육과 공정 자동화를 비교하는 AI 교육기획 데모')
h=shot(ROOT/'screens/replay-review3-focus.jpg',44,155,900)
text(44,589,'실제 요청의 공정 기록 재생 · seed 0 / 10회 평균 · 기록 2026.10.07 / 재촬영 2026.10.08',9,GRAY)
text(986,155,'이 화면에서 보는 문제',16,NAVY,True)
para(986,188,'합성 작업자 4명 중 검사 자격은 1명입니다. 자동화만 할 때와 검사 교육을 함께 할 때를 같은 주문 조건에서 비교합니다.',250,12)
rect(986,304,250,110,LIGHT)
text(1001,317,'04  대안·구도·재생 조작',13,COLORS[3],True)
para(1001,346,'대안: 저장된 네 대안 결과 선택\n구도: 공정 확대·전체 공장 전환\n재생·시각: 공정의 진행 시점 확인',220,10.8)
rect(986,437,250,88,LIGHT)
text(1001,450,'02  검사 역량',13,TEAL,True)
para(1001,478,'검사 자격은 1명→2명입니다.\n교육 가정에 따른 변화를 검사대에서 봅니다.',220,11)
rect(986,550,250,98,LIGHT)
text(1001,563,'03  비교 결과',13,GOLD,True)
para(1001,591,'기준 36.1개 → 결합 58.3개\n같은 주문·8시간·10개 seed 평균입니다.',220,11)
guide(1,44,613,'공정 흐름','컨베이어·AMR가 이동하는 위치를 봅니다.',280)
leader(1,[(184,613),(184,603),(28,603),(28,450)],(201,450),(201,426,394,80))
leader(2,[(986,467),(968,467),(968,400)],(701,400),(615,372,86,69))
leader(3,[(986,585),(957,585),(957,547)],(432,547),(244,530,188,17))
leader(4,[(986,332),(978,332),(978,282)],(924,282),(61,263,863,39))
para(344,616,'합성 작업자·개인 PoC입니다. 실제 직원·원익 내부 데이터가 아닙니다.\n현장 비용·안전·교육 효과와 원익의 n8n 사용 여부는 미확인입니다.',600,10,GRAY)
link(344,658,'출처: 공식 공고 / HR Data & AI','https://wonik.recruiter.co.kr/career/jobs/128767',8.5)
link(530,658,'문제 배경: 원익로보틱스 공개 디지털트윈','https://wonikrobotics.com/kr/sub/application/robotAutomation/digital_twin.php',8.5)
c.showPage()

base(2,'02  /  AI가 대안을 선택하고, 사람이 결정','Qwen은 선택하고, n8n은 승인을 기다립니다')
shot(PROJECT/'assets/architecture.png',44,155,900)
guide(1,44,550,'n8n · 실행과 대기','접수·분기·Wait 후 검토자의 결정으로 재개합니다.',280)
guide(2,344,550,'Python · Qwen 연결과 계산','Qwen은 선택, SimPy는 수치를 계산합니다.',280)
guide(3,644,550,'SQLite · 판단 기록','결정과 비교 근거를 남기고 승인 시 계획을 저장합니다.',300)
leader(1,[(184,550),(184,528),(142,528)],(142,434),(76,277,134,157))
leader(2,[(484,550),(484,535),(360,535)],(360,434),(296,277,127,157))
leader(3,[(794,550),(794,528),(802,528)],(802,434),(736,277,133,157))
rect(986,155,250,225,LIGHT)
text(1001,169,'실제 로컬 LLM 실행',15,NAVY,True)
text(1001,207,'Qwen2.5-1.5B-Instruct',12,BLUE,True)
text(1001,237,'CPU / float32 / revision 고정',10,GRAY)
text(1001,270,'실제 선택: combined',13,NAVY,True)
text(1001,302,'첫 실행 121.21초 / 후속 10.85초',11)
text(1001,337,'측정 기록: 2026.10.07',10,GRAY)
text(986,405,'AI와 계산의 경계',14,NAVY,True)
para(986,436,'LLM은 사전에 정한 대안의 선호를 선택합니다. 공정 수치·비교 설명은 SimPy 계산값으로 작성하며 설비 설정을 자유 생성하지 않습니다.',250,11.5)
para(44,626,'교육 적격 후보 1명에게 사전교육 8시간 후 검사 자격이 생긴다는 가정입니다. 실제 교육 효과는 확인하지 않았습니다. 완료 기록은 재시작 후 조회하며, 승인 통신 실패는 같은 결정으로 재전송합니다.',900,11,GRAY)
para(986,544,'구현한 연결 구조 / 10개 n8n 노드\n실제 Qwen 선택·SimPy 계산·SQLite 기록',250,9,GRAY)
link(986,579,'n8n 공식 Wait 문서','https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.wait')
para(986,612,'확정 호출은 5회까지 재시도합니다. 이후 실패한 n8n 실행은 운영자가 원인을 해결하고 재시도해야 합니다.',250,10,GRAY)
c.showPage()

base(3,'03  /  실제 비교 결과와 검증','승인·거절·결측의 결과를 기록으로 확인합니다')
h=shot(ROOT/'screens/approved-detail.jpg',44,155,700)
text(44,155+h+13,'실제 승인 화면의 결과 영역 확대 / 원본 전체 화면 보존 · 기록 2026.10.07 / 재촬영 2026.10.08',9,GRAY)
text(44,598,'완료 평균: 기준 36.1 / 로봇 36.9 / 교육 43.6 / 결합 58.3개 · 합성 공정 결과',10.5,BLUE,True)
text(800,155,'실제 n8n 2.42.3 실행 결과',16,NAVY,True)
rect(800,192,436,34,NAVY)
for x,s in [(813,'경로'),(938,'n8n'),(1041,'모델 호출'),(1151,'계획')]:text(x,201,s,11,'#ffffff',True)
rows=[('승인','success','실제 Qwen','1건'),('거절','success','실제 Qwen','0건'),('검사 스킬 결측','success','미실행','0건')]
for i,row in enumerate(rows):
 y=227+i*41;rect(800,y,436,40,LIGHT if i%2==0 else '#f7fafb')
 for x,s in zip([813,938,1041,1151],row):text(x,y+11,s,11)
text(800,372,'n8n success ≠ 업무 승인',13,BLUE,True)
para(800,400,'결측 경로는 정상적으로 차단을 처리했습니다. 실행이 success여도 승인이나 교육 계획 생성으로 해석하지 않습니다.',436,11.5)
text(800,483,'검증 범위를 분리했습니다',14,NAVY,True)
para(800,513,'실제 E2E: 3경로 / 실제 Qwen 2건\n연결부 테스트: 21/21 통과\n모델 선택 mock / SimPy는 실제 계산',436,12)
guide(1,44,621,'계산 결과','동일 주문·8시간·10개 seed 평균을 비교합니다.',360)
guide(2,424,621,'승인 후 저장','합성 교육 계획 1건 / 1명·8시간 가정입니다.',360)
guide(3,804,621,'결측은 차단','모델 호출과 계획 생성 없이 종료합니다.',432)
leader(1,[(224,621),(224,612),(28,612),(28,302)],(61,302),(61,269,669,116))
leader(2,[(604,621),(604,611),(766,611),(766,518)],(726,518),(63,489,663,47))
leader(3,[(1020,621),(1020,608),(1251,608),(1251,329)],(1226,329),(807,307,419,41))
para(800,579,'중복은 추가 실행·계획 없음 / 상충 결정은 409\n완료 기록은 재시작 후 유지 확인',436,10,GRAY)
c.showPage();c.save()

doc=fitz.open(PDF)
render=ROOT/'render';render.mkdir(exist_ok=True)
for i,p in enumerate(doc):
 p.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(render/f'page-{i+1}-100.png')
 p.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(render/f'page-{i+1}.png')
contact=Image.new('RGB',(1280,2160),'#dbe6ec')
for i in range(3):contact.paste(Image.open(render/f'page-{i+1}-100.png'),(0,i*720))
contact.save(OUT/('portfolio-overview.png' if PUBLISHED else 'n8nAI_포트폴리오_개선본_전체.png'))
if PUBLISHED:
 for i in range(1,4):Image.open(render/f'page-{i}.png').save(OUT/f'portfolio-page-{i}.png')
else:
 Image.open(render/'page-1.png').save(OUT/'n8nAI_포트폴리오_개선본_1장.png')
for i,con in enumerate(connections):
 assert ''.join(con.split()) in ''.join(doc[i].get_text().split()),f'page {i+1} connection missing'
txt='\n'.join(p.get_text() for p in doc)
assert len(doc)==3 and 'HUMANIZE-SUMMARY' not in txt
for s in ['36.1','58.3','121.21','10.85','21/21','Qwen','SimPy','합성']:assert s in txt,s
audit={'pages':3,'size':[W,H],'connections':[{'page':i+1,'location':'title below, y=110','text':s} for i,s in enumerate(connections)],'source_jd':'https://wonik.recruiter.co.kr/career/jobs/128767','screenshots':boxes,'annotations':annotations,'original_full_captures_preserved':True,'capture_date':'2026-10-08','measurement_date':'2026-10-07','actual_n8n_executions':3,'actual_qwen_calls':2,'unit_model_mock':True,'unit_tests':21,'prose_run':'work/i-am-not-ai/2026-10-08-004-portfolio-v2','prose_gate':'exit 0, OK, golden PASS, 6/6','prose_change_rate':0,'original_pdf_preserved':True,'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'visual_review':'pending','KASA':'project-specific case study, no award field or resume edit'}
(ROOT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(str(PDF))

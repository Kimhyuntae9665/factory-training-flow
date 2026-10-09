"""Build only from real captured UI and live validation evidence; no placeholders."""
from pathlib import Path
import json, hashlib, re, argparse
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from PIL import Image, ImageOps
import fitz

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / 'docs'
EVIDENCE = BASE / 'wonik-learning-lens/evidence'
REV = BASE / 'docs/portfolio-source-v2'
COPY = REV / 'copy.json'
RUN = REV / 'validation'
PDF = OUT / 'portfolio.pdf'
W, H = 1280, 720
NAVY, BLUE, TEAL, GOLD, GRAY = '#17384e', '#246aa1', '#1b7b70', '#a57421', '#556c7c'
COLORS = [BLUE, TEAL, GOLD]

def prose(data):
    result = [data['positioning']]
    for p in data['pages']:
        result.extend([p['title'], p['connection'], p['caption']])
        for g in p['guides']: result.extend([g['title'], g['desc']])
        for s in p.get('side', []): result.extend([s['title'], s['body']])
        result.extend([p[k] for k in ['validation','validationDetails','boundaries', 'provenance','recordSummary'] if k in p])
        if 'comparisonTitle' in p:
            result.append(p['comparisonTitle'])
            result.extend(' / '.join(row) for row in p['comparisonRows'])
    return '\n\n'.join(result) + '\n'

def prepare():
    data = json.loads(COPY.read_text(encoding='utf-8'))
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / '01_input.txt').write_text(prose(data), encoding='utf-8')
    print(RUN)

def build():
    data = json.loads(COPY.read_text(encoding='utf-8'))
    # A final accepted text and live files are mandatory before any PDF is made.
    final = (RUN / 'final.md').read_text(encoding='utf-8')
    accepted = re.sub(r'<!-- HUMANIZE-SUMMARY -->.*', '', final, flags=re.S).strip()
    assert accepted == prose(data).strip(), 'Copy changed: reconcile accepted prose with copy JSON first.'
    gate_output=(RUN/'gate-output.txt').read_text(encoding='utf-8-sig')
    assert '"exit_code": 0' in gate_output, 'Prose gate must pass before PDF delivery.'
    captures = json.loads((REV / 'capture-map.json').read_text(encoding='utf-8'))
    live = json.loads((EVIDENCE / 'live-validation.json').read_text(encoding='utf-8'))
    assert live['automaticTests']['passed']==49 and live['automaticTests']['failed']==0
    assert live['automaticTests']['newMockAndUi']==10
    assert len(live['checks'])>=14 and all(item['pass'] for item in live['checks'])
    assert live['browserFirstReview']['llmMs']==86470
    shots = {}
    for name in ['factory', 'review', 'plans', 'blocked']:
        path = EVIDENCE / f'{name}.jpg'
        assert path.is_file(), f'Missing live capture: {path}'
        shots[name] = path
    shots['review'] = REV / 'review.jpg'
    archived = json.loads((REV/'capture-review.json').read_text(encoding='utf-8'))
    assert archived['stateUnchanged'] and archived['newModelCall'] is False
    assert archived['requestId'] == live['browserFirstReview']['requestId']
    assert archived['hours'] == 2 and archived['selectedWorkerId'] == 'SYN-101'
    pdfmetrics.registerFont(TTFont('KR', 'C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('KR-B', 'C:/Windows/Fonts/malgunbd.ttf'))
    c = canvas.Canvas(str(PDF), pagesize=(W,H), pageCompression=1)
    c.setTitle('Wonik Learning Lens | 김현태 | 원익홀딩스 HR Data & AI')
    c.setAuthor('김현태')
    shot_records, annotation_records, connections = [], [], []
    pageno = 0

    def box(x,y,w,h,fill=None,stroke=None,width=1):
        if fill:c.setFillColor(HexColor(fill))
        if stroke:c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(width); c.rect(x,H-y-h,w,h,fill=bool(fill),stroke=bool(stroke))
    def text(x,y,s,size=12,color=NAVY,bold=False):
        c.setFillColor(HexColor(color));c.setFont('KR-B' if bold else 'KR',size);c.drawString(x,H-y-size,s)
    def para(x,y,s,w,size=12,color=NAVY,bold=False):
        style=ParagraphStyle('p',fontName='KR-B' if bold else 'KR',fontSize=size,leading=size*1.48,textColor=HexColor(color),wordWrap='CJK')
        p=Paragraph(escape(s).replace('\n','<br/>'),style);_,height=p.wrap(w,H);p.drawOn(c,x,H-y-height);return height
    def link(x,y,label,url,size=9):
        text(x,y,label,size,BLUE);c.linkURL(url,(x,H-y-size-2,x+pdfmetrics.stringWidth(label,'KR',size),H-y),relative=0,thickness=0)
    def base(n,p):
        nonlocal pageno
        pageno=n;box(0,0,W,H,'#fbfcfd');box(0,0,7,H,BLUE)
        text(44,18,data['identity'],11,GRAY)
        text(1006,18,'개인 데모 · 기준 '+data['date'],10,GRAY)
        c.setStrokeColor(HexColor('#d4dfe7'));c.line(44,H-38,1236,H-38)
        text(44,51,p['kicker'],11,TEAL,True)
        text(44,72,p['title'],30,NAVY,True)
        para(44,118,p['connection'],1192,13,BLUE,True)
        connections.append({'page':n,'position':'제목 바로 아래 y=118','text':p['connection']})
        text(44,694,'Wonik Learning Lens  /  Codex 활용 개인 프로젝트 · 합성 데이터 · 원익 내부 적용 실적 아님',9,GRAY)
        text(1185,693,f'{n} / 3',11,GRAY)
    def shot(name,x,y,maxw,maxh):
        im=Image.open(shots[name]);iw,ih=im.size;scale=min(maxw/iw,maxh/ih);w,h=iw*scale,ih*scale
        c.drawImage(str(shots[name]),x,H-y-h,w,h,mask='auto')
        # Four uninterrupted sides sit outside the pixels; source UI stays unchanged.
        box(x-3,y-3,w+6,h+6,None,NAVY,1.2)
        placement={'x':x,'y':y,'w':w,'h':h,'scale':scale,'source_size':[iw,ih]}
        shot_records.append({'page':pageno,'name':name,'path':str(shots[name].relative_to(BASE)),'placement':placement,'outer':[x-3,y-3,w+6,h+6],'border_pt':1.2})
        return placement
    def entry(name):
        raw=captures.get('captures',captures)
        if isinstance(raw,list):return next(v for v in raw if v.get('name')==name or Path(v.get('file','')).stem==name)
        return raw[name]
    def region(name,key):
        e=entry(name);r=e.get('regions',e.get('boxes',{}))[key]
        if isinstance(r,dict):return [r['x'],r['y'],r.get('width',r.get('w')),r.get('height',r.get('h'))]
        return r
    def guide(n,g,x,y,w):
        box(x,y,w,61,'#edf3f8')
        text(x+12,y+9,f'{n:02d}  '+g['title'],12,COLORS[n-1],True)
        para(x+12,y+29,g['desc'],w-24,10.6,GRAY)
    def annotate(n,g,name,placement,guide_x,guide_y,guide_w,route=None):
        raw=region(name,g['key']);scale=placement['scale']
        iw,ih=placement['source_size']
        assert raw[2]>0 and raw[3]>0 and raw[0]>=0 and raw[1]>=0, f'Invalid DOM region: {name}/{g["key"]}'
        assert raw[0]+raw[2]<=iw+1 and raw[1]+raw[3]<=ih+1, f'DOM region exceeds image: {name}/{g["key"]}'
        rx=placement['x']+raw[0]*scale;ry=placement['y']+raw[1]*scale;rw=raw[2]*scale;rh=raw[3]*scale
        color=COLORS[n-1];box(rx,ry,rw,rh,None,color,.9)
        # Number tabs are outside the target, never a substitute for its full outline.
        text(rx+3,max(placement['y']-16,ry-15),str(n),9,color,True)
        target=[rx+rw,ry+rh]
        anchor=[guide_x+guide_w/2,guide_y]
        gutter=min(1250,placement['x']+placement['w']+15+(n-1)*12)
        bend=guide_y-9+(n-1)*3
        pts=route or [target,[gutter,target[1]],[gutter,bend],[anchor[0],bend],anchor]
        c.setStrokeColor(HexColor(color));c.setLineWidth(.85);p=c.beginPath();p.moveTo(pts[0][0],H-pts[0][1])
        for xx,yy in pts[1:]:p.lineTo(xx,H-yy)
        c.drawPath(p)
        annotation_records.append({'page':pageno,'number':n,'capture':name,'key':g['key'],'source_region':raw,'highlight_region':[rx,ry,rw,rh],'route':pts,'description':g['desc'],'guide':[guide_x,guide_y,guide_w,61],'outline_pt':.9})
    def side(p,x=1012,w=224,start=162):
        y=start
        for s in p['side']:
            text(x,y,s['title'],14,NAVY,True);y+=28
            y+=para(x,y,s['body'],w,11,GRAY)+24
    for n,name in [(1,'factory')]:
        p=data['pages'][n-1];base(n,p)
        placement=shot(name,44,163,940,430)
        text(44,placement['y']+placement['h']+9,p['caption'],9,GRAY)
        side(p,x=711,w=470,start=226) if n==1 else side(p)
        for i,g in enumerate(p['guides']):
            gx=44+i*(211 if n==1 else 319);gw=197 if n==1 else 301;gy=622
            guide(i+1,g,gx,gy,gw);annotate(i+1,g,name,placement,gx,gy,gw)
        if n==1:
            para(711,163,data['positioning'],470,14,BLUE,True)
        else:
            link(1012,583,'직무 근거: 원익홀딩스 공식 공고',data['sources']['jd'],9)
        c.showPage()
    p=data['pages'][1];base(2,p)
    placement=shot('review',44,163,790,505)
    text(44,placement['y']+placement['h']+9,p['caption'],8.8,GRAY)
    s=p['side'][0];text(880,166,s['title'],14,NAVY,True)
    para(880,196,s['body'],350,11,GRAY)
    positions=[(880,270,350),(880,368,350),(880,532,350)]
    for i,(g,(gx,gy,gw)) in enumerate(zip(p['guides'],positions)):
        guide(i+1,g,gx,gy,gw)
        raw=region('review',g['key']);scale=placement['scale']
        target=[placement['x']+(raw[0]+raw[2])*scale,placement['y']+(raw[1]+raw[3])*scale]
        route=[target,[850+i*7,target[1]],[850+i*7,gy+30],[gx,gy+30]]
        annotate(i+1,g,'review',placement,gx,gy,gw,route)
    s=p['side'][1];text(880,446,s['title'],13,NAVY,True)
    para(880,470,s['body'],350,10.5,GRAY)
    s=p['side'][2];text(880,611,s['title'],12,NAVY,True)
    para(880,632,s['body'],350,10,GRAY)
    c.showPage()
    p=data['pages'][2];base(3,p)
    placements={name:shot(name,x,168,572,303) for name,x in [('plans',44),('blocked',664)]}
    text(44,427,'2장과 같은 요청 · SYN-101 / C-LOAD / 2시간',10,BLUE,True)
    para(44,449,p['recordSummary'],572,11,GRAY)
    text(664,294,'별도 예외 요청 · POLICY_CONFLICT',10,GOLD,True)
    text(664,320,p['comparisonTitle'],11,NAVY,True)
    for j,row in enumerate(p['comparisonRows']):
        y=346+j*32;box(664,y,572,30,'#edf3f8' if j%2==0 else '#f5f8fa')
        text(674,y+6,row[0],10,NAVY,True)
        text(824,y+6,row[1],10,GRAY)
        text(1135,y+6,row[2],10,TEAL,True)
    for i,g in enumerate(p['guides']):
        gx=44+i*404;guide(i+1,g,gx,507,384);annotate(i+1,g,g['shot'],placements[g['shot']],gx,507,384)
    text(44,583,p['validation'],11,BLUE,True)
    text(44,602,p['validationDetails'],10,GRAY)
    para(44,626,p['provenance'],1192,10.3,BLUE,True)
    para(44,648,p['boundaries'],1192,10.3,GRAY)
    c.showPage();c.save()
    doc=fitz.open(PDF)
    assert len(doc)==3
    text_all='\n'.join(p.get_text() for p in doc)
    assert 'HUMANIZE-SUMMARY' not in text_all
    for i,item in enumerate(connections):
        assert ''.join(item['text'].split()) in ''.join(doc[i].get_text().split()),f'Missing job linkage page {i+1}'
    overview=Image.new('RGB',(W,H*3),'#d7e1e9')
    for i,page in enumerate(doc):
        page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(RUN/f'page-{i+1}-100.png')
        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
        path=OUT/f'portfolio-page-{i+1}.png';ImageOps.expand(Image.frombytes('RGB',[pix.width,pix.height],pix.samples),border=2,fill=NAVY).save(path)
        im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples).resize((W,H));overview.paste(im,(0,H*i))
    overview.save(OUT/'portfolio-overview.png')
    record={'pages':3,'page_size':[W,H],'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'connections':connections,'screenshots':shot_records,'annotations':annotation_records,'source_jd':data['sources']['jd'],'manufacturing_context_only':data['sources']['manufacturing_context'],'live_validation':live,'prose_run':str(RUN.relative_to(BASE)),'prose_route':'light','prose_change_rate':0,'prose_gate':'exit 0 / golden PASS / 서법 소실 0 / 원문 직접 대조','visual_review':'pending','source_ui_preserved':True,'KASA':'프로젝트 사례 3페이지이며 이력서나 수상란이 아님'}
    md='# Wonik Learning Lens 포트폴리오 검수\n\n'
    md+='- 결과: 3페이지 PDF와 페이지별 PNG 생성. 육안 검수는 아직 pending.\n'
    md+='- 모든 직무 연결 문장을 각 장 제목 아래에 넣고 PDF 텍스트로 재확인.\n'
    md+='- 실제 캡처의 DOM 좌표로 관찰 사각형을 배치하고 연결선·바깥 네 변 테두리 기록.\n'
    md+='- 개인 데모, 합성 자료, 원익 실제 설비 아님, 교육성과 미측정, n8n 실행 미검증을 본문에 표시.\n'
    md+='- 원본 창신 산출물·기타 PDF는 수정하지 않음.\n\n```json\n'+json.dumps(record,ensure_ascii=False,indent=2)+'\n```\n'
    record['archive_capture']=archived
    record['changes']=['One SYN-101 C-LOAD case across all pages','Same 86470ms timing','Actual normal/duplicate/conflict/opposite results compared','Archive renderer uses saved actual response; no fresh inference','Prior PDF and app code preserved']
    record['reference_patterns']=['ui-reference-kit/20 explanation with experiment','ui-reference-kit/09 result comparison','ui-reference-kit/15 explicit state; document labels only']
    md+='\n## 이번 수정\n\n'+json.dumps(record['changes'],ensure_ascii=False)+'\n'
    (REV/'validation.md').write_text(md,encoding='utf-8')
    (REV/'audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(PDF)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-prose',action='store_true');args=parser.parse_args()
    prepare() if args.prepare_prose else build()

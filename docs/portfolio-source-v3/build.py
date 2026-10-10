from pathlib import Path
import json, re, hashlib
from xml.sax.saxutils import escape
from PIL import Image
import fitz
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parents[2]
REV=ROOT/'docs/portfolio-source-v3'
PROJECT=ROOT/'wonik-learning-lens'
CAPTURES=ROOT/'docs/screenshots/wonik-learning-lens-v3'
OUT=ROOT/'docs/portfolio.pdf'
W,H=1280,720
NAVY,GRAY='#19394e','#556e7d'
COLORS=['#286ea0','#237e72','#a47122']
copy=json.loads((REV/'copy.json').read_text(encoding='utf-8'))
comparison=json.loads((PROJECT/'evidence/comparison-20261010-final/results.json').read_text(encoding='utf-8'))
n8n=json.loads((PROJECT/'evidence/n8n-20261010.json').read_text(encoding='utf-8'))
assert comparison['summary']['rules']['correct']==12 and comparison['summary']['llm']['correct']==15
assert n8n['passed'] and len(n8n['cases'])==3
assert all(all(v for v in case['checks'].values() if isinstance(v,bool)) for case in n8n['cases'])
assert 'tests 56' in (REV/'publication-tests.txt').read_text(encoding='utf-8-sig')
capture=json.loads((REV/'capture-map.json').read_text(encoding='utf-8'))
pdfmetrics.registerFont(TTFont('KR','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('KRB','C:/Windows/Fonts/malgunbd.ttf'))
c=canvas.Canvas(str(OUT),pagesize=(W,H),pageCompression=1)
c.setTitle('김현태 | 원익홀딩스 HR Data & AI | Learning Lens v3')
c.setAuthor('김현태')
records=[]
def box(x,y,w,h,fill=None,stroke=None,width=1):
    if fill:c.setFillColor(HexColor(fill))
    if stroke:c.setStrokeColor(HexColor(stroke))
    c.setLineWidth(width);c.rect(x,H-y-h,w,h,fill=bool(fill),stroke=bool(stroke))
def text(x,y,s,size=12,color=NAVY,bold=False):
    c.setFillColor(HexColor(color));c.setFont('KRB' if bold else 'KR',size);c.drawString(x,H-y-size,s)
def para(x,y,s,width,size=13,color=NAVY,bold=False):
    style=ParagraphStyle('p',fontName='KRB' if bold else 'KR',fontSize=size,leading=size*1.5,wordWrap='CJK',textColor=HexColor(color))
    p=Paragraph(escape(s),style);_,height=p.wrap(width,700);p.drawOn(c,x,H-y-height);return height
def base(n):
    p=copy['pages'][n-1];box(0,0,W,H,'#fbfcfd');box(0,0,7,H,COLORS[0])
    text(44,18,copy['identity'],11,GRAY);text(1084,18,copy['date']+' 검수',10,GRAY)
    box(44,39,1192,1,'#d3dfe7');text(44,52,p['kicker'],11,COLORS[1],True)
    size=29 if n>1 else 32;text(44,76,p['title'],size,NAVY,True)
    para(44,122,p['connection'],1192,13,COLORS[0],True)
    text(44,695,'합성 자료 · 개인 데모 · 교육계획과 이수/자격/생산 효과를 구분 · 원익 내부 적용 실적 아님',9,GRAY)
    label='공식 공고';text(987,695,label,9,COLORS[0]);c.linkURL('https://wonik.recruiter.co.kr/career/jobs/128767',(987,9,1040,24),relative=0,thickness=0)
    text(1072,695,'공개 저장소',9,COLORS[0]);c.linkURL('https://github.com/Kimhyuntae9665/factory-training-flow',(1072,9,1160,24),relative=0,thickness=0)
    text(1199,694,f'{n}/3',11,GRAY)
    return p
def section(s,x,y,width=366,size=13):
    text(x,y,s['title'],15,NAVY,True);return para(x,y+27,s['body'],width,size,GRAY)
def shot(name,x,y,width):
    info=capture[name];source=CAPTURES/info['file'];sx,sy,sw,sh=info['crop'];iw,ih=Image.open(source).size
    assert sx>=0 and sy>=0 and sx+sw<=iw and sy+sh<=ih
    scale=width/sw;height=sh*scale
    c.saveState();p=c.beginPath();p.rect(x,H-y-height,width,height);c.clipPath(p,stroke=0,fill=0)
    c.drawImage(str(source),x-sx*scale,H-y+sy*scale-ih*scale,iw*scale,ih*scale,mask='auto');c.restoreState()
    box(x-3,y-3,width+6,height+6,None,NAVY,1.2)
    records.append({'page':pageNo,'screenshot':name,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'crop':info['crop'],'placement':[x,y,width,height],'outerBorder':True})
    return {'x':x,'y':y,'s':scale,'w':width,'h':height,'info':info}
def guide(n,g,x,y,width,height=66):
    color=COLORS[n-1];box(x,y,width,height,'#eef4f8');text(x+13,y+10,f'{n:02d}  '+g['title'],12,color,True);para(x+13,y+32,g['desc'],width-26,10.8,GRAY)
def annotation(n,key,shot,g,gx,gy,gw,route='right',height=66):
    sx,sy,sw,sh=shot['info']['crop'];a,b,rw,rh=shot['info']['regions'][key]
    assert 0<=a and 0<=b and a+rw<=sw and b+rh<=sh
    x=shot['x']+a*shot['s'];y=shot['y']+b*shot['s'];w=rw*shot['s'];h=rh*shot['s'];color=COLORS[n-1]
    box(x,y,w,h,None,color,.85)
    if route=='below-left':
        gutter=shot['x']-(24 if n==1 else 16); bend=gy-(2 if n==1 else 5)
        points=[(x,y+h/2),(gutter,y+h/2),(gutter,bend),(gx+gw/2,bend),(gx+gw/2,gy)]
    elif route=='below-right':
        gutter=shot['x']+shot['w']+16+(n-1)*8; bend=gy-6+(n-1)*2
        points=[(x+w,y+h/2),(gutter,y+h/2),(gutter,bend),(gx+gw/2,bend),(gx+gw/2,gy)]
    elif route=='bottom':
        points=[(x+w/2,y+h),(x+w/2,gy-8),(gx+gw/2,gy-8),(gx+gw/2,gy)]
    elif route=='top':
        points=[(x+w/2,y),(x+w/2,shot['y']-10),(gx-14,shot['y']-10),(gx-14,gy+height/2),(gx,gy+height/2)]
    else:
        gutter=shot['x']+shot['w']+12+(n-1)*8
        points=[(x+w,y+h/2),(gutter,y+h/2),(gutter,gy+height/2),(gx,gy+height/2)]
    c.setStrokeColor(HexColor(color));c.setLineWidth(.8);path=c.beginPath();path.moveTo(points[0][0],H-points[0][1])
    for px,py in points[1:]:path.lineTo(px,H-py)
    c.drawPath(path);guide(n,g,gx,gy,gw,height)
    records.append({'page':pageNo,'target':key,'rectangle':[x,y,w,h],'line':points,'guide':[gx,gy,gw,height]})

pageNo=1;p=base(1);s=shot('factory',44,168,650)
section(p['sections'][0],800,174,426,13)
section(p['sections'][1],800,252,426,13)
text(800,372,'교육 요청 입력 · SYN-101',12,NAVY,True)
r=shot('request',800,397,426)
for n,key,gx,gw in [(1,'process',44,376),(2,'station',448,376)]:
    annotation(n,key,s,p['guides'][n-1],gx,637,gw,'below-left',48)
annotation(3,'query',r,p['guides'][2],852,637,384,'below-right',48)
para(44,150,p['caption'],1192,9.5,GRAY);c.showPage()

pageNo=2;p=base(2);s=shot('comparison',44,173,800)
annotation(1,'metrics',s,p['guides'][0],882,173,354,height=72)
annotation(2,'rules',s,p['guides'][1],44,624,386,'bottom',56)
annotation(3,'llm',s,p['guides'][2],458,624,386,'bottom',56)
for i,y in enumerate([276,401,541]):section(p['sections'][i],882,y,354,12.5)
para(44,151,p['caption'],1192,10,GRAY);c.showPage()

pageNo=3;p=base(3);s=shot('n8n',44,173,800)
annotation(1,'trace',s,p['guides'][0],882,173,354,'top',64)
annotation(2,'output',s,p['guides'][1],882,349,354,'right',64)
annotation(3,'cases',s,p['guides'][2],882,531,354,'right',64)
section(p['sections'][0],882,252,354,12.2);section(p['sections'][1],882,428,354,12.2)
para(44,151,p['caption'],800,10,GRAY)
text(44,640,p['sections'][2]['title'],12,NAVY,True)
para(44,660,p['sections'][2]['body'],1192,10.8,GRAY)
c.save()
doc=fitz.open(OUT);assert len(doc)==3
for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1,1)).save(ROOT/f'docs/portfolio-page-{i+1}.png')
(REV/'layout-validation.json').write_text(json.dumps({'pages':3,'records':records,'comparison':comparison['summary'],'n8nPassed':n8n['passed'],'tests':56,'connections':[{'page':i+1,'text':p['connection'],'position':'title below'} for i,p in enumerate(copy['pages'])]},ensure_ascii=False,indent=2),encoding='utf-8')
print(OUT)

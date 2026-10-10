const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sec = ms => (ms / 1000).toFixed(1);
const view = new URL(location.href).searchParams.get('view') || 'comparison';
async function read(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw new Error(`기록 파일을 읽지 못했습니다 (${r.status}). 검증을 실행한 뒤 다시 열어 주세요.`);return r.json();}
function metric(value,label){return `<div class="metric"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;}
async function comparison(){
 const data=await read('evidence/comparison-20261010-final/results.json');
 if(!data.completedAt || !data.summary?.llm || data.summary.llm.total!==20 || data.summary.rules.total!==20)throw new Error('20개 비교 검증이 아직 완료되지 않았습니다. 일부 결과를 최종 결과로 표시하지 않습니다.');
 $('title').textContent='같은 요청, 규칙과 LLM은 어떻게 다른가';
 $('archive').textContent=`${data.date} 실제 실행 기록 재열람 · ${data.model} · 합성 요청 20개 · 새 모델 호출 없음`;
 const cases=await read('evaluation/cases.json');
 $('content').innerHTML=`<div class="metrics" id="comparison-metrics">${metric(`${data.summary.rules.correct}/20`,'정확 키워드 규칙 · 시연 기준 일치')}${metric(`${data.summary.llm.correct}/20`,'로컬 LLM 의미 선택 · 시연 기준 일치')}${metric(`${sec(data.summary.llm.medianModelMs)}초`,'실제 모델 호출 응답시간 중앙값')}</div><div class="request" id="example-request"><select id="example" aria-label="비교 요청 선택">${cases.cases.map(c=>`<option value="${c.id}" ${c.id==='E07'?'selected':''}>${c.id} · ${esc(c.category)}</option>`).join('')}</select><label id="example-meta"></label><p id="query"></p></div><div class="grid" id="example-results"></div><div id="categories"></div><p class="note">개발자가 작성한 합성 요청의 기준 답과 비교했습니다. 독립 홀드아웃·실제 담당자 평가가 아닙니다. 두 방식 모두 동일한 자격·기이수·현행 근거 검사를 거치며, 승인은 사람이 결정합니다. 규칙은 모델을 호출하지 않습니다.</p>`;
 const labels={literal:'직접 표현',paraphrase:'동의어·우회 표현',negation:'부정 표현',ambiguous:'모호한 요청',qualification:'자격 부족',completed:'기이수',off_topic:'무관한 요청',conflict:'현행 문서 충돌'};
 const keys=Object.keys(data.summary.rules.byCategory);
 $('categories').innerHTML=`<table class="table" id="category-table"><thead><tr><th>요청 유형</th><th>규칙 일치</th><th>LLM 일치</th></tr></thead><tbody>${keys.map(k=>`<tr><td>${labels[k]||k}</td><td>${data.summary.rules.byCategory[k].correct}/${data.summary.rules.byCategory[k].total}</td><td>${data.summary.llm.byCategory[k].correct}/${data.summary.llm.byCategory[k].total}</td></tr>`).join('')}</tbody></table>`;
 function show(){
  const id=$('example').value,c=cases.cases.find(c=>c.id===id);
  $('query').textContent=c.query;$('example-meta').textContent=`${c.id} · ${c.worker} · 합성 시연 기준 답: ${c.expected}`;
  $('example-results').innerHTML=['rules','llm'].map(mode=>{const r=data.results.find(r=>r.id===id&&r.mode===mode);const p=r.review?.proposal;return `<article class="card" id="result-${mode}"><h2>${mode==='rules'?'규칙 기준선 · 정확 키워드':'로컬 LLM · 자연어 의미 선택'}</h2><div class="result ${p?'':'blocked'}" id="decision-${mode}"><span class="pill">${r.correct?'시연 기준 일치':'시연 기준 불일치'}</span><h3>${p?esc(p.title):'검토 보류 / 차단'}</h3><p>${p?`${p.hours}시간 · ${esc(p.id)}`:esc(r.code||r.error?.code)}</p></div><p>${esc(p?.reason||r.review?.message||r.error?.message)}</p><p class="small">${mode==='rules'?'모델 호출 0회':(r.llmStatus==='not_called'?'모델 호출 없음':`모델 응답 ${sec(r.llmMs)}초`)} · 자동 승인 없음</p><div class="sources" id="evidence-${mode}">${p?`현행 근거: ${p.evidenceIds.map(esc).join(' · ')}<br>자격·기이수·필수 근거 코드 검사 통과`:'저장된 교육계획 없음'}</div></article>`;}).join('');
 }
 $('example').addEventListener('change',show);show();
}
async function n8n(){
 const data=await read('evidence/n8n-20261010.json');
 if(!data.passed || !data.cases?.length || !data.cases.every(c=>Object.values(c.checks||{}).filter(v=>typeof v==='boolean').every(Boolean)))throw new Error('n8n 실행 검수가 완료되지 않았습니다.');
 $('title').textContent='요청부터 승인·CSV 출력까지 연결';
 $('archive').textContent=`${data.date.slice(0,10)} 실제 n8n ${data.n8nVersion} 실행 기록 재열람 · 합성 자료 · 이 화면에서 승인하지 않음`;
 const normal=data.cases.find(c=>c.decision==='approve'),review=normal.review,plan=normal.plan;
 if(!normal || !review || !plan)throw new Error('승인 사례의 실제 결과가 없습니다.');
 $('content').innerHTML=`<div class="metrics" id="n8n-metrics">${metric(`${data.cases.length}건`,'실제 n8n 실행 · 승인 / 거절 / 충돌')}${metric('담당자 결정 대기','Wait 전 교육계획 저장 없음')}${metric(`${normal.planCountAfter-normal.planCountBefore}건`,'승인 후 계획 저장 · CSV 대조')}</div><div class="grid"><article class="card" id="n8n-trace"><h2>실제 실행 흐름</h2><p class="small">실행 ${esc(normal.executionId)} · ${esc(normal.status)}</p><ol class="trace">${normal.nodeNames.map((name,i)=>`<li class="${name.includes('대기')?'wait':''}"><b>${i+1}</b><span>${esc(name)}</span></li>`).join('')}</ol><p class="small">Wait와 추가 저장 0건을 확인한 뒤 검수용 approve POST를 전송했습니다.</p></article><article class="card" id="n8n-output"><h2>같은 요청의 실제 출력</h2><div class="request" id="n8n-request"><label>${esc(normal.requestId)}</label><p>${esc(review.query)}</p></div><div class="result" id="n8n-plan"><span class="pill">승인 원장 · CSV 일치</span><h3>${esc(plan.courseTitle)}</h3><p>${esc(plan.workerId)} · ${plan.hours}시간 · ${esc(plan.selectionMode)}</p><p class="small">교육계획 확정 · 이수 / 자격 취득 처리 없음</p></div><div class="sources" id="n8n-evidence">근거 ${plan.evidenceIds.map(esc).join(' · ')}<br>모델 ${esc(plan.modelId||'호출 없음')}</div><p class="note">입력은 Webhook의 합성 교육 요청입니다. 출력은 승인 계획 JSON과 CSV입니다. 외부 HRIS·LMS·SaaS 연계는 포함하지 않습니다.</p></article></div><table class="table" id="n8n-cases"><thead><tr><th>실제 실행 사례</th><th>종료 상태</th><th>저장 변화</th></tr></thead><tbody>${data.cases.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.finalState)} / ${esc(c.status)}</td><td>추가 ${c.planCountAfter-c.planCountBefore}건</td></tr>`).join('')}</tbody></table>`;
}
try{await (view==='n8n'?n8n():comparison());}catch(e){$('content').innerHTML=`<p class="error">${esc(e.message)}</p>`;}

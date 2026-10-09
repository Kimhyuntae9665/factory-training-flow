const API = '/api/learning/';
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function download(filename, content, type) { const url = URL.createObjectURL(new Blob([content], { type })); const a = element('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
async function api(path, input) { const response = await fetch(API + path, input ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) } : {}); const data = await response.json(); if (!response.ok) { const error = new Error(data.error?.message || data.message || '교육 API 요청에 실패했습니다.'); error.code = data.error?.code || data.code; throw error; } return data; }
export async function initLearningUI({ getSimulationSummary } = {}) {
  const panel = document.querySelector('#learning-panel'); if (!panel) return;
  const find = id => panel.querySelector('#learning-' + id);
  const workerSelect = find('worker'), progress = find('progress'), result = find('review-result');
  let contextData, activeReview, working = false;
  function setBusy(value) { working = value; find('review').disabled = value; if (find('reset')) find('reset').disabled = value; find('worker').disabled = value; find('scope').disabled = value; find('query').disabled = value; find('approve').disabled = value || activeReview?.state !== 'awaiting_approval'; find('reject').disabled = value || activeReview?.state !== 'awaiting_approval'; }
  function message(node, text, error = false) { node.textContent = text; node.classList.toggle('learning-error', error); }
  function renderWorker() { const worker = contextData?.roster.find(item => item.workerId === workerSelect.value); const box = find('worker-context'); box.replaceChildren(); if (!worker) return; box.append(element('p', `현재 역할: ${worker.role}`), element('p', `현재 자격: ${worker.qualifications.join(', ') || '없음'}`), element('p', `기이수 과정: ${worker.completedCourses.join(', ') || '없음'}`)); }
  function renderDocs(target, docs, columns = false) { const wrapper = element('div', undefined, columns ? 'learning-evidence-grid' : 'learning-document-list'); for (const doc of docs) { const box = element('div', undefined, 'learning-source'); box.append(element('strong', doc.title), element('p', `${doc.id} · v${doc.version} · ${doc.section} · ${doc.status === 'current' ? '현행' : '구버전 제외'}`, 'learning-meta'), element('p', doc.text)); wrapper.append(box); } target.append(wrapper); }
  function renderReview(review) {
    result.replaceChildren();
    const meta = element('div', undefined, 'learning-review-meta');
    meta.append(element('p', `요청 ${review.requestId}`, 'learning-muted'), element('p', `${review.worker.displayName} (${review.worker.workerId}) · 현재 자격 ${review.worker.qualifications.join(', ') || '없음'}`)); result.append(meta);
    if (review.proposal) { const heading = element('div', undefined, 'learning-proposal-heading'); heading.append(element('h3', `${review.proposal.title} · ${review.proposal.hours}시간`), element('p', `자격·현행 근거 코드 검증 통과 · 실제 LLM 응답 ${review.llmMs.toLocaleString()} ms (${review.llmModel})`, 'learning-success')); result.append(heading, element('p', review.proposal.reason)); }
    else result.append(element('p', `${review.code}: ${review.message}`, 'learning-error'), element('p', 'LLM 호출 없음 · 교육계획 저장 없음', 'learning-muted'));
    const evidenceIds = element('div', undefined, 'learning-evidence-ids');
    evidenceIds.append(element('p', `키워드 검색 후보: ${(review.retrievedEvidence || review.evidence).map(doc => doc.id).join(', ') || '없음'}`, 'learning-muted'), element('p', `LLM 선택 근거: ${review.proposal?.evidenceIds.join(', ') || '모델 호출 없음'}`, 'learning-muted')); result.append(evidenceIds);
    result.append(element('h4', review.proposal ? 'LLM이 선택하고 코드가 검증한 근거' : '검색 근거')); renderDocs(result, review.evidence, true);
    if (review.excludedOld?.length) result.append(element('p', `제외한 구버전: ${review.excludedOld.map(doc => `${doc.id} v${doc.version}`).join(', ')}`, 'learning-muted'));
    result.append(element('h4', '공정 참고 · 교육성과와 분리'));
    result.append(element('p', '현재 3D 공정 요약은 읽기 전용 참고입니다. 교육 추천에는 공정 생산량 효과 계수를 적용하지 않습니다.', 'learning-muted'));
    const simulation = review.currentSimulation;
    if (simulation) {
      const config = simulation.config || {};
      const baseline = simulation.baseline?.goodPairs ?? simulation.baselineGoodPairs ?? '미제공';
      const improved = simulation.improved?.goodPairs ?? simulation.improvedGoodPairs ?? '미제공';
      const box = element('div', undefined, 'learning-inset learning-simulation-summary');
      box.append(element('p', `선택 공정: ${simulation.selectedStation || '미제공'}`), element('p', `합성 양품 수량: 기준 ${baseline} → 변경 ${improved}`), element('p', `인원 ${config.manualWorkers ?? '미제공'} · 속도 ${config.pacePercent ?? '미제공'}% · 휴식 ${config.breakEveryMinutes ?? '미제공'}분마다 ${config.breakMinutes ?? '미제공'}분`));
      result.append(box);
    } else result.append(element('p', '공정 요약 없음 · 교육 검토는 독립 실행됩니다.', 'learning-muted'));
    find('evidence').disabled = false; setBusy(false);
  }
  async function renderPlans() { const data = await api('plans'); const box = find('plans'); box.replaceChildren(); if (!data.plans.length) box.append(element('p', '아직 승인된 교육계획이 없습니다.', 'learning-muted')); for (const plan of data.plans) { const row = element('div', undefined, 'learning-plan'); row.append(element('strong', `${plan.workerId} · ${plan.courseTitle}`), element('p', `${plan.hours}시간 · ${new Date(plan.plannedAt).toLocaleString('ko-KR')}`), element('p', '교육계획 확정 · 이수/자격 취득 아님'), element('p', `근거: ${plan.evidenceIds.join(', ')}`, 'learning-muted')); box.append(row); } }
  async function modelStatus() {
    const badge = find('model-status');
    try { const status = await api('status'); badge.textContent = status.reachable ? `로컬 ${status.model} 연결됨` : '로컬 모델 연결 안 됨'; badge.title = status.error?.message || status.endpoint; }
    catch (error) { badge.textContent = '모델 상태 재조회 실패'; badge.title = error.message; }
  }
  workerSelect.addEventListener('change', renderWorker);
  find('reset')?.addEventListener('click', () => {
    if (working) return; activeReview = null; find('scope').value = 'current'; find('query').value = '자재 투입과 라벨 확인을 익힐 교육을 계획해 주세요.'; workerSelect.selectedIndex = 0; renderWorker(); result.replaceChildren(element('p', '요청을 검토하면 과정·시간·현행 근거와 자격 검증 결과를 표시합니다.', 'learning-muted')); find('evidence').disabled = true; message(progress, '새 요청 준비 완료 · 저장된 원장은 유지됩니다.'); message(find('decision-status'), ''); setBusy(false);
  });
  find('form').addEventListener('submit', async event => {
    event.preventDefault(); if (working) return; activeReview = null; setBusy(true); find('evidence').disabled = true; message(find('decision-status'), ''); message(progress, '현행 문서 검색 → 로컬 모델 선택 → 규정 검증 중…');
    try { const currentSimulation = getSimulationSummary ? getSimulationSummary() : null; activeReview = await api('review', { requestId: crypto.randomUUID(), selectedWorkerId: workerSelect.value, query: find('query').value, policyScope: find('scope').value, currentSimulation }); renderReview(activeReview); message(progress, activeReview.state === 'blocked' ? activeReview.message : '검토 완료. 근거와 현재 자격을 확인한 후 결정해 주세요.', activeReview.state === 'blocked'); }
    catch (error) { activeReview = null; find('evidence').disabled = true; result.replaceChildren(element('p', `${error.code || 'ERROR'}: ${error.message}`, 'learning-error')); message(progress, '검토 실패 · 모델 대체 결과나 계획 저장 없음', true); setBusy(false); return; }
    void modelStatus();
  });
  for (const action of ['approve', 'reject']) find(action).addEventListener('click', async () => {
    if (working || activeReview?.state !== 'awaiting_approval') return; setBusy(true);
    try {
      const response = await api('decision', { requestId: activeReview.requestId, action }); activeReview = response.review;
      const confirmedMessage = action === 'approve' ? '승인됨 · 서버 원장에 교육계획 1건 저장. 이수·자격 취득 아님.' : '거절됨 · 교육계획을 저장하지 않았습니다.';
      message(find('decision-status'), confirmedMessage);
      try { await renderPlans(); }
      catch (error) { find('plans').replaceChildren(element('p', '원장 목록 재조회 실패 · 새로고침으로 저장된 원장을 다시 확인해 주세요.', 'learning-error')); message(find('decision-status'), `${confirmedMessage} 원장 목록 재조회에는 실패했습니다. 확정된 결정은 유지됩니다. 페이지를 새로고침해 원장을 다시 확인해 주세요. (${error.message})`, true); }
    }
    catch (error) { message(find('decision-status'), `${error.code || 'ERROR'}: ${error.message}`, true); }
    finally { setBusy(false); }
  });
  find('evidence').addEventListener('click', () => { if (activeReview) download('learning-review-evidence.json', JSON.stringify(activeReview, null, 2), 'application/json'); });
  find('export').addEventListener('click', async () => { try { const response = await fetch(API + 'export.csv'); if (!response.ok) throw new Error('원장 CSV를 읽을 수 없습니다.'); download('synthetic-learning-plans.csv', await response.text(), 'text/csv;charset=utf-8'); } catch (error) { message(find('decision-status'), error.message, true); } });
  try { contextData = await api('context'); workerSelect.replaceChildren(...contextData.roster.map(worker => { const option = element('option', `${worker.displayName} (${worker.workerId}) · ${worker.role}`); option.value = worker.workerId; return option; })); renderWorker(); const sources = find('sources'); sources.replaceChildren(); if (contextData.rawRosterCsv) sources.append(element('h4', '합성 원본 CSV'), element('pre', contextData.rawRosterCsv)); sources.append(element('h4', '표준화한 합성 작업자 원장'), element('p', contextData.normalization || '원본 값을 추정하지 않고 보존합니다.', 'learning-muted'), element('pre', JSON.stringify(contextData.roster, null, 2))); renderDocs(sources, contextData.documents); await Promise.all([modelStatus(), renderPlans()]); message(progress, '합성 원장 준비 완료 · 요청을 검토해 주세요.'); }
  catch (error) { message(progress, `교육 API 준비 실패: ${error.message}`, true); find('review').disabled = true; find('model-status').textContent = '교육 API 확인 필요'; }
  return { refreshPlans: renderPlans };
}

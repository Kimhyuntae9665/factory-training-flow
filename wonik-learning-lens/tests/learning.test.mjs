import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createLearningService, LearningError } from '../learning-service.js';
import { initLearningUI } from '../learning-ui.js';

const answer = { action: 'select', courseId: 'C-LOAD', evidenceIds: ['SOP-LOAD-2', 'QUAL-1', 'COURSE-LOAD-1'], reasonCode: 'REQUEST_MATCH' };
async function setup(customAnswer = answer, options = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'wonik-learning-test-'));
  const calls = [];
  const fetchImpl = async (url, init = {}) => { calls.push({ url, ...init }); return { ok: true, json: async () => url.endsWith('/models') ? { data: [{ id: 'Qwen3-4B-Q4_K_M' }] } : { choices: [{ finish_reason: 'stop', message: { content: typeof customAnswer === 'string' ? customAnswer : JSON.stringify(customAnswer) } }] } }; };
  const storagePath = join(dir, '.learning-state.json');
  return { dir, calls, storagePath, fetchImpl, service: createLearningService({ fetchImpl, storagePath, ...options }) };
}
const input = (extra = {}) => ({ requestId: randomUUID(), selectedWorkerId: 'SYN-101', query: '자재 투입 라벨 교육', policyScope: 'current', ...extra });

test('mock: LLM gets all current bodies and qualified course enums for semantic selection without keyword hits', async () => {
  const { service, calls } = await setup();
  const result = await service.review(input({ query: '상자에 붙은 이름이 맞는지 대조하는 법을 배우고 싶어요.', currentSimulation: { delta: 7, educationEffectModeled: false } }));
  assert.equal(result.state, 'awaiting_approval'); assert.equal(result.proposal.qualificationChecked, true); assert.equal(result.rules.effectsOnProduction, 'none');
  assert.equal(result.selectionMode, 'llm'); assert.equal(result.modelId, 'Qwen3-4B-Q4_K_M'); assert.equal(result.retrieval, 'all-current-documents');
  const sent = JSON.parse(calls.find(call => call.url.endsWith('/chat/completions')).body);
  assert.deepEqual(sent.response_format.json_schema.schema.properties.courseId.enum, ['C-LOAD', 'AMBIGUOUS', 'NO_MATCH']);
  assert.deepEqual(sent.response_format.json_schema.schema.properties.action.enum, ['select', 'clarify', 'no_match']);
  const user = JSON.parse(sent.messages[1].content);
  assert.equal(user.selectedWorker.workerId, 'SYN-101'); assert.ok(user.retrievedDocuments.every(doc => doc.status === 'current')); assert.ok(user.retrievedDocuments.some(doc => doc.text.includes('자재 라벨'))); assert.equal(user.currentSimulation, undefined); assert.equal(user.roster, undefined);
  assert.equal(user.retrievedDocuments.length, 7); assert.ok(user.retrievedDocuments.some(doc => doc.id === 'COURSE-MAINT-1'));
});
test('rules: one exact match needs no LLM; multiple candidates require clarification; no keywords abstains', async () => {
  const { service, calls } = await setup();
  const request = input({ mode: 'rules' }); const result = await service.review(request);
  assert.equal(result.state, 'awaiting_approval'); assert.equal(result.proposal.id, 'C-LOAD'); assert.equal(result.llmStatus, 'not_called'); assert.equal(result.modelId, null); assert.equal(result.selectionMode, 'rules');
  const multiple = await service.review(input({ mode: 'rules', selectedWorkerId: 'SYN-103', query: '자재 투입 또는 품질 검사 교육' }));
  assert.equal(multiple.code, 'AMBIGUOUS_REQUEST'); assert.equal(multiple.state, 'blocked'); assert.equal(multiple.proposal, null);
  const none = await service.review(input({ mode: 'rules', query: '상자에 붙은 이름이 맞는지 대조하는 법을 배우고 싶어요.' }));
  assert.equal(none.code, 'NO_EVIDENCE'); assert.equal(calls.length, 0);
  const approved = await service.decision({ requestId: request.requestId, action: 'approve' }); assert.equal(approved.plan.selectionMode, 'rules'); assert.equal(approved.plan.modelId, null);
});
test('mock: LLM may choose any eligible course and uses semantic action with required evidence', async () => {
  const selected = { action: 'select', courseId: 'C-QUALITY', evidenceIds: ['SOP-QUALITY-1', 'QUAL-1', 'COURSE-QUALITY-1'], reasonCode: 'REQUEST_MATCH' };
  const { service, calls } = await setup(selected);
  const result = await service.review(input({ selectedWorkerId: 'SYN-103', query: '정해진 수치와 실제 숫자가 다를 때 남기는 법을 익히고 싶어요.' }));
  assert.equal(result.proposal.id, 'C-QUALITY');
  const sent = JSON.parse(calls.find(call => call.url.endsWith('/chat/completions')).body);
  assert.deepEqual(sent.response_format.json_schema.schema.properties.courseId.enum, ['C-LOAD', 'C-QUALITY', 'C-MAINT', 'AMBIGUOUS', 'NO_MATCH']);
  assert.deepEqual(result.evidence.map(doc => doc.id), selected.evidenceIds);
});
test('mock: no-match and ambiguity are persisted model abstentions that cannot be approved', async () => {
  for (const [action, courseId, reasonCode, code] of [['no_match', 'NO_MATCH', 'NO_RELEVANT_COURSE', 'NO_MATCH'], ['clarify', 'AMBIGUOUS', 'REQUEST_AMBIGUOUS', 'AMBIGUOUS_REQUEST']]) {
    const { service, calls } = await setup({ action, courseId, reasonCode, evidenceIds: [] }); const request = input({ query: action === 'no_match' ? '맛있는 저녁을 추천해 주세요.' : '업무 교육을 하고 싶어요.' });
    const result = await service.review(request); assert.equal(result.state, 'blocked'); assert.equal(result.code, code); assert.equal(result.llmStatus, 'ready'); assert.equal(result.proposal, null); assert.deepEqual(result.evidence, []);
    assert.deepEqual(await service.review(request), result); assert.equal(calls.length, 2); await assert.rejects(() => service.decision({ requestId: request.requestId, action: 'approve' }), error => error.code === 'REVIEW_BLOCKED'); assert.equal((await service.plans()).plans.length, 0);
  }
});
test('mock: approval is concurrent-idempotent, persisted, and never grants qualification', async () => {
  const { service, storagePath, fetchImpl } = await setup(); const request = input(); await service.review(request);
  const decisions = await Promise.all([service.decision({ requestId: request.requestId, action: 'approve' }), service.decision({ requestId: request.requestId, action: 'approve' })]);
  assert.equal(decisions.filter(item => item.idempotent).length, 1); assert.equal((await service.plans()).plans.length, 1);
  const reopened = createLearningService({ storagePath, fetchImpl }); const saved = await reopened.plans(); assert.equal(saved.plans.length, 1); assert.equal(saved.plans[0].qualificationGranted, false);
  assert.equal(saved.plans[0].selectionMode, 'llm'); assert.equal(saved.plans[0].modelId, 'Qwen3-4B-Q4_K_M');
  await assert.rejects(() => service.decision({ requestId: request.requestId, action: 'reject' }), error => error.status === 409);
  assert.match(await service.exportCsv(), /education_plan_confirmed/); assert.equal(JSON.parse(await readFile(storagePath, 'utf8')).plans.length, 1);
});
test('mock: rejection produces zero plans and opposite repeat conflicts', async () => {
  const { service } = await setup(); const request = input(); await service.review(request); await service.decision({ requestId: request.requestId, action: 'reject' });
  assert.equal((await service.plans()).plans.length, 0); assert.equal((await service.decision({ requestId: request.requestId, action: 'reject' })).idempotent, true); await assert.rejects(() => service.decision({ requestId: request.requestId, action: 'approve' }), error => error.status === 409);
});
test('mock: missing evidence and conflict block without any model request', async () => {
  for (const policyScope of ['missing', 'conflict']) { const { service, calls } = await setup(); const request = input({ policyScope }); const result = await service.review(request); assert.equal(result.state, 'blocked'); assert.equal(result.llmStatus, 'not_called'); assert.equal(calls.length, 0); await assert.rejects(() => service.decision({ requestId: request.requestId, action: 'approve' }), error => error.code === 'REVIEW_BLOCKED'); }
});
test('mock: missing worker qualification blocks before model when no courses are eligible', async () => { const { service, calls } = await setup(); const result = await service.review(input({ selectedWorkerId: 'SYN-104', query: '품질 검사 기록 교육' })); assert.equal(result.code, 'QUALIFICATION_GAP'); assert.equal(calls.length, 0); });
test('mock: qualification and completed exclusions stay out of schema and fail post-response validation', async () => {
  const disallowed = { action: 'select', courseId: 'C-MAINT', evidenceIds: ['SOP-MAINT-1', 'QUAL-1', 'COURSE-MAINT-1'], reasonCode: 'REQUEST_MATCH' };
  const { service, calls } = await setup(disallowed); await assert.rejects(() => service.review(input({ selectedWorkerId: 'SYN-102', query: '설비 점검 교육' })), error => error.code === 'LLM_INVALID_SELECTION');
  const sent = JSON.parse(calls.find(call => call.url.endsWith('/chat/completions')).body); assert.ok(!sent.response_format.json_schema.schema.properties.courseId.enum.includes('C-MAINT'));
  const roster = [{ workerId: 'SYN-103', displayName: '합성 C', qualifications: ['SAFE-BASE', 'EQUIP-BASE'], completedCourses: ['C-LOAD'] }];
  const completed = await setup(answer, { roster }); await assert.rejects(() => completed.service.review(input({ selectedWorkerId: 'SYN-103' })), error => error.code === 'LLM_INVALID_SELECTION');
  assert.equal((await service.plans()).plans.length, 0); assert.equal((await completed.service.plans()).plans.length, 0);
});
test('mock: model invalid course, stale evidence, omitted required evidence, invalid JSON fail without fallback', async () => {
  for (const value of [{ ...answer, courseId: 'C-UNKNOWN' }, { ...answer, evidenceIds: ['SOP-LOAD-1', 'QUAL-1', 'COURSE-LOAD-1'] }, { ...answer, evidenceIds: ['COURSE-LOAD-1'] }, { ...answer, action: 'no_match' }, { action: 'clarify', courseId: 'AMBIGUOUS', evidenceIds: ['QUAL-1'], reasonCode: 'REQUEST_AMBIGUOUS' }, 'not-json', 'null']) { const { service } = await setup(value); await assert.rejects(() => service.review(input()), error => error instanceof LearningError && error.status === 502); assert.equal((await service.plans()).plans.length, 0); }
});
test('mock: same request is stable, changed payload conflicts, invalid ID/text rejected', async () => {
  const { service, calls } = await setup(); const request = input(); const first = await service.review(request); assert.deepEqual(await service.review(request), first); assert.equal(calls.length, 2); await assert.rejects(() => service.review({ ...request, query: '다른 내용' }), error => error.code === 'REQUEST_CONFLICT');
  await assert.rejects(() => service.review({ ...request, mode: 'rules' }), error => error.code === 'REQUEST_CONFLICT');
  await assert.rejects(() => service.review(input({ requestId: 'x' })), error => error.code === 'INVALID_REQUEST_ID'); await assert.rejects(() => service.review(input({ query: 'x'.repeat(601) })), error => error.code === 'INVALID_QUERY');
  await assert.rejects(() => service.review(input({ mode: 'unknown' })), error => error.code === 'INVALID_MODE');
});
test('local endpoint only; unavailable model surfaced with no synthetic success', async () => {
  assert.throws(() => createLearningService({ endpoint: 'https://outside.example/v1' }), error => error.code === 'INVALID_ENDPOINT'); const { service } = await setup(answer, { fetchImpl: async () => { throw new Error('offline'); } }); assert.equal((await service.status()).reachable, false); await assert.rejects(() => service.review(input()), error => error.code === 'LLM_UNAVAILABLE'); assert.equal((await service.plans()).plans.length, 0);
});

// A minimal DOM/event adapter exercises UI state without pretending to be a browser rendering test.
class UiNode {
  constructor() { this.children = []; this.listeners = {}; this._text = ''; this.disabled = false; this.value = ''; this.classList = { toggle() {} }; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(' '); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  addEventListener(event, listener) { this.listeners[event] = listener; }
  async emit(event) { return this.listeners[event]?.({ preventDefault() {} }); }
}
async function setupUi(t, { failStatusRefresh = false, failPlanRefresh = false, deferReview = false } = {}) {
  const previous = { document: globalThis.document, fetch: globalThis.fetch };
  t.after(() => { globalThis.document = previous.document; globalThis.fetch = previous.fetch; });
  const ids = ['worker', 'progress', 'review-result', 'review', 'reset', 'scope', 'mode', 'query', 'approve', 'reject', 'evidence', 'decision-status', 'plans', 'model-status', 'form', 'export', 'sources', 'worker-context'];
  const nodes = Object.fromEntries(ids.map(id => [id, new UiNode()]));
  nodes.worker.value = 'SYN-101'; nodes.query.value = '자재 투입 교육'; nodes.scope.value = 'current';
  const panel = { querySelector: selector => nodes[selector.replace('#learning-', '')] };
  globalThis.document = { querySelector: () => panel, createElement: () => new UiNode() };
  const worker = { workerId: 'SYN-101', displayName: '합성 작업자 A', role: '자재 투입', qualifications: [], completedCourses: [] };
  const review = { requestId: randomUUID(), worker, state: 'awaiting_approval', evidence: [], retrievedEvidence: [], excludedOld: [], proposal: { title: '자재 투입 기초', hours: 2, evidenceIds: [], reason: '검증 통과' }, llmMs: 23, llmModel: 'mock-Qwen' };
  const counts = {}, requests = [], savedPlans = []; let failReview = false, releaseReview;
  const reviewGate = deferReview ? new Promise(resolve => { releaseReview = resolve; }) : null;
  globalThis.fetch = async (url, init = {}) => {
    const path = url.slice(url.lastIndexOf('/') + 1); counts[path] = (counts[path] || 0) + 1;
    if (init.body) requests.push({ path, input: JSON.parse(init.body) });
    if ((path === 'status' && failStatusRefresh && counts.status > 1) || (path === 'plans' && failPlanRefresh && counts.plans > 1) || (path === 'review' && failReview)) throw new Error('simulated read failure');
    if (path === 'review' && reviewGate) await reviewGate;
    const mode = init.body ? JSON.parse(init.body).mode : 'llm';
    if (path === 'decision' && JSON.parse(init.body).action === 'approve') savedPlans.push({ workerId: worker.workerId, courseTitle: review.proposal.title, hours: review.proposal.hours, plannedAt: '2026-10-10T00:00:00Z', evidenceIds: [] });
    const data = path === 'context' ? { roster: [worker], documents: [] } : path === 'status' ? { reachable: true, model: 'mock-Qwen', endpoint: 'loopback' } : path === 'plans' ? { plans: structuredClone(savedPlans) } : path === 'review' ? { ...structuredClone(review), selectionMode: mode, llmStatus: mode === 'rules' ? 'not_called' : 'ready' } : { review: { ...structuredClone(review), state: 'approved', decision: { action: 'approve' } } };
    return { ok: true, json: async () => data };
  };
  await initLearningUI();
  return { nodes, requests, releaseReview, failNextReview() { failReview = true; } };
}

test('UI: mode switch sends rules baseline and labels code validation without claiming a model call', async t => {
  const { nodes, requests } = await setupUi(t); assert.equal(nodes.mode.value, 'llm'); nodes.mode.value = 'rules';
  await nodes.form.emit('submit'); assert.equal(requests.find(item => item.path === 'review').input.mode, 'rules'); assert.match(nodes['review-result'].textContent, /규칙 기준선/); assert.match(nodes['review-result'].textContent, /LLM 호출 없음/); assert.match(nodes['review-result'].textContent, /코드 검증/); assert.doesNotMatch(nodes['review-result'].textContent, /실제 LLM 응답/);
  await nodes.reset.emit('click'); assert.equal(nodes.mode.value, 'llm'); assert.equal(nodes.approve.disabled, true); assert.equal(nodes.evidence.disabled, true);
});

test('UI: edits to any request field invalidate pending approval and evidence without changing the ledger', async t => {
  const { nodes, requests } = await setupUi(t);
  for (const [field, event, value] of [['worker', 'change', 'SYN-102'], ['scope', 'change', 'missing'], ['mode', 'change', 'rules'], ['query', 'input', '품질 검사 교육']]) {
    await nodes.form.emit('submit'); assert.equal(nodes.approve.disabled, false); assert.equal(nodes.evidence.disabled, false);
    const ledger = nodes.plans.textContent; nodes[field].value = value; await nodes[field].emit(event);
    assert.equal(nodes.approve.disabled, true); assert.equal(nodes.reject.disabled, true); assert.equal(nodes.evidence.disabled, true); assert.match(nodes['review-result'].textContent, /다시 검토/);
    await nodes.approve.emit('click'); await nodes.reject.emit('click'); assert.equal(requests.filter(item => item.path === 'decision').length, 0); assert.equal(nodes.plans.textContent, ledger);
  }
  await nodes.form.emit('submit'); await nodes.approve.emit('click'); const decisions = requests.filter(item => item.path === 'decision').length; const finishedLedger = nodes.plans.textContent;
  assert.match(finishedLedger, /교육계획 확정/); assert.match(finishedLedger, /자재 투입 기초/);
  nodes.query.value = '새 요청'; await nodes.query.emit('input'); await nodes.approve.emit('click'); assert.equal(requests.filter(item => item.path === 'decision').length, decisions); assert.equal(nodes.plans.textContent, finishedLedger);
});

test('UI: in-flight review locks inputs and cannot install a response after an input revision', async t => {
  const { nodes, requests, releaseReview } = await setupUi(t, { deferReview: true });
  const submitted = nodes.form.emit('submit');
  for (const field of ['worker', 'scope', 'mode', 'query']) assert.equal(nodes[field].disabled, true);
  nodes.query.value = '전혀 다른 요청'; await nodes.query.emit('input'); releaseReview(); await submitted;
  assert.match(nodes['review-result'].textContent, /입력이 변경/); assert.doesNotMatch(nodes['review-result'].textContent, /자재 투입 기초/); assert.equal(nodes.approve.disabled, true); assert.equal(nodes.reject.disabled, true); assert.equal(nodes.evidence.disabled, true); assert.equal(nodes.query.disabled, false);
  await nodes.approve.emit('click'); assert.equal(requests.filter(item => item.path === 'decision').length, 0);
});
test('UI: successful review survives status-refresh failure; subsequent failed review clears approval and evidence', async t => {
  const { nodes, failNextReview } = await setupUi(t, { failStatusRefresh: true });
  await nodes.form.emit('submit'); await new Promise(resolve => setImmediate(resolve));
  assert.match(nodes['review-result'].textContent, /자재 투입 기초/); assert.equal(nodes.approve.disabled, false); assert.equal(nodes.reject.disabled, false); assert.equal(nodes.evidence.disabled, false); assert.match(nodes['model-status'].textContent, /재조회 실패/);
  failNextReview(); await nodes.form.emit('submit');
  assert.match(nodes['review-result'].textContent, /simulated read failure/); assert.equal(nodes.approve.disabled, true); assert.equal(nodes.reject.disabled, true); assert.equal(nodes.evidence.disabled, true);
});
test('UI: confirmed approval remains locked when plan-list refresh fails and gives reload guidance', async t => {
  const { nodes } = await setupUi(t, { failPlanRefresh: true });
  await nodes.form.emit('submit'); await nodes.approve.emit('click');
  assert.match(nodes['decision-status'].textContent, /승인됨/); assert.match(nodes['decision-status'].textContent, /확정된 결정은 유지/); assert.match(nodes['decision-status'].textContent, /새로고침/); assert.match(nodes.plans.textContent, /재조회 실패/); assert.equal(nodes.approve.disabled, true); assert.equal(nodes.reject.disabled, true);
});

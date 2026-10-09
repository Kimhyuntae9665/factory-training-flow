import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createLearningService, LearningError } from '../learning-service.js';
import { initLearningUI } from '../learning-ui.js';

const answer = { courseId: 'C-LOAD', evidenceIds: ['SOP-LOAD-2', 'QUAL-1', 'COURSE-LOAD-1'], reasonCode: 'REQUEST_MATCH' };
async function setup(customAnswer = answer, options = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'wonik-learning-test-'));
  const calls = [];
  const fetchImpl = async (url, init = {}) => { calls.push({ url, ...init }); return { ok: true, json: async () => url.endsWith('/models') ? { data: [{ id: 'Qwen3-4B-Q4_K_M' }] } : { choices: [{ finish_reason: 'stop', message: { content: typeof customAnswer === 'string' ? customAnswer : JSON.stringify(customAnswer) } }] } }; };
  const storagePath = join(dir, '.learning-state.json');
  return { dir, calls, storagePath, fetchImpl, service: createLearningService({ fetchImpl, storagePath, ...options }) };
}
const input = (extra = {}) => ({ requestId: randomUUID(), selectedWorkerId: 'SYN-101', query: '자재 투입 라벨 교육', policyScope: 'current', ...extra });

test('mock: retrieval sends actual current bodies and selected synthetic worker with schema enums', async () => {
  const { service, calls } = await setup();
  const result = await service.review(input({ currentSimulation: { delta: 7, educationEffectModeled: false } }));
  assert.equal(result.state, 'awaiting_approval'); assert.equal(result.proposal.qualificationChecked, true); assert.equal(result.rules.effectsOnProduction, 'none');
  const sent = JSON.parse(calls.find(call => call.url.endsWith('/chat/completions')).body);
  assert.deepEqual(sent.response_format.json_schema.schema.properties.courseId.enum, ['C-LOAD']);
  const user = JSON.parse(sent.messages[1].content);
  assert.equal(user.selectedWorker.workerId, 'SYN-101'); assert.ok(user.retrievedDocuments.every(doc => doc.status === 'current')); assert.ok(user.retrievedDocuments.some(doc => doc.text.includes('자재 라벨'))); assert.equal(user.currentSimulation, undefined); assert.equal(user.roster, undefined);
});
test('mock: approval is concurrent-idempotent, persisted, and never grants qualification', async () => {
  const { service, storagePath, fetchImpl } = await setup(); const request = input(); await service.review(request);
  const decisions = await Promise.all([service.decision({ requestId: request.requestId, action: 'approve' }), service.decision({ requestId: request.requestId, action: 'approve' })]);
  assert.equal(decisions.filter(item => item.idempotent).length, 1); assert.equal((await service.plans()).plans.length, 1);
  const reopened = createLearningService({ storagePath, fetchImpl }); const saved = await reopened.plans(); assert.equal(saved.plans.length, 1); assert.equal(saved.plans[0].qualificationGranted, false);
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
test('mock: missing worker qualification blocks before model', async () => { const { service, calls } = await setup(); const result = await service.review(input({ selectedWorkerId: 'SYN-104', query: '품질 검사 기록 교육' })); assert.equal(result.code, 'QUALIFICATION_GAP'); assert.equal(calls.length, 0); });
test('mock: model invalid course, stale evidence, omitted required evidence, invalid JSON fail without fallback', async () => {
  for (const value of [{ ...answer, courseId: 'C-UNKNOWN' }, { ...answer, evidenceIds: ['SOP-LOAD-1', 'QUAL-1', 'COURSE-LOAD-1'] }, { ...answer, evidenceIds: ['COURSE-LOAD-1'] }, 'not-json']) { const { service } = await setup(value); await assert.rejects(() => service.review(input()), error => error instanceof LearningError && error.status === 502); assert.equal((await service.plans()).plans.length, 0); }
});
test('mock: same request is stable, changed payload conflicts, invalid ID/text rejected', async () => {
  const { service, calls } = await setup(); const request = input(); const first = await service.review(request); assert.deepEqual(await service.review(request), first); assert.equal(calls.length, 2); await assert.rejects(() => service.review({ ...request, query: '다른 내용' }), error => error.code === 'REQUEST_CONFLICT');
  await assert.rejects(() => service.review(input({ requestId: 'x' })), error => error.code === 'INVALID_REQUEST_ID'); await assert.rejects(() => service.review(input({ query: 'x'.repeat(601) })), error => error.code === 'INVALID_QUERY');
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
async function setupUi(t, { failStatusRefresh = false, failPlanRefresh = false } = {}) {
  const previous = { document: globalThis.document, fetch: globalThis.fetch };
  t.after(() => { globalThis.document = previous.document; globalThis.fetch = previous.fetch; });
  const ids = ['worker', 'progress', 'review-result', 'review', 'reset', 'scope', 'query', 'approve', 'reject', 'evidence', 'decision-status', 'plans', 'model-status', 'form', 'export', 'sources', 'worker-context'];
  const nodes = Object.fromEntries(ids.map(id => [id, new UiNode()]));
  nodes.worker.value = 'SYN-101'; nodes.query.value = '자재 투입 교육'; nodes.scope.value = 'current';
  const panel = { querySelector: selector => nodes[selector.replace('#learning-', '')] };
  globalThis.document = { querySelector: () => panel, createElement: () => new UiNode() };
  const worker = { workerId: 'SYN-101', displayName: '합성 작업자 A', role: '자재 투입', qualifications: [], completedCourses: [] };
  const review = { requestId: randomUUID(), worker, state: 'awaiting_approval', evidence: [], retrievedEvidence: [], excludedOld: [], proposal: { title: '자재 투입 기초', hours: 2, evidenceIds: [], reason: '검증 통과' }, llmMs: 23, llmModel: 'mock-Qwen' };
  const counts = {}; let failReview = false;
  globalThis.fetch = async (url) => {
    const path = url.slice(url.lastIndexOf('/') + 1); counts[path] = (counts[path] || 0) + 1;
    if ((path === 'status' && failStatusRefresh && counts.status > 1) || (path === 'plans' && failPlanRefresh && counts.plans > 1) || (path === 'review' && failReview)) throw new Error('simulated read failure');
    const data = path === 'context' ? { roster: [worker], documents: [] } : path === 'status' ? { reachable: true, model: 'mock-Qwen', endpoint: 'loopback' } : path === 'plans' ? { plans: [] } : path === 'review' ? structuredClone(review) : { review: { ...structuredClone(review), state: 'approved', decision: { action: 'approve' } } };
    return { ok: true, json: async () => data };
  };
  await initLearningUI();
  return { nodes, failNextReview() { failReview = true; } };
}
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

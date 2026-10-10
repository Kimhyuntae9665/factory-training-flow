import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { randomUUID, createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLearningService } from '../learning-service.js';

const root = dirname(fileURLToPath(import.meta.url));
const input = JSON.parse(await readFile(resolve(root, 'cases.json'), 'utf8'));
const out = resolve(process.env.EVAL_OUT || resolve(root, '../evidence/comparison-20261010-final'));
const endpoint = process.env.LINE_LENS_LLM_URL || 'http://127.0.0.1:8787/v1';
await mkdir(out, { recursive: true });
const selected = process.env.EVAL_IDS ? new Set(process.env.EVAL_IDS.split(',')) : null;
const modes = (process.env.EVAL_MODES || 'rules,llm').split(',');
const cases = input.cases.filter(item => !selected || selected.has(item.id));
const resultPath = resolve(out, 'results.json');
let previous = null;
try { previous = JSON.parse(await readFile(resultPath, 'utf8')); } catch (e) { if (e.code !== 'ENOENT') throw e; }
let results = previous?.results || [];
const startedAt = new Date().toISOString();
function acceptable(test, review) {
  if (test.expected.startsWith('C-')) return review.state === 'awaiting_approval' && review.proposal?.id === test.expected;
  if (test.expected === 'AMBIGUOUS') return review.state === 'blocked' && review.code === 'AMBIGUOUS_REQUEST';
  if (test.expected === 'NO_MATCH') return review.state === 'blocked' && ['NO_EVIDENCE','NO_MATCH','NO_RELEVANT_COURSE'].includes(review.code);
  return review.state === 'blocked';
}
const services = Object.fromEntries(modes.map(mode => [mode, createLearningService({ endpoint, timeoutMs: 300000, storagePath: resolve(out, `.state-${mode}.json`) })]));
// Readiness failures are setup errors, not recommendation-quality samples.
if (services.llm) {
  const deadline = Date.now() + 180000;
  let available;
  do {
    available = await services.llm.status();
    if (available.reachable) break;
    if (Date.now() >= deadline) throw new Error('Model not ready; no quality comparison was started.');
    await new Promise(resolve => setTimeout(resolve, 1000));
  } while (!available.reachable);
}
const context = services[modes[0]].context();
const hash = async path => createHash('sha256').update(await readFile(resolve(root,path))).digest('hex');
const fingerprint = {casesSha256:await hash('cases.json'),codeSha256:await hash('../learning-service.js'),documentsSha256:await hash('../fixtures/learning-documents.json'),rosterSha256:await hash('../fixtures/learning-roster.csv'),endpoint,model:'Qwen3-4B-Q4_K_M'};
if(previous && Object.entries(fingerprint).some(([key,value])=>previous[key]!==value)) throw new Error('Existing evaluation provenance differs. Preserve it and use a new EVAL_OUT folder.');
const manifest = previous || {date:startedAt.slice(0,10),startedAt,executionHost:process.env.COMPUTERNAME || 'unknown',...fingerprint,synthetic:true,boundary:input.boundary,results};
if(previous) manifest.resumedAt = startedAt;
for (const test of cases) for (const mode of modes) {
  if (results.some(r => r.id === test.id && r.mode === mode)) continue;
  const requestId = randomUUID();
  const t = performance.now();
  let review, error = null;
  try { review = await services[mode].review({ requestId, mode, selectedWorkerId:test.worker, query:test.query, policyScope:test.policyScope || 'current' }); }
  catch (e) { error = {code:e.code || 'ERROR',message:e.message,...(Number.isFinite(e.llmMs)?{llmMs:Math.round(e.llmMs)}:{})}; }
  const course = context.courses.find(c => c.id === review?.proposal?.id);
  const evidenceValid = !!course && course.evidenceIds.every(id=>review.proposal.evidenceIds.includes(id)) && review.proposal.evidenceIds.every(id=>context.documents.some(d=>d.id===id && d.status==='current'));
  const attemptedModelCall = review?.llmStatus==='ready' || Number.isFinite(error?.llmMs);
  const row = {id:test.id,category:test.category,mode,worker:test.worker,query:test.query,expected:test.expected,requestId,state:review?.state || 'error',code:review?.code || null,actualCourse:review?.proposal?.id || null,llmStatus:review?.llmStatus || (attemptedModelCall?'failed':'not_called'),attemptedModelCall,llmMs:review?.llmMs || error?.llmMs || 0,elapsedMs:Math.round(performance.now()-t),correct:error ? false : acceptable(test,review),evidenceValid:course ? evidenceValid : null,error,review};
  results.push(row);
  await writeFile(resultPath, JSON.stringify(manifest,null,2));
  console.log(JSON.stringify({id:row.id,mode,state:row.state,actualCourse:row.actualCourse,code:row.code,correct:row.correct,llmMs:row.llmMs,error}));
}
manifest.completedAt = new Date().toISOString();
manifest.summary = Object.fromEntries(modes.map(mode => {
  const rows = results.filter(r=>r.mode===mode);
  const calls = rows.filter(r=>r.attemptedModelCall ?? (r.llmStatus==='ready' || r.llmMs>0));
  const successful = calls.filter(r=>r.llmStatus==='ready');
  const byCategory = Object.fromEntries([...new Set(input.cases.map(c=>c.category))].map(category=>{const c=rows.filter(r=>r.category===category);return [category,{total:c.length,correct:c.filter(r=>r.correct).length}];}));
  return [mode,{total:rows.length,correct:rows.filter(r=>r.correct).length,errors:rows.filter(r=>r.error).length,selected:rows.filter(r=>r.state==='awaiting_approval').length,invalidSelectedEvidence:rows.filter(r=>r.evidenceValid===false).length,modelCalls:calls.length,successfulModelCalls:successful.length,medianModelMs:successful.length ? ((sorted)=> (sorted[Math.floor((sorted.length-1)/2)].llmMs+sorted[Math.floor(sorted.length/2)].llmMs)/2)([...successful].sort((a,b)=>a.llmMs-b.llmMs)) : 0,byCategory}];
}));
await writeFile(resultPath, JSON.stringify(manifest,null,2));
console.log(JSON.stringify(manifest.summary));

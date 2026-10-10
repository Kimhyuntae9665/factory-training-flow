# 합성 교육계획 API

공고의 교육 분야 AI 과제 발굴·LLM 자동화 운영·HR 데이터 정제 업무를 위해 교육 요청의 근거 검토와 교육계획 기록을 구현했습니다. 직원·SOP·과정·자격은 모두 합성입니다.

현재 검수 앱은 `http://127.0.0.1:8798`, 모델은 `http://127.0.0.1:8797/v1`의 `Qwen3-4B-Q4_K_M`입니다. `PORT=8798`, `LINE_LENS_LLM_URL=http://127.0.0.1:8797/v1`을 지정합니다. 서버 코드 기본값은 8786/8787, 서비스 생성자의 기본 모델 주소는 8767/v1입니다.

## 입출력

| HTTP | 경로 | 응답 |
|---|---|---|
| GET | `/api/learning/status` | 모델의 정확 ID 연결 상태 |
| GET | `/api/learning/context` | 합성 CSV·표준화 원장·문서·과정·자료 경계 |
| POST | `/api/learning/review` | `awaiting_approval`과 제안 또는 `blocked`와 코드 |
| POST | `/api/learning/decision` | 확정 검토, 승인 계획 또는 `null`, `idempotent` |
| GET | `/api/learning/plans` | 파일 원장의 합성 교육계획 목록 |
| GET | `/api/learning/export.csv` | UTF-8 BOM CSV |

POST는 `Content-Type: application/json`을 사용하며 본문 제한은 16KB입니다. 서버는 로컬 Host/Origin만 허용합니다.

```json
{
  "requestId": "8375d184-3d06-41af-bc37-75c388e0f79d",
  "selectedWorkerId": "SYN-101",
  "query": "새 직원이 물건을 넣을 때 바코드를 잘못 읽어요. 무엇부터 익히면 좋을까요?",
  "policyScope": "current",
  "mode": "llm"
}
```

`requestId`는 UUID, `selectedWorkerId`는 SYN-101~104, `query`는 1~600자입니다. `policyScope`는 `current`·`missing`·`conflict`이며 `현행`·`자료없음` 별칭을 정규화합니다. `mode`는 `rules` 또는 `llm`, 생략하면 `llm`입니다. 선택적인 `currentSimulation`은 읽기 전용 화면 참고이며 모델에 전송하거나 교육성과 계산에 사용하지 않습니다.

요청 ID의 멱등성 서명은 작업자·정규화 요청·자료 범위·mode를 포함합니다. 동일 ID와 동일 서명은 저장된 검토를 반환하며 mode를 포함한 내용 변경은 `REQUEST_CONFLICT`/409입니다. 새 조건 비교에는 새 UUID를 사용합니다.

## 선택과 코드 검증

두 방식 모두 구버전을 제외하고 선수 자격·기이수·필수 근거를 확인합니다. 같은 문서 키에 복수 현행 문서가 있으면 `POLICY_CONFLICT`로 차단합니다. 이는 문서 키 중복 검사이며 자연어 규정 전체의 논리 모순 탐지가 아닙니다.

| 방식 | 모델 입력/처리 | 선택 결과 |
|---|---|---|
| `rules` | 정확 키워드가 일치하는 문서와 수강 조건을 코드로 대조. 모델 무호출 | 과정 1개면 승인 대기, 여러 개면 `AMBIGUOUS_REQUEST`, 없으면 `NO_EVIDENCE` 또는 `QUALIFICATION_GAP` |
| `llm` | 전체 현행 문서 7개와 수강 가능한 과정만 전달. 전체 인력 원장은 전송하지 않음 | 의미 선택 `select`, 재질문 `clarify`, 미일치 `no_match` |

LLM은 임베딩 없이 작은 현행 문서 묶음을 전체 읽습니다. 문서가 없거나 수강 가능한 과정 자체가 없으면 호출 전 차단합니다. 수강 가능한 다른 과정이 있으면 모델에 요청을 판단하게 하며, 제외된 과정을 요청했을 때 관련 없는 허용 과정을 대신 고르지 않도록 지시합니다. 이 의미 판단의 정확성은 평가와 사람 검토가 필요합니다.

모델용 schema는 `action`, `courseId`, `evidenceIds`, `reasonCode`만 허용합니다.

| 모델 action | courseId | evidenceIds | reasonCode | API 상태 |
|---|---|---|---|---|
| `select` | 수강 가능한 과정 enum 중 하나 | 해당 과정의 필수 근거 전부 | `REQUEST_MATCH` | 후검증 통과 시 `awaiting_approval` |
| `clarify` | `AMBIGUOUS` | `[]` | `REQUEST_AMBIGUOUS` | `blocked` / `AMBIGUOUS_REQUEST` |
| `no_match` | `NO_MATCH` | `[]` | `NO_RELEVANT_COURSE` | `blocked` / `NO_MATCH` |

응답 후 코드가 action 조합·허용 과정·선수 자격·기이수·현행 근거·중복 ID·필수 근거·여분 필드를 다시 검증합니다. 잘못된 JSON은 `LLM_INVALID_RESPONSE`, 잘못된 선택은 `LLM_INVALID_SELECTION`/502이며 다른 과정으로 자동 대체하지 않습니다. `proposal.reason`은 코드 검증을 설명하는 고정 문구이며 모델이 작성한 판단 근거가 아닙니다. 구조와 자격 검증을 통과한 선택도 요청 의미에 맞지 않을 수 있습니다.

실제 비교 E16·E17에서는 자격이 없는 요청 과정을 대신해 다른 허용 과정이 선택되었습니다. enum·근거 검증은 이 의미 오류를 차단하지 못했습니다. `awaiting_approval`은 의미 적합성 확정이 아니며 담당자가 요청과 제안을 직접 대조해야 합니다.

검토 응답의 `selectionMode`, `modelId`, `llmStatus`, `llmMs`, `retrievedEvidence`, `evidence`로 선택 방식·호출 여부·입력 문서·선택 근거를 구분합니다. 규칙 선택은 `modelId:null`, `llmStatus:not_called`입니다. 모델의 `clarify`와 `no_match`는 오류와 구분되는 저장된 보류 결과입니다.

## 별도 결정과 파일 원장

```json
{"requestId":"8375d184-3d06-41af-bc37-75c388e0f79d","action":"approve"}
```

결정 API의 action은 `approve`·`reject`이며 모델의 선택 action과 다릅니다. `blocked` 요청은 `REVIEW_BLOCKED`/409로 결정할 수 없습니다. 동일 승인 재전송은 계획 1건, 동일 거절 재전송은 0건을 유지하고 반대 결정은 `DECISION_CONFLICT`/409입니다.

계획에는 `selectionMode`, `modelId`, 과정·시간·근거·결정 시각이 기록됩니다. `education_plan_confirmed`는 계획 확정이며 `qualificationGranted:false`입니다. 승인 API의 source 문자열 `explicit-human-action`은 서버가 저장하는 분류값입니다. 검수 스크립트의 승인 POST는 명시적인 합성 테스트 결정이며 실제 사람 클릭을 증명하지 않습니다.

기본 저장은 `.learning-state.json` 파일이며 `LEARNING_STATE_PATH`로 앱 원장을 분리할 수 있습니다. 파일 원장은 DB가 아닙니다. 단일 프로세스 직렬화 잠금과 임시 파일 후 rename으로 저장하며 실패하면 성공을 반환하지 않습니다. 같은 원장을 여러 앱 프로세스에 연결하지 않습니다. 정적 dotfile 접근은 차단하고 API로만 읽습니다.

서비스 생성자는 `createLearningService({endpoint, model, fetchImpl, storagePath, documents, roster, timeoutMs})`입니다. 기본 모델 응답 제한 120초, 상태 조회 최대 5초이며 별도 평가 스크립트는 모델 응답 제한을 300초로 지정합니다. HTTP loopback 모델 주소만 허용하고 리다이렉트를 거부합니다.

## UI와 n8n

UI는 입력 변경 시 이전 activeReview를 지우고 승인·거절·근거 다운로드를 비활성화합니다. 진행 중 입력 잠금과 입력 버전 검사로 오래된 응답 설치를 막습니다. 저장된 계획 목록은 변경하지 않습니다. 사용자 텍스트는 `textContent`로 표시합니다.

`workflow-learning.json`은 `/webhook/wonik-learning` POST의 requestId·selectedWorkerId·query·mode·policyScope를 앱 review에 전달합니다. `awaiting_approval`만 Wait로 이동하고 실행 중 생성된 resume URL에 `{"action":"approve"}` 또는 `{"action":"reject"}`를 POST하면 decision → plans JSON → CSV를 실행합니다. 차단된 검토는 종료합니다. 최초 webhook 접수 응답을 최종 계획 출력으로 해석하지 않습니다.

실행은 [README](../README.md)의 n8n 스크립트를 따릅니다. 현재 앱 8798/n8n 5697이며 검증 스크립트의 `--db`·`--out` 옵션은 DB 읽기/증거 저장 경로만 바꿉니다. 자체 실행 증거 뷰어는 n8n UI가 아닙니다. [n8n 실행 증거](../evidence/n8n-20261010.json)의 실행 ID·Wait 관측·계획/CSV 일치와 상세 trace를 확인합니다. 합성 결정과 실제 담당자 승인, 로컬 연결과 사내 운영을 구분합니다.

## 검증 기록을 읽는 방법

`node --test tests/learning.test.mjs`는 서비스 Mock와 최소 DOM·이벤트 UI 회귀를 실행합니다. 자격·근거 제외, 보류, 잘못된 모델 응답, 중복/반대 결정, 저장·재열람, 오류와 입력 변경 상태를 검증합니다. Mock는 실제 모델 정확도나 실제 브라우저 렌더링 증거가 아닙니다.

[최종 비교 결과](../evidence/comparison-20261010-final/results.json)의 `completedAt`, 두 방식 각각 20건의 `summary`, 문항별 `correct`·`evidenceValid`·오류·호출 시간과 코드/자료/문항 해시를 확인합니다. 20개 개발자 라벨 합성 사례이며 규칙 기준선은 고정 키워드 구현입니다. 최적화한 규칙 전체의 정확도, 현업 성과, 처리시간 보장으로 확대하지 않습니다. 구조·근거의 적법성과 의미 선택 정답은 별도로 읽습니다.

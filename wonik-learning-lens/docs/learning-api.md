# 합성 교육계획 API

원익 HR Data & AI 활용 방안 기획 담당의 교육 과제 발굴·LLM 자동화 운영·HR 데이터 정제 업무에 맞춘 로컬 데모다. 모든 직원·SOP·과정·자격 규정은 합성이며 회사에서 운영된 결과가 아니다.

앱 기본 주소: `http://127.0.0.1:8786`. 실제 연결 모델: `http://127.0.0.1:8787/v1`, `Qwen3-4B-Q4_K_M`. 서비스 생성자의 기본 모델 주소는 재사용을 위해 `8767/v1`이며 앱 서버가 `8787/v1`을 명시 전달한다.

## 인터페이스

`createLearningService({endpoint, model, fetchImpl, storagePath, documents, roster, timeoutMs})`는 `status()`, `context()`, `review(input)`, `decision(input)`, `plans()`, `exportCsv()`를 제공한다. 기본 원장은 앱 폴더의 `.learning-state.json`이다. `LearningError`는 `code`, `message`, `status`를 가진다.

| HTTP | 경로 | 응답 |
|---|---|---|
| GET | `/api/learning/status` | 로컬 모델 정확 ID 연결 상태 |
| GET | `/api/learning/context` | 합성 원장·문서 본문·절·버전·과정·제외 구버전·업무/자료 경계 |
| POST | `/api/learning/review` | 검토 및 근거 또는 `blocked`; 잘못된 LLM 선택은 오류 |
| POST | `/api/learning/decision` | 명시적 승인/거절 결과, 원장 계획 1건 또는 `null` |
| GET | `/api/learning/plans` | `.learning-state.json` 출처와 교육계획 목록 |
| GET | `/api/learning/export.csv` | UTF-8 BOM CSV 문자열 |

검토 요청 예시:

```json
{
  "requestId": "8375d184-3d06-41af-bc37-75c388e0f79d",
  "selectedWorkerId": "SYN-101",
  "query": "자재 투입 라벨 교육",
  "policyScope": "current",
  "currentSimulation": {"educationEffectModeled": false}
}
```

`requestId`는 UUID, `selectedWorkerId`는 `SYN-101`~`SYN-104`, `query`는 1~600자다. `policyScope`는 `current`(현행), `missing`(자료 없음 합성 시나리오), `conflict`(현행 문서 충돌 합성 시나리오)다. `currentSimulation`은 선택적인 읽기 전용 공정 참고로 검토 화면에만 보관하고 모델에 보내지 않는다. 교육 성과와 공정 결과는 연결 계산하지 않는다.

```json
{"requestId":"8375d184-3d06-41af-bc37-75c388e0f79d","action":"approve"}
```

`action`은 `approve` 또는 `reject`. 같은 승인 두 번은 1건, 같은 거절 두 번은 0건으로 유지된다. 반대 결정 재요청은 HTTP 409다. 차단된 검토도 결정할 수 없다. 계획 상태 `education_plan_confirmed`는 교육계획 확정이며 이수·자격 취득을 의미하지 않는다. `qualificationGranted`는 항상 `false`다.

## 검증 순서와 경계

1. 합성 원장에서 작업자 ID·현재 자격·기이수 과정을 선택한다.
2. 요청의 정확 한국어 키워드와 현행 문서를 대조한다. SOP·과정 정의·자격 규정의 필수 근거가 모두 있고 선수 자격을 만족한 과정을 코드가 먼저 제한한다.
3. 현행 문서 본문, 선택 작업자 1명, 허용 과정 목록만 로컬 모델로 보낸다. 전체 인력 원장과 외부 인사 정보는 보내지 않는다. 임베딩 없이 검색 본문을 추론에 전달하는 문서 검색 증강이다.
4. 실제 모델 API에 JSON schema를 전달해 허용 과정 ID와 근거 문서 ID의 enum을 제공한다. 응답 ID·필수 근거·중복·이외 필드를 다시 검증한다. 설명은 검증된 고정 문구로 만든다.
5. 자료 없음·현행 문서 충돌·선수 자격 부족은 LLM 호출 전 차단한다. JSON 오류·잘못된 과정/근거·모델 연결 오류는 명시적 오류이며 대체 성공 결과를 만들지 않는다.
6. 담당자의 별도 승인 동작만 계획 원장에 기록한다. 직렬화 잠금과 임시 파일 작성 후 rename으로 결정과 원장 저장을 함께 확정한다. 저장 실패에는 성공을 반환하지 않는다.

서버는 dotfile 제공을 차단해야 한다. 원장 파일은 API로만 열람한다. 이 잠금은 앱 서버 프로세스 하나 안에서 동작하며 같은 원장에 여러 서버 프로세스를 연결하지 않는다. 모델 응답 제한은 기본 120초, 상태 확인은 최대 5초다.

## UI

`learning-panel.html`을 index에 삽입하고 `learning.css`를 연결한 뒤 `initLearningUI({getSimulationSummary})`를 호출한다. 패널 ID는 `learning-panel`. 교육 API 초기화 실패가 기존 3D 장면 초기화를 방해하지 않도록 루트가 별도 호출한다. 사용자가 입력한 텍스트는 `textContent`로 렌더링한다. 근거 JSON 및 원장 CSV 다운로드는 로컬 파일이다. 데스크톱에서 검토 카드는 전체 폭, 근거 문서는 3열로 배치하며 모바일에서는 1열로 표시한다.

## 검수

`node --test tests/learning.test.mjs`: 서비스 mock 테스트 8개와 UI 오류 회귀 테스트 2개, 총 10개 통과. 구조화 요청의 실제 본문·허용 enum·부분 인력만 전송, 현행/구버전 구분, 동시 승인 멱등성, 저장 후 재열람, 거절 0건, 반대 결정 409, 자료 없음/충돌/자격 부족의 무호출 차단, 잘못된 모델 선택/JSON 오류, loopback 주소 제한을 확인한다. UI 테스트는 최소 DOM·이벤트 어댑터로 검토 성공 후 모델 상태 조회 실패와 이후 검토 실패, 승인 확정 후 원장 목록 조회 실패를 재현해 근거·승인 상태의 일치와 재조회 안내를 검증한다. Mock 통과는 실제 모델의 성능·정확도나 브라우저 렌더링 검수를 의미하지 않는다.

2026-10-09 실제 로컬 `Qwen3-4B-Q4_K_M`(8787) API 검수: SYN-101 자재 투입→C-LOAD 34,060ms, SYN-102 품질 기록→C-QUALITY 23,045ms, SYN-103 설비 점검→C-MAINT 25,232ms. 세 요청 모두 필수 SOP·QUAL·COURSE 근거 ID와 선수 자격 검증을 통과해 `awaiting_approval`을 반환했다. 검수 원장은 `%TEMP%/wonik-learning-real-W1EZP9/.learning-state.json`, 교육계획은 0건이며 앱 원장을 사용하지 않았다. 이 세 합성 예시는 일반적 모델 정확도나 회사 실제 업무 성과의 평가가 아니다. 브라우저 통합 검수는 루트 README의 실행 기록을 따른다.

## workflow-learning.json

동봉 n8n 파일은 **가져오기용 설계이며 이번 작업에서 n8n 실행은 검증하지 않았다.** 수동 시작 → 원장 GET → 합성 교육 요청 POST → 검토 가능한 경우 담당자 결정 Wait → 결정 POST → 계획 GET이다. 자동 승인 노드는 없다. Wait 노드 재개 webhook에 담당자가 `{"action":"approve"}` 또는 `{"action":"reject"}`를 POST해야 한다. API 주소의 loopback은 n8n이 같은 컴퓨터에서 실행될 때만 유효하다. n8n 버전별 import·Wait webhook 인증 설정은 실행 환경에서 별도 검증한다.

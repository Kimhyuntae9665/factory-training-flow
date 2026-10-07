# API와 데이터 흐름

이 API는 `127.0.0.1:8770`에서 실행하는 합성 데이터 데모입니다. 포털 UI를 통한 사용을 권장합니다. 응답의 요청 ID로 결과·결정·공장 기록을 연결합니다.

## 브라우저 API

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/api/status` | 모델 상태와 로컬 실행 설정 확인 |
| GET | `/api/fixture` | 번들에 포함된 합성 역량 원장 4행 |
| GET | `/api/jobs` | 저장된 요청의 공개 상태 목록 |
| GET | `/api/job?id=<id>` | 계산 결과, 검토 상태, 교육 계획, 사건 이력 |
| POST | `/api/submit` | 요청을 저장하고 고정된 n8n Webhook으로 전달 |
| POST | `/api/decision` | 승인 또는 거절을 먼저 영속화한 후 n8n Wait 재개 |

POST는 JSON과 `Origin: http://127.0.0.1:8770`이 필요합니다. 최대 본문은 32KB이며 잘못된 타입·예상하지 않은 키를 거절합니다.

`/api/submit` 요청 형태:

```json
{
  "request": "수요 1.0배, 로봇 자동화와 검사 교육을 함께 비교해 주세요.",
  "records": ["/api/fixture의 records 배열 전체를 넣습니다. 이 문자열은 설명용입니다."],
  "synthetic": true,
  "idempotency_key": "새 요청마다 다른 키"
}
```

위 예시는 구조 설명이며 그대로 실행할 유효한 원장이 아닙니다. 원장은 `/api/fixture` 응답의 `records`를 사용하세요. 정상 원장은 검증된 번들 원장과 일치해야 합니다. 임의 직원 데이터를 넣는 기능은 구현하지 않았습니다.

같은 키와 같은 본문은 기존 요청을 반환합니다. 같은 키에 다른 본문을 보내면 HTTP 409입니다.

`/api/decision`:

```json
{"request_id":"실제 요청 ID","decision":"approve"}
```

`decision`은 `approve` 또는 `reject`입니다. 서버는 `decision_pending` 상태와 결정을 저장한 다음 n8n을 재개합니다. API 수신 성공과 계획 확정 완료는 다른 단계입니다. UI에서 최종 `approved` 또는 `rejected`를 확인하세요. 같은 결정의 재전송은 중복 계획을 만들지 않고 반대 결정은 HTTP 409입니다.

## n8n 내부 API

| 경로 | 입력 | 처리 |
|---|---|---|
| `/api/workflow/validate` | `request_id` | 원장·조건 검수, 소스 해시 기록 |
| `/api/workflow/analyze` | `request_id` | 실제 Qwen 선택과 SimPy 비교, 결과 저장 |
| `/api/workflow/await-review` | `request_id`, `resume_url`, `execution_id` | n8n 실행 ID와 내부 재개 URL 저장 |
| `/api/workflow/finalize` | `request_id`, `decision` | 저장된 결정과 대조 후 승인·거절 확정 |

내부 HTTP 노드는 `X-Workflow-Client: factory-training-local-v1`을 보냅니다. 이 값은 워크플로 구분 표식이며 운영 환경의 인증 수단이 아닙니다.

Wait URL은 로컬 n8n의 고정 포트·경로·실행 ID와 서명 형식만 허용합니다. n8n이 발급한 서명을 보존하고 검증을 끄지 않습니다. URL과 서명은 내부 SQLite에만 보관하며 공개 응답·증거 JSON·저장소에 포함하지 않습니다.

## 데이터 일관성

- 원본 요청은 저장 후 변경하지 않습니다.
- 교육 계획의 `job_id`에 UNIQUE 제약을 사용합니다.
- 승인 확정은 저장된 동일 결정이 있어야 가능합니다. 결정 API가 교육 계획을 직접 만들지 않습니다.
- 실제 모델 실행 전, 계산 전후에 소스 해시를 대조합니다. 도중에 원장이 바뀌면 결과를 확정하지 않습니다.
- 교육이 포함된 대안을 승인할 때만 계획을 만들며 거절은 계획 0건입니다. 교육 없는 대안 승인은 비교 기록만 남길 수 있습니다.
- 공개된 기록의 검토자는 합성 시연 역할입니다. 실제 직원의 교육·인사 결정을 수행하지 않습니다.

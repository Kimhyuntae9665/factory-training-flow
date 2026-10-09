# Wonik Learning Lens

공고의 **교육 분야 AI 과제 발굴·LLM 자동화 도입·HR 데이터 정제** 업무를 위해, 직접 조작하는 공정 시뮬레이션과 근거 기반 교육계획 검토를 연결한 개인 데모입니다.

창신 Lean 세션의 **Line Lens**를 별도 복사해 확장했습니다. 기존 3D·계산·공정 AI 조언을 재사용하고, 합성 교육 원장·현행 문서 검색·로컬 LLM 과정 선택·규정 검증·승인·거절·저장을 추가했습니다. 원본은 수정하지 않았습니다.

## 실제 화면

실제 브라우저 캡처와 검수 JSON은 `evidence/`에 있습니다. 전체 원본과 설명에 적합한 크롭을 구분했습니다. 최신 3페이지 PDF는 [docs/portfolio.pdf](docs/portfolio.pdf)이며, [저장소의 페이지별 미리보기](../docs/portfolio-page-1.png)와 [편집·검수 기록](../docs/portfolio-source-v2/README.md)도 제공합니다.

![공정 근접 실행 화면](../docs/screenshots/wonik-learning-lens/factory.png)

![SYN-101의 실제 교육안·근거 검토 기록 재열람](../docs/screenshots/wonik-learning-lens/review.png)

*2026.10.09 저장된 실제 응답(86,470ms)을 2026.10.10 원본 UI 렌더러로 재열람했습니다. 승인 완료 기록이며 새 LLM 호출은 없습니다.*

![실제로 승인 저장한 교육계획](../docs/screenshots/wonik-learning-lens/plans.png)

![현행 규정 충돌 차단](../docs/screenshots/wonik-learning-lens/blocked.png)

## 먼저 알아둘 범위

- 공정·작업자·SOP·자격·교육과정은 모두 합성입니다. 원익 내부 시스템·직원 자료가 아닙니다.
- 기존 신발 생산 모델의 규칙을 일반 부품 조립 화면으로 바꿨습니다. 원익 설비에 맞춰 보정한 디지털 트윈이 아닙니다.
- 승인은 교육계획만 저장합니다. 교육 이수·작업 자격·생산량 효과를 자동 처리하지 않습니다.
- 검색은 **현행 버전 필터 + 정확한 키워드 매칭**입니다. 문서 본문을 LLM에 전달하지만 임베딩·벡터 검색은 구현하지 않았습니다.
- n8n JSON은 **미실행 연계 템플릿**입니다. 앱의 로컬 입출력·저장은 실제 동작하지만 실제 n8n 인스턴스 연계는 검증하지 않았습니다.

## 실행

Node.js 22 이상을 권장합니다. npm 외부 의존성 설치 없이 실행합니다. Three.js는 `vendor/`에 포함됩니다.

```powershell
cd <압축을 푼 wonik-learning-lens 폴더>
$env:PORT = '8786'
$env:LINE_LENS_LLM_URL = 'http://127.0.0.1:8787/v1'
npm start
```

[http://127.0.0.1:8786](http://127.0.0.1:8786)을 엽니다. 앱은 127.0.0.1에만 바인딩합니다. 로컬 AI에는 별도로 llama.cpp와 Qwen3-4B-Q4_K_M GGUF가 필요하며 모델·실행 파일은 배포 묶음에 포함하지 않았습니다.

이번 검수의 CPU 서버 구성:

```powershell
llama-server.exe --model <GGUF 경로> --alias Qwen3-4B-Q4_K_M --host 127.0.0.1 --port 8787 --ctx-size 4096 --n-gpu-layers 0 --threads 6 --threads-batch 6 --reasoning off --reasoning-budget 0
```

llama.cpp 버전에 맞는 옵션을 확인하세요. `/v1/models`의 ID는 `Qwen3-4B-Q4_K_M`이어야 합니다. HTTP loopback만 허용하고 리다이렉트는 거부합니다. 모델이 없으면 공정 계산은 실행되며 AI 요청은 명확한 실패로 표시합니다. 모의 추천을 성공 결과로 대신 표시하지 않습니다.

## 3분 사용 순서

1. 공정을 선택하고 타임라인·회전·확대·평면 보기로 작업 셀을 관찰합니다.
2. 인원·속도·휴식 또는 자재 대기·조립 주기·검사 조건을 바꿔 같은 시드의 교대 전체 지표를 비교합니다. `처음부터 재생`은 시간만 초기화합니다.
3. `AI 교육계획`에서 작업자 A·현행 자료·기본 자재투입 요청을 검토합니다.
4. 과정·시간·SOP·자격·과정 정의·구버전 제외를 확인합니다. 승인하면 계획 1건, 거절하면 계획 미저장입니다.
5. `새 요청 · 화면 초기화`는 저장된 계획을 보존합니다. `자료 없음`·`규정 충돌` 또는 선수 자격 없는 작업자로 승인 차단을 확인합니다.
6. `검토 근거 JSON`과 `CSV 내보내기`로 검토·원장을 내려받습니다. 새로고침·서버 재실행 후에도 원장을 확인합니다.

## 입력 → 검증 → 출력

| 단계 | 구현 | 검증 |
|---|---|---|
| 입력 | 합성 CSV 원장 → 정규화 배열, 요청·자료 범위 | 자격·기이수는 추정하지 않음 |
| 검색 | 현행 문서 키워드 매칭 | 구버전 제외·근거 없음·현행 충돌 차단 |
| AI | 실제 검색 본문·과정 후보·자격을 로컬 Qwen에 전달 | JSON Schema의 과정·문서 ID 선택 |
| 검증 | 선수 자격·필수 문서·허용 ID | 없는 과정·오래된 근거·잘못된 JSON은 실패 |
| 결정 | 사람이 승인 또는 거절 | 승인 전 계획 미저장·반대 결정 충돌 |
| 출력 | 서버 JSON 원장·CSV·근거 JSON | 중복 승인 1건·이수/자격 부여 없음 |

현재 공정 요약은 **읽기 전용 참고**입니다. 공정 생산량 효과 점수로 교육과정을 고르지 않습니다.

## n8n

`workflow-learning.json`은 `context → review → IF → Wait → 명시적 decision → plans/export`의 비활성 템플릿입니다. 실제 내부 소프트웨어의 권한·API·승인 경로는 추가 확인이 필요합니다. 원익이 n8n·특정 LMS/ERP/MES를 사용한다는 주장은 하지 않습니다.

앱 API는 같은 PC의 loopback Host/Origin만 허용합니다. n8n을 Docker나 별도 호스트에서 실행하면 주소만 넣어 연결되지 않을 수 있습니다. 운영 배포를 위한 이 제한 해제는 이번 범위가 아닙니다. 자세한 API는 [docs/learning-api.md](docs/learning-api.md)를 확인하세요.

## 검증

```powershell
npm test
```

2026-10-09 최종 **49/49 통과**: 기존 공정·후보·분석 회귀 39개 + 교육 서비스 8개 + 비동기 UI 오류 재현 2개. 모의 모델 테스트와 실제 모델 호출을 구분합니다.

2026-10-10 저장소 게시 준비에서도 이 폴더의 자동 검사 49/49를 다시 통과했습니다. 새 모델 추론·n8n 실행·기존 통합 검수는 재실행하지 않았습니다.

실제 모델의 별도 자재투입·품질기록·설비점검 요청은 필수 근거 선택·검증을 통과했습니다. CPU 단일 관측값 34,060 / 23,045 / 25,232 ms이며 평균·성능 보장이 아닙니다. 브라우저 통합 결과와 추가 관측값은 [evidence/live-validation.json](evidence/live-validation.json)에 기록합니다.

실제 공정 UI에서 기준 양품 1,191개가 인원 축소·120%·무휴식 조건에서는 889개, 추천 공정 조건에서는 1,369개로 변했습니다. 합성 실험이며 교육 효과나 회사 성과가 아닙니다. 피로·작업부하·대기 지표도 함께 확인합니다.

## 파일

- `simulation.js`, `scene.js`, `app.js`: 재사용 공정 계산·3D·조작과 원익용 연결
- `advisor-*`: 재사용 목표 해석·계산 후보 검증
- `learning-service.js`: 교육 검색·모델·규정 검증·저장
- `learning-ui.js`, `learning.css`, `learning-panel.html`: 검토 화면
- `fixtures/`: 합성 원장·현행/구버전 문서·교육과정
- `serve.mjs`: 로컬 서버
- `.learning-state.json`: 실행 시 생성되는 합성 원장. 정적 접근 차단·배포 ZIP 제외
- `workflow-learning.json`: 미실행 n8n 템플릿
- `analysis/`: 창신 원본의 CSV 분석/회귀 보존 자료. 원익 메인 메뉴에서 제외했고 신규 HR 기능으로 주장하지 않음
- `docs/reuse-and-scope.md`: 출처·재사용·이번 구현·한계

## 공식 근거

[원익그룹 공식 채용공고](https://wonik.recruiter.co.kr/career/jobs/128767)의 원익홀딩스 HR Data & AI 활용 방안 기획 업무를 2026-10-09 확인했습니다. 공고 마감 2026-10-12 23:59입니다.

[원익로보틱스 디지털 트윈](https://wonikrobotics.com/kr/sub/application/robotAutomation/digital_twin.php)은 제조 시뮬레이션 사업 배경입니다. 해당 HR 조직의 내부 추진 과제·사용 도구를 확인한 자료가 아닙니다.

3D는 제조 업무를 관찰하는 프레임이며, 이 프로젝트의 직접 과업은 **교육계획 근거와 승인 기록을 검토하는 일**입니다. 직무 적합성은 교육·문서·데이터·AI 검증·저장 흐름에서 설명합니다.

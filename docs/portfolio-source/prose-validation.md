# 1장 제목·조작 안내 · light 문구 검증 완료

제목·kicker·실제 UI eyebrow와 h1·04 조작 카드·3줄 설명의 6블록을 light 경로로 검증했습니다. 문구가 이미 자연스러워 수정과 추가 제안은 없습니다.

- 실행 폴더: `work/i-am-not-ai/2026-10-08-006-portfolio-review3/`
- 원문과 백업: `01_input.txt`, `00_input_preserved.txt`. 원문·final 본문 직접 대조 완전 일치. 186자(끝 LF 포함) / 185자(끝 개행 제외).
- 사전채점: prepare_monolith_input exit 0, risk_band low, risk_score 0, route_hint light, degraded False.
- 독립 monolith: i-am-not-ai monolith·quick-rules를 실제 적용해 진단·윤문 필요 여부·직접 대조·6항 검증을 수행했습니다. 문구 수정 0곳, 자체검증 6/6, 등급 B.
- 복원: restore_modality exit 0, 복원 0문장 / 보류 0문장. strip_injected_commas exit 0.
- 게이트: verify_gates exit 0, change_rate 0.0%, gate OK — 수렴, P3 golden PASS, 문장 터치율 0/8. 수치 누락·서법 소실 없음.
- 보존: AI 교육기획 데모, 교육 AI 과제 발굴·합성 공정 비교, 검사 교육·자동화 대안 비교, `대안: 저장된 네 대안 결과 선택`, 공정 확대·전체 공장 전환, 재생·시각을 통한 진행 시점 확인. 저장된 결과 선택을 새 계산·실시간 AI 호출로 바꾸지 않았습니다.
- 실제 UI 소스 대조: `work/factory-n8n/web/replay.html`에 현재 eyebrow와 h1이 원문 그대로 존재함을 확인했습니다. UI 소스를 수정하지 않았습니다.
- 최종 PDF 대조: `outputs/김현태_원익홀딩스_n8nAI_포트폴리오_개선본.pdf`, SHA-256 `b4ccfcc53dd5503f74e216f43287a176bad34bf19f890ef326060a8207105e62`. 파일을 실제로 다시 열고 3페이지임을 확인했습니다. 1장 제목·kicker·04 카드·3줄 조작 안내는 선택 가능한 PDF 텍스트를 추출해 입력 원문과 공백 제외 일치를 확인했습니다.
- UI 캡처 대조 구분: eyebrow와 h1은 PDF의 이미지 내부에 있어 PDF 텍스트 추출로 검증했다고 표시하지 않습니다. 현재 `replay.html` 소스 원문 일치를 확인한 뒤 실제 사용한 `work/n8n-portfolio-v2/screens/replay-review3-focus.jpg`를 원본 해상도로 열어 두 문구를 육안 대조했습니다. 현재 캡처 SHA-256은 `b3b876ebef0ab05d5614fab7dbf5b8263bb50f5c820437c148b2526d056d215c`입니다.
- 최종 1장 100% 재열람: PDF를 이 실행 폴더의 `page1-review-100.png`로 렌더해 제목·kicker·캡처 속 UI 문구·04 카드·3줄 안내가 반영되어 있는지 확인했습니다. 화면 조작을 저장된 네 대안 결과 선택·구도 전환·진행 시점 확인으로 설명하고 있으며 새 계산이나 실시간 AI 호출을 주장하지 않습니다.
- 파일 경계: 이 신규 run만 작성했습니다. 기존 prose.md·루트 UI·build.py·PDF와 다른 작업자의 파일을 수정하거나 되돌리지 않았습니다.
- 증거: `03_prepare.txt`, `04_modality.txt`, `05_commas.txt`, `06_gates.txt`, `validation.json`, `direct-comparison.diff`. final.md 메타는 검증용이고 최종 PDF에 넣지 않았습니다.

## 영역 표시 변경 이후 문안 재대조

- 이번 변경은 문서 도형만 수정했습니다. 세 페이지 전체 텍스트가 기존 PDF와 공백 제외 완전히 동일함을 PyMuPDF로 대조했습니다. 위의 실제 윤문 검증을 유지하며 새 윤문 실행으로 표시하지 않습니다.
- 현재 영역 표시본 PDF SHA-256: `680be446d87c8f788fa3373a68d3fd9438005c1a0f2145412ff7b0a344421e24`

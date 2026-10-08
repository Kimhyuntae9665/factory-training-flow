# 3페이지 포트폴리오 개선본 편집 소스

원익홀딩스 공식 공고의 교육 AI 과제 발굴, LLM·생성형 AI·RPA 솔루션 도입·운영, 데이터 수집·정제·데이터베이스화 업무를 위해 만든 개인 PoC의 3페이지 설명 자료입니다. 실제 원익 내부 도입·직원 데이터·HR 실무 성과가 아닙니다.

- `build.py`: ReportLab 편집 소스. 레이아웃·테두리·안내선은 문서 레이어이며 원본 캡처를 덧칠하지 않습니다.
- `web/replay.html`(저장소 루트): 프로그램 제목을 직관적으로 수정한 실제 UI 소스입니다. 수정 후 다시 실행해 `replay-review3-full.jpg`와 `replay-review3-focus.jpg`를 촬영했습니다.
- `prose.md`: 페이지별 직무 연결 및 사실 문구.
- `screens/`: 2026.10.08 실제 localhost 화면 캡처. `*-full.jpg`는 전체 원본, `approved-detail.jpg`는 명시한 결과 영역 확대입니다. 공정 수치와 실제 Qwen 실행은 2026.10.07 기록입니다.
- `audit.json`, `검수기록.md`: 3페이지·연결 문장·네 변 테두리·10개 안내·실제 조작 검수 기록.
- `prose-validation.md`: 최종 서술형 본문의 윤문 검증 기록.

Windows의 맑은 고딕 폰트를 사용합니다. 저장소 루트에서 아래 명령으로 PDF를 다시 만들 수 있습니다.

```powershell
python -m pip install reportlab Pillow PyMuPDF
python -X utf8 docs/portfolio-source/build.py
```

재빌드 결과는 `docs/portfolio.pdf`에 저장합니다. 빌드는 기존 실험 증거만 읽고 LLM·n8n을 새로 실행하지 않습니다. `audit.json`의 새 빌드 시각적 검수는 pending으로 생성되므로 수정 후 실제 렌더링을 재열람해야 합니다.

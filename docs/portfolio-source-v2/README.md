# 최신 포트폴리오 v2 편집 원본

공고의 교육 분야 AI 과제 발굴·LLM 자동화 도입·HR 데이터 정제 업무를 설명하는 3페이지 자료입니다. 합성 작업자 SYN-101의 자재 투입 기초 2시간 요청을 관찰·검토·승인·저장까지 같은 사례로 연결합니다.

- `copy.json`: 직무 연결 문장, 페이지별 문안과 실제 검증 결과 비교.
- `build.py`: ReportLab 레이아웃·스크린샷 외곽 테두리·대상 사각형·연결선 및 렌더링.
- `capture-map.json`: 원본 캡처의 대상 영역 좌표.
- `review.jpg`, `review-record.html`, `capture-review.json`: 2026.10.09 저장된 실제 SYN-101 응답을 원본 UI 렌더러로 재열람한 보관 기록. 새 모델 호출이 아니며 승인 완료 상태를 표시합니다. HTML은 기록 뷰어로, 승인 버튼은 비활성입니다.
- `audit.json`, `validation.md`: 사례 일치·원장/CSV 대조와 전체/100% 시각 검수.
- `validation/`: 문안 light 진단·무수정 직접 대조·복원/게이트 통과 기록.

원본 실행 캡처와 기존 검수 JSON은 [wonik-learning-lens/evidence](../../wonik-learning-lens/evidence)에 있습니다. PDF의 49/49·14/14는 2026.10.09 검사 기록이며 포트폴리오 수정에서 새로 실행한 수치로 표현하지 않습니다.

Windows 맑은 고딕 폰트와 Python의 reportlab, Pillow, PyMuPDF가 필요합니다. 저장소 루트에서 실행합니다.

```powershell
python -m pip install reportlab Pillow PyMuPDF
python -X utf8 docs/portfolio-source-v2/build.py
```

출력은 `docs/portfolio.pdf`, `docs/portfolio-page-1.png`~`3.png`, `docs/portfolio-overview.png`입니다. 빌드는 새 LLM·n8n 호출을 하지 않습니다. 재빌드 뒤 시각 검수 상태는 pending으로 바뀌므로 실제 렌더링을 다시 확인해야 합니다. 이전 n8n 버전은 [별도 보관 PDF](../archive/factory-training-flow-20261008/portfolio.pdf)입니다.

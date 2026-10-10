# 포트폴리오 v3 편집 자료

공고의 교육 분야 AI 과제 발굴·LLM 자동화 도입·HR 데이터 정제 업무를 위해 만든 데모의 3페이지 설명입니다.

- [최종 PDF](../portfolio.pdf)와 [1장](../portfolio-page-1.png)·[2장](../portfolio-page-2.png)·[3장](../portfolio-page-3.png)
- `copy.json`: 페이지별 직무 연결·본문·관찰 안내
- `capture-map.json`: 원본 화면의 크롭과 설명 대상 사각형 좌표
- `layout-validation.json`: 외곽 테두리·대상 사각형·연결선·페이지 배치 기록
- `final-review.md`: 전체 보기 및 100% 시각 검수 결과
- [원본 실행 캡처](../screenshots/wonik-learning-lens-v3/manifest.json): 원본 픽셀 보존·출처·SHA-256
- [20건 비교](../../wonik-learning-lens/evidence/comparison-20261010-final/results.json), [실제 n8n 3회 실행](../../wonik-learning-lens/evidence/n8n-20261010.json), [56개 테스트 로그](../../wonik-learning-lens/evidence/tests-20261010.txt)

PDF는 1280×720의 총 3장입니다. 첫 장 관찰 안내는 화면 아래에 두고, 모든 주요 화면에 외곽 네 변 테두리·대상 사각형·연결선을 넣었습니다. 비교는 개발자 라벨의 합성 요청 20개에 한정하며, n8n 결정은 검수용 명시적 POST입니다. 실제 직원·원익 내부 적용·현장 성과로 표현하지 않습니다.
## 2026-10-10 설명 개선

첫 장에 교육 담당자의 업무 문제(가정), 본인이 제안·검토한 범위와 실제 교육 요청 입력 화면을 배치했습니다. 2장은 비교 수치에 따른 도입 조건을 보완했고, 3장의 n8n 실행·저장 검증 내용은 유지했습니다. 기존 56개 기능 테스트·40개 비교 결과·n8n 3건은 재실행하지 않았습니다.

- [이번 설명·링크·레이아웃 검수](revision-validation.json)
- [문체 직접 대조·게이트](copy-review.json): light, 추가 윤문 변경 0%, 게이트 exit 0
- [개선 전 공개본](../archive/learning-lens-v3-before-hr-edit-20261010/portfolio.pdf)
- `publication-validation.json`과 `publication-tests.txt`는 개선 전 최초 게시 시점 기록입니다. 현재 PDF 해시는 `revision-validation.json`을 사용합니다.

## PDF 다시 만들기

Windows, Python 3.13, `reportlab`, `PyMuPDF`, `Pillow`와 Windows 맑은 고딕(`C:/Windows/Fonts/malgun.ttf`, `malgunbd.ttf`)을 사용합니다. 저장소 루트에서 실행합니다.

```powershell
python -m pip install reportlab PyMuPDF Pillow
python -X utf8 docs/portfolio-source-v3/build.py
```

`build.py`는 저장소 기준 상대 경로로 원본 캡처·본문·기존 증거를 읽고 PDF·3개 페이지 PNG·레이아웃 기록을 만듭니다. 모델이나 n8n을 호출하지 않습니다. Linux/macOS의 폰트·실행은 확인하지 않았습니다. PDF를 다시 만든 후에는 모든 페이지의 실제 시각 검수가 필요합니다.

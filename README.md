# Python Flow Visualizer

Python 코드를 입력하면 실행 결과만 보여주는 것이 아니라,
**코드가 어떤 줄을 지나가고, 어떤 함수가 호출되고, 자료구조가 어떻게 변하는지**를
step 단위로 시각화해 주는 학습용 도구입니다.

## 왜 만들었는가

자료구조나 알고리즘을 공부할 때 가장 어려운 부분은
“코드가 실제로 어떻게 흘러가는지 눈으로 보기 어렵다”는 점이었습니다.

그래서 저희는:

- 현재 실행 중인 줄
- 함수 호출 스택
- 자료구조 상태
- stdout 출력
- 에러 메시지
- 알고리즘 설명

을 한 화면에서 같이 볼 수 있는 도구를 만들었습니다.

즉, 이 프로젝트는 단순한 Python 실행기가 아니라
**Python 코드의 실행 과정을 학습용으로 해석해서 보여주는 시각화 도구**입니다.

## 핵심 기능

- Python 코드를 step 단위로 trace
- 현재 실행 줄 하이라이트
- 함수 호출 스택 및 재귀 호출 트리 시각화
- 그래프 / 트리 / 스택 / 큐 자동 판단
- stdout / 에러 메시지 표시
- 현재 step 기준 코드 설명 제공
- `input()` 기반 입력 데이터 실행 지원

## 기술 스택

- Backend: Flask
- Frontend: HTML, CSS, Vanilla JavaScript
- Visualization: 자체 렌더링 기반 UI
- Test: `unittest`
- Deploy/CI: GitHub Actions, Vercel

## 역할 분담

- 이경근: 초기 화면 / 실행 화면 UI 개선, 에러 메시지 경험 정리, 프론트 인터랙션 조정
- 이현성: 핵심 시각화 기능 확장, 브랜치 통합, 배포 흐름 구성
- 여서진: 실행 흐름 패널, 시각화 패널 구조 개선, 병합 이후 화면 동작 정리
- 송채강: 실행 환경 관련 구조 변경, 런타임/프로젝트 구조 확장 작업

## 개발하면서 어려웠던 점

가장 어려웠던 부분은 **브랜치 병합과 트러블슈팅**이었습니다.

여러 명이 동시에 같은 프론트 파일과 실행 흐름 로직을 수정하다 보니:

- `templates/index.html`
- `static/js/controller.js`
- `static/js/renderers/visual_panel.js`

같은 핵심 파일에서 충돌이 자주 발생했습니다.

특히 병합 이후에는:

- 프런트와 백엔드의 응답 계약이 어긋나 실행 버튼이 동작하지 않거나
- 특정 코드가 그래프가 아니라 정렬로 잘못 분류되거나
- 테스트는 통과하지만 실제 UI에서는 다른 화면이 보이는 문제

같은 이슈를 하나씩 추적해야 했습니다.

그래서 이번 프로젝트에서는 기능 구현만큼이나
**병합 이후 문제를 재현하고, 원인을 분리하고, 다시 검증하는 과정**이 중요했습니다.

## 실행 방법

```bash
cd /Users/igyeong-geun/Documents/code/python_flow_visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

브라우저에서 `http://127.0.0.1:5050` 으로 접속하면 됩니다.

## 테스트

```bash
cd /Users/igyeong-geun/Documents/code/python_flow_visualizer
python -m unittest discover -s tests
```

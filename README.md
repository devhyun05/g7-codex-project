# Python Flow Visualizer

`pythontutor.com` 스타일을 참고해 만든 학습용 Python 실행 시각화 앱입니다.

## 포함된 기능

- Python 코드를 한 줄씩 trace
- 현재 실행 줄 하이라이트
- 현재 실행 코드 아래에서 `stdout` / 오류 확인
- 주 시각화 아래에서 현재 step과 자동 판단 결과 설명
- 재귀 함수 호출 트리 시각화
- 인접 구조는 그래프, 노드 구조는 트리, `append/pop`, `deque/popleft` 패턴은 스택/큐로 자동 판단
- 편집 화면의 입력 데이터로 `input()` 실행 지원

## 협업용 구조

- [app.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/app.py)
  역할: Flask 진입점만 유지
- [visualizer/routes.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/visualizer/routes.py)
  역할: 라우트 정의
- [visualizer/services/trace_service.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/visualizer/services/trace_service.py)
  역할: trace 서비스 연결
- [visualizer/tracing/runtime.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/visualizer/tracing/runtime.py)
  역할: 실행 추적 엔진
- [visualizer/tracing/code_analysis.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/visualizer/tracing/code_analysis.py)
  역할: 코드 패턴 기반 자료구조 추론
- [visualizer/tracing/structure_detection.py](/Users/igyeong-geun/Documents/code/python_flow_visualizer/visualizer/tracing/structure_detection.py)
  역할: 런타임 값 기반 구조 감지
- [static/js/controller.js](/Users/igyeong-geun/Documents/code/python_flow_visualizer/static/js/controller.js)
  역할: 프런트 상태와 이벤트 제어
- [static/js/renderers/code_panel.js](/Users/igyeong-geun/Documents/code/python_flow_visualizer/static/js/renderers/code_panel.js)
  역할: 코드 / 출력 렌더링
- [static/js/renderers/visual_panel.js](/Users/igyeong-geun/Documents/code/python_flow_visualizer/static/js/renderers/visual_panel.js)
  역할: 주 시각화 렌더링
- [static/js/renderers/explanation_panel.js](/Users/igyeong-geun/Documents/code/python_flow_visualizer/static/js/renderers/explanation_panel.js)
  역할: 코드 설명 패널 렌더링

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

## 제한 사항

- 학습용 로컬 도구 기준으로 만들었습니다.
- 안전을 위해 `os`, `sys` 같은 import는 막고 `math`, `random`, `itertools`, `collections`, `heapq`만 허용합니다.
- 무한 루프를 피하기 위해 실행 step 수와 시간을 제한합니다.
- 자료구조 자동 판단은 AST 패턴과 런타임 값을 함께 사용하므로, 아주 특이한 구현은 놓칠 수 있습니다.

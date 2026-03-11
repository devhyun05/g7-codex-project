# Python Flow Visualizer

`pythontutor.com` 스타일을 참고해 만든 학습용 Python 실행 시각화 앱입니다.

## 포함된 기능

- Python 코드를 한 줄씩 trace
- 현재 실행 줄 하이라이트
- 프레임별 지역 변수 / 전역 변수 표시
- `print()` 출력 누적 표시
- 재귀 함수 호출 트리 시각화
- `graph`, `tree`, `adj` 같은 인접 구조가 있으면 노드/간선 시각화

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

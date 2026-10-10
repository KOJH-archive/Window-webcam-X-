# Desk Guardian

Windows 노트북의 내장 카메라와 입력 유휴 시간으로 자리 감지, 자동 절전, 얼굴 기준 자세 알림, 분별 집중 추정치를 제공하는 로컬 앱입니다. [개발명세서](DEVELOPMENT_SPEC.md)를 구현 기준으로 삼았습니다.

## 설치

이 PC에는 `.venv`가 이미 준비되어 있습니다. 다시 설치해야 한다면 Windows 11에서 Python 3.11과 `uv`를 사용해 다음을 실행합니다.

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

`models/face_landmarker.task`는 이미 포함되어 있으며 앱은 실행 중 모델을 내려받지 않습니다. 카메라 접근이 필요합니다. Windows **설정 → 개인정보 및 보안 → 카메라**에서 카메라 액세스와 데스크톱 앱 액세스를 켜세요.

## 실행

가장 간단한 방법은 [Desk Guardian.vbs](Desk%20Guardian.vbs)를 더블클릭하는 것입니다. 명령창 없이 작은 시작 화면이 열리고 **안전 모드** 또는 **자동 절전 모드**를 선택할 수 있습니다. 실행이 완료되면 시작 화면은 자동으로 닫히고 앱은 작업표시줄 오른쪽 트레이에서 계속 작동합니다. Windows에서 스크립트 실행이 제한된 경우에는 `Desk Guardian.cmd`를 사용하세요.

처음에는 시작 화면의 **안전 모드로 시작**을 권장합니다. 카메라 감지·자세 알림·기록은 모두 작동하지만 실제 절전은 하지 않습니다.

## 명령줄 실행

```powershell
.\.venv\Scripts\python.exe -m src.main --dry-run
```

기본값도 모의 실행입니다. 트레이의 **자세 기준 설정**을 눌러 평소 자세를 10초 유지한 뒤 안내에 따라 5초간 고개를 숙이세요. 기준 설정 전에는 자세 알림과 집중 점수가 나오지 않습니다. 카메라 오류일 때 트레이는 빨간색이고 자동 절전은 실행되지 않습니다. 일시정지는 30분 후 자동 해제되며, **다시 시작**으로 즉시 해제할 수 있습니다.

`start-dry-run.cmd`를 더블클릭해 같은 모드로 바로 시작할 수도 있습니다.

실제 자동 절전을 원할 때만 `start-real.cmd`를 더블클릭하고 확인 질문에 답하거나 아래처럼 실행합니다. 두 모드 플래그를 함께 쓸 수 없습니다.

```powershell
.\.venv\Scripts\python.exe -m src.main --enable-sleep
```

얼굴 부재와 입력 유휴가 모두 300초 이상일 때 절전을 요청하고, 15초 전에 한 번 알립니다. 복귀 후 60초간 재절전을 막습니다. Windows의 전원 설정과 실행 중인 앱에 따라 실제 절전 동작은 달라질 수 있습니다. 자동 시작은 등록하지 않습니다.

카메라를 사용할 수 없으면 트레이가 빨간색으로 바뀌고 장애 구간마다 한 번만 알립니다. 이 상태에서는 자동 절전을 실행하지 않으며 30초 간격으로 카메라 복구를 시도합니다.

## 관찰과 대시보드

자세 임계값을 점검할 때는 `--observe --dry-run`을 붙이세요. 이 모드는 자세 알림을 끄고 5초마다 수치만 CSV에 남깁니다. 요약은 다음 명령으로 확인합니다.

```powershell
.\.venv\Scripts\python.exe scripts\summarize_metrics.py
```

트레이의 **대시보드 열기**를 누르거나 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

대시보드는 `127.0.0.1`에서만 열리고 DB를 읽기 전용으로 조회합니다. 기본 데이터 경로는 `%LOCALAPPDATA%\DeskGuardian`입니다. 공개 기본값은 `config.yaml`에 있으며, 개인 설정은 Git에서 제외되는 `config.local.yaml`에 둘 수 있습니다. 프레임·랜드마크 원본·키 내용·창 제목·프로세스 이름은 저장하지 않습니다. 자세 판정은 얼굴 특징을 이용한 간접 추정으로, 등·어깨 자세나 건강 상태를 판단하지 않습니다. 집중 점수 역시 생산성 평가용이 아닙니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tests\.pytest_tmp tests
```

실행 환경마다 카메라·전원 관리 방식이 다르므로 실제 자동 절전은 작업을 저장한 상태에서 별도로 확인하세요. 카메라 관찰 CSV, 데이터베이스, 로그, 로컬 설정, 개인 검증 보고서와 일회성 측정 도구는 공개 저장소에 포함되지 않습니다.

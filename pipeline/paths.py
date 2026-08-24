"""수집 데이터가 사는 곳. **경로의 단일 지점이다.**

`weeks.py`가 날짜 포맷의 단일 지점인 것과 같은 이유로 존재한다. 같은 경로를 네 파일이
제각기 계산하고 있으면 한 곳을 옮길 때 나머지가 조용히 예전 자리를 본다.

## 왜 저장소 밖으로 뺄 수 있어야 하는가

저장소는 공개다. 그런데 스냅샷은 소스의 **전체 카탈로그**이고 `raw/`는 응답 원본 그대로다.
공개 저장소에 두면 7장이 금지한 "소스 데이터를 통째로 재배포"가 된다 —
7장은 *페이지*를 말했지만 공개 저장소도 배포다.

그래서 이 디렉토리들은 비공개 저장소에 두고, 여기를 환경변수로 가리킨다.

## 발행물은 여기 해당하지 않는다

`data/weeks/`는 **요약 + 원문 링크**라 공개해도 되는 형태이고(7장), 웹 빌드가
저장소 상대 경로(`process.cwd()/../data/weeks`)로 읽으므로 옮기면 깨진다.
`publish.py`가 자기 경로를 따로 갖는 것은 그래서다. **여기에 넣지 말 것.**

## 값은 import 시점에 굳는다

환경변수는 프로세스 시작 전에 정해져 있어야 한다. 진입점이 전부
`python -m pipeline.<모듈>`이라 문제되지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 비면 저장소 안의 data/ 를 쓴다. 로컬에서 저장소 하나만 두고 돌릴 때의 기본값이다.
DATA_DIR = Path(os.environ.get("THIS_WEEK_TASTE_DATA_DIR") or (REPO_ROOT / "data"))

RAW_DIR = DATA_DIR / "raw"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DIFF_DIR = DATA_DIR / "diffs"
ENRICHED_DIR = DATA_DIR / "enriched"

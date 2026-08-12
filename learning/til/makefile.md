# Makefile

**프로젝트에서 할 수 있는 일들의 목록이자 진입점.**

원래는 1976년에 나온 C 프로그램 빌드 도구다. 지금도 빌드에 쓰지만, 이 프로젝트를 포함해
많은 저장소에서는 "명령어 모음집" 용도로 쓴다.

## 이 프로젝트의 예

```make
PY := .venv/bin/python

week: snapshot diff enrich publish

snapshot:
	$(PY) -m pipeline.snapshot --source $(SOURCE) $(WEEK_ARG)
```

`make week` 한 줄이 네 단계를 순서대로 돌린다.

## 셸 스크립트 대신 쓰는 이유

**1. 의존 관계를 선언한다**

```make
week: snapshot diff enrich publish
```

이 한 줄이 "week를 하려면 저 넷이 먼저"라는 뜻이다. make가 왼쪽에서 오른쪽으로
순서대로 실행하고, **중간에 하나라도 0이 아닌 종료 코드를 내면 거기서 멈춘다.**

이게 이 프로젝트에서는 그냥 편의가 아니다. `CLAUDE.md` 2.4가 "이상 상황이면 발행을
멈춘다"고 정했는데, `snapshot.py`가 이상을 감지하면 `sys.exit(1)`을 한다.
그러면 make가 diff 이후를 실행하지 않는다. **정책이 코드가 아니라 빌드 그래프로 강제된다.**

**2. 진입점이 한 곳에 모인다**

새로 온 사람이 `make help`만 보면 이 프로젝트로 뭘 할 수 있는지 안다.
README에 명령어를 적어두는 것과 다른 점은, Makefile은 **실제로 실행되는 것**이라
README처럼 낡지 않는다는 것이다.

**3. 환경 차이를 흡수한다**

`PY := .venv/bin/python` 한 줄로 가상환경 경로가 고정된다.
매번 `source .venv/bin/activate`를 기억할 필요가 없다.

## 문법에서 걸리는 것들

**들여쓰기는 반드시 탭이다.** 스페이스를 넣으면
`Makefile:12: *** missing separator. Stop.` 이 뜬다. make의 가장 악명 높은 함정이고,
에디터가 탭을 스페이스로 바꾸도록 설정돼 있으면 계속 당한다.

**각 줄은 별개의 셸에서 돈다.**

```make
bad:
	cd web
	npm run build      # ← web/ 이 아니라 원래 디렉토리에서 실행된다
```

`cd`의 효과가 다음 줄로 이어지지 않는다. 그래서 이 프로젝트는 `cd web && npm run build`처럼
한 줄로 붙여 쓴다.

**`.PHONY`**

```make
.PHONY: help setup test snapshot diff enrich publish week site clean-raw
```

make는 원래 "타깃 이름 = 만들어낼 파일 이름"이라고 가정한다. `test`라는 타깃이 있는데
디렉토리에 `test`라는 파일이 있으면, make는 "이미 있네"라며 아무것도 안 한다.
`.PHONY`는 "이건 파일 이름이 아니라 그냥 명령 이름"이라고 알려주는 선언이다.

이 프로젝트에는 실제로 `tests/` 디렉토리가 있어서, `.PHONY`가 없으면 위험할 뻔했다.

**변수 대입은 `:=` 와 `=` 가 다르다**

- `:=` 는 그 자리에서 한 번 평가한다 (단순 대입)
- `=` 는 쓰일 때마다 다시 평가한다 (지연 평가)

특별한 이유가 없으면 `:=` 를 쓴다. 예측 가능하고 빠르다.

## 대안

Python 프로젝트에서는 `just`, `task`, `invoke`, 혹은 `pyproject.toml`의 스크립트를
쓰기도 한다. Makefile의 장점은 **아무 데나 이미 깔려 있다는 것**이고,
단점은 문법이 낡고 함정이 많다는 것이다.

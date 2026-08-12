PY := .venv/bin/python
SOURCE ?= cu
WEEK ?=
WEEK_ARG := $(if $(WEEK),--week $(WEEK),)

.PHONY: help setup test snapshot diff enrich publish week site clean-raw

help:
	@echo "make setup      의존성 설치 (.venv)"
	@echo "make test       테스트 (네트워크 없이 동작)"
	@echo "make week       전 구간: 스냅샷 → diff → 보강 → 발행"
	@echo "make site       web 정적 빌드"
	@echo ""
	@echo "  SOURCE=cu     소스 지정 (기본 cu)"
	@echo "  WEEK=2026-W33 주차 지정 (기본 이번 주)"

setup:
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt
	cd web && npm install

test:
	$(PY) -m pytest tests/ -q

snapshot:
	$(PY) -m pipeline.snapshot --source $(SOURCE) $(WEEK_ARG)

diff:
	$(PY) -m pipeline.diff --source $(SOURCE) $(WEEK_ARG)

enrich:
	$(PY) -m pipeline.enrich --source $(SOURCE) $(WEEK_ARG)

publish:
	$(PY) -m pipeline.publish --source $(SOURCE) $(WEEK_ARG)

# 전 구간. snapshot이 이상을 감지하면 여기서 멈춘다 (2.4).
week: snapshot diff enrich publish

site:
	cd web && npm run build

# 90일 지난 원본 정리 (CLAUDE.md 2.5)
clean-raw:
	find data/raw -mindepth 1 -maxdepth 1 -type d -mtime +90 -print -exec rm -rf {} +

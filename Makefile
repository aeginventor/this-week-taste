PY := .venv/bin/python
SOURCE ?= cu
WEEK ?=
WEEK_ARG := $(if $(WEEK),--week $(WEEK),)

.PHONY: help setup test snapshot diff enrich publish week week-all site clean-raw

# 등록된 소스 전부. 표는 pipeline/sources.py 한 곳에 있다.
ALL_SOURCES = $(shell $(PY) -c "from pipeline import sources; print(' '.join(sources.known()))")

help:
	@echo "make setup      의존성 설치 (.venv)"
	@echo "make test       테스트 (네트워크 없이 동작)"
	@echo "make week       전 구간: 스냅샷 → diff → 보강 → 발행 (소스 1개)"
	@echo "make week-all   등록된 소스 전부. 하나가 실패해도 나머지는 계속 간다"
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

# 소스 격리 (2.3): 크롤러 하나가 실패해도 나머지는 정상 발행되어야 한다.
# 그래서 `week`를 소스별로 따로 부르고, 실패는 모아서 끝에 한 번에 알린다.
# 여기서 `&&`로 이으면 첫 실패에서 전부 멈춰 격리가 무의미해진다.
week-all:
	@failed=""; \
	for s in $(ALL_SOURCES); do \
		echo "════════ $$s ════════"; \
		$(MAKE) --no-print-directory week SOURCE=$$s WEEK=$(WEEK) || failed="$$failed $$s"; \
	done; \
	if [ -n "$$failed" ]; then \
		echo "‼️  실패한 소스:$$failed" >&2; exit 1; \
	fi; \
	echo "✅ 전 소스 완료: $(ALL_SOURCES)"

site:
	cd web && npm run build

# 90일 지난 원본 정리 (CLAUDE.md 2.5)
clean-raw:
	find data/raw -mindepth 1 -maxdepth 1 -type d -mtime +90 -print -exec rm -rf {} +

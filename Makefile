.DEFAULT_GOAL := help

# 上書き可能な変数（例: make start ENV=staging PORT=9090）
ENV     ?=
PORT    ?=
LINES   ?= all
FOLLOW  ?=
SETTINGS ?=
SECRET_ID ?=
PROJECT ?=
SERVICE_ACCOUNT ?=

RUN := uv run --active -- composer-local

.PHONY: help import import-dags start stop restart status logs sync auth remove test lint clean

help:
	@echo "利用可能なコマンド:"
	@echo ""
	@echo "  【基本操作】"
	@echo "  import        依存関係のインストールと pre-commit フックの設定（初回のみ）"
	@echo "  import-dags   DAG 開発用に apache-airflow を追加インストール（IDE補完用）"
	@echo "  start         環境を起動（無ければ自動作成）  例: make start PORT=9090"
	@echo "  stop          環境を停止"
	@echo "  restart       環境を再起動"
	@echo ""
	@echo "  【確認】"
	@echo "  status        環境の一覧と詳細を表示"
	@echo "  logs          ログを表示  例: make logs LINES=50 FOLLOW=1"
	@echo ""
	@echo "  【GCP 連携】"
	@echo "  auth          gcloud 認証  例: make auth SERVICE_ACCOUNT=sa@proj.iam.gserviceaccount.com"
	@echo "  sync          Cloud Composer から Variables を同期"
	@echo "                  例: make sync SETTINGS=1（設定同期） make sync SECRET_ID=xxx（SM経由）"
	@echo ""
	@echo "  【メンテナンス】"
	@echo "  remove        環境を削除"
	@echo "  test          テストを実行"
	@echo "  lint          lint とフォーマットチェック"
	@echo "  clean         キャッシュやビルド生成物を削除"
	@echo ""
	@echo "  クイックスタート: make import && make start"

import:
	@uv sync
	@uv run pre-commit install
	@echo "セットアップが完了しました。make start で環境を起動できます。"

import-dags:
	@uv sync --extra dag-dev
	@echo "DAG 開発用パッケージをインストールしました。"

start:
	@if [ ! -d ".venv" ]; then echo "依存関係をインストールしています..."; $(MAKE) import; fi
	@$(RUN) start $(ENV) $(if $(PORT),--port $(PORT))

stop:
	@$(RUN) stop $(ENV)

restart:
	@$(MAKE) stop || true
	@$(MAKE) start

status:
	@$(RUN) status $(ENV)

logs:
	@$(RUN) logs $(ENV) --max-lines $(LINES) $(if $(FOLLOW),--follow)

sync:
	@uv sync --extra gcp --quiet
	@$(RUN) sync $(ENV) \
		$(if $(SETTINGS),--settings) \
		$(if $(SECRET_ID),--secret-id $(SECRET_ID)) \
		$(if $(PROJECT),--project $(PROJECT))

auth:
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT))
	@gcloud auth application-default login \
		$(if $(SERVICE_ACCOUNT),--impersonate-service-account=$(SERVICE_ACCOUNT))
	@echo "認証が完了しました。"

remove:
	@$(RUN) remove $(ENV) --force --skip-confirmation

test:
	@uv run pytest tests/ -v

lint:
	@uv run --active -- ruff check composer_local/ tests/
	@uv run --active -- ruff format --check composer_local/ tests/
	@echo "lint OK"

clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} + || true
	@rm -rf build dist *.egg-info .pytest_cache .coverage || true

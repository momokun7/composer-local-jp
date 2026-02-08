.DEFAULT_GOAL := help

_DUMMY := $(shell uv run --active --quiet -- python scripts/load_make_settings.py > .make-settings.mk 2>/dev/null || true)
-include .make-settings.mk
.make-settings.mk:;

# composer_settings.py があれば使い、なければデフォルト値にフォールバック
ENV             ?= $(or $(_CS_ENV),my-local-env)
PORT            ?= $(or $(_CS_PORT),8080)
IMAGE           ?= $(or $(_CS_IMAGE),composer-3-airflow-2.10.5-build.13)
DAGS            ?= $(if $(_CS_DAGS),$(PWD)/$(_CS_DAGS),$(PWD)/dags)
DATABASE        ?= $(or $(_CS_DB),postgresql)
ADMIN_USERNAME  ?= $(or $(_CS_AU),admin)
ADMIN_PASSWORD  ?= $(or $(_CS_AP),admin)
ADMIN_EMAIL     ?= $(or $(_CS_AE),admin@example.com)
ADMIN_FIRSTNAME ?= $(or $(_CS_AF),Admin)
ADMIN_LASTNAME  ?= $(or $(_CS_AL),User)

# GCP 関連（オプション: 指定時のみ使用）
PROJECT         ?= $(_CS_PROJECT)
LOCATION        ?= $(_CS_LOCATION)
ENV_NAME        ?= $(_CS_ENV_NAME)
SECRET_ID       ?= $(_CS_SECRET_ID)
SERVICE_ACCOUNT ?= $(_CS_SA)

CONTAINER_NAME  ?= composer-local-dev

.PHONY: help import import-gcp start stop status logs \
        remove recreate \
        sync-vars sync-vars-sm setup-connections create-admin sync-settings \
        clean auth-user auth-sa

define check_gcp_settings
	@if [ -z "$(PROJECT)" ] || [ -z "$(LOCATION)" ] || [ -z "$(ENV_NAME)" ]; then \
		echo ""; \
		echo "GCP 設定が不足しています。以下のいずれかの方法で設定してください:"; \
		echo ""; \
		echo "  方法1: コマンドラインで指定"; \
		echo "    make $(MAKECMDGOALS) PROJECT=xxx LOCATION=xxx ENV_NAME=xxx"; \
		echo ""; \
		echo "  方法2: composer_settings.py で設定"; \
		echo "    cp composer_local/composer_settings.py.example composer_local/composer_settings.py"; \
		echo ""; \
		exit 1; \
	fi
endef

define check_env_exists
	@if [ ! -f "composer/$(ENV)/config.json" ]; then \
		echo ""; \
		echo "環境がまだ作成されていません。以下のコマンドで作成・起動できます:"; \
		echo "  make start"; \
		echo ""; \
		exit 1; \
	fi
endef

define ensure_env_exists
	@if [ ! -f "composer/$(ENV)/config.json" ]; then \
		echo "\033[0;34m環境が存在しません。作成しています...\033[0m"; \
		uv run --active -- composer-local create \
			$(if $(PROJECT),--project $(PROJECT)) \
			--from-image-version $(IMAGE) \
			--port $(PORT) \
			--dags-path $(DAGS) \
			--database $(DATABASE) \
			$(ENV) || exit 1; \
		echo ""; \
	fi
endef

define check_env_running
	@docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$(CONTAINER_NAME)-$(ENV)" || \
		(echo "" && \
		 echo "環境が起動していません。以下のコマンドで起動してください:" && \
		 echo "  make start" && \
		 echo "" && \
		 exit 1)
endef

help:
	@echo "利用可能なコマンド:"
	@echo ""
	@echo "  【基本操作】"
	@echo "  import            依存関係をインストール（初回のみ）"
	@echo "  import-gcp        GCP 連携パッケージを追加インストール"
	@echo "  start             環境を起動（初回は自動作成します）"
	@echo "  stop              環境を停止（コンテナは保持されます）"
	@echo ""
	@echo "  【環境管理】"
	@echo "  status            環境の設定とステータスを表示"
	@echo "  logs              ログを表示（例: make logs LINES=50）"
	@echo "  remove            環境を削除"
	@echo "  recreate          環境を削除して再作成・起動"
	@echo "  clean             キャッシュやビルド生成物を削除"
	@echo ""
	@echo "  【GCP 連携（要: PROJECT, LOCATION, ENV_NAME）】"
	@echo "  auth-user         GCP ユーザー認証（個人アカウント）"
	@echo "  auth-sa           GCP サービスアカウント認証"
	@echo "  sync-vars         Cloud Composer → ローカルへ Variables を同期"
	@echo "  sync-vars-sm      Secret Manager 経由で Variables を同期"
	@echo "  sync-settings     Cloud Composer の設定を同期"
	@echo ""
	@echo "  【メンテナンス】"
	@echo "  setup-connections  Google Cloud のデフォルト接続を設定"
	@echo "  create-admin       Airflow Admin ユーザーを作成"
	@echo ""
	@echo "  クイックスタート: make import && make start"
	@echo ""
	@echo "  【現在の設定値】"
	@echo "  ENV=$(ENV)  PORT=$(PORT)  IMAGE=$(IMAGE)  DATABASE=$(DATABASE)"
	@echo ""
	@echo "  【カスタマイズ例】"
	@echo "  make start PORT=9090          ポートを変更して起動"
	@echo "  make start ENV=staging        環境名を指定して起動"
	@echo "  make logs LINES=50            最新50行のログを表示"
	@echo ""
	@echo "  詳細: uv run -- composer-local --help"

import:
	@uv sync

import-gcp:
	@uv sync --extra gcp

start:
	$(call ensure_env_exists)
	@uv run --active -- composer-local start $(ENV)

stop:
	$(call check_env_exists)
	@uv run --active -- composer-local stop $(ENV)

remove:
	$(call check_env_exists)
	@uv run --active -- composer-local remove $(ENV) --force --skip-confirmation

recreate:
	@$(MAKE) remove
	@$(MAKE) start

status:
	$(call check_env_exists)
	@uv run --active -- composer-local describe $(ENV)

logs:
	$(call check_env_running)
	@uv run --active -- composer-local logs $(ENV) --max-lines $(or $(LINES),all)

sync-vars:
	$(call check_gcp_settings)
	$(call check_env_running)
	@uv run --active -- python composer_local/sync_variables.py \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env-name $(ENV_NAME) \
		--local-env-dir $(PWD)/composer/$(ENV) || exit 1

sync-vars-sm:
	@if [ -z "$(SECRET_ID)" ]; then \
		echo ""; \
		echo "SECRET_ID の指定が必要です。使用例:"; \
		echo "  make sync-vars-sm SECRET_ID=xxx"; \
		echo "  または composer_settings.py で SECRET_ID を設定"; \
		echo ""; \
		exit 1; \
	fi
	$(call check_gcp_settings)
	$(call check_env_running)
	@uv run --active -- python composer_local/export_composer_variables.py \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env-name $(ENV_NAME) \
		--secret-id $(SECRET_ID) || exit 1
	@uv run --active -- python composer_local/import_variables_to_local.py \
		--project $(PROJECT) \
		--secret-id $(SECRET_ID) \
		--local-env-dir $(PWD)/composer/$(ENV) \
		--airflow-url http://localhost:$(PORT) || exit 1

setup-connections:
	$(call check_env_running)
	@uv run --active -- composer-local run-airflow $(ENV) connections add google_cloud_default \
		--conn-type google_cloud_platform \
		--conn-extra '{"extra__google_cloud_platform__key_path": null, "extra__google_cloud_platform__keyfile_dict": null, "extra__google_cloud_platform__scope": "https://www.googleapis.com/auth/cloud-platform"}' \
		|| echo "接続 google_cloud_default は既に存在するか、作成に失敗しました"

create-admin:
	$(call check_env_running)
	@uv run --active -- composer-local run-airflow $(ENV) users create \
		--role Admin \
		--username $(or $(USERNAME),$(ADMIN_USERNAME)) \
		--password $(or $(PASSWORD),$(ADMIN_PASSWORD)) \
		--email $(or $(EMAIL),$(ADMIN_EMAIL)) \
		--firstname $(or $(FIRSTNAME),$(ADMIN_FIRSTNAME)) \
		--lastname $(or $(LASTNAME),$(ADMIN_LASTNAME)) \
		|| echo "管理者ユーザーは既に存在するか、作成に失敗しました"

sync-settings:
	$(call check_gcp_settings)
	@uv run --active -- composer-local sync-settings \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env $(ENV_NAME) \
		|| (echo "設定の同期に失敗しました。" && exit 1)

auth-user:
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT)) \
		|| (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login || (echo "アプリケーションデフォルト認証に失敗しました。" && exit 1)
	@echo "ユーザーによる認証が完了しました。"

auth-sa:
	@if [ -z "$(SERVICE_ACCOUNT)" ]; then \
		echo ""; \
		echo "SERVICE_ACCOUNT の指定が必要です。使用例:"; \
		echo "  make auth-sa SERVICE_ACCOUNT=xxx@yyy.iam.gserviceaccount.com"; \
		echo ""; \
		exit 1; \
	fi
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT)) \
		|| (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login \
		--impersonate-service-account=$(SERVICE_ACCOUNT) \
		|| (echo "サービスアカウント認証に失敗しました。" && exit 1)
	@echo "Composerのサービスアカウントによる認証が完了しました。"

clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} + || true
	@rm -rf build dist *.egg-info || true
	@rm -f .make-settings.mk

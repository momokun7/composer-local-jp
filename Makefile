# =============================================================================
# 設定読み込み
# =============================================================================

# composer_settings.py の値を1回の Python 実行で読み込む
# __init__.py の重い import chain をバイパスして直接読み込み（~0.03s）
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

# Docker コンテナ名プレフィックス（constants.py の CONTAINER_NAME と一致させる）
CONTAINER_NAME  ?= composer-local-dev

# =============================================================================
# .PHONY 宣言
# =============================================================================

.PHONY: help import import-gcp start stop status logs \
        remove recreate create \
        sync-vars sync-vars-sm setup-connections create-admin sync-settings \
        clean auth-user auth-sa

# =============================================================================
# ヘルパー関数
# =============================================================================

# GCP 設定の確認（sync-vars 等の GCP 連携ターゲット用）
define check_gcp_settings
	@if [ -z "$(PROJECT)" ] || [ -z "$(LOCATION)" ] || [ -z "$(ENV_NAME)" ]; then \
		echo ""; \
		echo "=========================================="; \
		echo " GCP 設定が不足しています！"; \
		echo "=========================================="; \
		echo ""; \
		echo " 以下のいずれかの方法で設定してください:"; \
		echo ""; \
		echo " 方法1: コマンドラインで指定"; \
		echo "   make $(MAKECMDGOALS) PROJECT=xxx LOCATION=xxx ENV_NAME=xxx"; \
		echo ""; \
		echo " 方法2: 設定ファイルを作成"; \
		echo "   cp composer_local/composer_settings.py.example \\"; \
		echo "      composer_local/composer_settings.py"; \
		echo "   # 編集して PROJECT_ID 等を設定"; \
		echo "=========================================="; \
		exit 1; \
	fi
endef

# 環境の存在を確認（config.json の有無で判定、CLI を経由しないため高速）
define check_env_exists
	@if [ ! -f "composer/$(ENV)/config.json" ]; then \
		echo ""; \
		echo "=========================================="; \
		echo " 環境が存在しません！"; \
		echo "=========================================="; \
		echo ""; \
		echo " 環境を作成・起動するには:"; \
		echo "   make start"; \
		echo "=========================================="; \
		exit 1; \
	fi
endef

# 環境が存在しない場合に自動作成
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

# 環境が起動していることを確認（Docker コンテナの実行状態で判定）
define check_env_running
	@docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$(CONTAINER_NAME)-$(ENV)" || \
		(echo "" && \
		 echo "エラー: 環境が起動していません。" && \
		 echo "" && \
		 echo "以下のコマンドで起動してください:" && \
		 echo "  make start" && \
		 echo "" && \
		 exit 1)
endef

# =============================================================================
# ターゲット: メインコマンド
# =============================================================================

help:
	@echo "利用可能なターゲット:"
	@echo ""
	@echo "  【基本操作（GCP 設定不要）】"
	@echo "  import            uv 環境にプロジェクトをインストール（uv sync）"
	@echo "  import-gcp        GCP 連携パッケージを追加インストール（uv sync --extra gcp）"
	@echo "  start             環境を起動（未作成なら自動作成、フォアグラウンド実行、Ctrl+Cで停止）"
	@echo "  stop              $(ENV) を停止（環境は残す）"
	@echo ""
	@echo "  【GCP 連携（要: PROJECT, LOCATION, ENV_NAME）】"
	@echo "  auth-user         GCP ユーザー認証（個人アカウント）"
	@echo "  auth-sa           GCP サービスアカウント認証（staging環境と同等の権限）"
	@echo "  sync-vars         staging Composer → ローカル Composer へVariablesを直接同期"
	@echo "  sync-vars-sm      staging Composer → Secret Manager → ローカル Composer へVariablesを同期"
	@echo "  sync-settings     Cloud Composer の設定を composer_settings.py に同期"
	@echo ""
	@echo "  【環境管理】"
	@echo "  status            $(ENV) の設定とステータスを表示"
	@echo "  logs              $(ENV) のログを表示（LINES=all または行数を指定）"
	@echo "  remove            環境を削除"
	@echo "  recreate          環境を削除して再作成・起動"
	@echo ""
	@echo "  【その他】"
	@echo "  setup-connections Google Cloud のデフォルト接続を設定（要: 環境起動）"
	@echo "  create-admin      Airflow Adminユーザーを作成（要: 環境起動、USERNAME/PASSWORD/EMAIL など指定可）"
	@echo "  clean             __pycache__ やビルド生成物を削除"
	@echo ""
	@echo "  【オプション引数】"
	@echo "  GCP 設定は composer_settings.py またはコマンドラインで指定:"
	@echo "    make sync-vars PROJECT=xxx LOCATION=xxx ENV_NAME=xxx"

import:
	@uv sync

import-gcp:
	@uv sync --extra gcp

start:
	$(call ensure_env_exists)
	@uv run --active -- python -c "from composer_local import files, environment as env; e=env.Environment.load_from_config(files.resolve_environment_path('$(ENV)'), None); e.start_foreground()"

# 後方互換: make create は make start のエイリアス
create: start

stop:
	@uv run --active -- python -c "from composer_local import files, environment as env; e=env.Environment.load_from_config(files.resolve_environment_path('$(ENV)'), None); e.stop()" \
		|| (echo "停止に失敗しました。" && exit 1)

# =============================================================================
# ターゲット: 環境管理
# =============================================================================

remove:
	$(call check_env_exists)
	@if [ -n "$(ENV)" ] && [ "$(ENV)" != "$(_CS_ENV)" ]; then \
		uv run --active -- composer-local remove $(ENV) --force --skip-confirmation || (echo "環境 $(ENV) の削除に失敗しました。" && exit 1); \
	else \
		uv run --active -- composer-local remove --force --skip-confirmation || (echo "現在のローカル環境の削除に失敗しました。" && exit 1); \
	fi

recreate:
	@$(MAKE) remove
	@$(MAKE) start

status:
	$(call check_env_exists)
	@uv run --active -- python -c "from composer_local import files, environment as env; e=env.Environment.load_from_config(files.resolve_environment_path('$(ENV)'), None); e.describe()"

logs:
	$(call check_env_running)
	@uv run --active -- composer-local logs $(ENV) --max-lines $(or $(LINES),all)

# =============================================================================
# ターゲット: GCP 連携・同期
# =============================================================================

sync-vars:
	$(call check_gcp_settings)
	$(call check_env_running)
	@uv run --active -- python composer_local/sync_variables.py \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env-name $(ENV_NAME) \
		--local-env-dir $(PWD)/composer/$(ENV) || exit 1

sync-vars-sm:
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

# =============================================================================
# ターゲット: 認証
# =============================================================================

auth-user:
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT)) \
		|| (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login || (echo "アプリケーションデフォルト認証に失敗しました。" && exit 1)
	@echo "ユーザーによる認証が完了しました。"

auth-sa:
	@if [ -z "$(SERVICE_ACCOUNT)" ]; then \
		echo ""; \
		echo "=========================================="; \
		echo " SERVICE_ACCOUNT が未指定です！"; \
		echo "=========================================="; \
		echo ""; \
		echo " 使用方法:"; \
		echo "   make auth-sa SERVICE_ACCOUNT=xxx@yyy.iam.gserviceaccount.com"; \
		echo "=========================================="; \
		exit 1; \
	fi
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT)) \
		|| (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login \
		--impersonate-service-account=$(SERVICE_ACCOUNT) \
		|| (echo "サービスアカウント認証に失敗しました。" && exit 1)
	@echo "Composerのサービスアカウントによる認証が完了しました。"

# =============================================================================
# ターゲット: クリーンアップ
# =============================================================================

clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} + || true
	@rm -rf build dist *.egg-info || true
	@rm -f .make-settings.mk

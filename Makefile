# =============================================================================
# 設定読み込み
# =============================================================================

# composer_settings.py の値を1回の Python 実行で読み込む
# __init__.py の重い import chain をバイパスして直接読み込み（~0.03s）
_DUMMY := $(shell uv run --active --quiet -- python scripts/load_make_settings.py > .make-settings.mk 2>/dev/null || true)
-include .make-settings.mk
.make-settings.mk:;

ENV             ?= $(_CS_ENV)
PORT            ?= $(_CS_PORT)
IMAGE           ?= $(_CS_IMAGE)
DAGS            ?= $(PWD)/$(_CS_DAGS)
PROJECT         ?= $(_CS_PROJECT)
LOCATION        ?= $(_CS_LOCATION)
ENV_NAME        ?= $(_CS_ENV_NAME)
SECRET_ID       ?= $(_CS_SECRET_ID)
SERVICE_ACCOUNT ?= $(_CS_SA)
ADMIN_USERNAME  ?= $(_CS_AU)
ADMIN_PASSWORD  ?= $(_CS_AP)
ADMIN_EMAIL     ?= $(_CS_AE)
ADMIN_FIRSTNAME ?= $(_CS_AF)
ADMIN_LASTNAME  ?= $(_CS_AL)

# =============================================================================
# .PHONY 宣言
# =============================================================================

.PHONY: help import create remove recreate start stop status logs \
        sync-vars setup-connections create-admin sync-settings clean \
        auth-user auth-sa wait-ready init-all

# =============================================================================
# ヘルパー関数
# =============================================================================

# 環境の存在を確認（存在しなければエラー終了）
define check_env_exists
	@if ! uv run --active -- composer-local describe $(ENV) > /dev/null 2>&1; then \
		echo ""; \
		echo "=========================================="; \
		echo " 環境が存在しません！"; \
		echo "=========================================="; \
		echo ""; \
		echo " 環境を作成してください:"; \
		echo "   make create   - 環境を作成"; \
		echo "=========================================="; \
		exit 1; \
	fi
endef

# バナー付きエラーメッセージを表示して終了
define fail_with_msg
	(echo "" && echo "==========================================" && echo " $(1)" && echo "==========================================" && echo "" && exit 1)
endef

# GCP認証
define check_auth
	@gcloud auth login --project $(PROJECT) || (echo "ユーザー認証に失敗しました。" && exit 1)
	@read -p "staging環境のサービスアカウントでDAGを実行しますか？(y/n) " confirm && \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		gcloud auth application-default login \
			--impersonate-service-account=$(SERVICE_ACCOUNT) \
			|| (echo "サービスアカウント認証に失敗しました。" && exit 1); \
	else \
		gcloud auth application-default login \
			|| (echo "アプリケーションデフォルト認証に失敗しました。" && exit 1); \
	fi
endef

# 環境作成
define create_env
	@if ! uv run --active -- composer-local create \
		--project $(PROJECT) \
		--from-image-version $(IMAGE) \
		--port $(PORT) \
		--dags-path $(DAGS) \
		--database $(_CS_DB) \
		$(ENV); then \
		echo ""; \
		echo "=========================================="; \
		echo " 環境の作成に失敗しました！"; \
		echo "=========================================="; \
		echo ""; \
		echo " エラーの詳細を確認してください:"; \
		echo "   make logs     - ログを表示"; \
		echo "   make status   - 環境の状態を表示"; \
		echo "=========================================="; \
		exit 1; \
	fi
	@echo ""
endef

# セットアップ完了バナー
define show_setup_complete
	@echo ""
	@echo "=========================================="
	@echo " ローカル環境のセットアップが完了しました！"
	@echo "=========================================="
	@echo ""
	@echo "\033[38;5;197m  ██████╗ ██████╗ ███╗   ███╗██████╗  ███████╗███████╗██████╗ \033[0m"
	@echo "\033[38;5;163m ██╔════╝██╔═══██╗████╗ ████║██╔══██╗██╔════╝██╔════╝██╔══██╗\033[0m"
	@echo "\033[38;5;164m ██║     ██║   ██║██╔████╔██║██████╔╝███████╗█████╗  ██████╔╝\033[0m"
	@echo "\033[38;5;165m ██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ╚════██║██╔══╝  ██╔══██╗\033[0m"
	@echo "\033[38;5;201m ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ███████║███████╗██║  ██║\033[0m"
	@echo "\033[38;5;200m  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝\033[0m"
	@echo ""
	@echo "\033[38;5;197m ██╗      ██████╗  ██████╗ █████╗ ██╗     \033[0m"
	@echo "\033[38;5;163m ██║     ██╔═══██╗██╔════╝██╔══██╗██║     \033[0m"
	@echo "\033[38;5;164m ██║     ██║   ██║██║     ███████║██║     \033[0m"
	@echo "\033[38;5;165m ██║     ██║   ██║██║     ██╔══██║██║     \033[0m"
	@echo "\033[38;5;201m ███████╗╚██████╔╝╚██████╗██║  ██║███████╗\033[0m"
	@echo "\033[38;5;200m ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝\033[0m"
	@echo ""
	@echo "\033[38;5;197m      ██╗██████╗ \033[0m"
	@echo "\033[38;5;163m      ██║██╔══██╗\033[0m"
	@echo "\033[38;5;164m      ██║██████╔╝\033[0m"
	@echo "\033[38;5;163m ██   ██║██╔═══╝ \033[0m"
	@echo "\033[38;5;201m  ╚████╔╝██║     \033[0m"
	@echo "\033[38;5;200m   ╚═══╝ ╚═╝     \033[0m"
	@echo ""
	@echo "\033[1;33m=========================================="
	@echo "   次のステップ"
	@echo "==========================================\033[0m"
	@echo ""
	@echo "\033[1;32m 1. 環境を起動:\033[0m"
	@echo "    \033[1;36mmake start\033[0m"
	@echo ""
	@echo "\033[1;32m 2. Airflow Web UI にアクセス:\033[0m"
	@echo "    \033[1;36m👉 http://localhost:$(PORT)\033[0m"
	@echo ""
	@echo "\033[1;33m==========================================\033[0m"
endef

# =============================================================================
# ターゲット: 環境セットアップ
# =============================================================================

help:
	@echo "利用可能なターゲット:"
	@echo ""
	@echo "  【環境セットアップ】"
	@echo "  import            uv 環境にプロジェクトをインストール（uv sync）"
	@echo "  create            ローカル環境を作成し、初期セットアップを自動実行"
	@echo "  start             $(ENV) を起動（フォアグラウンドで実行、Ctrl+Cで停止）"
	@echo "  stop              $(ENV) を停止（環境は残す）"
	@echo ""
	@echo "  【認証】"
	@echo "  auth-user         GCP ユーザー認証（個人アカウント）"
	@echo "  auth-sa           GCP サービスアカウント認証（staging環境と同等の権限）"
	@echo ""
	@echo "  【Variables同期】"
	@echo "  sync-vars         staging Composer → Secret Manager → ローカル Composer へVariablesを同期"
	@echo ""
	@echo "  【環境管理】"
	@echo "  status            $(ENV) の設定とステータスを表示"
	@echo "  logs              $(ENV) のログを表示（LINES=all または行数を指定）"
	@echo "  remove            環境を削除"
	@echo "  recreate          環境を削除して再作成"
	@echo ""
	@echo "  【その他】"
	@echo "  sync-settings     Cloud Composer の設定を composer_settings.py に同期"
	@echo "  setup-connections Google Cloud のデフォルト接続を設定（要: 環境起動）"
	@echo "  create-admin      Airflow Adminユーザーを作成（要: 環境起動、USERNAME/PASSWORD/EMAIL など指定可）"
	@echo "  init-all          起動をデタッチで行い、起動完了後に sync-vars → setup-connections → create-admin を順に実行"
	@echo "  clean             __pycache__ やビルド生成物を削除"

import:
	@uv sync

create:
	$(call check_auth)
	$(call create_env)
	@$(MAKE) init-all

start:
	$(call check_env_exists)
	@uv run --active -- composer-local start $(ENV)

stop:
	@uv run --active -- composer-local stop $(ENV) || (echo "停止に失敗しました。" && exit 1)

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
	@$(MAKE) create

status:
	$(call check_env_exists)
	@uv run --active -- composer-local describe $(ENV)

logs:
	@uv run --active -- composer-local logs $(ENV) --max-lines $(or $(LINES),all)

# =============================================================================
# ターゲット: 初期化・同期
# =============================================================================

wait-ready:
	@timeout=900; interval=5; \
	while [ $$timeout -gt 0 ]; do \
		if uv run --active -- composer-local describe $(ENV) | grep -q "状態: running"; then \
			exit 0; \
		fi; \
		sleep $$interval; \
		timeout=$$((timeout-interval)); \
	done; \
	echo "タイムアウト: Airflow が起動しませんでした"; exit 1

init-all:
	@uv run --active -- python -c "from composer_local import files, environment as env; p=files.resolve_environment_path('$(ENV)'); e=env.Environment.load_from_config(p, None); e.start()" \
		|| $(call fail_with_msg,環境の起動に失敗しました！)
	@$(MAKE) wait-ready        || $(call fail_with_msg,環境の起動待機がタイムアウトしました！)
	@$(MAKE) sync-vars         || $(call fail_with_msg,Variables の同期に失敗しました！)
	@$(MAKE) setup-connections || $(call fail_with_msg,接続のセットアップに失敗しました！)
	@$(MAKE) create-admin      || $(call fail_with_msg,管理者ユーザーの作成に失敗しました！)
	@$(MAKE) stop
	$(call show_setup_complete)

sync-vars:
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
	@uv run --active -- composer-local run-airflow $(ENV) connections add google_cloud_default \
		--conn-type google_cloud_platform \
		--conn-extra '{"extra__google_cloud_platform__key_path": null, "extra__google_cloud_platform__keyfile_dict": null, "extra__google_cloud_platform__scope": "https://www.googleapis.com/auth/cloud-platform"}' \
		|| echo "接続 google_cloud_default は既に存在するか、作成に失敗しました"

create-admin:
	@uv run --active -- composer-local run-airflow $(ENV) users create \
		--role Admin \
		--username $(or $(USERNAME),$(ADMIN_USERNAME)) \
		--password $(or $(PASSWORD),$(ADMIN_PASSWORD)) \
		--email $(or $(EMAIL),$(ADMIN_EMAIL)) \
		--firstname $(or $(FIRSTNAME),$(ADMIN_FIRSTNAME)) \
		--lastname $(or $(LASTNAME),$(ADMIN_LASTNAME)) \
		|| echo "管理者ユーザーは既に存在するか、作成に失敗しました"

sync-settings:
	@uv run --active -- composer-local sync-settings \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env $(ENV_NAME) \
		|| (echo "設定の同期に失敗しました。" && exit 1)

# =============================================================================
# ターゲット: 認証
# =============================================================================

auth-user:
	@gcloud auth login --project $(PROJECT) || (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login || (echo "アプリケーションデフォルト認証に失敗しました。" && exit 1)
	@echo "ユーザーによる認証が完了しました。"

auth-sa:
	@gcloud auth login --project $(PROJECT) || (echo "ユーザー認証に失敗しました。" && exit 1)
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

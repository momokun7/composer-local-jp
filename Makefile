# Variables - デフォルト値は composer_settings.py から取得
ENV ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.LOCAL_ENV_NAME)")
PORT ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.LOCAL_PORT)")
IMAGE ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.COMPOSER_IMAGE_VERSION)")
DAGS ?= $(PWD)/$(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.DAGS_PATH)")
PROJECT ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.PROJECT_ID)")
LOCATION ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.COMPOSER_LOCATION)")
ENV_NAME ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.COMPOSER_ENV_NAME)")
SECRET_ID ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.SECRET_ID)")
SERVICE_ACCOUNT ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.SERVICE_ACCOUNT)")

# Defaults for admin user creation - composer_settings.py から取得
ADMIN_USERNAME ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.ADMIN_USERNAME)")
ADMIN_PASSWORD ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.ADMIN_PASSWORD)")
ADMIN_EMAIL ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.ADMIN_EMAIL)")
ADMIN_FIRSTNAME ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.ADMIN_FIRSTNAME)")
ADMIN_LASTNAME ?= $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.ADMIN_LASTNAME)")


# Common functions
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

define check_env_status
	@echo "環境の状態を確認しています..."
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
	@if ! uv run --active -- composer-local describe $(ENV) | grep -q "状態: running"; then \
		echo ""; \
		echo "=========================================="; \
		echo " 環境が起動していません！"; \
		echo "=========================================="; \
		echo ""; \
		echo " 環境を起動してください:"; \
		echo "   make start    - 環境を起動"; \
		echo "   make logs     - ログを表示"; \
		echo "   make status   - 環境の状態を表示"; \
		echo ""; \
		echo " 💡 ヒント: Docker関連の問題で起動しない場合:"; \
		echo "   docker system prune -f  # 不要なDockerリソースを削除"; \
		echo "   make recreate           # 環境を再作成（深刻な問題の場合）"; \
		echo "=========================================="; \
		exit 1; \
	fi
endef

define create_env
	@if ! uv run --active -- composer-local create \
		--project $(PROJECT) \
		--from-image-version $(IMAGE) \
		--port $(PORT) \
		--dags-path $(DAGS) \
		--database $(shell uv run --active --quiet -- python -c "import composer_local.composer_settings as s; print(s.DATABASE_ENGINE)") \
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

.PHONY: help
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

.PHONY: import
import:
	@uv sync

.PHONY: create
create:
	$(call check_auth)
	$(call create_env)
	@$(MAKE) init-all

.PHONY: remove
remove:
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
	@if [ -n "$(ENV)" ] && [ "$(ENV)" != "$(shell uv run --active --quiet -- python -c "import importlib; m=importlib.import_module('composer_local.composer_settings'); print(getattr(m,'LOCAL_ENV_NAME','my-local-env'))")" ]; then \
		uv run --active -- composer-local remove $(ENV) --force --skip-confirmation || (echo "環境 $(ENV) の削除に失敗しました。" && exit 1); \
	else \
		uv run --active -- composer-local remove --force --skip-confirmation || (echo "現在のローカル環境の削除に失敗しました。" && exit 1); \
	fi

.PHONY: recreate
recreate:
	@make remove
	@make create

.PHONY: start
start:
	@echo "環境の存在を確認しています..."
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
	@uv run --active -- composer-local start $(ENV)

.PHONY: wait-ready
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

.PHONY: init-all
init-all:
	@uv run --active -- python -c "from composer_local import files, environment as env; p=files.resolve_environment_path('$(ENV)'); e=env.Environment.load_from_config(p, None); e.start()" || \
		(echo "" && \
		 echo "==========================================" && \
		 echo " 環境の起動に失敗しました！" && \
		 echo "==========================================" && \
		 echo "" && exit 1)
	@$(MAKE) wait-ready || \
		(echo "" && \
		 echo "==========================================" && \
		 echo " 環境の起動待機がタイムアウトしました！" && \
		 echo "==========================================" && \
		 echo "" && exit 1)
	@$(MAKE) sync-vars || \
		(echo "" && \
		 echo "==========================================" && \
		 echo " Variables の同期に失敗しました！" && \
		 echo "==========================================" && \
		 echo "" && exit 1)
	@$(MAKE) setup-connections || \
		(echo "" && \
		 echo "==========================================" && \
		 echo " 接続のセットアップに失敗しました！" && \
		 echo "==========================================" && \
		 echo "" && exit 1)
	@$(MAKE) create-admin || \
		(echo "" && \
		 echo "==========================================" && \
		 echo " 管理者ユーザーの作成に失敗しました！" && \
		 echo "==========================================" && \
		 echo "" && exit 1)
	@$(MAKE) stop
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

.PHONY: stop
stop:
	@uv run --active -- composer-local stop $(ENV) || (echo "停止に失敗しました。" && exit 1)

.PHONY: status
status:
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
	@uv run --active -- composer-local describe $(ENV)

.PHONY: logs
logs:
	@uv run --active -- composer-local logs $(ENV) --max-lines $(or $(LINES),all)

.PHONY: sync-vars
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

.PHONY: setup-connections
setup-connections:
	@uv run --active -- composer-local run-airflow $(ENV) connections add google_cloud_default \
		--conn-type google_cloud_platform \
		--conn-extra '{"extra__google_cloud_platform__key_path": null, "extra__google_cloud_platform__keyfile_dict": null, "extra__google_cloud_platform__scope": "https://www.googleapis.com/auth/cloud-platform"}' \
		|| echo "接続 google_cloud_default は既に存在するか、作成に失敗しました"

.PHONY: create-admin
create-admin:
	@uv run --active -- composer-local run-airflow $(ENV) users create \
		--role Admin \
		--username $(or $(USERNAME),$(ADMIN_USERNAME)) \
		--password $(or $(PASSWORD),$(ADMIN_PASSWORD)) \
		--email $(or $(EMAIL),$(ADMIN_EMAIL)) \
		--firstname $(or $(FIRSTNAME),$(ADMIN_FIRSTNAME)) \
		--lastname $(or $(LASTNAME),$(ADMIN_LASTNAME)) \
		|| echo "管理者ユーザーは既に存在するか、作成に失敗しました"

.PHONY: sync-settings
sync-settings:
	@uv run --active -- composer-local sync-settings \
		--project $(PROJECT) \
		--location $(LOCATION) \
		--env $(ENV_NAME) \
		|| (echo "設定の同期に失敗しました。" && exit 1)

.PHONY: clean
clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} + || true
	@rm -rf build dist *.egg-info || true

.PHONY: auth-user
auth-user:
	@gcloud auth login --project $(PROJECT) || (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login || (echo "アプリケーションデフォルト認証に失敗しました。" && exit 1)
	@echo "ユーザーによる認証が完了しました。"

.PHONY: auth-sa
auth-sa:
	@gcloud auth login --project $(PROJECT) || (echo "ユーザー認証に失敗しました。" && exit 1)
	@gcloud auth application-default login \
		--impersonate-service-account=$(SERVICE_ACCOUNT) \
		|| (echo "サービスアカウント認証に失敗しました。" && exit 1)
	@echo "Composerのサービスアカウントによる認証が完了しました。"

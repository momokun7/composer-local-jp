#!/usr/bin/env python3
"""
GCP 統合テストスクリプト

実際の GCP プロジェクト・サービスアカウントを使って、
GCP 連携機能が正しく動作するかを段階的に検証します。

使い方:
  # 全テスト実行
  uv run python scripts/test_gcp_integration.py

  # 特定のステップのみ
  uv run python scripts/test_gcp_integration.py --step auth
  uv run python scripts/test_gcp_integration.py --step composer
  uv run python scripts/test_gcp_integration.py --step secret-manager
  uv run python scripts/test_gcp_integration.py --step sync-vars
  uv run python scripts/test_gcp_integration.py --step sync-settings
  uv run python scripts/test_gcp_integration.py --step docker

前提条件:
  - gcloud CLI がインストール済み
  - gcloud auth login 済み（またはサービスアカウント認証済み）
  - composer_settings.py の GCP セクションが設定済み
  - make import-gcp 済み
"""

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 表示ヘルパー
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def header(title: str):
    print(f"\n{'='*60}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{'='*60}")


def ok(msg: str):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}[NG]{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}[--]{RESET} {msg}")


def info(msg: str):
    print(f"  {BLUE}[..]{RESET} {msg}")


# ---------------------------------------------------------------------------
# Step 1: 設定ファイルの検証
# ---------------------------------------------------------------------------

def test_settings() -> dict:
    """composer_settings.py の GCP 設定を検証する。"""
    header("Step 1: composer_settings.py の検証")

    results = {"passed": True, "settings": {}}

    try:
        from composer_local import composer_settings as settings
    except ImportError as e:
        fail(f"composer_settings.py の読み込みに失敗: {e}")
        results["passed"] = False
        return results

    checks = {
        "PROJECT_ID": "GCP プロジェクト ID",
        "COMPOSER_LOCATION": "Composer ロケーション",
        "COMPOSER_ENV_NAME": "Composer 環境名",
    }

    for attr, desc in checks.items():
        value = getattr(settings, attr, None)
        if value and value not in ("", "your-staging-project-id", "your-composer-env-name"):
            ok(f"{desc}: {value}")
            results["settings"][attr] = value
        else:
            fail(f"{desc} が未設定です（{attr}）")
            results["passed"] = False

    # オプション設定
    optional = {
        "SERVICE_ACCOUNT": "サービスアカウント",
        "SECRET_ID": "Secret Manager シークレット ID",
    }
    for attr, desc in optional.items():
        value = getattr(settings, attr, None)
        if value and value not in ("", "your-secret-id", "your-sa@your-project.iam.gserviceaccount.com"):
            ok(f"{desc}: {value}")
            results["settings"][attr] = value
        else:
            warn(f"{desc} が未設定（オプション）")

    return results


# ---------------------------------------------------------------------------
# Step 2: GCP 認証の検証
# ---------------------------------------------------------------------------

def test_auth() -> dict:
    """gcloud 認証が有効かを検証する。"""
    header("Step 2: GCP 認証の検証")

    results = {"passed": True}

    # gcloud コマンドの存在確認
    try:
        version = subprocess.run(
            ["gcloud", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        first_line = version.stdout.strip().split("\n")[0]
        ok(f"gcloud CLI: {first_line}")
    except FileNotFoundError:
        fail("gcloud CLI が見つかりません。Google Cloud SDK をインストールしてください")
        results["passed"] = False
        return results
    except subprocess.TimeoutExpired:
        fail("gcloud --version がタイムアウトしました")
        results["passed"] = False
        return results

    # アクティブアカウント
    try:
        account = subprocess.run(
            ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        if account:
            ok(f"認証アカウント: {account}")
        else:
            fail("アクティブな認証アカウントがありません。'gcloud auth login' を実行してください")
            results["passed"] = False
    except subprocess.CalledProcessError:
        fail("認証情報の取得に失敗しました")
        results["passed"] = False

    # プロジェクト設定
    try:
        project = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        if project:
            ok(f"gcloud デフォルトプロジェクト: {project}")
        else:
            warn("gcloud のデフォルトプロジェクトが未設定（composer_settings.py の設定が使われます）")
    except subprocess.CalledProcessError:
        warn("gcloud プロジェクト設定の取得に失敗")

    # アクセストークン取得
    try:
        subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True, timeout=15,
        )
        ok("アクセストークンの取得に成功")
    except subprocess.CalledProcessError:
        fail("アクセストークンの取得に失敗。認証が期限切れの可能性があります")
        results["passed"] = False

    # Application Default Credentials
    try:
        subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, check=True, timeout=15,
        )
        ok("Application Default Credentials (ADC) が有効")
    except subprocess.CalledProcessError:
        warn("ADC が未設定。Secret Manager 連携には 'gcloud auth application-default login' が必要です")

    return results


# ---------------------------------------------------------------------------
# Step 3: Composer 環境への接続テスト
# ---------------------------------------------------------------------------

def test_composer(settings: dict) -> dict:
    """Cloud Composer 環境に接続できるか検証する。"""
    header("Step 3: Cloud Composer 環境への接続テスト")

    results = {"passed": True}

    project = settings.get("PROJECT_ID")
    location = settings.get("COMPOSER_LOCATION")
    env_name = settings.get("COMPOSER_ENV_NAME")

    if not all([project, location, env_name]):
        fail("PROJECT_ID, COMPOSER_LOCATION, COMPOSER_ENV_NAME が必要です")
        results["passed"] = False
        return results

    info(f"Composer 環境: {project}/{location}/{env_name}")

    # Composer API 経由で環境情報を取得
    try:
        from composer_local.sync_settings import fetch_composer_env_details

        details = fetch_composer_env_details(project, location, env_name)
        ok(f"環境名: {details['env_name']}")
        ok(f"イメージバージョン: {details['image_version']}")
        ok(f"Python バージョン: {details.get('python_version', '未設定')}")
        results["composer_details"] = details
    except ImportError:
        fail("GCP パッケージが未インストールです。'make import-gcp' を実行してください")
        results["passed"] = False
    except Exception as e:
        fail(f"Composer 環境への接続に失敗: {e}")
        results["passed"] = False

    return results


# ---------------------------------------------------------------------------
# Step 4: Secret Manager テスト
# ---------------------------------------------------------------------------

def test_secret_manager(settings: dict) -> dict:
    """Secret Manager への接続を検証する。"""
    header("Step 4: Secret Manager 接続テスト")

    results = {"passed": True}

    project = settings.get("PROJECT_ID")
    secret_id = settings.get("SECRET_ID")

    if not project:
        fail("PROJECT_ID が必要です")
        results["passed"] = False
        return results

    if not secret_id:
        warn("SECRET_ID が未設定のためスキップします")
        results["passed"] = None  # スキップ
        return results

    info(f"Secret: projects/{project}/secrets/{secret_id}")

    try:
        from composer_local.secret_manager_sync import SecretManagerSync

        sync = SecretManagerSync(project_id=project, secret_id=secret_id)

        # Secret の読み取りテスト
        raw_value = sync.get_secret_value()
        variables = json.loads(raw_value)

        if isinstance(variables, dict):
            ok(f"Secret から {len(variables)} 件の Variables を取得")
            # 最初の3つのキーだけ表示（値は表示しない）
            keys = list(variables.keys())[:3]
            if keys:
                info(f"  キー例: {', '.join(keys)}{'...' if len(variables) > 3 else ''}")
        else:
            warn("Secret の値が JSON オブジェクトではありません")

    except ImportError:
        fail("GCP パッケージが未インストールです。'make import-gcp' を実行してください")
        results["passed"] = False
    except Exception as e:
        error_str = str(e).lower()
        if "not found" in error_str or "does not exist" in error_str:
            warn(f"Secret '{secret_id}' が存在しません（初回は export-vars で作成されます）")
            results["passed"] = None
        elif "destroyed" in error_str:
            warn(f"Secret '{secret_id}' の全バージョンが DESTROYED 状態です（sync-vars-sm で新しいバージョンが作成されます）")
            results["passed"] = None
        else:
            fail(f"Secret Manager への接続に失敗: {e}")
            results["passed"] = False

    return results


# ---------------------------------------------------------------------------
# Step 5: Variables 同期テスト（読み取りのみ）
# ---------------------------------------------------------------------------

def test_sync_vars(settings: dict) -> dict:
    """Composer から Variables を取得できるか検証する（書き込みはしない）。"""
    header("Step 5: Variables 取得テスト（読み取りのみ）")

    results = {"passed": True}

    project = settings.get("PROJECT_ID")
    location = settings.get("COMPOSER_LOCATION")
    env_name = settings.get("COMPOSER_ENV_NAME")

    if not all([project, location, env_name]):
        fail("PROJECT_ID, COMPOSER_LOCATION, COMPOSER_ENV_NAME が必要です")
        results["passed"] = False
        return results

    try:
        from composer_local.secret_manager_sync import export_variables_via_gcloud

        info("gcloud 経由で Composer Variables を取得中...")
        variables = export_variables_via_gcloud(project, location, env_name)

        ok(f"{len(variables)} 件の Variables を取得")
        # キー名のみ表示（値はセキュリティのため非表示）
        keys = sorted(variables.keys())[:5]
        if keys:
            info(f"  キー例: {', '.join(keys)}{'...' if len(variables) > 5 else ''}")

    except Exception as e:
        fail(f"Variables の取得に失敗: {e}")
        info("  権限を確認してください: composer.environments.get")
        results["passed"] = False

    return results


# ---------------------------------------------------------------------------
# Step 6: sync-settings テスト（読み取りのみ）
# ---------------------------------------------------------------------------

def test_sync_settings(settings: dict) -> dict:
    """Composer 設定を取得できるか検証する（ファイル書き込みはしない）。"""
    header("Step 6: Composer 設定取得テスト（読み取りのみ）")

    results = {"passed": True}

    project = settings.get("PROJECT_ID")
    location = settings.get("COMPOSER_LOCATION")
    env_name = settings.get("COMPOSER_ENV_NAME")

    if not all([project, location, env_name]):
        fail("PROJECT_ID, COMPOSER_LOCATION, COMPOSER_ENV_NAME が必要です")
        results["passed"] = False
        return results

    try:
        from composer_local.sync_settings import fetch_composer_env_details

        details = fetch_composer_env_details(project, location, env_name)

        ok(f"イメージバージョン: {details['image_version']}")
        ok(f"Python バージョン: {details.get('python_version') or 'デフォルト'}")
        ok(f"環境名: {details['env_name']}")
        ok(f"ロケーション: {details['location']}")

        info("注意: このテストは読み取りのみです。composer_settings.py への書き込みは行いません")
        info("  実際に同期するには: make sync-settings")

    except Exception as e:
        fail(f"設定の取得に失敗: {e}")
        results["passed"] = False

    return results


# ---------------------------------------------------------------------------
# Step 7: Docker / ローカル環境テスト
# ---------------------------------------------------------------------------

def test_docker() -> dict:
    """Docker が動作しているか検証する。"""
    header("Step 7: Docker 環境の検証")

    results = {"passed": True}

    # Docker デーモン
    try:
        version = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        ok(f"Docker Engine: {version}")
    except FileNotFoundError:
        fail("docker コマンドが見つかりません")
        results["passed"] = False
        return results
    except subprocess.CalledProcessError:
        fail("Docker デーモンが起動していません。Docker Desktop を起動してください")
        results["passed"] = False
        return results

    # メモリ
    try:
        mem_info = subprocess.run(
            ["docker", "info", "--format", "{{.MemTotal}}"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        mem_gb = int(mem_info) / (1024**3)
        if mem_gb >= 4:
            ok(f"Docker メモリ: {mem_gb:.1f} GB")
        else:
            warn(f"Docker メモリ: {mem_gb:.1f} GB（4GB 以上を推奨）")
    except Exception:
        warn("Docker メモリ情報の取得に失敗")

    # 既存の composer コンテナ
    try:
        containers = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=composer-local", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        if containers:
            ok("既存の Composer コンテナ:")
            for line in containers.split("\n"):
                info(f"  {line}")
        else:
            info("Composer コンテナはまだありません（make start で作成されます）")
    except Exception:
        pass

    return results


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

STEPS = {
    "settings": ("設定ファイル", test_settings),
    "auth": ("GCP 認証", test_auth),
    "composer": ("Composer 接続", None),  # settings が必要
    "secret-manager": ("Secret Manager", None),
    "sync-vars": ("Variables 取得", None),
    "sync-settings": ("設定取得", None),
    "docker": ("Docker 環境", test_docker),
}


def main():
    parser = argparse.ArgumentParser(
        description="GCP 統合テスト: 実際の GCP 環境との接続を段階的に検証します",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
実行例:
  uv run python scripts/test_gcp_integration.py              # 全テスト
  uv run python scripts/test_gcp_integration.py --step auth   # 認証のみ
  uv run python scripts/test_gcp_integration.py --step docker # Docker のみ
        """,
    )
    parser.add_argument(
        "--step",
        choices=list(STEPS.keys()),
        help="特定のステップのみ実行",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}GCP 統合テスト{RESET}")
    print(f"{'─'*60}")

    results_summary = {}
    settings = {}

    def run_step(name, fn, **kwargs):
        result = fn(**kwargs)
        results_summary[name] = result
        return result

    if args.step:
        # 特定ステップのみ
        if args.step == "settings":
            run_step("settings", test_settings)
        elif args.step == "auth":
            run_step("auth", test_auth)
        elif args.step == "docker":
            run_step("docker", test_docker)
        elif args.step in ("composer", "secret-manager", "sync-vars", "sync-settings"):
            s = run_step("settings", test_settings)
            settings = s.get("settings", {})
            if not s["passed"]:
                fail("設定が不足しているため続行できません")
                sys.exit(1)
            if args.step == "composer":
                run_step("composer", test_composer, settings=settings)
            elif args.step == "secret-manager":
                run_step("secret-manager", test_secret_manager, settings=settings)
            elif args.step == "sync-vars":
                run_step("sync-vars", test_sync_vars, settings=settings)
            elif args.step == "sync-settings":
                run_step("sync-settings", test_sync_settings, settings=settings)
    else:
        # 全ステップ実行
        s = run_step("settings", test_settings)
        settings = s.get("settings", {})

        run_step("auth", test_auth)
        run_step("docker", test_docker)

        if settings.get("PROJECT_ID"):
            run_step("composer", test_composer, settings=settings)
            run_step("sync-settings", test_sync_settings, settings=settings)
            run_step("sync-vars", test_sync_vars, settings=settings)
            run_step("secret-manager", test_secret_manager, settings=settings)
        else:
            warn("\nGCP 設定が不足しているため、Composer/Secret Manager テストはスキップしました")

    # サマリー
    header("テスト結果サマリー")
    total = 0
    passed = 0
    failed = 0
    skipped = 0

    for name, result in results_summary.items():
        total += 1
        status = result.get("passed")
        if status is True:
            ok(f"{name}")
            passed += 1
        elif status is False:
            fail(f"{name}")
            failed += 1
        else:
            warn(f"{name}（スキップ）")
            skipped += 1

    print(f"\n  合計: {total}  成功: {GREEN}{passed}{RESET}  失敗: {RED}{failed}{RESET}  スキップ: {YELLOW}{skipped}{RESET}")

    if failed > 0:
        print(f"\n{RED}一部のテストが失敗しました。上記のエラーメッセージを確認してください。{RESET}")
        sys.exit(1)
    elif passed > 0:
        print(f"\n{GREEN}テストが完了しました。{RESET}")

    # 次のステップの案内
    if not settings.get("PROJECT_ID"):
        print(f"\n{YELLOW}次のステップ:{RESET}")
        print("  1. composer_settings.py の GCP セクションのコメントアウトを解除")
        print("  2. PROJECT_ID, COMPOSER_LOCATION, COMPOSER_ENV_NAME を設定")
        print("  3. このスクリプトを再実行")


if __name__ == "__main__":
    main()

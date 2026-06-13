# 軽量化リファクタリング設計書

日付: 2026-06-13
対象: composer-local-jp 全体
方針: 全方位スリム化（互換性は維持しない）

## 目的

「軽量でサクサク使える」ツールにする。具体的には以下の3点を改善する。

1. 起動・実行速度: `make import` と各 `make` コマンドの体感速度
2. CLI操作の簡素化: 覚える入口（Makeターゲット・CLIコマンド）の削減
3. コードベースの軽量化: コード量削減と構造の単純化
4. シークレット漏洩防止: シークレット・APIキーがコミットに乗らない多層防御

## 現状の問題

- `apache-airflow==2.10.5` がCLI本体の必須依存になっており、`make import`（uv sync）で数百MBのダウンロードが発生する。CLI・テストコードはどこも `airflow` をimportしていない（Airflowの実体はDockerコンテナ内で動く）
- Makefileが全コマンド実行時に `uv run python scripts/load_make_settings.py` をシェル起動しており、`make help` ですら遅い
- GCP連携が5ファイル約950行・Makeターゲット7個に分散している
- `Environment` クラスが3つの専用Mixin（DockerManager/HealthCheck/Initialization）に分割されており、再利用がないのにコードジャンプを強いる
- 入口が多い: Makeターゲット21個、CLIコマンド10個

## 設計

### 1. 依存関係の分離

```toml
dependencies = ["click>=8.1.8,<9.0.0", "docker>=7.0.0", "rich>=13.7.0"]

[project.optional-dependencies]
gcp = [
    "google-auth>=2.29.0,<3.0.0",
    "google-cloud-orchestration-airflow>=1.2.0",
    "google-cloud-artifact-registry>=1.2.0",
    "google-cloud-secret-manager>=2.0.0",
]
dag-dev = [
    "apache-airflow==2.10.5",
    "apache-airflow-providers-google>=14.0.0",
]
```

- `make import` はCLI + devツールのみをインストール（数秒）
- `make import-dags` で `uv sync --extra dag-dev`（IDE補完・DAGユニットテスト用、オプトイン）
- `dag-dev` のAirflowバージョンはコンテナイメージ（composer-3-airflow-2.10.5）と同一に固定する
- `sync` コマンドは `gcp` extra 未導入時に導入コマンドを含む明確なエラーを出す（既存 `require_gcp_*` の仕組みを流用）
- READMEに「IDE補完が効かない場合」のセクションを追加

### 2. GCP連携の統合

統合元（廃止）: `sync_variables.py` / `export_composer_variables.py` /
`import_variables_to_local.py` / `secret_manager_sync.py` / `sync_settings.py`

統合先: `gcp_sync.py` 1ファイル。

- standalone実行（`python composer_local/xxx.py`）は廃止し、CLI経由に一本化
- CLIコマンドは `composer-local sync` 1つに統合
  - `sync --vars`: Composer → ローカルへ Variables 同期（直接 or `--secret-id` 指定でSecret Manager経由）
  - `sync --settings`: Composer設定を composer_settings.py に同期
  - オプションなしは `--vars` と同等（最頻用途をデフォルトに）
- `utils.py` のGCP認証系関数（`get_auth_info` / `check_auth_validity` / `resolve_project_id` / `require_gcp_*` 等、約200行）を `gcp_sync.py` へ移動

### 3. Mixin解体

- `DockerManagerMixin` / `HealthCheckMixin` / `InitializationMixin` を解体
- Docker操作の純粋関数群を `docker_ops.py` に置き、`Environment` はそれを呼ぶ通常のクラスにする（コンポジション）
- `environment.py` + `docker_manager.py` + `health_check.py` + `initialization.py`（計約906行）→ `environment.py` + `docker_ops.py` の2ファイル約600行を目標

### 4. Makefile刷新（21 → 14ターゲット）

- `load_make_settings.py` のシェル起動を廃止。設定（環境名・ポート等）の解決はCLI側の責務に移し、Makefileは薄いラッパーにする
- 環境存在チェック・自動作成等のシェルロジックもCLI側へ移管

| 新ターゲット | 統合元 | 備考 |
|---|---|---|
| `help` | help | 静的echoのみ（Python起動なし） |
| `import` | import | CLI + devツールのみ |
| `import-dags` | import-gcp(改) | dag-dev extra |
| `start` | start | 環境がなければ自動作成 |
| `stop` | stop | |
| `restart` | recreate | |
| `status` | status + list/describe | |
| `logs` | logs | |
| `sync` | sync-vars / sync-vars-sm / sync-settings | VARS/SETTINGS等は引数で |
| `auth` | auth-user / auth-sa | SERVICE_ACCOUNT指定時はSA認証 |
| `remove` / `clean` | remove / clean | |
| `test` / `lint` | test / test-dags / test-gcp / lint / format | 開発者向け |

- `setup-connections` / `create-admin` は初回起動時の自動初期化（現InitializationMixinの処理）に吸収して廃止

### 5. CLI体系（10 → 7コマンド）

| 新コマンド | 統合元 |
|---|---|
| `start` | create + start（環境がなければ作成して起動） |
| `stop` | stop |
| `status` | list + describe（環境一覧 + 詳細） |
| `logs` | logs |
| `run` | run-airflow（短縮） |
| `sync` | sync-vars + sync-settings |
| `remove` | remove |

- `create` の `--from-source-environment` / `--from-image-version` 等のオプションは `start` に引き継ぐ
- グローバルオプション（`--verbose` / `--debug`）は維持

### 6. テスト・スクリプト

- テストを新構造に追従させる。GCP系テスト4ファイル（約1,370行）は `test_gcp_sync.py` に統合し、重複ケースを整理（全体約2,700行 → 約1,500行目標）
- `scripts/load_make_settings.py` は廃止
- `scripts/test_gcp_integration.py`（576行）は手動検証用の簡素なスクリプトに縮小する
- テスト実行による検証はユーザーが `make test` で行う（Claude側で自動実行しない）

### 7. ドキュメント

- README: 新コマンド体系・新クイックスタート・IDE補完セクションを反映
- docs/gcp-integration.md: `sync` / `auth` の新体系に書き換え

### 8. シークレット漏洩防止

シークレット・APIキーが絶対にコミットに乗らない環境を多層防御で作る。

現状の問題: `.pre-commit-config.yaml` は detect-secrets を `--baseline .secrets.baseline` 付きで設定しているが、`.secrets.baseline` が存在せずフックが壊れている。また `pre-commit install` が自動化されておらず、フック未導入のままコミットできる。

1. **コミット時スキャン（第一防衛線）**: detect-secrets を gitleaks（zricethezav/gitleaks、20k+ stars、活発にメンテ、Go製）に置き換える。baseline ファイル不要で運用が軽い。`detect-private-key` / `check-added-large-files` 等の基本フックは維持
2. **フック導入の自動化**: `make import` で `pre-commit install` を自動実行し、フック未導入状態をなくす
3. **CIスキャン（安全網）**: `ci.yml` に gitleaks ジョブを追加（`--no-commit` でフックを回避したコミットを検出）
4. **シークレット格納先の不変条件**: `sync` が書き込む Variables・Secret 由来のファイルは必ず gitignore 済みの `composer/` 配下に限定する。`composer_settings.py`（プロジェクトID等を含む）は gitignore 済みを維持し、コミットするのは `.example` のみ
5. **.gitignore 強化**: サービスアカウントキー等のパターンを追加（`*-key.json` / `service-account*.json` / `credentials*.json` / `variables*.json` / `.secrets.baseline`）
6. **pre-commit の軽量化**: black / isort フックを ruff-pre-commit（lint + format）に置き換え、Makefile の `format` も ruff format に統一（ツール削減）

## エラー処理

- `errors.py` の `catch_exceptions` デコレータ方式は維持
- gcp extra 未導入・gcloud 未認証時は、解決コマンドを含む日本語エラーメッセージを表示（既存方針を踏襲）

## 期待効果

| 指標 | Before | After（目標） |
|---|---|---|
| `make import` | 数分（Airflow全体DL） | 数秒 |
| `make` 各コマンドの起動オーバーヘッド | 毎回Python起動 | なし |
| 本体コード | 約3,000行・13ファイル | 約1,800行・8ファイル |
| 入口 | Make 21 + CLI 10 | Make 14 + CLI 7 |

## スコープ外

- Docker イメージ自体の軽量化・起動高速化（Composerイメージ準拠のため対象外）
- 新機能の追加
- 後方互換レイヤー（旧コマンド名のエイリアス等）は作らない

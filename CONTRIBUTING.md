# 貢献ガイド

このプロジェクトへの貢献をありがとうございます。このガイドに従い、円滑な開発をお願いします。

## 貢献の流れ

1. **Issue を作成する**
   - バグ報告や機能リクエストは、まず Issue を開いてください
   - タイトル、説明、期待される動作を明確に記載してください

2. **リポジトリをフォークする**
   - GitHub の「Fork」ボタンをクリック

3. **ローカルで開発用ブランチを作成**
   ```bash
   git checkout -b feature/issue-description
   ```
   - ブランチ名は `feature/`, `fix/`, `refactor/` などで始めてください

4. **変更をコミット**
   - コミットメッセージは日本語で、形式は以下に従います
   - 詳細は「コミットメッセージ形式」を参照

5. **Pull Request を作成**
   - PR タイトルと説明は日本語で記載してください
   - 関連する Issue を `Closes #123` の形式でリンク

## 開発環境のセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/composer-local-jp.git
cd composer-local-jp

# 依存パッケージのインストール
make import

# テスト実行（既存テストがある場合）
make test
```

## コーディング規約

### Python コード

- **バージョン**: Python 3.11 以上
- **コードスタイル**: PEP 8 に準拠
- **フォーマッタ**: `black` または `autopep8` の使用を推奨
- **型ヒント**: 可能な限り型ヒントを記載してください

### メッセージとドキュメント

- すべてのユーザー向けメッセージ、コメント、ドキュメントは日本語で記載
- エラーメッセージは明確で、ユーザーが解決方法を理解できるようにしてください

### セキュリティ

- 認証情報（APIキー、パスワード、GCP サービスアカウントキー）をコードに埋め込まない
- 環境変数または設定ファイル経由で読み込む
- 詳細は `.claude/CLAUDE.md` を参照

## テストの書き方

このプロジェクトでは [pytest](https://docs.pytest.org/) を使用してテストを記述します。

### 基本ルール

- テストファイルは `tests/` ディレクトリ配下に配置してください
- ファイル名は `test_*.py` の形式にしてください（例: `test_environment.py`）
- テスト関数名は `test_` で始めてください（例: `def test_create_environment():`）
- 新しい機能やバグ修正には、対応するテストを追加してください

### テストの実行

```bash
# 全テストを実行
make test

# 特定のファイルだけ実行
uv run pytest tests/test_environment.py -v

# 特定のテスト関数だけ実行
uv run pytest tests/test_environment.py::test_create_environment -v
```

### テストの例

```python
# tests/test_example.py
from composer_local import utils


def test_example_function():
    """関数の動作を説明するドキュメント文字列"""
    result = utils.some_function("input")
    assert result == "expected_output"
```

## CHANGELOG の更新ルール

ユーザーに影響のある変更を行った場合は、`CHANGELOG.md` を更新してください。

### 更新が必要なケース

- 新機能の追加（`feat`）
- バグ修正（`fix`）
- 破壊的変更
- 依存関係の重要な更新

### 更新が不要なケース

- ドキュメントのみの変更（`docs`）
- リファクタリング（`refactor`、動作変更なし）
- テストの追加・修正（`test`）
- コードスタイルの修正（`style`）

### 記載形式

`CHANGELOG.md` の `[Unreleased]` セクションに、以下の形式で追記してください:

```markdown
## [Unreleased]

### Added（追加）
- 新機能の説明

### Fixed（修正）
- バグ修正の説明

### Changed（変更）
- 既存機能の変更内容

### Removed（削除）
- 削除された機能
```

## コミットメッセージ形式

コミットメッセージは以下の形式で、日本語で記載してください:

```
<type>: <日本語の説明>

<詳細説明（必要な場合）>
```

### type の種類

- `feat`: 新機能の追加
- `fix`: バグ修正
- `refactor`: コードリファクタリング（動作変更なし）
- `docs`: ドキュメント更新
- `style`: コードスタイルの修正（機能変更なし）
- `test`: テストの追加・修正
- `chore`: ビルド、依存関係の更新など

### 例

```
feat: Makefile に new-env コマンドを追加

このコマンドで新しい環境を自動生成できます。

fix: environment.py の環境変数解析エラーを修正
```

## Pull Request のガイドライン

### PR 作成時の確認事項

- [ ] ブランチは最新の `main` から作成されているか
- [ ] コミットメッセージが形式に従っているか
- [ ] PR タイトルは明確で説明的か（日本語）
- [ ] PR 説明に目的、変更内容、テスト方法を記載したか
- [ ] コードに認証情報が含まれていないか
- [ ] `.gitignore` が適切に設定されているか
- [ ] 新規の機能には簡潔なテストまたはドキュメント更新が含まれているか

### PR タイトルの例

```
feat: GCP Variables 同期機能を追加
fix: Docker イメージビルドエラーを修正
refactor: environment.py の初期化ロジックを簡略化
```

## 質問やサポート

- 質問や懸念事項は Issue で相談してください
- PR の形式やルールが不明な場合は、遠慮なく質問してください

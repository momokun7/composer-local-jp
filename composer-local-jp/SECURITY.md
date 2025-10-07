# Security Policy

## セキュリティ脆弱性の報告

このプロジェクトでセキュリティ脆弱性を発見した場合は、以下の方法で報告してください。

### 報告方法

**重要: セキュリティ脆弱性は公開のIssueとして報告しないでください。**

以下のいずれかの方法で報告してください：

1. GitHubのSecurity Advisoriesを使用
   - リポジトリの「Security」タブから「Report a vulnerability」をクリック


### 報告に含めるべき情報

- 脆弱性の種類（例: SQL Injection, XSS, CSRF等）
- 脆弱性の場所（ファイル名、行番号）
- 再現手順
- 潜在的な影響
- 可能であれば、修正案


## セキュリティベストプラクティス

### 開発者向け

1. **機密情報の管理**
   - `composer_settings.py`は必ず`.gitignore`に追加されていることを確認
   - APIキー、パスワード、トークンをコードにハードコードしない
   - `.env`ファイルを使用する場合は必ず`.gitignore`に追加

2. **認証情報**
   - GCPサービスアカウントキーをリポジトリにコミットしない
   - `gcloud auth application-default login`を使用して認証

3. **依存関係の管理**
   - 定期的に`uv lock --upgrade`を実行して依存関係を更新
   - セキュリティアドバイザリを確認

### ユーザー向け

1. **初回セットアップ**
   ```bash
   # 設定ファイルをテンプレートからコピー
   cp composer_local/composer_settings.py.example composer_local/composer_settings.py

   # 自分の認証情報を設定
   # vi composer_local/composer_settings.py
   ```

2. **本番環境での使用禁止**
   - このツールはローカル開発・テスト環境専用です
   - 本番環境では使用しないでください

3. **定期的な更新**
   - 最新版への更新を推奨します
   - `git pull`後は依存関係も更新してください

## 既知の制限事項

- ローカル環境のAirflowは開発用途のみを想定
- Dockerコンテナは特権モードで実行される可能性があるため、信頼できる環境でのみ使用

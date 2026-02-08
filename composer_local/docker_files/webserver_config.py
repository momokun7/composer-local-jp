"""
開発環境専用: Airflow ログイン画面をスキップする設定

AUTH_ROLE_PUBLIC = "Admin" により、未認証ユーザーに Admin ロールを付与し、
ログインなしで Airflow Web UI にアクセスできるようにします。

警告: 本番環境では絶対に使用しないでください。
      この設定は localhost バインドのローカル開発環境専用です。
"""

AUTH_ROLE_PUBLIC = "Admin"

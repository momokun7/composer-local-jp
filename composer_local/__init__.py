# composer_local package
#
# 注意: ここで cli 等を import すると click, rich, GCP SDK 等の重い依存が
# すべて読み込まれ、パッケージの import に数秒かかる。
# 各モジュールは from composer_local import xxx で必要に応じて直接 import すること。

#!/bin/sh

set -xe

run_as_user=/home/airflow/run_as_user.sh

init_airflow() {
  $run_as_user mkdir -p ${AIRFLOW__CORE__DAGS_FOLDER}
  $run_as_user mkdir -p ${AIRFLOW__CORE__PLUGINS_FOLDER}
  $run_as_user mkdir -p ${AIRFLOW__CORE__DATA_FOLDER}

  if [ -f /var/local/setup_python_command.sh ]; then
      $run_as_user /var/local/setup_python_command.sh
  fi

  # uv がなければインストール（初回のみ、バイナリ直接DLで高速）
  if ! command -v uv > /dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh 2>/dev/null \
      || pip3 install --quiet uv
  fi

  # requirements が変更された場合のみインストールを実行
  req_hash=$(md5sum composer_requirements.txt 2>/dev/null | cut -d' ' -f1)
  cached_hash=""
  if [ -f /tmp/.composer_req_hash ]; then
    cached_hash=$(cat /tmp/.composer_req_hash)
  fi
  if [ "$req_hash" != "$cached_hash" ]; then
    # Docker イメージ内の site-packages に書き込み不可のファイルがあるため権限を修正
    sudo chmod -R u+w /opt/python3.11/lib/python3.11/site-packages/airflow/ 2>/dev/null || true
    sudo uv pip install --system -r composer_requirements.txt
    echo "$req_hash" > /tmp/.composer_req_hash
  fi

  # airflow version を高速取得（airflow コマンドのフル import を回避）
  airflow_version=$($run_as_user python3 -c "from importlib.metadata import version; print(version('apache-airflow'))" 2>/dev/null)
  if [ -z "$airflow_version" ]; then
    airflow_version=$(${run_as_user} airflow version | grep -o "^[0-9\.]*")
  fi

  # db migrate はバージョン変更時のみ実行（2回目以降スキップで大幅高速化）
  cached_db_version=""
  if [ -f /tmp/.airflow_db_version ]; then
    cached_db_version=$(cat /tmp/.airflow_db_version)
  fi
  if [ "$airflow_version" != "$cached_db_version" ]; then
    original_ifs="$IFS"
    IFS='.'
    set -- $airflow_version
    major="$1"
    minor="$2"
    IFS="$original_ifs"

    if [ "$major" -eq "2" ] && [ "$minor" -lt "7" ]; then
      $run_as_user airflow db init
    else
      $run_as_user airflow db migrate
    fi
    echo "$airflow_version" > /tmp/.airflow_db_version
  fi

  # webserver_config.py で AUTH_ROLE_PUBLIC='Admin' を設定済み（ログイン画面スキップ）
}

create_user() {
  local user_name="$1"
  local user_id="$2"

  local old_user_name
  old_user_name="$(whoami)"
  local old_user_id
  old_user_id="$(id -u)"

  echo "Adding user ${user_name}(${user_id})"
  sudo useradd -m -r -g airflow -G airflow --home-dir /home/airflow \
    -u "${user_id}" -o "${user_name}"

  echo "Updating the owner of the dirs owned by ${old_user_name}(${old_user_id}) to ${user_name}(${user_id})"
  sudo find /home -user "${old_user_id}" -exec chown -h "${user_name}" {} \;
  sudo find /var -user "${old_user_id}" -exec chown -h "${user_name}" {} \;
}

main() {
  mkdir -p /home/airflow/airflow
  sudo chown airflow:airflow /home/airflow/airflow

  # webserver_config.py を Airflow 設定ディレクトリに配置（ログイン画面スキップ）
  { cp /home/airflow/webserver_config.py /home/airflow/airflow/webserver_config.py && \
    chown airflow:airflow /home/airflow/airflow/webserver_config.py; } 2>/dev/null || true

  sudo chmod +x $run_as_user

  if [ "${COMPOSER_CONTAINER_RUN_AS_HOST_USER}" = "True" ]; then
    create_user "${COMPOSER_HOST_USER_NAME}" "${COMPOSER_HOST_USER_ID}" || true
    echo "ユーザー ${COMPOSER_HOST_USER_NAME}(${COMPOSER_HOST_USER_ID}) として Airflow を実行します"
  else
    echo "ユーザー airflow(999) として Airflow を実行します"
  fi

  init_airflow

  if [ ${AIRFLOW__SCHEDULER__STANDALONE_DAG_PROCESSOR} = "True" ]; then
    $run_as_user airflow dag-processor &
  fi

  $run_as_user airflow scheduler &
  $run_as_user airflow triggerer &
  exec $run_as_user airflow webserver
}

main "$@"

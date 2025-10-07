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

  $run_as_user pip3 install --upgrade -r composer_requirements.txt
  $run_as_user pip3 check

  airflow_version=$(${run_as_user} airflow version | grep -o "^[0-9\.]*")

  original_ifs="$IFS"
  IFS='.'
  set -- $airflow_version
  major="$1"
  minor="$2"
  patch="$3"
  IFS="$original_ifs"

  if [ "$major" -eq "2" ] && [ "$minor" -lt "7" ]; then
    $run_as_user airflow db init
  else
    $run_as_user airflow db migrate
  fi

  # Do NOT override AUTH_ROLE_PUBLIC. Keep default auth; no public admin.
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

#!/bin/sh

set -e

if [ "${COMPOSER_CONTAINER_RUN_AS_HOST_USER}" = "True" ]; then
    sudo -E -u "${COMPOSER_HOST_USER_NAME}" env ENV="${ENV}" PYTHONPATH="${PYTHONPATH}" PATH="${PATH}" "$@"
else
    exec "$@"
fi

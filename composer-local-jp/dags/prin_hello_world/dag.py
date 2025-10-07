from datetime import datetime, timedelta
import logging
from airflow import DAG
from airflow.operators.python import PythonOperator

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Create the DAG
dag = DAG(
    'print_hello_world',
    default_args=default_args,
    description='A simple hello world DAG',
    schedule_interval=None,
    catchup=False,
    tags=["local_test"],
)


# Define the function that will be executed
def print_hello_world():
    print("hello world")
    logging.info("こんにちは 世界")


# Create the task
hello_world_task = PythonOperator(
    task_id='print_hello_world',
    python_callable=print_hello_world,
    dag=dag,
)

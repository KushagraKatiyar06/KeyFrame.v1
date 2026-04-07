import os
from dotenv import load_dotenv
from celery import Celery
import ssl

load_dotenv()

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')


broker_use_ssl = {
    'ssl_cert_reqs': ssl.CERT_NONE
}


app = Celery(
    'keyframe_worker',
    broker=redis_url,
    backend=redis_url,
)

# celery configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_time_limit=300,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',  
    imports=(
        'orchestrator', 
    )
)


if __name__ == '__main__':
    app.start()
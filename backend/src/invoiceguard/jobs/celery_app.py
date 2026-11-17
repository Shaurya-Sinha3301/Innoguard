import ssl

from celery import Celery

from invoiceguard.config import settings

celery_app = Celery(
    "invoiceguard",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["invoiceguard.jobs.tasks"],
)

# Hosted Redis (for example Upstash) uses rediss:// and needs TLS settings.
if settings.redis_url.startswith("rediss://"):
    tls = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    celery_app.conf.broker_use_ssl = tls
    celery_app.conf.redis_backend_use_ssl = tls

celery_app.conf.task_acks_late = True

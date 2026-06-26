from celery import shared_task

from .models import GeneratedImage, GenerationJob
from .services import generate_image, refund_credit


@shared_task
def generate_image_task(image_id):
    image = GeneratedImage.objects.select_related("job", "prompt", "job__shop").get(pk=image_id)
    try:
        generate_image(image)
    except Exception as exc:
        image.status = GeneratedImage.Status.FAILED
        image.error_message = str(exc)
        image.save(update_fields=["status", "error_message"])
        refund_credit(image.job)
    finally:
        job = GenerationJob.objects.get(pk=image.job_id)
        statuses = list(job.images.values_list("status", flat=True))
        if any(status in {GeneratedImage.Status.PENDING, GeneratedImage.Status.PROCESSING} for status in statuses):
            return
        completed = statuses.count(GeneratedImage.Status.COMPLETED)
        if completed == len(statuses):
            job.status = GenerationJob.Status.COMPLETED
        elif completed:
            job.status = GenerationJob.Status.PARTIAL
        else:
            job.status = GenerationJob.Status.FAILED
        job.save(update_fields=["status"])


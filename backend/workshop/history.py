"""Earlier job cards that used the same serial, newest id first, capped at 20."""

from __future__ import annotations

from django.utils import timezone

from .models import JobCard, JobCardLine

HISTORY_CAP = 20


def serial_history(job: JobCard) -> list[dict]:
    serial_ids = []
    for line in job.lines.all():
        if line.serial_id and line.serial_id not in serial_ids:
            serial_ids.append(line.serial_id)
    groups = []
    for serial_id in serial_ids:
        job_ids = (
            JobCardLine.objects.filter(
                company_id=job.company_id, serial_id=serial_id, job_id__lt=job.pk,
            )
            .values_list("job_id", flat=True)
            .distinct()
        )
        earlier = JobCard.objects.filter(company_id=job.company_id, pk__in=job_ids).order_by("-id")
        total = earlier.count()
        rows = list(earlier[:HISTORY_CAP])
        groups.append({
            "serial_id": serial_id,
            "capped": total > HISTORY_CAP,
            "jobs": [
                {
                    "id": row.id,
                    "number": row.number,
                    "status": row.status,
                    "date": timezone.localtime(row.created_at).date().isoformat(),
                }
                for row in rows
            ],
        })
    return groups

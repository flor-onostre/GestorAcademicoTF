from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import ActivityLog, BulkUploadRequest


def enqueue_ai_processing(upload_request: BulkUploadRequest):
    """
    Placeholder para el pipeline de IA.
    Por ahora solo marca el registro como \"en procesamiento\" y registra una notificación.
    """
    upload_request.status = BulkUploadRequest.Status.PROCESSING
    upload_request.notes = upload_request.notes or ""
    upload_request.notes += (
        "\n" if upload_request.notes else ""
    ) + str(_("Procesamiento automático pendiente de integración con el servicio de IA."))
    upload_request.processed_at = timezone.now()
    upload_request.save(update_fields=["status", "notes", "processed_at"])

    ActivityLog.objects.create(
        message=_(
            f"Se recibió una planilla de {upload_request.get_kind_display()} para {upload_request.section}."
        )
    )

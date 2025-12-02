from datetime import datetime, timedelta

from django.shortcuts import render
from django.utils import timezone
from django.contrib.auth.decorators import login_required

from accounts.decorators import admin_required


def _week_bounds(base_date):
    start = base_date - timedelta(days=base_date.weekday())
    end = start + timedelta(days=6)
    return start, end


@login_required
@admin_required
def assignment_week_view(request):
    """Renderiza la página de cronograma semanal con JS que consume las APIs JSON."""
    ref_str = request.GET.get("fecha")
    try:
        base_date = datetime.strptime(ref_str, "%Y-%m-%d").date() if ref_str else timezone.localdate()
    except Exception:
        base_date = timezone.localdate()
    week_start, week_end = _week_bounds(base_date)
    return render(
        request,
        "asignacion/semana.html",
        {
            "title": "Distribución áulica (semanal)",
            "week_start": week_start,
            "week_end": week_end,
            "base_date": base_date,
        },
    )

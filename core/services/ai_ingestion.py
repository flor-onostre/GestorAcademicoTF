import csv
import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from core.models import ActivityLog, AttendanceRecord, BulkUploadRequest


def call_local_llm(prompt: str, model: str = "llama3"):
    """
    Invoca el LLM local de Ollama y devuelve el texto de respuesta.
    Requiere que el servicio Ollama est? corriendo en localhost:11434.
    """
    import requests  # lazy import

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def _parse_llm_json(text: str):
    """
    Acepta respuestas con o sin fences ```json ... ``` y devuelve la carga JSON.
    Devuelve [] si no puede parsear.
    """
    if not text:
        return []
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Elimina fences tipo ```json ... ```
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except Exception:
        return []


def _read_rows(file_path: Path):
    ext = file_path.suffix.lower()
    if ext in {".csv", ".txt"}:
        # Detectar delimitador (coma o punto y coma) y manejar BOM
        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            except Exception:
                dialect = csv.get_dialect("excel")
            reader = csv.DictReader(f, dialect=dialect)
            return list(reader)
    if ext in {".xlsx", ".xls"}:
        try:
            import openpyxl  # type: ignore
        except ImportError:
            raise RuntimeError("Falta instalar openpyxl para leer planillas Excel.")
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        # Toma la hoja con más filas no vacías
        ws = max(wb.worksheets, key=lambda sh: sh.max_row or 0)
        # Detectar fila de encabezados (primera fila con al menos un valor)
        header_row = None
        for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=ws.max_row), start=1):
            if any(cell.value is not None for cell in row):
                header_row = idx
                break
        if header_row is None:
            return []
        headers = [
            (str(c.value).strip() if c.value is not None else "")
            for c in next(ws.iter_rows(min_row=header_row, max_row=header_row))
        ]
        rows = []
        for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
            values = {headers[i]: (row[i].value if i < len(headers) else None) for i in range(len(headers))}
            # Ignorar filas totalmente vacías
            if not any(v not in (None, "") for v in values.values()):
                continue
            rows.append(values)
        return rows
    raise RuntimeError(f"Formato no soportado: {ext}")


def _map_status(value: str):
    if not value:
        return AttendanceRecord.Status.PRESENT
    v = str(value).strip().lower()
    if v in {"p", "presente", "present"}:
        return AttendanceRecord.Status.PRESENT
    if v in {"a", "ausente", "absent"}:
        return AttendanceRecord.Status.ABSENT
    if v in {"j", "justificada", "justified"}:
        return AttendanceRecord.Status.JUSTIFIED
    if v in {"t", "tarde", "late"}:
        return AttendanceRecord.Status.LATE
    return AttendanceRecord.Status.PRESENT


def _rows_from_llm(text: str):
    """
    Usa el LLM local para normalizar a una lista de dicts con campos
    dni, email, status, comentario. Devuelve [] en caso de error.
    """
    prompt = (
        "Devuelve un JSON array con objetos {dni,email,status,comentario}. "
        "status usa P (presente), A (ausente), J (justificada), T (tarde). "
        "Si falta email o dni, deja \"\". Texto de origen:\n\n"
        f"{text}"
    )
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if api_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=api_key)
            model_name = getattr(settings, "GEMINI_MODEL", "models/gemini-2.5-flash")
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(
                prompt,
                safety_settings=None,
                generation_config={"response_mime_type": "application/json"},
            )
            payload = getattr(resp, "text", None)
            if not payload and getattr(resp, "candidates", None):
                first = resp.candidates[0].content.parts[0]
                payload = getattr(first, "text", None) or getattr(first, "data", None)
            return _parse_llm_json(payload or "")
        except Exception:
            pass
    try:
        response = call_local_llm(prompt)
        return _parse_llm_json(response)
    except Exception:
        return []


def _rows_from_llm_students(headers: str, sample_rows: str):
    """
    Usa el LLM para mapear columnas heterogéneas a campos de alumno:
    dni, first_name, last_name, email, legajo, phone, address, emergency_contact, locality, nationality.
    Devuelve [] si falla.
    """
    prompt = (
        "Devuelve un JSON array con objetos que tengan estas claves: "
        "{dni, first_name, last_name, email, legajo, phone, address, emergency_contact, locality, nationality}. "
        "Completa solo lo que encuentres, si falta algún dato deja \"\". No inventes. "
        "Los encabezados y filas de ejemplo son:\n"
        f"Encabezados: {headers}\n"
        f"Filas de ejemplo:\n{sample_rows}\n"
    )
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if api_key:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=api_key)
            model_name = getattr(settings, "GEMINI_MODEL", "models/gemini-2.5-flash")
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(
                prompt,
                safety_settings=None,
                generation_config={"response_mime_type": "application/json"},
            )
            payload = getattr(resp, "text", None)
            if not payload and getattr(resp, "candidates", None):
                first = resp.candidates[0].content.parts[0]
                payload = getattr(first, "text", None) or getattr(first, "data", None)
            return _parse_llm_json(payload or "")
        except Exception:
            pass
    try:
        response = call_local_llm(prompt)
        return _parse_llm_json(response)
    except Exception:
        return []


def _extract_text(file_path: Path) -> str:
    """
    Intenta extraer texto v?a OCR para PDF/imagenes con pdf2image + pytesseract.
    Devuelve "" si no se puede.
    """
    # Primero intentar lectura directa de PDF (texto embebido) si PyPDF2 est? disponible
    if file_path.suffix.lower() == ".pdf":
        try:
            import PyPDF2  # type: ignore

            text_parts = []
            with file_path.open("rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    try:
                        text_parts.append(page.extract_text() or "")
                    except Exception:
                        continue
            direct_text = "\n".join(text_parts).strip()
            if direct_text:
                return direct_text
        except Exception:
            pass

    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        return ""

    ext = file_path.suffix.lower()
    images = []
    try:
        if ext == ".pdf":
            images = convert_from_path(str(file_path))
        elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            from PIL import Image  # type: ignore
            images = [Image.open(file_path)]
    except Exception:
        return ""

    texts = []
    for img in images:
        try:
            texts.append(pytesseract.image_to_string(img))
        except Exception:
            continue
    return "\n".join(texts).strip()


def _process_attendance(upload_request: BulkUploadRequest, rows):
    section = upload_request.section
    log_lines = []
    session = section.sessions.order_by("-date").first()
    if not session:
        return ["La comision no tiene clases generadas; no se aplico asistencia."]
    for row in rows:
        dni = (row.get("dni") or row.get("DNI") or "").strip()
        email = (row.get("email") or row.get("Email") or "").strip()
        status_val = _map_status(row.get("status") or row.get("estado") or row.get("asistencia"))
        comment = row.get("comentario") or row.get("comment") or ""
        student_qs = None
        if dni:
            student_qs = User.objects.filter(dni=dni)
        elif email:
            student_qs = User.objects.filter(email__iexact=email)
        student = student_qs.first() if student_qs else None
        if not student:
            log_lines.append(f"No se encontro estudiante para la fila (DNI/email={dni or email}).")
            continue
        AttendanceRecord.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "section": section,
                "status": status_val,
                "comment": comment,
                "recorded_by": upload_request.uploaded_by,
            },
        )
    return log_lines


def _process_enrollment(upload_request: BulkUploadRequest, rows):
    section = upload_request.section
    log_lines = []
    for row in rows:
        dni = (row.get("dni") or row.get("DNI") or "").strip()
        email = (row.get("email") or row.get("Email") or "").strip()
        student_qs = None
        if dni:
            student_qs = User.objects.filter(dni=dni)
        elif email:
            student_qs = User.objects.filter(email__iexact=email)
        student = student_qs.first() if student_qs else None
        if not student:
            log_lines.append(f"No se encontro estudiante para la fila (DNI/email={dni or email}).")
            continue
        section.students.add(student)
    return log_lines


def process_upload(upload_request: BulkUploadRequest):
    file_path = Path(upload_request.file.path)
    try:
        rows = _read_rows(file_path)
    except Exception as exc:
        # Fallback: OCR + LLM
        raw_text = _extract_text(file_path)
        if not raw_text:
            try:
                raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw_text = ""
        rows = _rows_from_llm(raw_text)
        if not rows:
            raise RuntimeError(f"No se pudo leer la planilla ni mapear con LLM/OCR: {exc}")

    def _has_keys(rs):
        return any(isinstance(r, dict) and (r.get("dni") or r.get("email")) for r in rs)

    if not _has_keys(rows):
        try:
            sample = json.dumps(rows[:5], ensure_ascii=False)
        except Exception:
            sample = str(rows[:5])
        rows = _rows_from_llm(sample)
        if not _has_keys(rows):
            raise RuntimeError("No se pudieron mapear columnas a dni/email con el LLM.")

    log_lines = []
    if upload_request.kind == BulkUploadRequest.Kind.ATTENDANCE:
        log_lines = _process_attendance(upload_request, rows)
    elif upload_request.kind == BulkUploadRequest.Kind.ENROLLMENT:
        log_lines = _process_enrollment(upload_request, rows)
    else:
        log_lines.append("Tipo de carga no implementado en el stub actual.")
    upload_request.status = BulkUploadRequest.Status.COMPLETED
    upload_request.processed_at = timezone.now()
    upload_request.result_log = "\n".join(log_lines)
    upload_request.save(update_fields=["status", "processed_at", "result_log"])
    ActivityLog.objects.create(
        message=f"Procesada planilla de {upload_request.get_kind_display()} para {upload_request.section}.",
    )


def enqueue_ai_processing(upload_request: BulkUploadRequest):
    """
    Procesamiento basico con hook para IA. Si ocurre un error, marca FAILED.
    Reemplaza esta funcion para integrar un servicio externo de IA/ML.
    """
    upload_request.status = BulkUploadRequest.Status.PROCESSING
    upload_request.save(update_fields=["status"])
    try:
        process_upload(upload_request)
    except Exception as exc:  # noqa: BLE001
        upload_request.status = BulkUploadRequest.Status.FAILED
        upload_request.processed_at = timezone.now()
        upload_request.result_log = f"Error de procesamiento: {exc}"
        upload_request.save(update_fields=["status", "processed_at", "result_log"])
        ActivityLog.objects.create(
            message=f"Error al procesar planilla de {upload_request.get_kind_display()} para {upload_request.section}: {exc}"
        )




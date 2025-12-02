import json
from datetime import timedelta, time
from collections import defaultdict

from django.conf import settings

from core.notifications import notify_room_change


def _time_overlap(start1, end1, start2, end2):
    if not start1 or not start2 or not end1 or not end2:
        return False
    return start1 < end2 and end1 > start2


class RoomAutoAssigner:
    """
    Servicio de autoasignación de aulas combinando IA (Gemini) y fallback determinístico.
    """

    def __init__(self, date, rooms, sections):
        self.date = date
        self.rooms = rooms
        self.sections = sections

    def generate_prompt(self):
        """Construye un prompt JSON con aulas, bloqueos y comisiones con reglas explicitadas."""
        rooms_payload = []
        for r in self.rooms:
            rooms_payload.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "code": r.code,
                    "capacity": r.capacity,
                    "type": r.get_room_type_display(),
                    "baja_prioridad": r.baja_prioridad,
                    "blocks": [
                        {
                            "start_date": b.start_date.isoformat(),
                            "end_date": b.end_date.isoformat(),
                            "start_time": b.start_time.isoformat() if b.start_time else "",
                            "end_time": b.end_time.isoformat() if b.end_time else "",
                        }
                        for b in r.blocks.filter(is_active=True)
                    ],
                }
            )
        sections_payload = []
        for s in self.sections:
            sections_payload.append(
                {
                    "id": s.id,
                    "code": s.code or "",
                    "course": s.course.title,
                    "turn": s.turn.name if s.turn else "",
                    "start_date": s.start_date.isoformat(),
                    "end_date": s.end_date.isoformat(),
                    "days": s.days_of_week or [],
                    "schedule_by_day": s.schedule_by_day or [],
                    "start_time": s.start_time.isoformat() if s.start_time else "",
                    "end_time": s.end_time.isoformat() if s.end_time else "",
                    "students": s.students.count(),
                    "virtual_days": s.virtual_days or [],
                    "virtual_from": s.virtual_from.isoformat() if s.virtual_from else "",
                    "virtual_to": s.virtual_to.isoformat() if s.virtual_to else "",
                    "current_room": s.room.code if s.room else "",
                    "teachers": [t.get_full_name for t in s.teachers.all()],
                }
            )
        rules = (
            "Asigna aulas evitando bloqueos y respetando capacidad. "
            "Usa la misma aula para comisiones con alumnos/docentes compartidos en horarios consecutivos o días distintos. "
            "No asignes aula en días virtuales ni entre virtual_from/virtual_to. "
            "Evita aulas de baja prioridad salvo que no haya alternativa. Minimiza cambios. "
            "Marca cada asignación con nivel necesario/sugerido/opcional. Devuelve JSON con lista asignaciones: "
            "[{section_id, room_id, motivo, nivel}]."
        )
        return json.dumps(
            {
                "fecha_base": self.date.isoformat(),
                "aulas": rooms_payload,
                "comisiones": sections_payload,
                "reglas": rules,
            }
        )

    def call_gemini(self, prompt):
        """Invoca Gemini y devuelve texto o None."""
        api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        if not api_key:
            return None
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
            return getattr(resp, "text", None)
        except Exception:
            return None

    def parse_response(self, text):
        """Devuelve lista de asignaciones o [] si falla."""
        if not text:
            return []
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "asignaciones" in data:
                data = data.get("asignaciones")
            if isinstance(data, list):
                # normaliza claves
                cleaned = []
                for d in data:
                    if not isinstance(d, dict):
                        continue
                    sec = d.get("section_id") or d.get("id") or d.get("section")
                    room = d.get("room_id") or d.get("room")
                    if not (sec and room):
                        continue
                    cleaned.append(
                        {
                            "section_id": sec,
                            "room_id": room,
                            "motivo": d.get("motivo", "gemini"),
                            "nivel": d.get("nivel", "sugerido"),
                        }
                    )
                return cleaned
        except Exception:
            return []
        return []

    def _section_needs_room(self, sec, dayname, current_date):
        if sec.virtual_days and dayname in sec.virtual_days:
            return False
        if sec.virtual_from and sec.virtual_to and sec.virtual_from <= current_date <= sec.virtual_to:
            return False
        return True

    def _available_rooms_for(self, sec, dayname):
        """Filtra aulas por capacidad, baja prioridad al final, y bloqueos."""
        candidates = []
        for room in self.rooms:
            if room.capacity and sec.students.count() > room.capacity:
                continue
            # chequeo básico de bloqueos por día (no horario exacto aquí)
            blocked = room.blocks.filter(is_active=True, start_date__lte=sec.end_date, end_date__gte=sec.start_date)
            if blocked.exists():
                continue
            candidates.append(room)
        # Ordena: no baja prioridad primero, luego por capacidad ascendente
        candidates.sort(key=lambda r: (r.baja_prioridad, r.capacity or 0))
        return candidates

    def compute_fallback_strategy(self):
        """Greedy determinístico: respeta capacidad, evita baja_prioridad si hay opción."""
        assignments = []
        for sec in self.sections:
            if sec.room_id:
                assignments.append(
                    {"section_id": sec.id, "room_id": sec.room_id, "nivel": "existente", "motivo": "mantener"}
                )
                continue
            room = None
            for candidate in self._available_rooms_for(sec, None):
                room = candidate
                break
            if room:
                assignments.append(
                    {"section_id": sec.id, "room_id": room.id, "nivel": "sugerido", "motivo": "fallback"}
                )
        return assignments

    def minimize_changes(self, assignments):
        """Marca necesario si no tenía aula previa; si ya tenía, sugerido/opcional."""
        result = []
        for a in assignments:
            sec = next((s for s in self.sections if s.id == a.get("section_id")), None)
            if not sec:
                continue
            if not sec.room_id:
                a["nivel"] = a.get("nivel") or "necesario"
            else:
                a["nivel"] = a.get("nivel") or "sugerido"
            result.append(a)
        return result

    def build_assignment_proposal(self):
        prompt = self.generate_prompt()
        raw = self.call_gemini(prompt)
        parsed = self.parse_response(raw)
        if not parsed:
            parsed = self.compute_fallback_strategy()
        parsed = self._enforce_capacity_and_blocks(parsed)
        return self.minimize_changes(parsed)

    def apply_assignments(self, proposal):
        """Aplica propuesta y notifica cambios."""
        applied = 0
        for item in proposal:
            sec_id = item.get("section_id")
            room_id = item.get("room_id")
            if not sec_id or not room_id:
                continue
            section = next((s for s in self.sections if s.id == sec_id), None)
            room = next((r for r in self.rooms if r.id == room_id), None)
            if not section or not room:
                continue
            # Validación estricta de capacidad
            if room.capacity and section.students.count() > room.capacity:
                continue
            prev = section.room
            section.room = room
            section.save(update_fields=["room"])
            try:
                notify_room_change(section, prev, room)
            except Exception:
                pass
            applied += 1
        return applied

    def _enforce_capacity_and_blocks(self, assignments):
        """
        Ajusta la propuesta para eliminar asignaciones inválidas por capacidad/bloqueos,
        intentando reasignar al mejor candidato disponible.
        """
        valid = []
        for a in assignments:
            sec = next((s for s in self.sections if s.id == a.get("section_id")), None)
            room = next((r for r in self.rooms if r.id == a.get("room_id")), None)
            if not sec or not room:
                continue
            if room.capacity and sec.students.count() > room.capacity:
                # Buscar alternativa
                alt = None
                for cand in self._available_rooms_for(sec, None):
                    if cand.capacity and sec.students.count() > cand.capacity:
                        continue
                    alt = cand
                    break
                if alt:
                    a["room_id"] = alt.id
                    a["motivo"] = f"reemplazo por capacidad ({room.code}->{alt.code})"
                    valid.append(a)
                # si no hay alternativa, se descarta
                continue
            valid.append(a)
        return valid

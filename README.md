# Proyecto Final – Gestión Universitaria (Django)

## Descripción
Aplicación web en Django para gestionar carreras, materias, comisiones, asistencia y notificaciones en un centro universitario. Se basa en SkyLearn (MIT) y fue adaptada a los requerimientos del TFI de Tecnicatura Universitaria en Programación (UTN, Plan 2024).

Principales módulos:
- **Usuarios y roles**: Admin, Coordinador, Bedelía/Gestión, Docente, Alumno.
-, **Carreras / Materias / Comisiones**: altas, asignación de docentes, turnos, cuatrimestres, aulas.
- **Asistencia**: registro por comisión, cálculo de regularidad, justificaciones y recordatorios.
- **Noticias/Eventos** segmentados por rol, carrera, materia o comisión.
- **Carga masiva**: subida de planillas (Excel/PDF) para asistencia/notas (stub de IA).
- **Emails de alta**: se envían credenciales temporales; al primer login se fuerza cambio de contraseña.

## Requisitos
- Python 3.12
- Django 4.0.8
- SQLite (desarrollo) u otro motor soportado
- Dependencias en `requirements.txt`

## Instalación rápida
```bash
git clone <repo>
cd ProyectoFinal
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env  # y completar valores
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Variables clave (.env)
- `SECRET_KEY`: clave Django.
- `DEBUG`: `True` en desarrollo.
- `EMAIL_BACKEND=accounts.email_backend.MailtrapBackend` (usa SMTP sin keyfile).
- Para Gmail (entrega real):
  ```
  EMAIL_HOST=smtp.gmail.com
  EMAIL_PORT=587
  EMAIL_USE_TLS=True
  EMAIL_USE_SSL=False
  EMAIL_HOST_USER=tu_usuario@gmail.com
  EMAIL_HOST_PASSWORD=tu_app_password_16c   # App Password de Gmail
  EMAIL_FROM_ADDRESS=tu_usuario@gmail.com
  ```
- Para Mailtrap (sandbox):
  ```
  EMAIL_HOST=sandbox.smtp.mailtrap.io
  EMAIL_PORT=2525
  EMAIL_USE_TLS=True
  EMAIL_USE_SSL=False
  EMAIL_HOST_USER=<user>
  EMAIL_HOST_PASSWORD=<pass>
  EMAIL_FROM_ADDRESS=no-reply@example.com
  ```

## Flujo de credenciales
- Al crear docente/alumno se genera usuario= DNI y contraseña temporal= DNI.
- Se marca `must_change_password=True`; al primer login se redirige a “Cambiar contraseña”.
- Después de cambiarla, se desactiva la bandera y se redirige a inicio.

## Comisiones y asistencia
- Crear comisión: seleccionar Materia, Turno, Código, Ciclo lectivo, Cuatrimestre, fechas/horarios, docentes (solo nombre/apellido).
- Registro de asistencia por comisión; cálculo de regularidad según % requerido; justificaciones de inasistencia con aprobación.

## Notificaciones
- Noticias/Eventos segmentables por rol, carrera, materia o comisión.
- Emails de alta con plantillas HTML en `templates/accounts/email/`.

## Otros
- UI en español, textos de cambio de contraseña y formularios localizados.
- Para probar envíos sin SMTP real, usar backend de consola: `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.

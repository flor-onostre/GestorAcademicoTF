# Proyecto Final – Tecnicatura Universitaria en Programación

## 📚 Base del proyecto

Este proyecto se desarrolló a partir del código abierto **[SkyLearn](https://github.com/SkyCascade/SkyLearn)** (licencia MIT), un sistema LMS escrito en Django.  
El presente repositorio adapta y extiende esa base para cumplir con los requerimientos del **Trabajo Final Integrador (TFI)** de la carrera **Tecnicatura Universitaria en Programación (UTN, Plan 2024)**.

---

## 👥 Participantes

- Florencia Onostre
- Facundo Gallardo

---

## 📝 Descripción del proyecto

El sistema tiene como objetivo facilitar la **gestión académica universitaria**, enfocándose en:

- **Asistencia**: registro de presentes/ausentes, cálculo automático de regularidad y avisos.
- **Notificaciones**: recordatorios a docentes, avisos a alumnos y comunicación con Bedelía.
- **Carga por archivos**: importación automática desde Excel/PDF para evitar doble carga de datos.
- **Asignación de aulas**: administración de espacios con capacidad, recursos y reacomodamiento automático ante cambios.
- **Dashboard**: visualización centralizada para Bedelía sobre cargas de asistencia, ausencias y uso de aulas.

El proyecto se estima en **96 horas de desarrollo** (según requerimientos de la materia).

---

## 👤 Usuarios principales

- **Administrador**: gestiona organizaciones, usuarios, aulas y reportes globales.
- **Docente**: marca asistencia, recibe alertas y aprueba justificaciones de alumnos.
- **Alumno**: registra su asistencia (QR), recibe mails con estado de regularidad y carga justificaciones de inasistencias.
- **Bedelía**: supervisa cargas, recibe alertas si hay omisiones, define aulas y horarios.

---

## ⚙️ Requerimientos

- Python 3.12
- Django 4.0.8
- SQLite (desarrollo) / posibilidad futura de migrar a PostgreSQL o MySQL
- Dependencias en `requirements.txt`

---

## 🚀 Instalación y ejecución

```bash
# Clonar repositorio
git clone https://github.com/<tu_usuario>/skylearn-tfi.git
cd skylearn-tfi

# Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configuración de entorno
copy .env.example .env
# Editar .env con SECRET_KEY y demás variables

# Migraciones y superusuario
python manage.py migrate
python manage.py createsuperuser

# Levantar servidor
python manage.py runserver
```

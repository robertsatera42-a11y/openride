FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
RUN useradd -u 10001 -m openride && chown -R openride:openride /app
USER openride
CMD ["gunicorn", "project.wsgi:application", "-b", "0.0.0.0:8000", "-w", "3", "--error-logfile", "-"]

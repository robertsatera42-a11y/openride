import os,sys
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.environ.get('SECRET_KEY','development-only')
DEBUG=os.environ.get('DEBUG','0')=='1'
ALLOWED_HOSTS=os.environ.get('ALLOWED_HOSTS','localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS=[x for x in os.environ.get('CSRF_TRUSTED_ORIGINS','').split(',') if x]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','app']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','app.middleware.SchoolAccountMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='project.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.debug','django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','app.context.app_config']}}]
WSGI_APPLICATION='project.wsgi.application'
if os.environ.get('DATABASE_URL'):
 from urllib.parse import urlparse
 u=urlparse(os.environ['DATABASE_URL'])
 DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':u.path.lstrip('/'),'USER':u.username,'PASSWORD':u.password,'HOST':u.hostname,'PORT':u.port or 5432,'CONN_MAX_AGE':60}}
else:
 DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'dev.sqlite3'}}
AUTH_USER_MODEL='app.User'
AUTHENTICATION_BACKENDS=['app.auth.SchoolBackend']
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='cs'
TIME_ZONE='Europe/Prague'
USE_TZ=True
STATIC_URL='/openride/static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
STATICFILES_DIRS=[BASE_DIR/'static']
STORAGES={'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
LOGIN_URL='/openride/login/'
LOGIN_REDIRECT_URL='/openride/'
LOGOUT_REDIRECT_URL='/openride/login/'
SESSION_COOKIE_NAME='openride_session'
SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','1')=='1'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_AGE=1209600
CSRF_COOKIE_SECURE=SESSION_COOKIE_SECURE
SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_REFERRER_POLICY='strict-origin-when-cross-origin'
X_FRAME_OPTIONS='DENY'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
EMAIL_BACKEND='app.email_backend.BrevoBackend'
BREVO_API_KEY=os.environ.get('BREVO_API_KEY','')
BREVO_FROM_EMAIL=os.environ.get('BREVO_FROM_EMAIL','')
DEFAULT_FROM_EMAIL=f'OpenRide <{BREVO_FROM_EMAIL}>' if BREVO_FROM_EMAIL else 'OpenRide <noreply@invalid.example>'
GEOAPIFY_SERVER_KEY=os.environ.get('GEOAPIFY_SERVER_KEY','')

if 'test' in sys.argv:
    STORAGES={'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    DATABASES['default']['CONN_MAX_AGE']=0
LOGGING={'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'}},'loggers':{'django.request':{'handlers':['console'],'level':'ERROR','propagate':False}}}

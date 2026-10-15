from django.urls import path,include
from app import views
from django.contrib import admin
urlpatterns=[path('openride/django-admin/',admin.site.urls),path('openride/',include('app.urls'))]

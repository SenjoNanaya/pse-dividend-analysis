"""
URL configuration for django_backend project.
"""
from django.contrib import admin
from django.urls import path, include, re_path

from django_backend.spa import frontend_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    re_path(r'^(?P<path>.*)$', frontend_file),
]

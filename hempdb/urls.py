from django.contrib import admin
from django.urls import include, path

from hempdb import health

"""
Top-level URLs

- default: imports all routes in helloworld/urls.py
- admin/: django admin portal
- user/: django auth urls
"""
urlpatterns = [
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("", include("helloworld.urls")),
    path('admin/', admin.site.urls),
    path("user/", include("django.contrib.auth.urls")),
]

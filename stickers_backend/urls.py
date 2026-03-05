"""
URL configuration for stickers_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls import handler404, handler400, handler403, handler500
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from modules import startup_tasks


def error404(request, exception):
    return JsonResponse({
        "status": "Error",
        "message": "The requested URL was not found on the server.",
    }, status=404)


def error500(request):
    return JsonResponse({
        "status": "Error",
        "message": "Internal Server Error",
    }, status=500)


def error400(request, exception):
    return JsonResponse({
        "status": "Error",
        "message": "Bad Request",
    }, status=400)


def error403(request, exception):
    return JsonResponse({
        "status": "Error",
        "message": "Forbidden",
    }, status=403)


handler404 = "stickers_backend.urls.error404"
handler500 = "stickers_backend.urls.error500"
handler400 = "stickers_backend.urls.error400"
handler403 = "stickers_backend.urls.error403"

def asd():
    asd

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path("asd", asd)

]

startup_tasks.run_startup_tasks()

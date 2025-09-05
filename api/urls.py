from django.urls import path, include
import authenticate.urls

urlpatterns = [
    path('auth/', include(authenticate.urls)),
]

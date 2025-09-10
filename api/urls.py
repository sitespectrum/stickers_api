from django.urls import path, include
import authenticate.urls, stickers.urls

urlpatterns = [
    path('auth/', include(authenticate.urls)),
    path('stickers/', include(stickers.urls)),
]

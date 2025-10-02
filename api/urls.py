from django.urls import path, include
import authenticate.urls, stickers.urls, site_admin.urls

urlpatterns = [
    path('auth/', include(authenticate.urls)),
    path('stickers/', include(stickers.urls)),
    path('admin/', include(site_admin.urls)),
]

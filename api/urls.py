from django.urls import path, include
import authenticate.urls, stickers.urls, site_admin.urls, notes.urls

urlpatterns = [
    path('auth/', include(authenticate.urls)),
    path('stickers/', include(stickers.urls)),
    path('notes/', include(notes.urls)),
    path('admin/', include(site_admin.urls)),
]

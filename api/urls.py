from django.urls import path, include
import authenticate.urls, stickers.urls, site_admin.urls, notes.urls, bookmarks.urls

urlpatterns = [
    path('auth/', include(authenticate.urls)),
    path('stickers/', include(stickers.urls)),
    path('notes/', include(notes.urls)),
    path('bookmarks/', include(bookmarks.urls)),
    path('admin/', include(site_admin.urls)),
]

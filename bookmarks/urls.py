from bookmarks import response
from django.urls import path

urlpatterns = [
    path("all", response.get_all_bookmarks, name="get_all_bookmarks"),
    path("get/<int:bookmark_id>", response.get_bookmark_by_id, name="get_bookmark_by_id"),
    path("save/<int:bookmark_id>", response.save_bookmark, name="save_bookmark"),
    path("delete/<int:bookmark_id>", response.delete_bookmark, name="delete_bookmark"),
]

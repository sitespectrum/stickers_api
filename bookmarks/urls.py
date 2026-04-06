from bookmarks import response
from django.urls import path

urlpatterns = [
    path("all", response.get_all_bookmarks, name="get_all_bookmarks"),
    path("get/<int:bookmark_id>", response.get_bookmark_by_id, name="get_bookmark_by_id"),
    path("save/<int:bookmark_id>", response.save_bookmark, name="save_bookmark"),
    path("delete/<int:bookmark_id>", response.delete_bookmark, name="delete_bookmark"),
    path("folders/all", response.get_all_bookmark_folders, name="get_all_bookmark_folders"),
    path("folders/get/<int:folder_id>", response.get_bookmark_folder_by_id, name="get_bookmark_folder_by_id"),
    path("folders/save/<int:folder_id>", response.save_bookmark_folder, name="save_bookmark_folder"),
    path("folders/delete/<int:folder_id>", response.delete_bookmark_folder, name="delete_bookmark_folder"),
    path("meta", response.get_bookmark_metadata_from_url, name="get_bookmark_metadata_from_url"),
]

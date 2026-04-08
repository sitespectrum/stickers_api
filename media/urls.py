from . import response
from django.urls import path

urlpatterns = [
    path("upload", response.upload_file, name="upload_file"),
    path("upload_gallery", response.upload_gallery, name="upload_gallery"),
    path("get/<str:filename>", response.get_file, name="get_file"),
    path("files", response.get_all_files, name="get_file"),
    path('get/<str:file_name>/metadata', response.get_file_metadata, name='get_file_metadata'),
    path("delete/<int:file_id>", response.delete_file, name="get_file"),

    path("list", response.list_folder, name="list_folder"),

    path("recent", response.list_recent_files, name="list_recent_files"),

    path("library", response.list_media_library, name="list_media_library"),

    path("folders", response.get_all_folders, name="get_all_folders"),

    path("folder/create", response.create_folder, name="create_folder"),
    path("folder/<int:folder_id>/rename", response.rename_folder, name="rename_folder"),
    path("folder/<int:folder_id>/move", response.move_folder, name="move_folder"),
    path("folder/<int:folder_id>/delete", response.delete_folder, name="delete_folder"),

    path("file/<int:file_id>", response.get_file_by_id, name="get_file_by_id"),
    path("file/<int:file_id>/metadata", response.get_file_metadata_by_id, name="get_file_metadata_by_id"),
    path("file/<int:file_id>/rename", response.rename_file, name="rename_file"),
    path("file/<int:file_id>/move", response.move_file, name="move_file"),
]
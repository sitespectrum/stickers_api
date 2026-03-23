from . import response
from django.urls import path

urlpatterns = [
    path("upload", response.upload_file, name="upload_file"),
    path("get/<str:filename>", response.get_file, name="get_file"),
    path("files", response.get_all_files, name="get_file"),
    path('get/<str:file_name>/metadata', response.get_file_metadata, name='get_file_metadata'),
    path("delete/<int:file_id>", response.delete_file, name="get_file"),
]
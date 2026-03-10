from notes import response
from django.urls import path

urlpatterns = [
    path("all", response.get_all_notes, name="get_all_notes"),
    path("get/<int:note_id>", response.get_note_by_id, name="get_note_by_id"),
    path("save/<int:note_id>", response.save_note, name="save_note"),
    path("delete/<int:note_id>", response.delete_note, name="delete_note"),
]

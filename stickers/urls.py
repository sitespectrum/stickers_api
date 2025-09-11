from django.urls import path
from . import response

urlpatterns = [
    path("add_pack", response.add_sticker_pack, name="add_pack"),
    path("get_packs", response.get_packs, name="get_packs"),
    path("get_sticker/<str:type>/<str:file_name>", response.get_sticker, name="get_packs"),
    path("get_pack/<str:pack_name>", response.get_one_pack, name="get_one_pack"),
    path("remove_pack/<str:pack_name>", response.remove_pack, name="remove_pack"),
]

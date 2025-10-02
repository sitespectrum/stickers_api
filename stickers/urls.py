from django.urls import path
from . import response

urlpatterns = [
    path("add_pack", response.add_sticker_pack, name="add_pack"),
    path("update_pack", response.update_pack, name="update_pack"),
    path("get_packs", response.get_packs, name="get_packs"),
    path("get_sticker/<int:sticker_id>", response.get_sticker, name="get_packs"),
    path("favourites", response.favourite_stickers, name="get_favourite_stickers"),
    path("get_pack/<str:pack_name>", response.get_one_pack, name="get_one_pack"),
    path("remove_pack/<str:pack_name>", response.remove_pack, name="remove_pack"),
    path("stats", response.stats, name="stats"),
]

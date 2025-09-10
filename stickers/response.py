import time
from json import JSONDecodeError
from pprint import pprint
import mimetypes
from django.db import IntegrityError
from django.forms import model_to_dict
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.handlers.wsgi import WSGIRequest
from concurrent.futures import ThreadPoolExecutor
import json
import requests
from authenticate import wrappers
from api.models import StickerPack, UserData, Sticker
from stickers_backend.settings import TELEGRAM_TOKEN

from stickers_backend import utils

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILE = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"

# Create your views here.

@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def add_sticker_pack(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    try:
        pack_name = body["pack_name"].split("/")[-1]
    except KeyError:
        return JsonResponse({"error": "Missing pack_name"}, status=400)

    user_data = UserData.objects.get(user=request.user)

    if not StickerPack.objects.filter(name=pack_name).exists():

        url = f"{TELEGRAM_API}/getStickerSet?name={pack_name}"
        res = requests.get(url).json()
        if not res["ok"]:
            return JsonResponse({"error": "Pack not found"}, status=404)
        data = res["result"]
        pack = StickerPack.objects.create(
            name=data["name"],
            title=data["title"],
        )

        thumbnail_data = requests.get(f"{TELEGRAM_API}/getFile?file_id={data['thumbnail']['file_id']}").json()["result"]
        print(thumbnail_data)

        thumbnail = Sticker.objects.create(
            file_name=thumbnail_data["file_path"],
            is_video=False,
            is_animated=False,
        )
        thumbnail.save()
        pack.thumbnail = thumbnail

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Create a list to hold concurrent threads
            future_to_sticker_data = {
                executor.submit(
                    lambda sticker: requests.get(f"{TELEGRAM_API}/getFile?file_id={sticker['file_id']}").json(),
                    sticker
                ): sticker for sticker in data["stickers"]
            }

        for future in future_to_sticker_data.keys():
            try:
                # Retrieve the result of the API call
                file_name_data = future.result()["result"]
                sticker = future_to_sticker_data[future]  # Corresponding sticker

                if not Sticker.objects.filter(file_name=file_name_data["file_path"]).exists():
                    sticker_object = Sticker.objects.create(
                        emoji=sticker["emoji"],
                        file_name=file_name_data["file_path"],
                        is_video=sticker["is_video"],
                        is_animated=sticker["is_animated"],
                    )

                else:
                    sticker_object = Sticker.objects.get(file_name=file_name_data["file_path"])

                pack.stickers.add(sticker_object)
            except Exception as e:
                print(f"Error processing sticker: {e}")

        user_data.sticker_packs.add(pack)


        pack.save()

    else:
        user_data.sticker_packs.add(StickerPack.objects.get(name=pack_name))

    user_data.save()

    return JsonResponse({
        "status": "Ok"
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
@wrappers.login_required()
def get_packs(request: WSGIRequest):
    user_data = UserData.objects.get(user=request.user)
    packs = user_data.sticker_packs
    pack_list = []
    for i in packs.all():
        pack_list.append({
            "name": i.name,
            "title": i.title,
            "thumbnail": i.thumbnail.file_name,
        })
    return JsonResponse({
        "packs": pack_list
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
@wrappers.login_required()
def get_sticker(request: WSGIRequest, type: str, file_name: str):
    file_url = f"{TELEGRAM_FILE}/{type}/{file_name}"
    file_res = requests.get(file_url, stream=True)

    content_type = mimetypes.guess_type(file_name)

    return HttpResponse(file_res.content, content_type=content_type)

@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
@wrappers.login_required()
def get_one_pack(request: WSGIRequest, pack_name):
    if not StickerPack.objects.filter(name=pack_name).exists():
        return JsonResponse({"error": "Pack not found on our server"}, status=404)

    sticker_pack = StickerPack.objects.get(name=pack_name)

    return JsonResponse({
        "name": pack_name,
        "title": sticker_pack.title,
        "thumbnail": sticker_pack.thumbnail.file_name,
        "stickers": [i.file_name for i in sticker_pack.stickers.all()]
    }, status=200)

import mimetypes
import asyncio

from django.core.cache import cache
import httpx
from django.db.models import Count
from django.http import JsonResponse, StreamingHttpResponse, HttpResponseNotFound
from django.views.decorators.http import require_http_methods
from django.core.handlers.wsgi import WSGIRequest
import json
import requests
from authenticate import wrappers
from api.models import StickerPack, UserData, Sticker
from stickers_backend.settings import TELEGRAM_TOKEN

from stickers_backend import utils

mimetypes.add_type("image/webp", ".webp")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILE = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"


async def fetch_file(client: httpx.AsyncClient, file_id: str):
    r = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}")
    if r.status_code != 200:
        return None
    return r.json()["result"]


async def fetch_thumbnail(client: httpx.AsyncClient, data: dict):
    """
    Try to extract thumbnail from multiple possible places.
    """
    thumb = (
            data.get("thumbnail")
            or data.get("thumb")
            or data.get("stickers")[0].get("thumbnail")
            or data.get("stickers")[0].get("thumb")
            or data.get("stickers")[0]
    )
    if not thumb:
        return None
    r = await client.get(f"{TELEGRAM_API}/getFile?file_id={thumb['file_id']}")
    if r.status_code != 200:
        return None
    return r.json()["result"]


async def fetch_all(sticker_list, max_concurrency=50):
    limits = httpx.Limits(max_connections=max_concurrency)
    async with httpx.AsyncClient(timeout=10, limits=limits) as client:
        tasks = [
            _fetch_sticker_with_file(client, s) for s in sticker_list
        ]
        results = await asyncio.gather(*tasks)
        return results


async def _fetch_sticker_with_file(client, sticker):
    file_data = await fetch_file(client, sticker["file_id"])
    if not file_data:
        return None
    # Merge original sticker fields with file data
    return {**sticker, **file_data}


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
def add_sticker_pack(request: WSGIRequest, pack_name: str = None,):
    # Parse body
    if not pack_name and request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if not pack_name:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid request body"}, status=400)

    # Safely extract pack_name: prefer body value if present, fallback to argument
        body_pack_name = body.get("pack_name")
    else:
        body_pack_name = pack_name
    pack_name = body_pack_name.split("/")[-1].lower()
    if not pack_name:
        return JsonResponse({"error": "Missing pack_name"}, status=400)

    user_data = None
    if request.user.is_authenticated:
        user_data = UserData.objects.get(user=request.user)

    # Already exists?
    if StickerPack.objects.filter(name=pack_name).exists():
        if request.user.is_authenticated:
            user_data.sticker_packs.add(StickerPack.objects.get(name=pack_name))
        return JsonResponse({"status": "Ok"}, status=200)

    # Get pack info from Telegram
    r = httpx.get(f"{TELEGRAM_API}/getStickerSet?name={pack_name}", timeout=10)
    if r.status_code != 200:
        return JsonResponse({"error": "Pack not found"}, status=404)
    data = r.json()["result"]

    # Run async thumbnail + sticker fetch concurrently
    async def gather_all():
        async with httpx.AsyncClient(timeout=10) as client:
            thumb_task = fetch_thumbnail(client, data)
            stickers_task = fetch_all(data["stickers"])
            thumb_result, stickers_result = await asyncio.gather(thumb_task, stickers_task)
            return thumb_result, stickers_result

    thumb_data, stickers = asyncio.run(gather_all())

    if not thumb_data:
        return JsonResponse({"error": "Pack thumbnail not found"}, status=404)

    # Create StickerPack
    sticker_pack_obj = StickerPack.objects.create(
        name=data["name"].lower(), title=data["title"]
    )

    # Create thumbnail Sticker
    thumb_obj = Sticker.objects.create(
        emoji="",
        file_name=thumb_data["file_path"],
        file_id=thumb_data["file_id"],
        unique_file_id=thumb_data["file_unique_id"],
        is_video=False,
        is_animated=False,
    )
    sticker_pack_obj.thumbnail = thumb_obj

    # Bulk create stickers (preserving order)
    sticker_objs = []
    for sticker in stickers:
        if not sticker:
            continue
        sticker_objs.append(Sticker(
            emoji=sticker.get("emoji", ""),
            file_name=sticker["file_path"],
            file_id=sticker["file_id"],
            unique_file_id=sticker["file_unique_id"],
            is_video=sticker.get("is_video", False),
            is_animated=sticker.get("is_animated", False),
        ))

    Sticker.objects.bulk_create(sticker_objs)
    sticker_pack_obj.stickers.add(*sticker_objs)

    sticker_pack_obj.save()
    if request.user.is_authenticated:
        user_data.sticker_packs.add(sticker_pack_obj)
        user_data.save()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["POST"])
def update_pack(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    pack_name = body.get("pack_name")
    if not pack_name:
        return JsonResponse({"error": "Missing pack_id"}, status=400)
    if not StickerPack.objects.filter(name=pack_name).exists():
        return JsonResponse({"error": "Pack not found on our server"}, status=404)

    sticker_pack = StickerPack.objects.get(name=pack_name)
    r = httpx.get(f"{TELEGRAM_API}/getStickerSet?name={sticker_pack.name}", timeout=10)
    if r.status_code != 200:
        return JsonResponse({"error": "Pack not found"}, status=404)
    data = r.json()["result"]
    if data["title"] != sticker_pack.title:
        sticker_pack.title = data["title"]
        sticker_pack.save()
    thumb_task = fetch_thumbnail(httpx.AsyncClient(timeout=10), data)
    thumb_data = asyncio.run(thumb_task)
    if thumb_data and thumb_data["file_unique_id"] != sticker_pack.thumbnail.unique_file_id:
        sticker_pack.thumbnail.file_name = thumb_data["file_path"]
        sticker_pack.thumbnail.file_id = thumb_data["file_id"]
        sticker_pack.thumbnail.unique_file_id = thumb_data["file_unique_id"]
        sticker_pack.thumbnail.save()

    unique_ids = [i["file_unique_id"] for i in data["stickers"]]

    missing_stickers = []

    for i in data["stickers"]:
        if not sticker_pack.stickers.filter(unique_file_id=i["file_unique_id"]).exists():
            missing_stickers.append(i)
            continue
        current_sticker = sticker_pack.stickers.get(unique_file_id=i["file_unique_id"])

        if current_sticker.emoji != i["emoji"]:
            current_sticker.emoji = i["emoji"]
        if current_sticker.is_video != i.get("is_video", False):
            current_sticker.is_video = i.get("is_video", False)
        if current_sticker.is_animated != i.get("is_animated", False):
            current_sticker.is_animated = i.get("is_animated", False)
        current_sticker.save()

    task = fetch_all(missing_stickers)
    missing_stickers = asyncio.run(task)
    to_batch_create = []
    for i in missing_stickers:
        if not i:
            continue
        to_batch_create.append(Sticker(
            emoji=i["emoji"],
            file_name=i["file_path"],
            file_id=i["file_id"],
            unique_file_id=i["file_unique_id"],
            is_video=i.get("is_video", False),
            is_animated=i.get("is_animated", False),
        ))

    Sticker.objects.bulk_create(to_batch_create)
    sticker_pack.stickers.add(*to_batch_create)
    sticker_pack.save()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["GET"])
def get_packs(request: WSGIRequest):
    if request.user.is_authenticated:
        user_data = UserData.objects.get(user=request.user)
        packs = user_data.sticker_packs.order_by("title")
        pack_list = []
        for i in packs.all():
            pack_list.append({
                "name": i.name,
                "title": i.title,
                "thumbnail_id": i.thumbnail.id,
            })
        return JsonResponse({
            "packs": pack_list
        }, status=200)

    packs = StickerPack.objects.all().order_by("title")
    pack_list = []
    for i in packs.all():
        pack_list.append({
            "name": i.name,
            "title": i.title,
            "thumbnail_id": i.thumbnail.id,
        })
    return JsonResponse({
        "packs": pack_list
    }, status=200)


# Reuse a single session to enable connection pooling
session = requests.Session()


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["GET"])
def get_sticker(request, sticker_id):
    if not Sticker.objects.filter(id=sticker_id).exists():
        return JsonResponse({"error": "Sticker not found on our server"}, status=404)
    sticker = Sticker.objects.get(id=sticker_id)

    # Construct cache key
    cache_key = f"sticker:{sticker.file_name}"
    cached_file = cache.get(cache_key)

    content_type, _ = mimetypes.guess_type(sticker.file_name.split("/")[-1])
    content_type = content_type or "application/octet-stream"

    # Serve from cache if available
    if cached_file:
        response = StreamingHttpResponse(cached_file, content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{sticker.file_name}"'
        response['Content-Length'] = str(len(cached_file))
        response['Access-Control-Allow-Origin'] = request.headers.get('Referer', '*')
        response['Access-Control-Expose-Headers'] = 'Content-Length, Content-Disposition'
        return response

    # Fetch the file from remote server
    file_res = session.get(f"{TELEGRAM_FILE}/{sticker.file_name}", stream=True)
    if file_res.status_code != 200:
        file_info = session.get(f"{TELEGRAM_API}/getFile?file_id={sticker.file_id}")
        if file_info.status_code != 200:
            pack = session.get(f"{TELEGRAM_API}/getStickerSet?name={sticker.packs.all().first().name}")
            if pack.status_code != 200:
                return HttpResponseNotFound("Sticker not found")
            pack = pack.json()["result"]["stickers"]
            for i in pack:
                try:
                    temp_sticker = Sticker.objects.get(unique_file_id=i["file_unique_id"])
                    if temp_sticker.file_id != i["file_id"]:
                        temp_sticker.file_id = i["file_id"]
                        temp_sticker.save(update_fields=["file_id"])
                except Sticker.DoesNotExist:
                    continue
            sticker.refresh_from_db()
            file_info = session.get(f"{TELEGRAM_API}/getFile?file_id={sticker.file_id}")

        file_info = file_info.json()["result"]
        new_file_path = file_info["file_path"]
        sticker.file_name = new_file_path
        sticker.save()
        cache_key = f"sticker:{sticker.file_name}"  # update cache key
        file_res = session.get(f"{TELEGRAM_FILE}/{new_file_path}", stream=True)

        # Update content type for the new file
        content_type, _ = mimetypes.guess_type(new_file_path.split("/")[-1])
        content_type = content_type or "image/webp"

    # Stream content in chunks and optionally cache small files
    chunk_size = 8192
    content_chunks = []

    def file_iterator():
        for chunk in file_res.iter_content(chunk_size=chunk_size):
            if chunk:  # filter out keep-alive chunks
                if len(chunk) < 1024 * 1024:  # cache only files <1MB
                    content_chunks.append(chunk)
                yield chunk

    response = StreamingHttpResponse(file_iterator(), content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{sticker.file_name}"'
    response['Content-Length'] = file_res.headers.get('Content-Length', '')
    response['Access-Control-Allow-Origin'] = request.headers.get('Referer', '*')
    response['Access-Control-Expose-Headers'] = 'Content-Length, Content-Disposition'

    # Cache the file after streaming
    if content_chunks:
        cache.set(cache_key, b"".join(content_chunks), timeout=60*60)  # 1 hour

    return response


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["GET"])
def get_one_pack(request: WSGIRequest, pack_name):
    if request.GET.get("add") == "true" and not StickerPack.objects.filter(name=pack_name).exists():
        # Attempt to add pack; this may return 405 for GET, so we re-check existence after.
        print(add_sticker_pack(request, pack_name=pack_name).text)
    elif not StickerPack.objects.filter(name=pack_name).exists():
        return JsonResponse({"error": "Pack not found on our server"}, status=404)
    
    # Ensure the pack exists before calling .get()
    try:
        sticker_pack = StickerPack.objects.get(name=pack_name)
    except StickerPack.DoesNotExist:
        return JsonResponse({"error": "Pack not found on our server"}, status=404)

    sticker_list = []
    for i in sticker_pack.stickers.all():
        sticker_list.append({
            "id": i.id,
            "emoji": i.emoji,
            "is_video": i.is_video,
            "is_animated": i.is_animated,
        })

    return JsonResponse({
        "name": pack_name,
        "title": sticker_pack.title,
        "thumbnail": sticker_pack.thumbnail.id,
        "stickers": sticker_list
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["DELETE"])
@wrappers.login_required()
def remove_pack(request: WSGIRequest, pack_name):
    if not StickerPack.objects.filter(name=pack_name).exists():
        return JsonResponse({"error": "Pack not found on our server"}, status=404)

    user_data = UserData.objects.get(user=request.user)

    if user_data.sticker_packs.filter(name=pack_name).exists():
        user_data.sticker_packs.remove(StickerPack.objects.get(name=pack_name))
        user_data.save()

        return JsonResponse({"status": "Ok"}, status=200)
    return JsonResponse({"error": "Pack not found in your packs"}, status=404)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["GET", "POST"])
@wrappers.login_required()
def favourite_stickers(request: WSGIRequest):
    if request.method == "GET":
        user_data = UserData.objects.get(user=request.user)
        sticker_list = []
        for i in user_data.favourite_stickers.all():
            sticker_list.append({
                "id": i.id,
                "emoji": i.emoji,
                "is_video": i.is_video,
                "is_animated": i.is_animated,
            })
        return JsonResponse({
            "status": "Ok",
            "stickers": sticker_list
        }, status=200)
    if utils.SAFE:
        return JsonResponse({"error": "Unable to perform database write operation"}, status=503)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    sticker_id = body.get("sticker_id")
    if not sticker_id:
        return JsonResponse({"error": "Missing sticker_id"}, status=400)
    user_data = UserData.objects.get(user=request.user)
    if user_data.favourite_stickers.filter(id=sticker_id).exists():
        user_data.favourite_stickers.remove(Sticker.objects.get(id=sticker_id))
    else:
        user_data.favourite_stickers.add(Sticker.objects.get(id=sticker_id))
    user_data.save()
    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["GET"])
def stats(request: WSGIRequest):
    additional = {}
    if request.user.is_authenticated:
        user_data = UserData.objects.get(user=request.user)
        additional = {
            "favourite_stickers": user_data.favourite_stickers.count(),
            "sticker_packs": user_data.sticker_packs.count(),
        }
    stickerpacks_with_user_count = StickerPack.objects.annotate(
        user_count=Count('userdata')
    )

    sticker_packs = StickerPack.objects.all()

    most_used_packs = stickerpacks_with_user_count.order_by('-user_count')[:5]

    return JsonResponse({
        "status": "Ok",
        "most_used_packs": [{"name": i.name, "title": i.title, "thumbnail": i.thumbnail.id} for i in most_used_packs],
        "recently_added": [{"name": i.name, "title": i.title, "thumbnail": i.thumbnail.id} for i in sticker_packs.order_by("-id")[:5]],
        "total_packs": sticker_packs.count(),
        "total_stickers": Sticker.objects.count() - sticker_packs.count(),
        **additional,
    }, status=200)

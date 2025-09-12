import time
import mimetypes
import asyncio

from django.core.cache import cache
import httpx
from asgiref.sync import sync_to_async
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


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def add_sticker_pack(request: WSGIRequest):
    async def inner():
        body = _parse_request_body(request)
        if isinstance(body, JsonResponse):
            return body

        pack_name = body.get("pack_name", "").split("/")[-1]
        if not pack_name:
            return JsonResponse({"error": "Missing pack_name"}, status=400)

        user_data = await sync_to_async(UserData.objects.get)(user=request.user)
        pack = await sync_to_async(StickerPack.objects.filter(name=pack_name).first)()

        if not pack:
            start_time = time.time()
            pack = await _create_pack_from_telegram(pack_name)
            if not pack:
                return JsonResponse({"error": "Pack not found"}, status=404)

            await sync_to_async(user_data.sticker_packs.add)(pack)
            await sync_to_async(pack.save)()
            print(f"Pack processing completed in {time.time() - start_time:.2f} seconds")
        else:
            await sync_to_async(user_data.sticker_packs.add)(pack)

        await sync_to_async(user_data.save)()
        return JsonResponse({"status": "Ok"}, status=200)

    return asyncio.run(inner())


# -----------------------
# Helpers
# -----------------------

def _parse_request_body(request):
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)


def _http_client():
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0)
    limits = httpx.Limits(max_keepalive_connections=30, max_connections=50)
    return httpx.AsyncClient(timeout=timeout, limits=limits)


# noinspection PyUnresolvedReferences
async def _create_pack_from_telegram(pack_name: str):
    async with _http_client() as client:
        try:
            res = await client.get(f"{TELEGRAM_API}/getStickerSet?name={pack_name}")
            data = res.json()
            if not data.get("ok"):
                return None
            data = data["result"]
        except Exception as e:
            print(f"Failed to fetch pack: {e}")
            return None

        pack = await sync_to_async(StickerPack.objects.create)(
            name=data["name"], title=data["title"]
        )

        stickers_task = fetch_stickers_with_retries(client, data["stickers"])
        thumb_task = get_thumbnail_async(client, data)
        sticker_results, thumbnail = await asyncio.gather(stickers_task, thumb_task)

        sticker_objects = await create_stickers_bulk_robust(data["stickers"], sticker_results)
        if sticker_objects:
            await sync_to_async(pack.stickers.set)(sticker_objects)

        if thumbnail:
            thumb_obj = await sync_to_async(Sticker.objects.create)(
                file_name=thumbnail["file_path"],
                file_id=thumbnail["file_id"],
                unique_file_id=thumbnail["file_unique_id"],
                is_video=False,
                is_animated=False,
            )
            pack.thumbnail = thumb_obj

        return pack


# -----------------------
# Generic Retry Helper
# -----------------------

async def retry(coro_func, *args, retries=2, delay=0.5, backoff=2, **kwargs):
    """Retry coroutine on failure with exponential backoff."""
    for attempt in range(retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            if attempt == retries:
                print(f"Failed after {retries+1} attempts: {e}")
                return None
            await asyncio.sleep(delay * (backoff ** attempt))


# -----------------------
# Sticker Helpers
# -----------------------

async def fetch_stickers_with_retries(client, stickers, max_concurrent=30):
    """Fetch sticker metadata with concurrency + retries."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(sticker):
        async with semaphore:
            file_id = sticker["file_id"]

            async def get_file():
                resp = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}", timeout=8.0)
                data = resp.json()
                if resp.status_code == 200 and data.get("ok"):
                    return data["result"]
                raise Exception(f"Telegram API error {resp.status_code}: {data}")

            return await retry(get_file)

    results = await asyncio.gather(*(fetch_one(s) for s in stickers))
    return results


# noinspection PyArgumentList
async def create_stickers_bulk_robust(stickers_info, file_data_list):
    """Create or update stickers in bulk, skipping failures."""
    valid = [(i, d) for i, d in zip(stickers_info, file_data_list) if d]
    if not valid:
        return []

    unique_ids = [i["file_unique_id"] for i, _ in valid]
    existing = {
        s.unique_file_id: s
        for s in await sync_to_async(list)(
            Sticker.objects.filter(unique_file_id__in=unique_ids)
        )
    }

    new_stickers, result = [], []
    for info, data in valid:
        unique_id = info["file_unique_id"]
        if unique_id in existing:
            sticker = existing[unique_id]
            if sticker.file_id != info["file_id"]:
                sticker.file_id = info["file_id"]
                await sync_to_async(sticker.save)()
            result.append(sticker)
        else:
            new = Sticker(
                emoji=info.get("emoji", ""),
                file_name=data["file_path"],
                file_id=info["file_id"],
                unique_file_id=unique_id,
                is_video=info.get("is_video", False),
                is_animated=info.get("is_animated", False),
            )
            new_stickers.append(new)
            result.append(new)

    if new_stickers:
        await sync_to_async(Sticker.objects.bulk_create)(new_stickers)

    return result


async def get_thumbnail_async(client, data):
    """Fetch thumbnail metadata from Telegram API."""
    try:
        file_id = (
                data.get("thumbnail", {}).get("file_id")
                or data.get("thumb", {}).get("file_id")
                or (data["stickers"][0].get("thumbnail", {}).get("file_id") if data.get("stickers") else None)
        )
        if not file_id:
            return None

        async def get_thumb():
            resp = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}", timeout=5.0)
            result = resp.json()
            if resp.status_code == 200 and result.get("ok"):
                return {
                    **result["result"],
                    "file_id": file_id,
                    "file_unique_id": data.get("thumbnail", {}).get("file_unique_id", file_id),
                }
            raise Exception(f"Thumb fetch error {resp.status_code}: {result}")

        return await retry(get_thumb, retries=1)
    except Exception as e:
        print(f"Thumbnail fetch error: {e}")
        return None


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
            "thumbnail_id": i.thumbnail.id,
        })
    return JsonResponse({
        "packs": pack_list
    }, status=200)


# Reuse a single session to enable connection pooling
session = requests.Session()


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
@wrappers.login_required()
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
        file_info = session.get(f"{TELEGRAM_API}/getFile?file_id={sticker.file_id}").json()["result"]
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
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
@wrappers.login_required()
def get_one_pack(request: WSGIRequest, pack_name):
    if not StickerPack.objects.filter(name=pack_name).exists():
        return JsonResponse({"error": "Pack not found on our server"}, status=404)

    sticker_pack = StickerPack.objects.get(name=pack_name)

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

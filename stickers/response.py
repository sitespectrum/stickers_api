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

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_FILE = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def add_sticker_pack(request: WSGIRequest):
    async def inner():
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid request body"}, status=400)

        try:
            pack_name = body["pack_name"].split("/")[-1]
        except KeyError:
            return JsonResponse({"error": "Missing pack_name"}, status=400)

        user_data = await sync_to_async(UserData.objects.get)(user=request.user)
        pack_exists = await sync_to_async(StickerPack.objects.filter(name=pack_name).exists)()

        if not pack_exists:
            start_time = time.time()

            # Optimized client settings
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0)
            limits = httpx.Limits(max_keepalive_connections=30, max_connections=50)

            async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
                # Get sticker pack info
                try:
                    res = await client.get(f"{TELEGRAM_API}/getStickerSet?name={pack_name}")
                    res = res.json()
                    if not res["ok"]:
                        return JsonResponse({"error": "Pack not found"}, status=404)
                except Exception as e:
                    return JsonResponse({"error": f"Failed to fetch pack: {str(e)}"}, status=500)

                data = res["result"]
                pack = await sync_to_async(StickerPack.objects.create)(
                    name=data["name"],
                    title=data["title"],
                )

                print(f"Processing {len(data['stickers'])} stickers...")

                # Fetch all sticker data with retries and better error handling
                sticker_results = await fetch_stickers_with_retries(client, data["stickers"])

                # Count successes/failures
                successful = sum(1 for result in sticker_results if result is not None)
                failed = len(sticker_results) - successful

                print(f"Fetched {successful}/{len(data['stickers'])} stickers successfully")
                if failed > 0:
                    print(f"Failed to fetch {failed} stickers")

                # Create sticker objects (only for successful fetches)
                sticker_objects = await create_stickers_bulk_robust(data["stickers"], sticker_results)

                # Handle thumbnail concurrently (don't block main processing)
                thumbnail_task = asyncio.create_task(get_thumbnail_async(client, data))

                # Add stickers to pack
                if sticker_objects:
                    await sync_to_async(pack.stickers.set)(sticker_objects)
                    print(f"Added {len(sticker_objects)} stickers to pack")

                # Wait for thumbnail
                try:
                    thumbnail_data = await thumbnail_task
                    if thumbnail_data:
                        thumbnail = await sync_to_async(Sticker.objects.create)(
                            file_name=thumbnail_data["file_path"],
                            is_video=False,
                            is_animated=False,
                        )
                        pack.thumbnail = thumbnail
                except Exception as e:
                    print(f"Thumbnail failed (non-critical): {e}")

            await sync_to_async(user_data.sticker_packs.add)(pack)
            await sync_to_async(pack.save)()

            elapsed = time.time() - start_time
            print(f"Pack processing completed in {elapsed:.2f} seconds")

        else:
            pack = await sync_to_async(StickerPack.objects.get)(name=pack_name)
            await sync_to_async(user_data.sticker_packs.add)(pack)

        await sync_to_async(user_data.save)()
        return JsonResponse({"status": "Ok"}, status=200)

    return asyncio.run(inner())


async def fetch_stickers_with_retries(client, stickers, max_concurrent=30, max_retries=2):
    """Fetch sticker data with retries and better concurrency control"""

    # Use higher semaphore for better speed
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_single_sticker_with_retry(index, sticker):
        async with semaphore:
            file_id = sticker['file_id']

            for attempt in range(max_retries + 1):
                try:
                    # Individual timeout per request
                    response = await client.get(
                        f"{TELEGRAM_API}/getFile?file_id={file_id}",
                        timeout=8.0  # Shorter timeout per request
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("ok"):
                            return result["result"]
                        else:
                            print(f"API error for sticker {index}: {result.get('description', 'Unknown error')}")
                            if attempt < max_retries:
                                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                                continue
                            return None
                    else:
                        print(f"HTTP {response.status_code} for sticker {index}")
                        if attempt < max_retries:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        return None

                except asyncio.TimeoutError:
                    print(f"Timeout for sticker {index} (attempt {attempt + 1})")
                    if attempt < max_retries:
                        await asyncio.sleep(1.0)  # Longer wait for timeout
                        continue
                    return None

                except Exception as e:
                    print(f"Error fetching sticker {index} (attempt {attempt + 1}): {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(0.5)
                        continue
                    return None

            return None  # All attempts failed

    # Create tasks with index tracking
    tasks = [
        fetch_single_sticker_with_retry(i, sticker)
        for i, sticker in enumerate(stickers)
    ]

    # Gather all results (preserves order)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that slipped through
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Exception for sticker {i}: {result}")
            processed_results.append(None)
        else:
            processed_results.append(result)

    return processed_results


async def create_stickers_bulk_robust(stickers_info, file_data_list):
    """Create sticker objects with better error handling"""
    valid_pairs = []

    # Only process successfully fetched stickers
    for i, (info, data) in enumerate(zip(stickers_info, file_data_list)):
        if data is not None:
            valid_pairs.append((info, data))
        else:
            print(f"Skipping sticker {i} due to fetch failure")

    if not valid_pairs:
        print("No valid stickers to process!")
        return []

    print(f"Processing {len(valid_pairs)} valid stickers in database")

    try:
        # Get existing stickers
        file_paths = [data["file_path"] for _, data in valid_pairs]
        # noinspection PyArgumentList
        existing_dict = {
            s.file_name: s for s in
            await sync_to_async(list)(
                Sticker.objects.filter(file_name__in=file_paths)
            )
        }

        print(f"Found {len(existing_dict)} existing stickers")

        # Prepare new stickers
        new_stickers = []
        result_stickers = []

        for sticker_info, file_data in valid_pairs:
            file_path = file_data["file_path"]

            if file_path in existing_dict:
                result_stickers.append(existing_dict[file_path])
            else:
                new_sticker = Sticker(
                    emoji=sticker_info.get("emoji", ""),
                    file_name=file_path,
                    is_video=sticker_info.get("is_video", False),
                    is_animated=sticker_info.get("is_animated", False),
                )
                new_stickers.append(new_sticker)
                result_stickers.append(new_sticker)

        # Bulk create new stickers
        if new_stickers:
            print(f"Creating {len(new_stickers)} new stickers")
            await sync_to_async(Sticker.objects.bulk_create)(new_stickers)

        print(f"Returning {len(result_stickers)} sticker objects")
        return result_stickers

    except Exception as e:
        print(f"Database error in create_stickers_bulk_robust: {e}")
        return []


async def get_thumbnail_async(client, data):
    """Get thumbnail data with better error handling"""
    file_id = None

    try:
        if data.get("thumbnail"):
            file_id = data["thumbnail"]["file_id"]
        elif data.get("thumb"):
            file_id = data["thumb"]["file_id"]
        elif data["stickers"] and data["stickers"][0].get("thumbnail"):
            file_id = data["stickers"][0]["thumbnail"]["file_id"]

        if file_id:
            response = await client.get(
                f"{TELEGRAM_API}/getFile?file_id={file_id}",
                timeout=5.0
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return result["result"]

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
            "thumbnail": i.thumbnail.file_name,
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
def get_sticker(request, file_type: str, file_name: str):

    # Construct cache key
    cache_key = f"sticker:{file_type}:{file_name}"
    cached_file = cache.get(cache_key)

    content_type, _ = mimetypes.guess_type(file_name)
    content_type = content_type or "application/octet-stream"

    # Serve from cache if available
    if cached_file:
        response = StreamingHttpResponse(cached_file, content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{file_name}"'
        response['Content-Length'] = str(len(cached_file))
        return response

    # Fetch the file from remote server
    file_url = f"{TELEGRAM_FILE}/{file_type}/{file_name}"
    try:
        file_res = session.get(file_url, stream=True, timeout=10)
        file_res.raise_for_status()
    except requests.RequestException:
        return HttpResponseNotFound("File not found or error fetching file.")

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
    response['Content-Disposition'] = f'inline; filename="{file_name}"'
    response['Content-Length'] = file_res.headers.get('Content-Length', '')

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
            "emoji": i.emoji,
            "file_name": i.file_name,
            "is_video": i.is_video,
            "is_animated": i.is_animated,
        })

    return JsonResponse({
        "name": pack_name,
        "title": sticker_pack.title,
        "thumbnail": sticker_pack.thumbnail.file_name,
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

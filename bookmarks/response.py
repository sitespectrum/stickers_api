import json
import bs4
import requests
from urllib.parse import urljoin

from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from url_normalize import url_normalize

from api.models import Bookmark, BookmarkFolder
from authenticate import wrappers
from stickers_backend import utils


# Create your views here.


def _bookmark_to_dict(bookmark: Bookmark):
    return {
        "id": bookmark.id,
        "name": bookmark.name,
        "url": bookmark.url,
        "folder": {
            "id": bookmark.folder.id,
            "name": bookmark.folder.name,
        } if bookmark.folder else None,
        "page_title": bookmark.page_title,
        "cover_image_url": bookmark.cover_image_url,
    }


def _extract_bookmark_metadata(url: str):
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AetherBookmarks/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=10,
        allow_redirects=True,
    )
    html = bs4.BeautifulSoup(r.text, "html.parser")

    def _get_meta(attrs):
        tag = html.find("meta", attrs=attrs)
        if not tag:
            return None
        content = tag.get("content")
        if not content:
            return None
        content = content.strip()
        return content or None

    title = (
        _get_meta({"property": "og:title"})
        or _get_meta({"name": "twitter:title"})
        or (html.title.text.strip() if html.title and html.title.text else None)
    )

    image = (
        _get_meta({"property": "og:image"})
        or _get_meta({"name": "twitter:image"})
        or _get_meta({"name": "twitter:image:src"})
        or _get_meta({"name": "thumbnail"})
    )

    if image:
        image = urljoin(r.url, image)

    return {
        "url": r.url,
        "title": title,
        "cover_image_url": image,
    }


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_bookmarks(request: WSGIRequest):
    return JsonResponse({"bookmarks": [
        _bookmark_to_dict(i) for i in Bookmark.objects.filter(owner=request.user)
    ]})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_bookmark_by_id(request: WSGIRequest, bookmark_id):
    if not Bookmark.objects.filter(id=bookmark_id, owner=request.user).exists():
        return JsonResponse({"error": "Bookmark not found"}, status=404)

    bookmark_object = Bookmark.objects.get(id=bookmark_id)
    return JsonResponse({"bookmark": _bookmark_to_dict(bookmark_object)})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["PUT"])
def save_bookmark(request: WSGIRequest, bookmark_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)

    folder_id = body.get("folder_id")
    folder = None
    if folder_id is not None:
        if folder_id == 0:
            folder = None
        elif not BookmarkFolder.objects.filter(id=folder_id, owner=request.user).exists():
            return JsonResponse({"error": "Folder not found"}, status=404)
        else:
            folder = BookmarkFolder.objects.get(id=folder_id)

    if bookmark_id == 0:
        name = body.get("name")
        url = url_normalize(body.get("url"), default_scheme="https")
        if not url:
            return JsonResponse({"error": "No URL"}, status=400)

        page_title = body.get("page_title")
        cover_image_url = body.get("cover_image_url")
        if not name or not page_title or not cover_image_url:
            try:
                meta = _extract_bookmark_metadata(url)
                page_title = page_title or meta.get("title")
                cover_image_url = cover_image_url or meta.get("cover_image_url")
                url = meta.get("url") or url
            except Exception:
                pass

        if not name:
            name = page_title or url

        Bookmark.objects.create(
            name=name,
            url=url,
            owner=request.user,
            folder=folder,
            page_title=page_title,
            cover_image_url=cover_image_url,
        )
        return JsonResponse({"status": "Success"}, status=201)
    if not Bookmark.objects.filter(id=bookmark_id, owner=request.user).exists():
        return JsonResponse({"error": "Bookmark not found"}, status=404)
    bookmark = Bookmark.objects.get(id=bookmark_id)
    name = body.get("name")
    url = url_normalize(body.get("url"), default_scheme="https")
    if not url:
        return JsonResponse({"error": "No URL"}, status=400)

    page_title = body.get("page_title")
    cover_image_url = body.get("cover_image_url")

    if (not name) or (not page_title) or (not cover_image_url) or (bookmark.url != url):
        try:
            meta = _extract_bookmark_metadata(url)
            page_title = page_title or meta.get("title")
            cover_image_url = cover_image_url or meta.get("cover_image_url")
            url = meta.get("url") or url
        except Exception:
            pass

    if not name:
        name = page_title or url

    bookmark.name = name
    bookmark.url = url
    bookmark.folder = folder
    bookmark.page_title = page_title
    bookmark.cover_image_url = cover_image_url
    bookmark.save()
    return JsonResponse({"status": "Success"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_bookmark(request: WSGIRequest, bookmark_id):
    if not Bookmark.objects.filter(id=bookmark_id, owner=request.user).exists():
        return JsonResponse({"error": "Bookmark not found"}, status=404)
    Bookmark.objects.get(id=bookmark_id).delete()
    return JsonResponse({"status": "Success"}, status=204)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_bookmark_folders(request: WSGIRequest):
    return JsonResponse({"folders": [{
        "id": i.id,
        "name": i.name,
    } for i in BookmarkFolder.objects.filter(owner=request.user)]})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_bookmark_folder_by_id(request: WSGIRequest, folder_id):
    if not BookmarkFolder.objects.filter(id=folder_id, owner=request.user).exists():
        return JsonResponse({"error": "Folder not found"}, status=404)

    folder = BookmarkFolder.objects.get(id=folder_id)
    return JsonResponse({"folder": {
        "id": folder.id,
        "name": folder.name,
    }})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["PUT"])
def save_bookmark_folder(request: WSGIRequest, folder_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "No name"}, status=400)

    if folder_id == 0:
        BookmarkFolder.objects.create(name=name, owner=request.user)
        return JsonResponse({"status": "Success"}, status=201)

    if not BookmarkFolder.objects.filter(id=folder_id, owner=request.user).exists():
        return JsonResponse({"error": "Folder not found"}, status=404)

    folder = BookmarkFolder.objects.get(id=folder_id)
    folder.name = name
    folder.save()
    return JsonResponse({"status": "Success"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_bookmark_folder(request: WSGIRequest, folder_id):
    if not BookmarkFolder.objects.filter(id=folder_id, owner=request.user).exists():
        return JsonResponse({"error": "Folder not found"}, status=404)

    folder = BookmarkFolder.objects.get(id=folder_id)
    Bookmark.objects.filter(owner=request.user, folder=folder).update(folder=None)
    folder.delete()
    return JsonResponse({"status": "Success"}, status=204)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_bookmark_metadata_from_url(request: WSGIRequest):
    url = url_normalize(request.GET.get("url"), default_scheme="https")
    if not url:
        return JsonResponse({"error": "No URL"}, status=400)

    try:
        meta = _extract_bookmark_metadata(url)
    except Exception:
        return JsonResponse({"error": "Unable to fetch metadata"}, status=400)

    return JsonResponse({
        "url": meta.get("url") or url,
        "title": meta.get("title"),
        "cover_image_url": meta.get("cover_image_url"),
    })

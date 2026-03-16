import json
import bs4
import requests
from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from url_normalize import url_normalize

from api.models import Bookmark
from authenticate import wrappers
from stickers_backend import utils


# Create your views here.


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_bookmarks(request: WSGIRequest):
    return JsonResponse({"bookmarks": [{
        "id": i.id,
        "name": i.name,
        "url": i.url,
    } for i in Bookmark.objects.filter(owner=request.user)]})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_bookmark_by_id(request: WSGIRequest, bookmark_id):
    if not Bookmark.objects.filter(id=bookmark_id, owner=request.user).exists():
        return JsonResponse({"error": "Bookmark not found"}, status=404)

    bookmark_object = Bookmark.objects.get(id=bookmark_id)
    return JsonResponse({"bookmark": {
        "id": bookmark_object.id,
        "name": bookmark_object.name,
        "url": bookmark_object.url
    }})


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
    if bookmark_id == 0:
        name = body.get("name")
        url = url_normalize(body.get("url"), default_scheme="https")
        if not url:
            return JsonResponse({"error": "No URL"}, status=400)
        if not name:
            try:
                r = requests.get(url)
                html = bs4.BeautifulSoup(r.text, "html.parser")
                name = html.title.text
            except Exception as e:
                name = url
        Bookmark.objects.create(name=name, url=url, owner=request.user)
        return JsonResponse({"status": "Success"}, status=201)
    if not Bookmark.objects.filter(id=bookmark_id, owner=request.user).exists():
        return JsonResponse({"error": "Bookmark not found"}, status=404)
    bookmark = Bookmark.objects.get(id=bookmark_id)
    name = body.get("name")
    url = url_normalize(body.get("url"), default_scheme="https")
    if not url:
        return JsonResponse({"error": "No URL"}, status=400)
    if not name or bookmark.url != url:
        # noinspection PyBroadException
        try:
            r = requests.get(url)
            html = bs4.BeautifulSoup(r.text, "html.parser")
            name = html.title.text
        except Exception as e:
            name = url
    bookmark.name = name
    bookmark.url = url
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

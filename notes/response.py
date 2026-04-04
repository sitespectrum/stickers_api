import json

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_GET

from api.models import Note

from authenticate import wrappers
from stickers_backend import utils


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_notes(request: WSGIRequest):
    return JsonResponse({"notes": [i.to_dict(truncate=True) for i in Note.objects.filter(owner=request.user)]})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_note_by_id(request: WSGIRequest, note_id):
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)

    note_object = Note.objects.get(id=note_id)
    return JsonResponse({"note": note_object.to_dict()})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["PUT"])
def save_note(request: WSGIRequest, note_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    if note_id == 0:
        name = body.get("name") or ""
        content = body.get("content") or ""
        Note.objects.create(name=name, content=content, owner=request.user)
        return JsonResponse({"status": "Success"}, status=201)
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)
    note = Note.objects.get(id=note_id)
    name = body.get("name") or ""
    content = body.get("content") or ""
    note.name = name
    note.content = content
    note.save()
    return JsonResponse({"status": "Success"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_note(request: WSGIRequest, note_id):
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)
    Note.objects.get(id=note_id).delete()
    return HttpResponse(status=204)

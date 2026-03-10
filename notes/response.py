import json

from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from api.models import Note

from authenticate import wrappers
from stickers_backend import utils

# Create your views here.


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_notes(request: WSGIRequest):
    return JsonResponse({"notes": [{
        "id": i.id,
        "name": i.name,
    } for i in Note.objects.filter(owner=request.user)]})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_note_by_id(request: WSGIRequest, note_id):
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)

    note_object = Note.objects.get(id=note_id)
    return JsonResponse({"note": {
        "id": note_object.id,
        "name": note_object.name,
        "content": note_object.content
    }})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def save_note(request: WSGIRequest, note_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    if note_id == 0:
        name = body.get("name")
        content = body.get("content")
        if not content:
            return JsonResponse({"error": "No content"}, status=400)
        if not name:
            name = content[:10] + "..." if len(content) > 13 else content
        Note.objects.create(name=name, content=content, owner=request.user)
        return JsonResponse({"status": "Success"}, status=200)
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)
    note = Note.objects.get(id=note_id)
    name = body.get("name")
    content = body.get("content")
    if not content:
        return JsonResponse({"error": "No content"}, status=400)
    if not name:
        name = content[:10] + "..." if len(content) > 13 else content
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
    return JsonResponse({"status": "Success"}, status=200)

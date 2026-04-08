import json

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_GET
from django.db.models import Q

from api.models import Note, NoteTag

from authenticate import wrappers
from stickers_backend import utils


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_notes(request: WSGIRequest):
    query = (request.GET.get("query") or "").strip()
    tags_raw = (request.GET.get("tags") or "").strip()

    notes = Note.objects.filter(owner=request.user)

    if query:
        notes = notes.filter(Q(name__icontains=query) | Q(content__icontains=query))

    if tags_raw:
        tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
        if tag_names:
            notes = notes.filter(tags__name__in=tag_names).distinct()

    return JsonResponse({"notes": [i.to_dict(truncate=True) for i in notes]})


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
        note = Note.objects.create(name=name, content=content, owner=request.user)

        tags = body.get("tags")
        if isinstance(tags, list):
            tag_ids = []
            for t in tags:
                if isinstance(t, int):
                    tag_ids.append(t)
                elif isinstance(t, dict) and isinstance(t.get("id"), int):
                    tag_ids.append(t.get("id"))
            if tag_ids:
                note.tags.set(NoteTag.objects.filter(id__in=tag_ids))

        return JsonResponse({"status": "Success"}, status=201)
    if not Note.objects.filter(id=note_id, owner=request.user).exists():
        return JsonResponse({"error": "Note not found"}, status=404)
    note = Note.objects.get(id=note_id)
    name = body.get("name") or ""
    content = body.get("content") or ""
    note.name = name
    note.content = content
    note.save()

    tags = body.get("tags")
    if isinstance(tags, list):
        tag_ids = []
        for t in tags:
            if isinstance(t, int):
                tag_ids.append(t)
            elif isinstance(t, dict) and isinstance(t.get("id"), int):
                tag_ids.append(t.get("id"))
        note.tags.set(NoteTag.objects.filter(id__in=tag_ids))

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


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_note_tags(request: WSGIRequest):
    return JsonResponse({
        "tags": [i.to_dict() for i in NoteTag.objects.all().order_by("name")]
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["PUT"])
def save_note_tag(request: WSGIRequest, tag_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Invalid name"}, status=400)

    if tag_id == 0:
        if NoteTag.objects.filter(name__iexact=name).exists():
            tag = NoteTag.objects.get(name__iexact=name)
            return JsonResponse({"tag": tag.to_dict()}, status=200)

        tag = NoteTag.objects.create(name=name)
        return JsonResponse({"tag": tag.to_dict()}, status=201)

    if not NoteTag.objects.filter(id=tag_id).exists():
        return JsonResponse({"error": "Tag not found"}, status=404)

    tag = NoteTag.objects.get(id=tag_id)
    tag.name = name
    tag.save()
    return JsonResponse({"tag": tag.to_dict()}, status=200)

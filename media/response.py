from django.core.handlers.wsgi import WSGIRequest
from django.db import IntegrityError
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from api.models import S3File
from authenticate import wrappers
from stickers_backend import utils
from stickers_backend.settings import MAX_UPLOAD_SIZE


# Create your views here.


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_file(request, filename):
    if filename.startswith(".."):
        return JsonResponse({"error": "File not found"}, status=404)
    if not S3File.objects.filter(name=filename, owner=request.user).exists():
        return JsonResponse({"error": "File not found"}, status=404)
    file = S3File.objects.get(name=filename, owner=request.user)
    return FileResponse(file.file, filename=file.name)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_POST
@wrappers.login_required()
def upload_file(request: WSGIRequest) -> JsonResponse:
    for file in request.FILES.getlist("file"):
        if file.size/1024/1024 > MAX_UPLOAD_SIZE:
            return JsonResponse({
                'status': 'Error',
                'error': f'File {file.name} too large',
            }, status=413)
        try:
            if S3File.objects.filter(name=file.name, owner=request.user).exists():
                return JsonResponse({
                    'status': 'Error',
                    'error': f'File {file.name} already exists',
                }, status=400)
            S3File.objects.create(name=file.name, owner=request.user, file=file)
        except IntegrityError:
            continue

    return JsonResponse({'status': 'Ok'}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_files(request: WSGIRequest):
    return JsonResponse({
        "files": [{
            "id": i.id,
            "name": i.name,
        } for i in S3File.objects.filter(owner=request.user)]
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_file(request: WSGIRequest, file_id):
    if not S3File.objects.filter(id=file_id, owner=request.user).exists():
        return JsonResponse({"error": "File not found"}, status=404)
    S3File.objects.get(id=file_id).delete()
    return JsonResponse({"status": "Ok"}, status=200)
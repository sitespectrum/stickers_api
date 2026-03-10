from django.core.handlers.wsgi import WSGIRequest
from django.db import IntegrityError
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from api.models import S3File, UserData
from authenticate import wrappers
from stickers_backend import utils
from stickers_backend.settings import MAX_UPLOAD_SIZE, MAX_USER_STORAGE


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
    user_data = UserData.objects.get(user=request.user)
    for file in request.FILES.getlist("file"):
        if file.size/1024/1024 > MAX_UPLOAD_SIZE:
            return JsonResponse({
                'status': 'Error',
                'error': f'File {file.name} is too large',
            }, status=413)
        try:
            if file.size + user_data.used_storage > MAX_USER_STORAGE*1024*1024:
                return JsonResponse({
                    'status': 'Error',
                    'error': f'You have reached your storage limit',
                }, status=403)
            if S3File.objects.filter(name=file.name, owner=request.user).exists():
                return JsonResponse({
                    'status': 'Error',
                    'error': f'File {file.name} already exists',
                }, status=400)
            S3File.objects.create(name=file.name, owner=request.user, file=file)
            user_data.refresh_from_db()
            user_data.used_storage += file.size
            if user_data.used_storage < 0:
                user_data.used_storage = 0
            user_data.save()
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
        } for i in S3File.objects.filter(owner=request.user)],
        "storage_used": UserData.objects.get(user=request.user).used_storage/1024/1024,
        "max_storage": MAX_USER_STORAGE,
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_file(request: WSGIRequest, file_id):
    if not S3File.objects.filter(id=file_id, owner=request.user).exists():
        return JsonResponse({"error": "File not found"}, status=404)
    file_obj = S3File.objects.get(id=file_id)
    user_data = UserData.objects.get(user=request.user)
    user_data.used_storage -= file_obj.file.size
    user_data.save()
    file_obj.delete()
    return JsonResponse({"status": "Ok"}, status=200)
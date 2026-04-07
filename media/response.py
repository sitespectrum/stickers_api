from django.core.handlers.wsgi import WSGIRequest
from django.db import IntegrityError
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from api.models import S3File, S3Folder, UserData
from authenticate import wrappers
from stickers_backend import utils
from stickers_backend.settings import MAX_UPLOAD_SIZE, MAX_USER_STORAGE


def _get_folder_or_400(request: WSGIRequest, folder_id):
    if folder_id is None:
        return None, None
    try:
        folder_id_int = int(folder_id)
    except (TypeError, ValueError):
        return None, JsonResponse({"error": "Invalid folder_id"}, status=400)
    try:
        folder = S3Folder.objects.get(id=folder_id_int, owner=request.user)
    except S3Folder.DoesNotExist:
        return None, JsonResponse({"error": "Folder not found"}, status=404)
    return folder, None


def _is_descendant(folder: S3Folder, possible_ancestor: S3Folder) -> bool:
    current = folder.parent
    while current is not None:
        if current.id == possible_ancestor.id:
            return True
        current = current.parent
    return False


# Create your views here.
@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
def get_file_metadata(request, file_name):
    try:
        file_obj = S3File.objects.get(name=file_name, owner=request.user)
        file_size = file_obj.size
    except S3File.DoesNotExist:
        return JsonResponse({'error': 'Not Found'}, status=404)

    return JsonResponse({
        "status": "Ok",
        "name": file_name,
        "size": file_size,
    })


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
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_file_by_id(request: WSGIRequest, file_id: int):
    try:
        file_obj = S3File.objects.get(id=file_id, owner=request.user)
    except S3File.DoesNotExist:
        return JsonResponse({"error": "File not found"}, status=404)
    return FileResponse(file_obj.file, filename=file_obj.name)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_file_metadata_by_id(request: WSGIRequest, file_id: int):
    try:
        file_obj = S3File.objects.get(id=file_id, owner=request.user)
    except S3File.DoesNotExist:
        return JsonResponse({'error': 'Not Found'}, status=404)

    return JsonResponse({
        "status": "Ok",
        "id": file_obj.id,
        "name": file_obj.name,
        "size": file_obj.size,
    })


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_POST
@wrappers.login_required()
def upload_file(request: WSGIRequest) -> JsonResponse:
    folder_id = request.GET.get("folder_id")
    folder, folder_error = _get_folder_or_400(request, folder_id)
    if folder_error is not None:
        return folder_error
    for file in request.FILES.getlist("file"):
        if file.size/1024/1024 > MAX_UPLOAD_SIZE:
            return JsonResponse({
                'status': 'Error',
                'error': f'File {file.name} is too large',
            }, status=413)
        try:
            if file.size + sum(i.size for i in S3File.objects.filter(owner=request.user)) > MAX_USER_STORAGE*1024*1024:
                return JsonResponse({
                    'status': 'Error',
                    'error': f'You have reached your storage limit',
                }, status=403)
            if S3File.objects.filter(name=file.name, owner=request.user, folder=folder).exists():
                return JsonResponse({
                    'status': 'Error',
                    'error': f'File {file.name} already exists',
                }, status=400)
            file_object = S3File.objects.create(name=file.name, owner=request.user, file=file, folder=folder)
            file_object.file.save(file.name, file)
            file_object.save()
            file_object.refresh_from_db()
            file_object.size = file.size
            file_object.save()
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
        "storage_used": sum(i.size for i in S3File.objects.filter(owner=request.user))/1024/1024,
        "max_storage": MAX_USER_STORAGE,
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def list_folder(request: WSGIRequest):
    folder_id = request.GET.get("folder_id")
    folder, folder_error = _get_folder_or_400(request, folder_id)
    if folder_error is not None:
        return folder_error

    folders_qs = S3Folder.objects.filter(owner=request.user, parent=folder).order_by("name")
    files_qs = S3File.objects.filter(owner=request.user, folder=folder).order_by("name")

    return JsonResponse({
        "status": "Ok",
        "folder": folder.to_dict() if folder is not None else None,
        "folders": [f.to_dict() for f in folders_qs],
        "files": [f.to_dict() for f in files_qs],
        "storage_used": sum(i.size for i in S3File.objects.filter(owner=request.user))/1024/1024,
        "max_storage": MAX_USER_STORAGE,
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_GET
def get_all_folders(request: WSGIRequest):
    folders_qs = S3Folder.objects.filter(owner=request.user).order_by("name")
    return JsonResponse({
        "status": "Ok",
        "folders": [f.to_dict() for f in folders_qs],
    })


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def create_folder(request: WSGIRequest):
    name = request.POST.get("name")
    if not name:
        return JsonResponse({"error": "Missing name"}, status=400)

    parent_id = request.POST.get("parent_id")
    parent, parent_error = _get_folder_or_400(request, parent_id)
    if parent_error is not None:
        return parent_error

    try:
        folder = S3Folder.objects.create(name=name, owner=request.user, parent=parent)
    except IntegrityError:
        return JsonResponse({"error": "Folder already exists"}, status=400)

    return JsonResponse({"status": "Ok", "folder": folder.to_dict()}, status=201)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def rename_folder(request: WSGIRequest, folder_id: int):
    new_name = request.POST.get("name")
    if not new_name:
        return JsonResponse({"error": "Missing name"}, status=400)
    try:
        folder = S3Folder.objects.get(id=folder_id, owner=request.user)
    except S3Folder.DoesNotExist:
        return JsonResponse({"error": "Folder not found"}, status=404)
    folder.name = new_name
    try:
        folder.save()
    except IntegrityError:
        return JsonResponse({"error": "Folder name already exists"}, status=400)
    return JsonResponse({"status": "Ok", "folder": folder.to_dict()})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def move_folder(request: WSGIRequest, folder_id: int):
    new_parent_id = request.POST.get("parent_id")
    new_parent, parent_error = _get_folder_or_400(request, new_parent_id)
    if parent_error is not None:
        return parent_error
    try:
        folder = S3Folder.objects.get(id=folder_id, owner=request.user)
    except S3Folder.DoesNotExist:
        return JsonResponse({"error": "Folder not found"}, status=404)
    if new_parent is not None:
        if new_parent.id == folder.id or _is_descendant(new_parent, folder):
            return JsonResponse({"error": "Invalid parent folder"}, status=400)
    folder.parent = new_parent
    try:
        folder.save()
    except IntegrityError:
        return JsonResponse({"error": "Folder name already exists in target"}, status=400)
    return JsonResponse({"status": "Ok", "folder": folder.to_dict()})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_folder(request: WSGIRequest, folder_id: int):
    try:
        folder = S3Folder.objects.get(id=folder_id, owner=request.user)
    except S3Folder.DoesNotExist:
        return JsonResponse({"error": "Folder not found"}, status=404)

    recursive_param = request.GET.get("recursive")
    recursive = str(recursive_param).lower() in ("1", "true", "yes")

    if not recursive:
        if S3Folder.objects.filter(owner=request.user, parent=folder).exists() or S3File.objects.filter(owner=request.user, folder=folder).exists():
            return JsonResponse({"error": "Folder not empty"}, status=400)
        folder.delete()
        return JsonResponse({"status": "Ok"}, status=204)

    # Recursive delete: delete all files in this folder subtree, then delete the folder.
    # Child folders are deleted via CASCADE on the parent relationship.
    folders_to_delete = [folder]
    idx = 0
    while idx < len(folders_to_delete):
        current = folders_to_delete[idx]
        children = list(S3Folder.objects.filter(owner=request.user, parent=current))
        folders_to_delete.extend(children)
        idx += 1

    S3File.objects.filter(owner=request.user, folder__in=folders_to_delete).delete()
    folder.delete()
    return JsonResponse({"status": "Ok"}, status=204)


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def rename_file(request: WSGIRequest, file_id: int):
    new_name = request.POST.get("name")
    if not new_name:
        return JsonResponse({"error": "Missing name"}, status=400)
    try:
        file_obj = S3File.objects.get(id=file_id, owner=request.user)
    except S3File.DoesNotExist:
        return JsonResponse({"error": "File not found"}, status=404)
    file_obj.name = new_name
    try:
        file_obj.save()
    except IntegrityError:
        return JsonResponse({"error": "File name already exists in folder"}, status=400)
    return JsonResponse({"status": "Ok", "file": file_obj.to_dict()})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_POST
def move_file(request: WSGIRequest, file_id: int):
    folder_id = request.POST.get("folder_id")
    folder, folder_error = _get_folder_or_400(request, folder_id)
    if folder_error is not None:
        return folder_error
    try:
        file_obj = S3File.objects.get(id=file_id, owner=request.user)
    except S3File.DoesNotExist:
        return JsonResponse({"error": "File not found"}, status=404)
    file_obj.folder = folder
    try:
        file_obj.save()
    except IntegrityError:
        return JsonResponse({"error": "File name already exists in target folder"}, status=400)
    return JsonResponse({"status": "Ok", "file": file_obj.to_dict()})


@utils.panic_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@wrappers.login_required()
@require_http_methods(["DELETE"])
def delete_file(request: WSGIRequest, file_id):
    if not S3File.objects.filter(id=file_id, owner=request.user).exists():
        return JsonResponse({"error": "File not found"}, status=404)
    file_obj = S3File.objects.get(id=file_id)
    file_obj.delete()
    return JsonResponse({"status": "Ok"}, status=204)
from functools import wraps
from django.http import HttpResponseForbidden, JsonResponse
from api.models import UserData


def require_role(role_list):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user_data = UserData.objects.get(user=request.user)
            if user_data.role not in role_list:
                if "/api/" not in request.path:
                    with open("frontend/403.html") as f:
                        return HttpResponseForbidden(f.read())
                else:
                    return JsonResponse({
                        "status": "Error",
                        "error": "You don't have permission to access this endpoint.",
                    }, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

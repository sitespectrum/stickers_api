from django.urls import path
from site_admin import response

urlpatterns = [
    path('logs/all', response.get_all),
    path('logs/<int:log_id>', response.get_log),
    path('reset', response.reset_warning_status),
    path('status', response.get_status),
    path('status/<str:status>', response.set_service_status),
    path('update', response.update),
    path('log', response.create_log),
    path('users/all', response.get_users),
    path('users/create', response.create_user),
    path('users/roles', response.get_roles),
    path('users/<int:user_id>', response.modify_user),
    path('users/<int:user_id>/bans', response.bans),
    path('users/<int:user_id>/ban', response.ban_user),
    path('users/search', response.search_users),
    path('users/logout', response.logout_user),
    # path('users/lock', response.lock_user),
]

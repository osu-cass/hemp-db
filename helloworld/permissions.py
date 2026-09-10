"""Application permissions and authorization helpers for HempDB workflows."""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import resolve_url

EDIT_COMPANIES = "helloworld.edit_companies"
REVIEW_COMPANY_CHANGES = "helloworld.review_company_changes"
EDIT_METADATA = "helloworld.edit_metadata"

def has_permission(user, permission):
    """Return whether an authenticated user has the named permission."""
    return user.is_authenticated and user.has_perm(permission)


def can_view_pending_change(user, change):
    """Allow reviewers to view any change and editors to view their own."""
    return has_permission(user, REVIEW_COMPANY_CHANGES) or (
        has_permission(user, EDIT_COMPANIES) and change.author_id == user.pk
    )


def require_permission(request, permission):
    """Raise HTTP 403 unless the request user has the named permission."""
    if not has_permission(request.user, permission):
        raise PermissionDenied


def require_post_permission(permission):
    """Require a permission when a view receives a POST request."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                require_permission(request, permission)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def require_any_application_permission(*permissions):
    """Require at least one of the named application permissions."""

    def decorator(view):
        """Wrap a view with application-permission enforcement."""

        @wraps(view)
        def wrapped(request, *args, **kwargs):
            """Enforce application access before calling the view."""
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(
                    request.get_full_path(), resolve_url(settings.LOGIN_URL)
                )
            if not any(
                has_permission(request.user, permission)
                for permission in permissions
            ):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def require_application_permission(permission):
    """Decorate a view with an application-permission requirement."""
    return require_any_application_permission(permission)


def users_with_application_permission(permission):
    """Return active users who effectively hold an application permission."""
    app_label, codename = permission.split(".", 1)
    user_model = get_user_model()
    return (
        user_model.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(
                user_permissions__codename=codename,
                user_permissions__content_type__app_label=app_label,
            )
            | Q(
                groups__permissions__codename=codename,
                groups__permissions__content_type__app_label=app_label,
            )
        )
        .distinct()
    )

"""Feature permissions and authorization helpers for HempDB workflows."""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import resolve_url

SUBMIT_COMPANY_CHANGE = "helloworld.submit_company_change"
REVIEW_PENDING_CHANGE = "helloworld.review_pending_change"
UPLOAD_COMPANY_DATA = "helloworld.upload_company_data"
REVIEW_COMPANY_UPLOAD = "helloworld.review_company_upload"

FEATURE_PERMISSIONS = (
    SUBMIT_COMPANY_CHANGE,
    REVIEW_PENDING_CHANGE,
    UPLOAD_COMPANY_DATA,
    REVIEW_COMPANY_UPLOAD,
)


def permission_name(permission):
    """Return a fully qualified permission name for the HempDB app."""
    return permission if "." in permission else f"helloworld.{permission}"


def has_permission(user, permission):
    """Return whether an authenticated user has the named permission."""
    return user.is_authenticated and user.has_perm(permission_name(permission))


def require_permission(request, permission):
    """Raise HTTP 403 unless the request user has the named permission."""
    if not has_permission(request.user, permission):
        raise PermissionDenied


def has_feature_permission(user, permission):
    """Return whether a user has a feature permission or is a superuser."""
    return has_permission(user, permission)


def require_feature_permission(permission):
    """Decorate a view with a stable feature-permission requirement."""

    def decorator(view):
        """Wrap a view with feature-permission enforcement."""

        @wraps(view)
        def wrapped(request, *args, **kwargs):
            """Enforce the feature permission before calling the view."""
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(
                    request.get_full_path(), resolve_url(settings.LOGIN_URL)
                )
            if not has_feature_permission(request.user, permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def can_view_pending_change(user, change):
    """Return whether the user may inspect a pending-change record."""
    return user.is_authenticated and (
        change.author_id == user.pk
        or has_feature_permission(user, REVIEW_PENDING_CHANGE)
    )


def effective_feature_permissions(user):
    """Return the effective feature permissions for a user."""
    return {
        permission: has_feature_permission(user, permission)
        for permission in FEATURE_PERMISSIONS
    }


def users_with_feature_permission(permission):
    """Return active users who effectively hold a feature permission."""
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

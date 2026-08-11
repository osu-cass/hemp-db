import json
import os

from django.conf import settings

from .csp import REPORTING_GROUP, validate_report_uri


class PermissionsPolicyMiddleware:
    """Add the configured Permissions-Policy header to responses."""

    def __init__(self, get_response):
        """Store the next middleware and configured policy."""
        self.get_response = get_response
        self.policy = settings.PERMISSIONS_POLICY

    def __call__(self, request):
        """Add the policy unless the response already defines one."""
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", self.policy)
        return response


class CSPReportingMiddleware:
    """Add Reporting API headers for a configured CSP endpoint."""

    def __init__(self, get_response):
        """Store the next middleware callable."""
        self.get_response = get_response

    def __call__(self, request):
        """Add reporting headers to the response when configured."""
        response = self.get_response(request)
        report_uri = validate_report_uri(os.getenv("CSP_REPORT_URI"))
        if not report_uri:
            return response

        response["Reporting-Endpoints"] = (
            f'{REPORTING_GROUP}="{report_uri}"'
        )
        response["Report-To"] = json.dumps(
            {
                "group": REPORTING_GROUP,
                "max_age": 10886400,
                "endpoints": [{"url": report_uri}],
            },
            separators=(",", ":"),
        )
        return response

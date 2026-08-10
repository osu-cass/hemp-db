import json
import os

from .csp import REPORTING_GROUP, validate_report_uri


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

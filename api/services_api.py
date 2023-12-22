from backoff import on_exception, expo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from ratelimit import limits, RateLimitException

from config import settings
from middleware import logger

SERVICES_API = "servicecontrol"
PROJECT_PREFIX = "DEMO-" if settings["is_codelab"] else ""
logger.info(f"project prefix", project_prefix=PROJECT_PREFIX)

FIFTEEN_MINUTES = 900


class ServicesApi(object):
    """Utilities for interacting with the Services API."""

    def __init__(self, project_id):
        if settings.use_service_account:
            credentials = service_account.Credentials.from_service_account_file('service-account.json', scopes=[])
            self.service = build(SERVICES_API, "v1", cache_discovery=False, credentials=credentials)
        else:
            self.service = build(SERVICES_API, "v1", cache_discovery=False)
        self.project_id = project_id

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def check_service(self, operation):
        """Check service is still ready to receive usage report."""
        try:
            request = self.service.services().check(
                serviceName="dynamic-landing-pages.endpoints.adeptmind-public.cloud.goog",
                body={"operation": operation}
            )
            response = request.execute()
            check_errors = response.get("checkErrors", [])
            return not bool(check_errors)
        except Exception as err:
            logger.error(f"error checking services api", exception=err)
            return False

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def report_usage(self, operations):
        """Report usage operations."""
        try:
            request = self.service.services().report(
                serviceName="dynamic-landing-pages.endpoints.adeptmind-public.cloud.goog",
                body={"operations": operations}
            )
            request.execute()
            return True
        except Exception as err:
            logger.error(f"error checking services api", exception=err)
            return False

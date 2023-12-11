import json

import requests
from backoff import on_exception, expo
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ratelimit import limits, RateLimitException

from config import settings
from middleware import logger

PROCUREMENT_API = "cloudcommerceprocurement"
# TODO: what is the prefix in prod
PROJECT_PREFIX = "DEMO-" if settings["is_codelab"] else ""
logger.info(f"project prefix", project_prefix=PROJECT_PREFIX)

FIFTEEN_MINUTES = 15


class ProcurementApi(object):
    """Utilities for interacting with the Procurement API."""

    def __init__(self, project_id):
        self.service = build(PROCUREMENT_API, "v1", cache_discovery=False)
        self.project_id = project_id

    ##########################
    ### Account operations ###
    ##########################

    def get_account_id(self, name):
        # name is of format "providers/DEMO-project_id/accounts/12345"
        return name[len(f"providers/{PROJECT_PREFIX}{self.project_id}/accounts/") :]

    def get_account_name(self, account_id):
        return f"providers/{PROJECT_PREFIX}{self.project_id}/accounts/{account_id}"

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def get_account(self, account_id):
        """Gets an account from the Procurement Service."""
        logger.debug("get_account", account_id=account_id)
        name = self.get_account_name(account_id)
        request = self.service.providers().accounts().get(name=name)
        try:
            response = request.execute()
            return response
        except HttpError as err:
            logger.error(f"error calling procurement api", exception=err)
            if err.resp.status == 404:
                return None

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def approve_account(self, account_id):
        """Approves the account in the Procurement Service."""
        logger.debug("approve_account", account_id=account_id)
        name = self.get_account_name(account_id)
        request = (
            self.service.providers()
            .accounts()
            .approve(name=name, body={"approvalName": "signup"})
        )
        return request.execute()

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def reset_account(self, account_id):
        """Resets the account in the Procurement Service."""
        logger.debug("reset_account", account_id=account_id)
        name = self.get_account_name(account_id)
        request = self.service.providers().accounts().reset(name=name)
        return request.execute()

    ##############################
    ### Entitlement operations ###
    ##############################

    def _get_entitlement_name(self, entitlement_id):
        return (
            f"providers/{PROJECT_PREFIX}{self.project_id}/entitlements/{entitlement_id}"
        )
    
    def get_entitlement_id(self, name):
        # name is of format "providers/{providerId}/entitlements/{entitlement_id}"
        return name.split("/")[-1]
    
    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def get_entitlement(self, entitlement_id):
        """Gets an entitlement from the Procurement Service."""
        logger.debug("get_entitlement", entitlement_id=entitlement_id)
        name = self._get_entitlement_name(entitlement_id)
        request = self.service.providers().entitlements().get(name=name)
        try:
            response = request.execute()
            return response
        except HttpError as err:
            logger.error(f"error calling procurement api", exception=err)
            if err.resp.status == 404:
                return None

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def approve_entitlement(self, account_id, entitlement_id):
        """Approves the entitlement in the Procurement Service."""
        logger.debug("approve_entitlement", entitlement_id=entitlement_id)
        name = self._get_entitlement_name(entitlement_id)
        request = self.service.providers().entitlements().approve(name=name, body={})
        request.execute()
        # self.add_entitlement_to_dlp_store(account_id, entitlement_id)

    def add_entitlement_to_dlp_store(self, account_id, entitlement_id):
        resp = requests.get(
            f"{settings.dlp_store_base}/api/v1/page/customer/?gcp_marketplace_account_id={account_id}",
            headers={
                "x-api-key": settings.dlp_store_api_key
            },
        )
        accounts = resp.json()
        if accounts["count"] != 1:
            raise Exception(f"GCP Customer accounts count should be exactly 1 but {accounts['count']} found")
        customer = accounts["results"][0]
        entitlements = customer["gcp_marketplace_entitlements"]
        entitlement = self.get_entitlement(entitlement_id)
        if entitlement is None:
            raise Exception("Could not fetch entitlement details")
        entitlements[entitlement_id] = entitlement
        customer["gcp_marketplace_entitlements"] = entitlements
        resp = requests.patch(
            f"{settings.dlp_store_base}/api/v1/page/customer/{customer['id']}/",
            data={
                "gcp_marketplace_entitlements": json.dumps(entitlements)
            },
            headers={
                "x-api-key": settings.dlp_store_api_key,
            },
        )
        if resp.status_code < 200 or resp.status_code >= 300:
            raise Exception("Could not update entitlement")

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def reject_entitlement(self, entitlement_id, reason):
        """Rejects the entitlement in the Procurement Service."""
        logger.debug("reject_entitlement", entitlement_id=entitlement_id)
        name = self._get_entitlement_name(entitlement_id)
        request = (
            self.service.providers()
            .entitlements()
            .reject(name=name, body={"reason": reason})
        )
        request.execute()

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=15, period=FIFTEEN_MINUTES)
    def approve_entitlement_plan_change(self, entitlement_id, new_pending_plan):
        """Approves the entitlement plan change in the Procurement Service."""
        logger.debug(
            "approve_entitlement_plan_change",
            entitlement_id=entitlement_id,
            new_pending_plan=new_pending_plan,
        )
        name = self._get_entitlement_name(entitlement_id)
        body = {"pendingPlanName": new_pending_plan}
        request = (
            self.service.providers()
            .entitlements()
            .approvePlanChange(name=name, body=body)
        )
        request.execute()

    def list_accounts(self):
        request = self.service.providers().accounts().list(parent=f"providers/{PROJECT_PREFIX}{self.project_id}")
        resp = request.execute()
        return resp

    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=150, period=FIFTEEN_MINUTES)
    def list_entitlements(self, state=None, account_id=None, offer=None):
        account_filter = f"account={account_id}" if account_id else ""
        offer_filter = f'offer="projects/965780882353/services/service.endpoints.private-adeptmind-1763358.cloud.goog/privateOffers/{offer}"' if offer else ""
        state_filter = f"state={state}" if state else ""
        filter_param = ",".join([f for f in [state_filter, account_filter, offer_filter] if f])
        # todo, maybe need to handle paging at some point
        request = (
            self.service.providers()
            .entitlements()
            .list(
                parent=f"providers/{PROJECT_PREFIX}{self.project_id}",
                filter=filter_param,
            )
        )
        try:
            response = request.execute()
            return response
        except HttpError as err:
            logger.error(f"error calling procurement api", exception=err)
            raise err

def is_account_approved(account: dict) -> bool:
    """Helper function to inspect the account to see if its approved"""

    approval = None
    for account_approval in account["approvals"]:
        if account_approval["name"] == "signup":
            approval = account_approval
            break
    logger.debug("found approval", approval=approval)

    if approval:
        if approval["state"] == "PENDING":
            logger.info("account is pending")
            return False
        elif approval["state"] == "APPROVED":
            logger.info("account is approved")
            return True
    else:
        logger.debug("no approval found")
        # The account has been deleted
        return False

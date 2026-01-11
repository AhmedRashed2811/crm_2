from __future__ import annotations
from django.utils.deprecation import MiddlewareMixin
from .utils.ids import new_request_id


class RequestIdMiddleware(MiddlewareMixin):
    HEADER_NAME = "HTTP_X_REQUEST_ID"

    def process_request(self, request):
        request.request_id = request.META.get(self.HEADER_NAME) or new_request_id()

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response["X-Request-Id"] = rid
        return response

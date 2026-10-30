"""Bounded JSON transport for trusted service endpoints, without redirects."""
import json
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoServiceRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a service bearer token to a redirected destination.
        raise HTTPError(req.full_url, code, 'Service redirects are not allowed', headers, fp)


def open_service_request(request, *, timeout, context=None):
    return build_opener(NoServiceRedirects(), HTTPSHandler(context=context)).open(
        request, timeout=timeout,
    )


def read_json_object(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('Service response exceeds the size limit')
    body = json.loads(raw.decode('utf-8'))
    if not isinstance(body, dict):
        raise ValueError('Service response must be a JSON object')
    return body
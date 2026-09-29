from urllib.parse import urlsplit, urlunsplit

from django.conf import settings


class StripPrefixFromRedirectsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return self.process_response(request, response)

    def process_response(self, request, response):
        if not settings.STRIP_PREFIX_FROM_REDIRECTS or not settings.FORCE_SCRIPT_NAME:
            return response
        if not 300 <= response.status_code < 400 or not response.has_header('Location'):
            return response

        location = urlsplit(response['Location'])
        if location.scheme or location.netloc:
            return response

        prefix = settings.FORCE_SCRIPT_NAME.rstrip('/')
        if location.path == prefix:
            path = '/'
        elif location.path.startswith(f'{prefix}/'):
            path = location.path[len(prefix):]
        else:
            return response

        response['Location'] = urlunsplit(('', '', path, location.query, location.fragment))
        return response

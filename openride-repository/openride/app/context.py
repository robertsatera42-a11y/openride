from django.conf import settings
def app_config(request):
    return {'map_enabled':bool(settings.GEOAPIFY_SERVER_KEY)}

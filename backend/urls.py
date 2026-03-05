# backend/backend/urls.py

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import FileResponse
import os

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

# Serve media files locally ONLY when R2 is disabled
if settings.DEBUG and not getattr(settings, 'CLOUDFLARE_R2_ENABLED', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ── Serve built React frontend ────────────────────────────────────────────────
FRONTEND_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'frontend', 'dist'
)

INDEX_HTML = os.path.join(FRONTEND_DIST, 'index.html')


def serve_index(request, **kwargs):
    """Always serve React's index.html for any non-API path."""
    return FileResponse(open(INDEX_HTML, 'rb'), content_type='text/html')


if os.path.exists(FRONTEND_DIST):
    urlpatterns += [
        # JS/CSS/image assets (Vite puts them in assets/)
        re_path(r'^assets/(?P<path>.*)$', serve,
                {'document_root': os.path.join(FRONTEND_DIST, 'assets')}),

        # Root-level static files
        re_path(
            r'^(?P<path>favicon\.ico|robots\.txt|manifest\.json|logo.*|vite\.svg)$',
            serve, {'document_root': FRONTEND_DIST}
        ),

        # ── ALL other routes → index.html ─────────────────────────────────────
        # Covers: /  /menu  /waiter  /kitchen  /staff  /mobile  etc.
        # React reads window.location in App.jsx to decide what to render.
        re_path(r'^(?!api/|admin/|static/|media/|ws/).*$', serve_index),
    ]
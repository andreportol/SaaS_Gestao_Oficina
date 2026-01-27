from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import include, path
from django.views.generic.base import RedirectView

from core import views as core_views

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url("core/favicon.svg"))),
    path('admin/', admin.site.urls),
    path('accounts/login/', core_views.CustomLoginView.as_view(), name='login'),
    path('accounts/recuperar/', core_views.PasswordRecoveryView.as_view(), name='password_recovery'),
    path('accounts/logout/', core_views.logout_view, name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('core.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

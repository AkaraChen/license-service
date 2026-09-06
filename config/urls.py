from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path

from licenses import api, views_ui

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views_ui.home, name="ui_home"),
    path("ui/register", views_ui.register_page, name="ui_register"),
    path("ui/login", views_ui.CustomerLoginView.as_view(), name="ui_login"),
    path("ui/logout", LogoutView.as_view(next_page="ui_login"), name="ui_logout"),
    path("ui/redeem", views_ui.redeem_page, name="ui_redeem"),
    path("ui/entitlements/<int:entitlement_id>", views_ui.entitlement_page, name="ui_entitlement"),
    path("ui/devices/<int:device_id>/unbind", views_ui.unbind_page, name="ui_unbind_device"),
    path("ui/devices/<int:device_id>/rename", views_ui.rename_page, name="ui_rename_device"),
    path("", api.api.urls),
]

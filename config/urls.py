from django.contrib import admin
from django.urls import path

from licenses import api, openapi, views_ui

urlpatterns = [
    path("admin/", admin.site.urls),
    path("openapi.json", openapi.openapi_view, name="openapi"),
    path("", views_ui.home, name="ui_home"),
    path("ui/register", views_ui.register_page, name="ui_register"),
    path("ui/login", views_ui.login_page, name="ui_login"),
    path("ui/logout", views_ui.logout_page, name="ui_logout"),
    path("ui/redeem", views_ui.redeem_page, name="ui_redeem"),
    path("ui/entitlements/<int:entitlement_id>", views_ui.entitlement_page, name="ui_entitlement"),
    path("ui/devices/<int:device_id>/unbind", views_ui.unbind_page, name="ui_unbind_device"),
    path("ui/devices/<int:device_id>/rename", views_ui.rename_page, name="ui_rename_device"),
    *api.urlpatterns,
]

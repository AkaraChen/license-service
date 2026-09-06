from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path

from licenses.views import api, customer

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", customer.home, name="ui_home"),
    path("ui/register", customer.register_page, name="ui_register"),
    path("ui/login", customer.CustomerLoginView.as_view(), name="ui_login"),
    path("ui/logout", LogoutView.as_view(next_page="ui_login"), name="ui_logout"),
    path("ui/redeem", customer.redeem_page, name="ui_redeem"),
    path("ui/entitlements/<int:entitlement_id>", customer.entitlement_page, name="ui_entitlement"),
    path("ui/devices/<int:device_id>/unbind", customer.unbind_page, name="ui_unbind_device"),
    path("ui/devices/<int:device_id>/rename", customer.rename_page, name="ui_rename_device"),
    path("", api.api.urls),
]

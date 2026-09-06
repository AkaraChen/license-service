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
    path("api/auth/register", api.register, name="api_register"),
    path("api/auth/login", api.login_op, name="api_login_op"),
    path("api/auth/logout", api.logout_op, name="api_logout_op"),
    path("api/products", api.products, name="api_products"),
    path("api/products/<int:pk>", api.product_detail, name="api_product_detail"),
    path("api/license-keys", api.license_keys, name="api_license_keys"),
    path("api/license-keys/<int:pk>/revoke", api.revoke_license_key, name="api_revoke_license_key"),
    path("api/entitlements/<int:pk>/status", api.set_entitlement_status, name="api_set_entitlement_status"),
    path("api/devices/<int:pk>/unbind", api.unbind_device, name="api_unbind_device"),
    path("api/accounts", api.list_accounts, name="api_list_accounts"),
    path("api/entitlements", api.list_entitlements, name="api_list_entitlements"),
    path("api/devices", api.list_devices, name="api_list_devices"),
    path("api/accounts/<int:pk>", api.get_account, name="api_get_account"),
    path("api/me/redeem", api.redeem_license_key, name="api_redeem_license_key"),
    path("api/me/entitlements", api.list_my_entitlements, name="api_list_my_entitlements"),
    path("api/me/entitlements/<int:pk>", api.get_my_entitlement, name="api_get_my_entitlement"),
    path("api/me/entitlements/<int:pk>/devices", api.my_devices, name="api_my_devices"),
    path("api/me/devices/<int:pk>/unbind", api.unbind_my_device, name="api_unbind_my_device"),
    path("api/me/devices/<int:pk>", api.set_my_device_display_name, name="api_set_my_device_display_name"),
    path("api/activate", api.activate_device, name="api_activate_device"),
    path("api/validate", api.validate_device, name="api_validate_device"),
]

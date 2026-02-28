# api/urls.py
# UPDATED: Added Table Master endpoints
# UPDATED: Added TV Banner endpoints

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MenuItemViewSet,
    CategoryViewSet,
    TaxViewSet,
    user_login,
    verify_secret_code,
    company_login,
    superadmin_login,
    create_super_admin,
    check_super_admin_exists,
    get_users,
    create_user,
    update_user,
    delete_user,
    get_user_stats,
    get_company_info,
    create_or_update_company,
    get_customization,
    save_customization,
    delete_customization_file,
    get_banners,
    upload_banners,
    delete_banner,
    reorder_banners,
    # ── NEW: Table Master ───────────────────────────────────────────────────────
    get_tables,
    create_table,
    update_table,
    delete_table,
    # ── NEW: TV Banner Manager ──────────────────────────────────────────────────
    get_tv_banners,
    upload_tv_banners,
    delete_tv_banner,
    reorder_tv_banners,
    # ── Orders ──────────────────────────────────────────────────────────────────
    create_order,
    get_orders,
    get_order_detail,
    update_order_status,
    cancel_order,
    get_order_stats,
    accept_order,
    get_waiter_list,
    staff_login,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'taxes', TaxViewSet, basename='tax')
router.register(r'menu-items', MenuItemViewSet, basename='menuitem')

urlpatterns = [
    path('', include(router.urls)),

    # ── Authentication ────────────────────────────────────────────────────────
    path('user-login/',         user_login,               name='user-login'),
    path('staff-login/',        staff_login,              name='staff-login'),
    path('verify-secret/',      verify_secret_code,       name='verify-secret'),
    path('company-login/',      company_login,            name='company-login'),
    path('superadmin-login/',   superadmin_login,         name='superadmin-login'),
    path('create-super-admin/', create_super_admin,       name='create-super-admin'),
    path('check-super-admin/',  check_super_admin_exists, name='check-super-admin'),

    # ── User management ───────────────────────────────────────────────────────
    path('users/',                      get_users,   name='get-users'),
    path('users/create/',               create_user, name='create-user'),
    path('users/<int:user_id>/',        delete_user, name='delete-user'),
    path('users/<int:user_id>/update/', update_user, name='update-user'),

    # ── User statistics ───────────────────────────────────────────────────────
    path('user-stats/', get_user_stats, name='user-stats'),

    # ── Waiters list (dropdown for waiter panel) ──────────────────────────────
    path('waiters/', get_waiter_list, name='get-waiter-list'),

    # ── Company information ───────────────────────────────────────────────────
    path('company-info/',      get_company_info,         name='get-company-info'),
    path('company-info/save/', create_or_update_company, name='save-company-info'),

    # ── Customization ─────────────────────────────────────────────────────────
    path('customization/',             get_customization,         name='get-customization'),
    path('customization/save/',        save_customization,        name='save-customization'),
    path('customization/delete-file/', delete_customization_file, name='delete-customization-file'),

    # ── Banner management ─────────────────────────────────────────────────────
    path('banners/',                 get_banners,    name='get-banners'),
    path('banners/upload/',          upload_banners, name='upload-banners'),
    path('banners/reorder/',         reorder_banners, name='reorder-banners'),
    path('banners/<int:banner_id>/', delete_banner,  name='delete-banner'),

    # ── Table Master  (NEW) ───────────────────────────────────────────────────
    path('tables/',                        get_tables,    name='get-tables'),
    path('tables/create/',                 create_table,  name='create-table'),
    path('tables/<int:table_id>/',         delete_table,  name='delete-table'),
    path('tables/<int:table_id>/update/',  update_table,  name='update-table'),

    # ── TV Banner management  (NEW) ───────────────────────────────────────────
    path('tv-banners/',                        get_tv_banners,     name='get-tv-banners'),
    path('tv-banners/upload/',                 upload_tv_banners,  name='upload-tv-banners'),
    path('tv-banners/reorder/',                reorder_tv_banners, name='reorder-tv-banners'),
    path('tv-banners/<int:banner_id>/',        delete_tv_banner,   name='delete-tv-banner'),

    # ── Order management ──────────────────────────────────────────────────────
    path('orders/',                         create_order,        name='create-order'),
    path('orders/list/',                    get_orders,          name='get-orders'),
    path('orders/stats/',                   get_order_stats,     name='get-order-stats'),
    path('orders/<int:order_id>/',          get_order_detail,    name='get-order-detail'),
    path('orders/<int:order_id>/status/',   update_order_status, name='update-order-status'),
    path('orders/<int:order_id>/cancel/',   cancel_order,        name='cancel-order'),
    path('orders/<int:order_id>/accept/',   accept_order,        name='accept-order'),
]
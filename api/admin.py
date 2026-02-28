# api/admin.py
# UPDATED: Added Banner admin
# UPDATED: Added Table admin
# UPDATED: Added TVBanner admin

from django.contrib import admin
from .models import Category, MenuItem, Tax, AppUser, CompanyInfo, Customization, Order, OrderItem, Banner, TVBanner, Table


@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'firm_name', 'place', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['client_id', 'firm_name', 'place', 'gst_number', 'pan_number']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'username', 'created_at', 'updated_at']
    search_fields = ['name', 'username']
    ordering = ['name']


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ['name', 'percentage', 'status', 'username', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'username', 'description']
    list_editable = ['status']
    ordering = ['-created_at']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['session_code', 'name', 'category', 'price1', 'status', 'username', 'created_at']
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['session_code', 'name', 'username']
    list_editable = ['status']
    ordering = ['category', 'name']


@admin.register(AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = ['get_client_id', 'username', 'full_name', 'user_type', 'is_active', 'created_at']
    list_filter = ['user_type', 'is_active', 'created_at']
    search_fields = ['username', 'full_name', 'company__client_id', 'company__firm_name']
    list_editable = ['is_active']
    ordering = ['-created_at']

    # Don't show password in admin
    exclude = ['password']
    readonly_fields = ['created_at', 'updated_at']

    def get_client_id(self, obj):
        """Display client_id from the related company"""
        return obj.company.client_id
    get_client_id.short_description = 'Client ID'
    get_client_id.admin_order_field = 'company__client_id'


@admin.register(Customization)
class CustomizationAdmin(admin.ModelAdmin):
    list_display = ['username', 'logo', 'banner', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']
    search_fields = ['username']


# ============================================
# BANNER ADMIN
# ============================================

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'client_id', 'order', 'is_active', 'image', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['username', 'client_id']
    list_editable = ['order', 'is_active']
    ordering = ['username', 'order', '-created_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Information', {
            'fields': ('client_id', 'username')
        }),
        ('Banner Details', {
            'fields': ('image', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )




# ============================================
# TV BANNER ADMIN  (NEW)
# ============================================

@admin.register(TVBanner)
class TVBannerAdmin(admin.ModelAdmin):
    list_display    = ['id', 'username', 'client_id', 'order', 'is_active', 'image', 'created_at']
    list_filter     = ['is_active', 'created_at']
    search_fields   = ['username', 'client_id']
    list_editable   = ['order', 'is_active']
    ordering        = ['username', 'order', '-created_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Restaurant', {
            'fields': ('client_id', 'username')
        }),
        ('Banner Details', {
            'fields': ('image', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# ============================================
# TABLE ADMIN  (NEW)
# ============================================

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display  = ['id', 'username', 'client_id', 'table_number', 'table_name', 'capacity', 'status', 'created_at']
    list_filter   = ['status', 'created_at']
    search_fields = ['username', 'client_id', 'table_number', 'table_name']
    list_editable = ['status']
    ordering      = ['username', 'table_number']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Restaurant', {
            'fields': ('client_id', 'username')
        }),
        ('Table Details', {
            'fields': ('table_number', 'table_name', 'capacity', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ============================================
# ORDER ADMIN
# ============================================

class OrderItemInline(admin.TabularInline):
    """Inline admin for order items"""
    model = OrderItem
    extra = 0
    readonly_fields = ['item_total', 'tax_amount', 'item_total_with_tax']
    fields = ['menu_item_id', 'name', 'portion', 'quantity', 'price', 'tax', 'item_total', 'tax_amount', 'item_total_with_tax']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'customer_name',
        'customer_phone',
        'table_number',
        'member_count',
        'get_item_count',
        'total_amount',
        'status',
        'username',
        'order_time',
        'created_at'
    ]
    list_filter = ['status', 'created_at', 'order_time']
    search_fields = [
        'id',
        'session_id',
        'customer_name',
        'customer_phone',
        'table_number',
        'client_id',
        'username'
    ]
    list_editable = ['status']
    readonly_fields = [
        'session_id',
        'client_id',
        'username',
        'customer_name',
        'customer_phone',
        'member_count',
        'table_number',
        'subtotal',
        'tax_amount',
        'total_amount',
        'order_time',
        'item_count',
        'created_at',
        'updated_at'
    ]
    ordering = ['-created_at']
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Information', {
            'fields': ('id', 'session_id', 'status', 'order_time')
        }),
        ('Customer Details', {
            'fields': ('customer_name', 'customer_phone', 'member_count', 'table_number')
        }),
        ('Restaurant Info', {
            'fields': ('client_id', 'username')
        }),
        ('Order Summary', {
            'fields': ('item_count', 'subtotal', 'tax_amount', 'total_amount')
        }),
        ('Additional Info', {
            'fields': ('special_instructions',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_item_count(self, obj):
        """Display total item count"""
        return obj.item_count
    get_item_count.short_description = 'Items'

    def has_add_permission(self, request):
        """Orders should only be created from the mobile app"""
        return False


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'order',
        'name',
        'portion',
        'quantity',
        'price',
        'item_total',
        'tax_amount',
        'item_total_with_tax'
    ]
    list_filter = ['portion', 'created_at']
    search_fields = ['name', 'order__customer_name', 'order__id']
    readonly_fields = ['item_total', 'tax_amount', 'item_total_with_tax', 'created_at']
    ordering = ['-created_at']

    def has_add_permission(self, request):
        """Order items should only be created with orders"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Don't allow deleting order items independently"""
        return False
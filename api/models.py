# api/models.py
# Complete Models with Client ID Integration
# Restaurant Menu Management System
# UPDATED: Added waiter_name field to Order model
# UPDATED: Added role field to AppUser for waiter/kitchen staff
# UPDATED: Added Table model for Table Master / QR Code generation
# UPDATED: Added TVBanner model for TV Menu Display banners
# FIXED:   Added tv_text_color, tv_accent_color, tv_card_bg_color to Customization model

from django.db import models
from django.db.models import Sum


class CompanyInfo(models.Model):
    """Company/Firm Information Model - Primary Key is client_id"""
    client_id = models.CharField(max_length=100, unique=True, primary_key=True)
    firm_name = models.CharField(max_length=300)
    place = models.CharField(max_length=200)
    
    address    = models.TextField(blank=True, null=True)
    district   = models.CharField(max_length=100, blank=True, null=True)
    pin_code   = models.CharField(max_length=10,  blank=True, null=True)
    phone      = models.CharField(max_length=50,  blank=True, null=True)
    phone2     = models.CharField(max_length=50,  blank=True, null=True)
    email      = models.EmailField(blank=True, null=True)
    gst_number = models.CharField(max_length=50,  blank=True, null=True)
    pan_number = models.CharField(max_length=50,  blank=True, null=True)
    
    leasing_key        = models.CharField(max_length=500, unique=True)
    leasing_start_date = models.DateField(blank=True, null=True)
    leasing_end_date   = models.DateField(blank=True, null=True)
    is_active          = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'company_info'
        verbose_name_plural = 'Company Information'
    
    def __str__(self):
        return f"{self.client_id} - {self.firm_name} ({self.place})"


class Category(models.Model):
    """Category Master Model"""
    name     = models.CharField(max_length=200)
    username = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'
        unique_together = ['username', 'name']

    def __str__(self):
        return self.name


class Tax(models.Model):
    """Tax Master Model"""
    STATUS_CHOICES = [
        ('active',   'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name        = models.CharField(max_length=100)
    percentage  = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    username    = models.CharField(max_length=100)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'taxes'
        ordering = ['-created_at']
        verbose_name_plural = 'Taxes'
        unique_together = ['username', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.percentage}%"


class MenuItem(models.Model):
    """Menu Item Master Model with Client ID"""
    STATUS_CHOICES = [
        ('active',   'Active'),
        ('inactive', 'Inactive'),
    ]
    
    PRICE_TYPE_CHOICES = [
        ('portion', 'Portion Prices (Full/Half/Quarter)'),
        ('combo',   'Combo Price'),
        ('single',  'Single Price'),
    ]

    session_code = models.CharField(max_length=50)
    name         = models.CharField(max_length=200)
    category     = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    price_type = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES, default='single')
    
    price1 = models.DecimalField(max_digits=10, decimal_places=2)
    price2 = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price3 = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    tax      = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    hsn_code = models.CharField(max_length=50, blank=True, null=True)
    
    remark = models.TextField(blank=True, null=True)
    image  = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    
    username  = models.CharField(max_length=100)
    client_id = models.CharField(max_length=100, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']
        unique_together = ['username', 'session_code']

    def __str__(self):
        return f"{self.session_code} - {self.name}"


class AppUser(models.Model):
    """
    User Model - Linked to Company via Client ID.

    user_type:
      'admin' — restaurant owner/manager, created via createsuperadmin command
      'user'  — waiter/staff created from WaiterManagement page

    role (only meaningful when user_type='user'):
      'waiter'  — can access Waiter Panel only
      'kitchen' — can access Kitchen Panel only
      'both'    — can access both panels (default for new staff)
      None/''   — no panel restriction (legacy records)
    """
    USER_TYPE_CHOICES = [
        ('user',  'User'),
        ('admin', 'Admin'),
    ]

    ROLE_CHOICES = [
        ('waiter',  'Waiter'),
        ('kitchen', 'Kitchen'),
        ('both',    'Both'),
    ]
    
    company = models.ForeignKey(
        CompanyInfo,
        on_delete=models.CASCADE,
        related_name='users',
        to_field='client_id',
        db_column='client_id'
    )
    
    username  = models.CharField(max_length=100, unique=True)
    password  = models.CharField(max_length=255)
    full_name = models.CharField(max_length=200, blank=True, null=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='user')
    role      = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        blank=True,
        null=True,
        default=None,
        help_text="Panel access role — only used for staff (user_type='user')"
    )
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'app_users'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.company.client_id} - {self.username}"


class Customization(models.Model):
    """Stores per-user customization options and uploaded assets"""
    username = models.CharField(max_length=100, unique=True)
    
    background_color = models.CharField(max_length=20, default='#f9fafb')
    font_color       = models.CharField(max_length=20, default='#000000')
    header_color     = models.CharField(max_length=20, default='#7c3aed')
    accent_color     = models.CharField(max_length=20, default='#10b981')
    
    header_bg_color   = models.CharField(max_length=20, default='#6366f1', blank=True, null=True)
    header_text_color = models.CharField(max_length=20, default='#ffffff', blank=True, null=True)
    primary_color     = models.CharField(max_length=20, default='#7c3aed', blank=True, null=True)
    
    qr_foreground_color = models.CharField(max_length=20, default='#000000', blank=True, null=True)
    qr_background_color = models.CharField(max_length=20, default='#ffffff', blank=True, null=True)
    qr_size             = models.IntegerField(default=512, blank=True, null=True)
    qr_margin           = models.IntegerField(default=2,   blank=True, null=True)

    # ── TV Menu Display theme colors ─────────────────────────────────────────
    # FIXED: tv_text_color, tv_accent_color, tv_card_bg_color were missing —
    #        they are now added so the TV theme saved in TVBannerManager
    #        is correctly persisted and returned to MenuDisplay.
    tv_bg_color = models.CharField(
        max_length=20, default='#000000', blank=True, null=True,
        help_text="Background color of the TV Menu Display screen"
    )
    tv_text_color = models.CharField(
        max_length=20, default='#ffffff', blank=True, null=True,
        help_text="Text color for the TV Menu Display screen"
    )
    tv_accent_color = models.CharField(
        max_length=20, default='#9333ea', blank=True, null=True,
        help_text="Accent/highlight color for the TV Menu Display screen"
    )
    tv_card_bg_color = models.CharField(
        max_length=20, default='#1f2937', blank=True, null=True,
        help_text="Card background color for the TV Menu Display screen"
    )

    logo_shape = models.CharField(max_length=20, default='round', blank=True, null=True)
    
    logo    = models.ImageField(upload_to='logos/',    blank=True, null=True)
    tv_logo = models.ImageField(upload_to='tv_logos/', blank=True, null=True,
                                help_text="Logo shown in the TV Menu Display header")
    banner  = models.ImageField(upload_to='banners/',  blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customizations'

    def __str__(self):
        return f"Customization for {self.username}"


class Banner(models.Model):
    """Model to store multiple banner images per user with Client ID"""
    client_id = models.CharField(max_length=100, db_index=True)
    username  = models.CharField(max_length=100, db_index=True)
    image     = models.ImageField(upload_to='banners/')
    order     = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'banners'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['client_id', 'username', 'is_active']),
        ]
    
    def __str__(self):
        return f"Banner {self.order} - {self.username}"


# ============================================
# TV BANNER
# ============================================

class TVBanner(models.Model):
    """
    Banner images displayed on the TV Menu Display screen (MenuDisplay.jsx).
    Shown in the left panel alongside the menu grid on the TV/monitor.
    Separate from the mobile Banner model — recommended portrait aspect ratio.
    """
    client_id  = models.CharField(max_length=100, db_index=True)
    username   = models.CharField(max_length=100, db_index=True)
    image      = models.ImageField(upload_to='tv_banners/')
    order      = models.PositiveIntegerField(default=0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'tv_banners'
        ordering            = ['order', '-created_at']
        verbose_name        = 'TV Banner'
        verbose_name_plural = 'TV Banners'
        indexes = [
            models.Index(fields=['client_id', 'username', 'is_active']),
        ]

    def __str__(self):
        return f"TVBanner [{self.username}] order={self.order}"


# ============================================
# TABLE MASTER
# ============================================

class Table(models.Model):
    """
    Restaurant Table Master.
    Each table gets its own unique QR code that encodes:
      /menu?client_id=<client_id>&username=<username>&table=<table_number>

    When a customer scans the QR code the mobile menu pre-fills the table
    number so they never have to enter it manually.
    """
    STATUS_CHOICES = [
        ('active',   'Active'),
        ('inactive', 'Inactive'),
    ]

    client_id    = models.CharField(max_length=100, db_index=True)
    username     = models.CharField(max_length=100, db_index=True)
    table_number = models.CharField(max_length=50)
    table_name   = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Optional descriptive label, e.g. 'Window Seat' or 'VIP Room'"
    )
    capacity     = models.PositiveIntegerField(default=4,
                                               help_text="Maximum number of guests")
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tables'
        ordering = ['table_number']
        # A table number must be unique per restaurant user
        unique_together = ['username', 'table_number']
        indexes = [
            models.Index(fields=['client_id', 'username', 'status']),
        ]

    def __str__(self):
        label = f" — {self.table_name}" if self.table_name else ""
        return f"Table {self.table_number}{label} ({self.username})"


# ============================================
# ORDER
# ============================================

class Order(models.Model):
    """Customer Order Model with Client ID"""
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('preparing',  'Preparing'),
        ('ready',      'Ready'),
        ('completed',  'Completed'),
        ('cancelled',  'Cancelled'),
    ]
    
    session_id = models.CharField(max_length=100, db_index=True)
    client_id  = models.CharField(max_length=100, db_index=True)
    username   = models.CharField(max_length=100, db_index=True)
    
    customer_name  = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    table_number   = models.CharField(max_length=20)
    waiter_name    = models.CharField(max_length=200, blank=True, null=True)
    member_count   = models.PositiveIntegerField(default=1,
                                                  help_text="Number of guests at the table")
    
    subtotal     = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount   = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order_time = models.DateTimeField()
    
    special_instructions = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client_id', 'username', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Order #{self.id} - {self.customer_name} (Table {self.table_number})"
    
    @property
    def item_count(self):
        return sum(item.quantity for item in self.order_items.all())


class OrderItem(models.Model):
    """Individual items in an order"""
    order = models.ForeignKey(Order, related_name='order_items', on_delete=models.CASCADE)
    
    menu_item_id = models.IntegerField()
    name         = models.CharField(max_length=200)
    
    portion  = models.CharField(max_length=20)
    quantity = models.IntegerField(default=1)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    tax      = models.DecimalField(max_digits=5,  decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_items'
    
    def __str__(self):
        return f"{self.name} ({self.portion}) x {self.quantity}"
    
    @property
    def item_total(self):
        return self.price * self.quantity
    
    @property
    def tax_amount(self):
        return (self.item_total * self.tax) / 100
    
    @property
    def item_total_with_tax(self):
        return self.item_total + self.tax_amount
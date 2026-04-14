# api/models.py
# UPDATED: user_type = 'superadmin' | 'admin' | 'user'
# Super Admin  → company FK is NULL (not tied to one company)
# Company Admin → company FK = their company
# Staff         → company FK = their company
# UPDATED: Added meal_type field to MenuItem (breakfast / lunch / dinner / all)
# UPDATED: Added MealType model for dynamic meal type management
# UPDATED: Added Kitchen model for Kitchen Master
# UPDATED: Added tv_theme field to Customization for TV layout selection
# UPDATED: Added price_category field to MenuItem (regular / sessional)
# UPDATED: Added SessionalPrice model for sessional price rows per MenuItem
# UPDATED: Added table_type ('sharing' | 'sitting') and occupied_seats to Table model
#          occupied_seats is auto-managed by create_order / update_order_status / cancel_order

from django.db import models
from django.db.models import Sum


class CompanyInfo(models.Model):
    """Company created by Super Admin from dashboard"""
    client_id = models.CharField(max_length=100, unique=True, primary_key=True)
    firm_name = models.CharField(max_length=300)
    place     = models.CharField(max_length=200)

    address    = models.TextField(blank=True, null=True)
    district   = models.CharField(max_length=100, blank=True, null=True)
    pin_code   = models.CharField(max_length=10,  blank=True, null=True)
    phone      = models.CharField(max_length=50,  blank=True, null=True)
    phone2     = models.CharField(max_length=50,  blank=True, null=True)
    email      = models.EmailField(blank=True, null=True)
    gst_number = models.CharField(max_length=50,  blank=True, null=True)
    pan_number = models.CharField(max_length=50,  blank=True, null=True)

    # Social media / contact links
    instagram_url = models.URLField(max_length=500, blank=True, null=True)
    google_url    = models.URLField(max_length=500, blank=True, null=True)
    whatsapp      = models.CharField(max_length=20,  blank=True, null=True)

    leasing_key        = models.CharField(max_length=500, unique=True, blank=True, null=True)
    leasing_start_date = models.DateField(blank=True, null=True)
    leasing_end_date   = models.DateField(blank=True, null=True)
    is_active          = models.BooleanField(default=True)

    # Pages Super Admin allows for this company — NULL = unrestricted
    allowed_pages = models.JSONField(
        blank=True, null=True, default=None,
        help_text='Page IDs this company can access. NULL = unrestricted.'
    )

    # Package / plan chosen by Super Admin
    PACKAGE_CHOICES = [
        ('premium', 'Premium'),
        ('pro',     'Pro'),
        ('basic',   'Basic'),
    ]
    package = models.CharField(
        max_length=20, choices=PACKAGE_CHOICES, default='premium',
        help_text="Subscription plan: premium=all pages, pro=core only, basic=core+staff+waiter"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_info'
        verbose_name_plural = 'Company Information'

    def __str__(self):
        return f"{self.client_id} - {self.firm_name} ({self.place})"


class Category(models.Model):
    name      = models.CharField(max_length=200)
    username  = models.CharField(max_length=100)
    client_id = models.CharField(max_length=100, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['name']
        verbose_name_plural = 'Categories'
        unique_together = ['client_id', 'name']

    def __str__(self):
        return self.name


class Tax(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]

    name        = models.CharField(max_length=100)
    percentage  = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    username    = models.CharField(max_length=100)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'taxes'
        ordering        = ['-created_at']
        verbose_name_plural = 'Taxes'
        unique_together = ['username', 'name']

    def __str__(self):
        return f"{self.name} - {self.percentage}%"


# ─────────────────────────────────────────────────────────────
# MEAL TYPE MODEL
# ─────────────────────────────────────────────────────────────
class MealType(models.Model):
    name       = models.CharField(max_length=100)
    start_time = models.TimeField(help_text='Meal period start time, e.g. 07:00')
    end_time   = models.TimeField(help_text='Meal period end time, e.g. 11:00')
    client_id  = models.CharField(max_length=100, db_index=True)
    username   = models.CharField(max_length=100, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'meal_types'
        ordering        = ['start_time', 'name']
        unique_together = ['client_id', 'name']
        indexes         = [models.Index(fields=['client_id', 'username'])]
        verbose_name        = 'Meal Type'
        verbose_name_plural = 'Meal Types'

    def __str__(self):
        return f"{self.name} ({self.start_time}–{self.end_time}) [{self.client_id}]"


# ─────────────────────────────────────────────────────────────
# KITCHEN MODEL
# ─────────────────────────────────────────────────────────────
class Kitchen(models.Model):
    kitchen_number = models.CharField(max_length=50)
    kitchen_name   = models.CharField(max_length=200, blank=True, null=True)
    client_id      = models.CharField(max_length=100, db_index=True)
    username       = models.CharField(max_length=100, db_index=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'kitchens'
        ordering        = ['kitchen_number']
        unique_together = ['username', 'kitchen_number']
        indexes         = [models.Index(fields=['client_id', 'username'])]
        verbose_name        = 'Kitchen'
        verbose_name_plural = 'Kitchens'

    def __str__(self):
        name = self.kitchen_name or ''
        return f"Kitchen {self.kitchen_number} — {name} ({self.username})"


class MenuItem(models.Model):
    STATUS_CHOICES     = [('active', 'Active'), ('inactive', 'Inactive')]
    PRICE_TYPE_CHOICES = [
        ('portion', 'Portion Prices'),
        ('combo',   'Combo Price'),
        ('single',  'Single Price'),
    ]
    FOOD_TYPE_CHOICES = [
        ('veg',     'Vegetarian'),
        ('non_veg', 'Non-Vegetarian'),
    ]
    PRICE_CATEGORY_CHOICES = [
        ('regular',   'Regular Price'),
        ('sessional', 'Sessional Price'),
    ]

    session_code = models.CharField(max_length=50)
    name         = models.CharField(max_length=200)
    category     = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    food_type    = models.CharField(
        max_length=10, choices=FOOD_TYPE_CHOICES, default='non_veg',
        help_text='Veg / Non-Veg indicator for the menu item.'
    )
    price_type     = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES, default='single')
    price_category = models.CharField(
        max_length=10, choices=PRICE_CATEGORY_CHOICES, default='regular',
        help_text='Regular price or Sessional (time-based) price.'
    )
    meal_type = models.JSONField(
        blank=True, null=True, default=list,
        help_text='List of MealType IDs (strings) this item belongs to.'
    )
    remark   = models.TextField(blank=True, null=True)
    price1   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price2   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price3   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax      = models.ForeignKey(Tax, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    image    = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    kitchen  = models.ForeignKey(
        Kitchen, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='menu_items',
        help_text='Which kitchen prepares this item.'
    )
    username   = models.CharField(max_length=100)
    client_id  = models.CharField(max_length=100, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menu_items'
        ordering = ['category', 'name']
        indexes  = [models.Index(fields=['client_id', 'username', 'status'])]

    def __str__(self):
        return f"{self.name} ({self.username})"


# ─────────────────────────────────────────────────────────────
# SESSIONAL PRICE MODEL
# ─────────────────────────────────────────────────────────────
class SessionalPrice(models.Model):
    menu_item    = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='sessional_prices')
    session_name = models.CharField(max_length=100, help_text='e.g. Breakfast, Lunch, Dinner')
    price1       = models.DecimalField(max_digits=10, decimal_places=2)
    price2       = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price3       = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sessional_prices'
        ordering = ['session_name']

    def __str__(self):
        return f"{self.menu_item.name} — {self.session_name}"


# ─────────────────────────────────────────────────────────────
# APP USER MODEL
# ─────────────────────────────────────────────────────────────
class AppUser(models.Model):
    USER_TYPE_CHOICES = [
        ('superadmin', 'Super Admin'),
        ('admin',      'Company Admin'),
        ('user',       'Staff'),
    ]

    username      = models.CharField(max_length=100, unique=True)
    password      = models.CharField(max_length=255)
    full_name     = models.CharField(max_length=200, blank=True, null=True)
    user_type     = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='user')
    role          = models.CharField(max_length=50, blank=True, null=True,
                        help_text='Staff role: waiter | cashier | both')
    is_active     = models.BooleanField(default=True)
    company       = models.ForeignKey(
        CompanyInfo, on_delete=models.CASCADE,
        related_name='users', null=True, blank=True
    )
    allowed_pages = models.JSONField(blank=True, null=True, default=None)
    plain_password = models.CharField(max_length=255, blank=True, null=True,
                        help_text='Stored in plain text for Super Admin visibility only.')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'app_users'
        indexes  = [
            models.Index(fields=['username']),
            models.Index(fields=['user_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.username} ({self.user_type})"


# ─────────────────────────────────────────────────────────────
# CUSTOMIZATION MODEL
# ─────────────────────────────────────────────────────────────
class Customization(models.Model):
    TV_THEME_CHOICES = [
        ('theme1', 'Theme 1 — Classic'),
        ('theme2', 'Theme 2 — Split Panel'),
        ('theme3', 'Theme 3 — Media Banner'),
    ]

    username          = models.CharField(max_length=100, unique=True)
    background_color  = models.CharField(max_length=20, default='#ffffff')
    font_color        = models.CharField(max_length=20, default='#1f2937')
    header_color      = models.CharField(max_length=20, default='#7c3aed')
    accent_color      = models.CharField(max_length=20, default='#10b981')
    header_bg_color   = models.CharField(max_length=20, default='#6366f1', blank=True, null=True)
    header_text_color = models.CharField(max_length=20, default='#ffffff', blank=True, null=True)
    primary_color     = models.CharField(max_length=20, default='#7c3aed', blank=True, null=True)
    qr_foreground_color = models.CharField(max_length=20, default='#000000', blank=True, null=True)
    qr_background_color = models.CharField(max_length=20, default='#ffffff', blank=True, null=True)
    qr_size             = models.IntegerField(default=512, blank=True, null=True)
    qr_margin           = models.IntegerField(default=2,   blank=True, null=True)
    tv_bg_color         = models.CharField(max_length=20, default='#000000', blank=True, null=True)
    tv_text_color       = models.CharField(max_length=20, default='#ffffff', blank=True, null=True)
    tv_accent_color     = models.CharField(max_length=20, default='#9333ea', blank=True, null=True)
    tv_card_bg_color    = models.CharField(max_length=20, default='#1f2937', blank=True, null=True)

    # ── TV layout theme selector ──────────────────────────────────────────
    tv_theme            = models.CharField(
        max_length=20, choices=TV_THEME_CHOICES, default='theme1',
        blank=True, null=True,
        help_text='Which TV display layout/theme to use on the MenuDisplay screen.'
    )

    logo_shape = models.CharField(max_length=20, default='round', blank=True, null=True)
    logo    = models.ImageField(upload_to='logos/',    blank=True, null=True)
    tv_logo = models.ImageField(upload_to='tv_logos/', blank=True, null=True)
    banner  = models.ImageField(upload_to='banners/',  blank=True, null=True)

    # ── Theme 2 background images (left + right panel) ────────────────────────
    tv_theme2_left  = models.FileField(upload_to='tv_theme2/', blank=True, null=True)
    tv_theme2_right = models.FileField(upload_to='tv_theme2/', blank=True, null=True)

    # ── Theme 3 media (banner image + video) ──────────────────────────────────
    tv_theme3_image = models.ImageField(upload_to='tv_theme3/', blank=True, null=True)
    tv_theme3_video = models.FileField(upload_to='tv_theme3/',  blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customizations'

    def __str__(self):
        return f"Customization for {self.username}"


class Banner(models.Model):
    client_id  = models.CharField(max_length=100, db_index=True)
    username   = models.CharField(max_length=100, db_index=True)
    image      = models.ImageField(upload_to='banners/')
    order      = models.IntegerField(default=0)
    plain_password = models.CharField(max_length=255, blank=True, null=True,
                        help_text='Stored in plain text for Super Admin visibility only.')
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'banners'
        ordering = ['order', 'created_at']
        indexes  = [models.Index(fields=['client_id', 'username', 'is_active'])]

    def __str__(self):
        return f"Banner {self.order} - {self.username}"


class TVBanner(models.Model):
    client_id  = models.CharField(max_length=100, db_index=True)
    username   = models.CharField(max_length=100, db_index=True)
    # FileField instead of ImageField so videos (mp4/webm) are accepted alongside images
    image      = models.FileField(upload_to='tv_banners/')
    order      = models.PositiveIntegerField(default=0)
    plain_password = models.CharField(max_length=255, blank=True, null=True,
                        help_text='Stored in plain text for Super Admin visibility only.')
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'tv_banners'
        ordering            = ['order', '-created_at']
        verbose_name        = 'TV Banner'
        verbose_name_plural = 'TV Banners'
        indexes             = [models.Index(fields=['client_id', 'username', 'is_active'])]

    def __str__(self):
        return f"TVBanner [{self.username}] order={self.order}"


# ─────────────────────────────────────────────────────────────
# TABLE MODEL  ← UPDATED: added table_type and occupied_seats
# ─────────────────────────────────────────────────────────────
class Table(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]

    # ── NEW: sharing = multiple groups can share seats
    #        sitting = whole table is reserved as one unit
    TABLE_TYPE_CHOICES = [
        ('sharing', 'Sharing'),
        ('sitting', 'Sitting / Fixed'),
    ]

    client_id    = models.CharField(max_length=100, db_index=True)
    username     = models.CharField(max_length=100, db_index=True)
    table_number = models.CharField(max_length=50)
    table_name   = models.CharField(max_length=100, blank=True, null=True)
    capacity     = models.PositiveIntegerField(default=4)

    # ── NEW FIELD: sharing | sitting ──────────────────────────────────────────
    table_type   = models.CharField(
        max_length=10, choices=TABLE_TYPE_CHOICES, default='sitting',
        help_text=(
            'sitting = the whole table is booked as one unit; '
            'sharing = multiple independent groups can occupy spare seats.'
        )
    )

    # ── NEW FIELD: live seat count — managed by order create/complete/cancel ──
    occupied_seats = models.PositiveIntegerField(
        default=0,
        help_text='Current number of occupied seats. Auto-managed by order lifecycle.'
    )

    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'tables'
        ordering        = ['table_number']
        unique_together = ['username', 'table_number']
        indexes         = [models.Index(fields=['client_id', 'username', 'status'])]

    def __str__(self):
        label = f" — {self.table_name}" if self.table_name else ""
        return f"Table {self.table_number}{label} ({self.username})"

    # ── Computed availability status (no extra DB column needed) ──────────────
    @property
    def availability_status(self):
        """
        Returns:
          'free'    — no seats occupied
          'partial' — some seats occupied (sharing tables only)
          'full'    — all seats occupied (or sitting table with any occupant)
        """
        if self.occupied_seats == 0:
            return 'free'
        if self.table_type == 'sitting' or self.occupied_seats >= self.capacity:
            return 'full'
        return 'partial'

    def release_seats(self, count):
        """Safely decrement occupied_seats, never below 0."""
        self.occupied_seats = max(0, self.occupied_seats - count)
        self.save(update_fields=['occupied_seats', 'updated_at'])

    def occupy_seats(self, count):
        """Increment occupied_seats, capped at capacity."""
        self.occupied_seats = min(self.capacity, self.occupied_seats + count)
        self.save(update_fields=['occupied_seats', 'updated_at'])


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('preparing', 'Preparing'),
        ('ready',     'Ready'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    session_id     = models.CharField(max_length=100, db_index=True)
    client_id      = models.CharField(max_length=100, db_index=True)
    username       = models.CharField(max_length=100, db_index=True)
    customer_name  = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    table_number   = models.CharField(max_length=20)
    waiter_name    = models.CharField(max_length=200, blank=True, null=True)
    member_count   = models.PositiveIntegerField(default=1)
    subtotal       = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount     = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount   = models.DecimalField(max_digits=10, decimal_places=2)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order_time     = models.DateTimeField()
    special_instructions = models.TextField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['client_id', 'username', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name} (Table {self.table_number})"

    @property
    def item_count(self):
        return sum(item.quantity for item in self.order_items.all())


class OrderItem(models.Model):
    order        = models.ForeignKey(Order, related_name='order_items', on_delete=models.CASCADE)
    menu_item_id = models.IntegerField()
    name         = models.CharField(max_length=200)
    portion      = models.CharField(max_length=20)
    quantity     = models.IntegerField(default=1)
    price        = models.DecimalField(max_digits=10, decimal_places=2)
    tax          = models.DecimalField(max_digits=5,  decimal_places=2, default=0.00)
    created_at   = models.DateTimeField(auto_now_add=True)

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


# ─────────────────────────────────────────────────────────────
# BillingRecord model — stores printed/saved bills for reporting
# ─────────────────────────────────────────────────────────────
class BillingRecord(models.Model):
    billing_id   = models.CharField(max_length=100, unique=True, primary_key=True)
    client_id    = models.CharField(max_length=100, db_index=True, blank=True, null=True)
    username     = models.CharField(max_length=100, db_index=True, blank=True, null=True)
    order_id     = models.IntegerField(blank=True, null=True)
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    table_number = models.CharField(max_length=50, blank=True, null=True)
    table_name   = models.CharField(max_length=200, blank=True, null=True)
    items        = models.JSONField(blank=True, null=True, default=list)
    subtotal     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_records'
        ordering = ['-created_at']

    def __str__(self):
        return f"Billing {self.billing_id} — Order {self.order_id} ({self.total_amount})"
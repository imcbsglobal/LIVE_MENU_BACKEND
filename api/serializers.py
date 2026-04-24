# api/serializers.py
# Enhanced serializers with Company Information, Banner, Table, and Order Management
# UPDATED: Added TableSerializer
# UPDATED: Added customer_phone and member_count to OrderCreateSerializer
# UPDATED: Added TVBannerSerializer for TV Menu Display banners
# UPDATED: Added meal_type to MenuItemSerializer
# UPDATED: Added MealTypeSerializer
# UPDATED: Added tv_theme to CustomizationSerializer
# UPDATED: TableSerializer now includes table_type, occupied_seats, availability_status,
#          free_seats, and color_code for Petpooja-style table management UI

from rest_framework import serializers
from .models import MenuItem, Category, Tax, AppUser, CompanyInfo
from .models import Customization, Banner, TVBanner, Table, Order, OrderItem
from .models import MealType, Kitchen
from .models import BillingRecord


def _build_url(request, url):
    if not url:
        return None
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if request:
        return request.build_absolute_uri(url)
    return url


class CompanyInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyInfo
        fields = [
            'client_id', 'firm_name', 'place',
            'address', 'district', 'pin_code',
            'phone', 'phone2',
            'email', 'gst_number', 'pan_number',
            'allowed_pages', 'package',
            'instagram_url', 'google_url', 'whatsapp',
            'leasing_key', 'leasing_start_date', 'leasing_end_date',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'leasing_key']
        extra_kwargs = {
            'leasing_key': {'required': False, 'allow_null': True, 'allow_blank': True},
        }


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'client_id', 'username', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ['id', 'name', 'percentage', 'description', 'status', 'username', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


# ============================================
# MEAL TYPE SERIALIZER
# ============================================

class MealTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealType
        fields = [
            'id', 'name', 'start_time', 'end_time',
            'client_id', 'username',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        start = data.get('start_time', getattr(self.instance, 'start_time', None))
        end   = data.get('end_time',   getattr(self.instance, 'end_time',   None))
        if start and end and start >= end:
            raise serializers.ValidationError({'end_time': 'End time must be after start time.'})
        return data


class MenuItemSerializer(serializers.ModelSerializer):
    category_name   = serializers.CharField(source='category.name', read_only=True)
    kitchen_name    = serializers.SerializerMethodField()
    image_url       = serializers.SerializerMethodField()
    meal_types      = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'id', 'session_code', 'name', 'category', 'category_name',
            'kitchen', 'kitchen_name',
            'status', 'food_type', 'price_type',
            'meal_type',
            'meal_types',
            'remark', 'price1', 'price2', 'price3',
            'tax', 'hsn_code', 'image', 'image_url',
            'username', 'client_id', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'category_name',
            'image_url', 'meal_types', 'kitchen_name',
        ]

    def get_image_url(self, obj):
        if obj.image:
            return _build_url(self.context.get('request'), obj.image.url)
        return None

    def get_kitchen_name(self, obj):
        if obj.kitchen:
            name = obj.kitchen.kitchen_name or ''
            return f"Kitchen {obj.kitchen.kitchen_number}" + (f" — {name}" if name else '')
        return None

    def get_meal_types(self, obj):
        """Always return meal_type as a clean list of string IDs."""
        raw = obj.meal_type
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
        if isinstance(raw, str):
            try:
                import json
                parsed = json.loads(raw)
                return [str(x) for x in parsed if x]
            except Exception:
                return [raw] if raw else []
        return []

    def validate_meal_type(self, value):
        """Accept list, JSON string, or empty — always store as list."""
        import json
        if not value:
            return []
        if isinstance(value, list):
            return [str(x) for x in value if x]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return [str(x) for x in parsed if x]
            except Exception:
                return [value] if value else []
        return []


class AppUserSerializer(serializers.ModelSerializer):
    password     = serializers.CharField(write_only=True, required=False)
    company_info = CompanyInfoSerializer(source='company', read_only=True)
    client_id    = serializers.CharField(source='company.client_id', read_only=True)
    firm_name    = serializers.CharField(source='company.firm_name', read_only=True)
    place        = serializers.CharField(source='company.place',     read_only=True)

    company_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = AppUser
        fields = [
            'id', 'client_id', 'company_id', 'username', 'password', 'full_name',
            'user_type', 'is_active', 'firm_name', 'place',
            'company_info', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'client_id', 'firm_name', 'place', 'company_info']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        company_id = validated_data.pop('company_id', None)
        if company_id:
            validated_data['company_id'] = company_id
        return super().create(validated_data)


# ============================================
# BANNER SERIALIZER
# ============================================

class BannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ['id', 'client_id', 'username', 'image', 'image_url', 'order', 'is_active', 'created_at']
        read_only_fields = ['id', 'image_url', 'created_at']

    def get_image_url(self, obj):
        if obj.image:
            return _build_url(self.context.get('request'), obj.image.url)
        return None


# ============================================
# TV BANNER SERIALIZER
# ============================================

class TVBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    is_video  = serializers.SerializerMethodField()

    class Meta:
        model  = TVBanner
        fields = ['id', 'client_id', 'username', 'image', 'image_url', 'is_video', 'order', 'is_active', 'created_at']
        read_only_fields = ['id', 'image_url', 'is_video', 'created_at']

    def get_image_url(self, obj):
        if obj.image:
            return _build_url(self.context.get('request'), obj.image.url)
        return None

    def get_is_video(self, obj):
        if obj.image:
            name = obj.image.name.lower()
            return name.endswith(('.mp4', '.webm', '.ogg', '.mov'))
        return False


# ============================================
# TABLE SERIALIZER  ← UPDATED for table management
# ============================================

class TableSerializer(serializers.ModelSerializer):
    # ── Computed / read-only fields for the UI ────────────────────────────────

    availability_status = serializers.SerializerMethodField(
        help_text="'free' | 'partial' | 'full'  — derived from occupied_seats vs capacity"
    )
    free_seats = serializers.SerializerMethodField(
        help_text="capacity minus occupied_seats"
    )
    color_code = serializers.SerializerMethodField(
        help_text=(
            "Hex color for the UI card border/background: "
            "#22c55e (green=free) | #f59e0b (amber=partial) | #ef4444 (red=full)"
        )
    )

    class Meta:
        model  = Table
        fields = [
            'id', 'client_id', 'username',
            'table_number', 'table_name',
            'capacity',
            # ── new fields ──────────────────────────
            'table_type',       # 'sharing' | 'sitting'
            'occupied_seats',   # live count, managed by order lifecycle
            # ── computed ─────────────────────────────
            'availability_status',  # 'free' | 'partial' | 'full'
            'free_seats',           # capacity - occupied_seats
            'color_code',           # hex string for UI
            # ─────────────────────────────────────────
            'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id',
            'availability_status', 'free_seats', 'color_code',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'table_name':     {'required': False, 'allow_null': True, 'allow_blank': True},
            'table_type':     {'required': False},   # defaults to 'sitting' in the model
            'occupied_seats': {'required': False},   # default 0; managed by order views
        }

    # ── computed field implementations ───────────────────────────────────────

    def get_availability_status(self, obj):
        """
        free    → occupied_seats == 0
        partial → sharing table with some but not all seats taken
        full    → sitting table with any occupant, OR sharing table at capacity
        """
        if obj.occupied_seats == 0:
            return 'free'
        if obj.table_type == 'sitting' or obj.occupied_seats >= obj.capacity:
            return 'full'
        return 'partial'

    def get_free_seats(self, obj):
        return max(0, obj.capacity - obj.occupied_seats)

    def get_color_code(self, obj):
        """
        🟢 #22c55e  — free   (Tailwind green-500)
        🟡 #f59e0b  — partial (Tailwind amber-400)
        🔴 #ef4444  — full   (Tailwind red-500)
        """
        status = self.get_availability_status(obj)
        return {
            'free':    '#22c55e',
            'partial': '#f59e0b',
            'full':    '#ef4444',
        }[status]

    # ── validation ────────────────────────────────────────────────────────────

    def validate(self, data):
        username     = data.get('username',     getattr(self.instance, 'username',     None))
        table_number = data.get('table_number', getattr(self.instance, 'table_number', None))
        qs = Table.objects.filter(username=username, table_number=table_number)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'table_number': f"Table '{table_number}' already exists for this restaurant."}
            )

        # occupied_seats must never exceed capacity
        capacity       = data.get('capacity',       getattr(self.instance, 'capacity',       4))
        occupied_seats = data.get('occupied_seats', getattr(self.instance, 'occupied_seats', 0))
        if occupied_seats > capacity:
            raise serializers.ValidationError(
                {'occupied_seats': 'occupied_seats cannot exceed capacity.'}
            )
        return data


# ============================================
# KITCHEN SERIALIZER
# ============================================

class KitchenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Kitchen
        fields = [
            'id', 'client_id', 'username',
            'kitchen_number', 'kitchen_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'kitchen_name': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def validate(self, data):
        username       = data.get('username', getattr(self.instance, 'username', None))
        kitchen_number = data.get('kitchen_number', getattr(self.instance, 'kitchen_number', None))
        qs = Kitchen.objects.filter(username=username, kitchen_number=kitchen_number)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'kitchen_number': f"Kitchen '{kitchen_number}' already exists for this restaurant."}
            )
        return data


# ============================================
# CUSTOMIZATION SERIALIZER
# ============================================

class CustomizationSerializer(serializers.ModelSerializer):
    logo_url         = serializers.SerializerMethodField()
    banner_url       = serializers.SerializerMethodField()
    tv_logo_url      = serializers.SerializerMethodField()
    banners          = serializers.SerializerMethodField()
    # Theme 2 background image URLs
    tv_theme2_left_url  = serializers.SerializerMethodField()
    tv_theme2_right_url = serializers.SerializerMethodField()
    # Theme 3 media URLs
    tv_theme3_image_url = serializers.SerializerMethodField()
    tv_theme3_video_url = serializers.SerializerMethodField()

    class Meta:
        model = Customization
        fields = [
            'username',
            'background_color', 'font_color', 'header_color', 'accent_color',
            'header_bg_color', 'header_text_color', 'primary_color',
            'qr_foreground_color', 'qr_background_color', 'qr_size', 'qr_margin',
            'tv_bg_color', 'tv_text_color', 'tv_accent_color', 'tv_card_bg_color',
            # ── TV layout theme selector ─────────────────────────────────────────
            'tv_theme',
            # ─────────────────────────────────────────────────────────────────────
            'logo_shape',
            'logo', 'banner', 'tv_logo',
            'logo_url', 'banner_url', 'tv_logo_url', 'banners',
            # Theme 2 fields
            'tv_theme2_left', 'tv_theme2_right',
            'tv_theme2_left_url', 'tv_theme2_right_url',
            # Theme 3 fields
            'tv_theme3_image', 'tv_theme3_video',
            'tv_theme3_image_url', 'tv_theme3_video_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'logo_url', 'banner_url', 'tv_logo_url', 'banners',
            'tv_theme2_left_url', 'tv_theme2_right_url',
            'tv_theme3_image_url', 'tv_theme3_video_url',
            'created_at', 'updated_at',
        ]

    def get_logo_url(self, obj):
        if obj.logo:
            return _build_url(self.context.get('request'), obj.logo.url)
        return None
    
    def get_banner_url(self, obj):
        if obj.banner:
            return _build_url(self.context.get('request'), obj.banner.url)
        return None

    def get_tv_logo_url(self, obj):
        if obj.tv_logo:
            return _build_url(self.context.get('request'), obj.tv_logo.url)
        return None

    def get_tv_theme2_left_url(self, obj):
        if obj.tv_theme2_left:
            return _build_url(self.context.get('request'), obj.tv_theme2_left.url)
        return None

    def get_tv_theme2_right_url(self, obj):
        if obj.tv_theme2_right:
            return _build_url(self.context.get('request'), obj.tv_theme2_right.url)
        return None

    def get_tv_theme3_image_url(self, obj):
        if obj.tv_theme3_image:
            return _build_url(self.context.get('request'), obj.tv_theme3_image.url)
        return None

    def get_tv_theme3_video_url(self, obj):
        if obj.tv_theme3_video:
            return _build_url(self.context.get('request'), obj.tv_theme3_video.url)
        return None

    def get_banners(self, obj):
        request   = self.context.get('request')
        client_id = None
        if request:
            client_id = request.query_params.get('client_id')
        if client_id:
            banners = Banner.objects.filter(
                username=obj.username, client_id=client_id, is_active=True
            ).order_by('order')
        else:
            banners = Banner.objects.filter(
                username=obj.username, is_active=True
            ).order_by('order')
        return BannerSerializer(banners, many=True, context={'request': request}).data


# ============================================
# BillingRecord Serializer
# ============================================
class BillingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingRecord
        fields = [
            'billing_id', 'client_id', 'username', 'order_id', 'customer_name',
            'table_number', 'table_name', 'items', 'subtotal', 'tax_amount', 'total_amount', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_banner_url(self, obj):
        if obj.banner:
            return _build_url(self.context.get('request'), obj.banner.url)
        return None

    def get_tv_logo_url(self, obj):
        if obj.tv_logo:
            return _build_url(self.context.get('request'), obj.tv_logo.url)
        return None

    def get_tv_theme2_left_url(self, obj):
        if obj.tv_theme2_left:
            return _build_url(self.context.get('request'), obj.tv_theme2_left.url)
        return None

    def get_tv_theme2_right_url(self, obj):
        if obj.tv_theme2_right:
            return _build_url(self.context.get('request'), obj.tv_theme2_right.url)
        return None

    def get_tv_theme3_image_url(self, obj):
        if obj.tv_theme3_image:
            return _build_url(self.context.get('request'), obj.tv_theme3_image.url)
        return None

    def get_tv_theme3_video_url(self, obj):
        if obj.tv_theme3_video:
            return _build_url(self.context.get('request'), obj.tv_theme3_video.url)
        return None

    def get_banners(self, obj):
        request   = self.context.get('request')
        client_id = None
        if request:
            client_id = request.query_params.get('client_id')
        if client_id:
            banners = Banner.objects.filter(
                username=obj.username, client_id=client_id, is_active=True
            ).order_by('order')
        else:
            banners = Banner.objects.filter(
                username=obj.username, is_active=True
            ).order_by('order')
        return BannerSerializer(banners, many=True, context={'request': request}).data


# ============================================
# ORDER SERIALIZERS
# ============================================

class OrderItemSerializer(serializers.ModelSerializer):
    item_total          = serializers.ReadOnlyField()
    tax_amount          = serializers.ReadOnlyField()
    item_total_with_tax = serializers.ReadOnlyField()
    kitchen_number      = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'menu_item_id', 'name', 'portion', 'quantity',
            'price', 'tax', 'item_total', 'tax_amount', 'item_total_with_tax',
            'kitchen_number',
            'created_at',
        ]
        read_only_fields = ['id', 'item_total', 'tax_amount', 'item_total_with_tax', 'kitchen_number', 'created_at']

    def get_kitchen_number(self, obj):
        try:
            from .models import MenuItem
            mi = MenuItem.objects.select_related('kitchen').get(id=obj.menu_item_id)
            return mi.kitchen.kitchen_number if mi.kitchen else None
        except Exception:
            return None


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, read_only=True)
    item_count  = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = [
            'id', 'session_id', 'client_id', 'username',
            'customer_name', 'customer_phone', 'table_number',
            'waiter_name', 'member_count',
            'subtotal', 'tax_amount', 'total_amount',
            'status', 'order_type', 'order_time', 'special_instructions',
            'order_items', 'item_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'item_count', 'created_at', 'updated_at']


class OrderCreateSerializer(serializers.Serializer):
    session_id     = serializers.CharField(max_length=100)
    client_id      = serializers.CharField(max_length=100)
    username       = serializers.CharField(max_length=100)
    customer_name  = serializers.CharField(max_length=200)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    table_number   = serializers.CharField(max_length=20)
    member_count   = serializers.IntegerField(min_value=1, default=1)
    subtotal       = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_amount     = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_amount   = serializers.DecimalField(max_digits=10, decimal_places=2)
    order_time     = serializers.DateTimeField()
    special_instructions = serializers.CharField(required=False, allow_blank=True)
    order_type = serializers.ChoiceField(
        choices=['self', 'staff'], default='self', required=False,
        help_text='"self" for QR customer orders, "staff" for direct staff orders.'
    )

    items = serializers.ListField(child=serializers.DictField(), write_only=True)

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(
                order        = order,
                menu_item_id = item_data['menu_item_id'],
                name         = item_data['name'],
                portion      = item_data['portion'],
                quantity     = item_data['quantity'],
                price        = item_data['price'],
                tax          = item_data.get('tax', 0),
            )
        return order
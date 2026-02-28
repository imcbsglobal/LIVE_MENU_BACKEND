# api/serializers.py
# Enhanced serializers with Company Information, Banner, Table, and Order Management
# UPDATED: Added TableSerializer
# UPDATED: Added customer_phone and member_count to OrderCreateSerializer
# UPDATED: Added TVBannerSerializer for TV Menu Display banners

from rest_framework import serializers
from .models import MenuItem, Category, Tax, AppUser, CompanyInfo
from .models import Customization, Banner, TVBanner, Table, Order, OrderItem


class CompanyInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyInfo
        fields = [
            'client_id', 'firm_name', 'place',
            'address', 'district', 'pin_code',
            'phone', 'phone2',
            'email', 'gst_number', 'pan_number',
            'leasing_key', 'leasing_start_date', 'leasing_end_date',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'username', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ['id', 'name', 'percentage', 'description', 'status', 'username', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    image_url     = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'session_code', 'name', 'category', 'category_name',
            'status', 'price_type', 'remark', 'price1', 'price2', 'price3',
            'tax', 'hsn_code', 'image', 'image_url',
            'username', 'client_id', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'category_name', 'image_url']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None


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
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None




# ============================================
# TV BANNER SERIALIZER  (NEW)
# ============================================

class TVBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = TVBanner
        fields = [
            'id', 'client_id', 'username',
            'image', 'image_url',
            'order', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'image_url', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

# ============================================
# TABLE SERIALIZER  (NEW)
# ============================================

class TableSerializer(serializers.ModelSerializer):
    """Serializer for Restaurant Tables"""

    class Meta:
        model = Table
        fields = [
            'id', 'client_id', 'username',
            'table_number', 'table_name', 'capacity', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        """Ensure table_number is unique per username (on create and update)."""
        username     = data.get('username', getattr(self.instance, 'username', None))
        table_number = data.get('table_number', getattr(self.instance, 'table_number', None))

        qs = Table.objects.filter(username=username, table_number=table_number)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'table_number': f"Table '{table_number}' already exists for this restaurant."}
            )
        return data


# ============================================
# CUSTOMIZATION SERIALIZER
# ============================================

class CustomizationSerializer(serializers.ModelSerializer):
    logo_url    = serializers.SerializerMethodField()
    banner_url  = serializers.SerializerMethodField()
    tv_logo_url = serializers.SerializerMethodField()
    banners     = serializers.SerializerMethodField()

    class Meta:
        model = Customization
        fields = [
            'username',
            'background_color', 'font_color', 'header_color', 'accent_color',
            'header_bg_color', 'header_text_color', 'primary_color',
            'qr_foreground_color', 'qr_background_color', 'qr_size', 'qr_margin',
            'tv_bg_color', 'tv_text_color', 'tv_accent_color', 'tv_card_bg_color',
            'logo_shape',
            'logo', 'banner', 'tv_logo',
            'logo_url', 'banner_url', 'tv_logo_url', 'banners',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['logo_url', 'banner_url', 'tv_logo_url', 'banners', 'created_at', 'updated_at']

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner_url(self, obj):
        if obj.banner:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner.url)
        return None

    def get_tv_logo_url(self, obj):
        if obj.tv_logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.tv_logo.url)
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
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'menu_item_id', 'name', 'portion', 'quantity',
            'price', 'tax', 'item_total', 'tax_amount', 'item_total_with_tax',
            'created_at',
        ]
        read_only_fields = ['id', 'item_total', 'tax_amount', 'item_total_with_tax', 'created_at']


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
            'status', 'order_time', 'special_instructions',
            'order_items', 'item_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'item_count', 'created_at', 'updated_at']


class OrderCreateSerializer(serializers.Serializer):
    """Serializer for creating orders with items"""
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
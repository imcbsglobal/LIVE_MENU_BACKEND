# api/views.py
# Complete Views with Client ID Integration and FIXED Authentication
# Restaurant Menu Management System
# UPDATED: Added WebSocket notifications for waiter/kitchen panels
#          Added accept_order endpoint (waiter accepts → kitchen notified)
#          Added get_waiter_list endpoint (for dropdown in WaiterPanel)
#          FIXED: create_user — role field handled safely (null for user_type='user')
#          FIXED: get_waiter_list — queries only user_type='user', no role filter
#          FIXED: staff_login — finds admin username correctly
#          NEW:   Table Master CRUD (get_tables, create_table, update_table, delete_table)
#          NEW:   TV Banner CRUD (get_tv_banners, upload_tv_banners, delete_tv_banner, reorder_tv_banners)

from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q, Count, Sum, Max
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import (
    MenuItem, Category, Tax, AppUser, CompanyInfo,
    Customization, Banner, TVBanner, Table, Order, OrderItem
)
from .serializers import (
    MenuItemSerializer, CategorySerializer, TaxSerializer,
    AppUserSerializer, CompanyInfoSerializer,
    CustomizationSerializer, BannerSerializer, TVBannerSerializer,
    TableSerializer,
    OrderSerializer, OrderCreateSerializer, OrderItemSerializer
)
import os
import uuid

# ── Shared channel layer instance ────────────────────────────────────────────
channel_layer = get_channel_layer()


# ============================================
# CATEGORY VIEWSET
# ============================================
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        username = self.request.query_params.get('username')
        if username:
            return Category.objects.filter(username=username)
        return Category.objects.all()

    def perform_create(self, serializer):
        serializer.save()


# ============================================
# TAX VIEWSET
# ============================================
class TaxViewSet(viewsets.ModelViewSet):
    serializer_class = TaxSerializer

    def get_queryset(self):
        username      = self.request.query_params.get('username')
        status_filter = self.request.query_params.get('status')
        queryset      = Tax.objects.all()
        if username:
            queryset = queryset.filter(username=username)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def perform_create(self, serializer):
        serializer.save()


# ============================================
# MENU ITEM VIEWSET
# ============================================
class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer

    def get_queryset(self):
        username      = self.request.query_params.get('username')
        client_id     = self.request.query_params.get('client_id')
        status_filter = self.request.query_params.get('status')
        category      = self.request.query_params.get('category')

        queryset = MenuItem.objects.select_related('category').all()

        # Always scope by both client_id AND username when both are present.
        # This guarantees data isolation — one user never sees another's items.
        if client_id and username:
            queryset = queryset.filter(client_id=client_id, username=username)
        elif username:
            queryset = queryset.filter(username=username)
        elif client_id:
            queryset = queryset.filter(client_id=client_id)

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if category:
            queryset = queryset.filter(category__name=category)
        return queryset.order_by('category', 'name')

    def perform_create(self, serializer):
        serializer.save()


# ============================================
# AUTHENTICATION
# ============================================

@api_view(['POST'])
def user_login(request):
    """
    Regular user login.
    Requires: client_id, username, password.
    """
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username', '').strip()
    password  = request.data.get('password', '')

    if not client_id or not username or not password:
        return Response({
            'success': False,
            'message': 'Client ID, username, and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = AppUser.objects.select_related('company').get(
            company__client_id=client_id,
            username=username,
            is_active=True
        )

        if not check_password(password, user.password):
            return Response({
                'success': False,
                'message': 'Invalid credentials. Please check your Client ID, username and password.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id':        user.id,
                'username':  user.username,
                'full_name': user.full_name,
                'user_type': user.user_type,
                'client_id': user.company.client_id,
                'firm_name': user.company.firm_name,
                'place':     user.company.place,
                'is_active': user.is_active,
            }
        })
    except AppUser.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid credentials. Please check your Client ID, username and password.'
        }, status=status.HTTP_401_UNAUTHORIZED)


# ============================================
# STAFF LOGIN  (Waiter / Kitchen)
# ============================================
#
# Staff are created from the WaiterManagement page with user_type='user'.
# They log in with just username + password (no client_id input).
# The client_id is resolved from settings.STAFF_CLIENT_ID.
#
# On success the response includes:
#   full_name           — auto-selected as waiter name in WaiterPanel
#   restaurant_username — the admin's username, used to fetch orders
#   role                — 'both' so StaffApp shows both panels

@api_view(['POST'])
def staff_login(request):
    """
    Staff login — username + password only, no client_id required.

    Usernames are globally unique across all companies, so we can
    look up the user directly by username alone.

    POST body:
        username  — the username created in WaiterManagement
        password  — the password set in WaiterManagement

    On success, returns full_name (auto-selected as waiter name) and
    restaurant_username (admin's username used to fetch orders in panels).
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')

    # ── 1. Both fields required ───────────────────────────────────────────────
    if not username or not password:
        return Response({
            'success': False,
            'message': 'Username and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # ── 2. Look up user by username — must be active + user_type='user' ───────
    #  Username is globally unique so no client_id needed for lookup.
    try:
        user = AppUser.objects.select_related('company').get(
            username=username,
            user_type='user',
            is_active=True,
        )
    except AppUser.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid credentials. Please check your username and password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    # ── 3. Validate password ──────────────────────────────────────────────────
    if not check_password(password, user.password):
        return Response({
            'success': False,
            'message': 'Invalid credentials. Please check your username and password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    # ── 4. Verify the company is still active ────────────────────────────────
    if not user.company.is_active:
        return Response({
            'success': False,
            'message': 'Your restaurant account is inactive. Contact your administrator.'
        }, status=status.HTTP_403_FORBIDDEN)

    # ── 5. Find restaurant_username — the username embedded in the QR code ─────
    #
    # Orders are stored with the username that appears in the QR code URL.
    # The QR code is generated by whoever owns the account:
    #   - Super Admin login → user_type='admin'
    #   - User Login        → user_type='user'  (but the first/oldest of the company)
    #
    # So we look for admin first, then fall back to the oldest non-staff user.
    restaurant_user = (
        AppUser.objects.filter(
            company=user.company,
            user_type='admin',
            is_active=True,
        ).order_by('created_at').first()
        or
        AppUser.objects.filter(
            company=user.company,
            is_active=True,
        ).exclude(id=user.id).order_by('created_at').first()
    )

    restaurant_username = restaurant_user.username if restaurant_user else user.username

    # ── 6. Success ────────────────────────────────────────────────────────────
    return Response({
        'success': True,
        'message': 'Login successful',
        'user': {
            'id':                  user.id,
            'username':            user.username,
            'full_name':           user.full_name or user.username,
            'restaurant_username': restaurant_username,
            'user_type':           'staff',
            'role':                'both',
            'client_id':           user.company.client_id,
            'firm_name':           user.company.firm_name,
            'place':               user.company.place,
            'is_active':           user.is_active,
        }
    })


# ============================================
# SUPER ADMIN LOGIN  (Company Login)
# ============================================

# Master secret — defined in settings.py as SUPER_ADMIN_SECRET.
_SUPER_ADMIN_SECRET = getattr(settings, 'SUPER_ADMIN_SECRET', 'ADMIN@2024')


@api_view(['POST'])
def verify_secret_code(request):
    """
    Step 1 of Super Admin login.
    Validates the master secret defined in settings.py (SUPER_ADMIN_SECRET).
    """
    secret_code = request.data.get('secret_code', '').strip()

    if not secret_code:
        return Response({
            'success': False,
            'message': 'Secret code is required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if secret_code == _SUPER_ADMIN_SECRET:
        return Response({
            'success': True,
            'message': 'Secret code verified. Please proceed to login.',
            'company': None
        })

    return Response({
        'success': False,
        'message': 'Invalid secret code. Please try again.'
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def company_login(request):
    """
    Step 2 of Super Admin login.
    Accepts: { client_id, username, password }
    All three must match an active CompanyInfo + AppUser(admin) pair.
    """
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username', '').strip()
    password  = request.data.get('password', '')

    if not client_id or not username or not password:
        return Response({
            'success': False,
            'message': 'Client ID, username, and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        company = CompanyInfo.objects.get(client_id=client_id, is_active=True)
    except CompanyInfo.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid Client ID. Please check the ID provided by your licensing software.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = AppUser.objects.select_related('company').get(
            company=company,
            username=username,
            is_active=True
        )
    except AppUser.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid username or password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not check_password(password, user.password):
        return Response({
            'success': False,
            'message': 'Invalid username or password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if user.user_type != 'admin':
        return Response({
            'success': False,
            'message': 'Access denied. This portal is for Super Admins only.'
        }, status=status.HTTP_403_FORBIDDEN)

    return Response({
        'success': True,
        'message': 'Login successful',
        'user': {
            'id':        user.id,
            'username':  user.username,
            'full_name': user.full_name,
            'user_type': 'company',
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
            'is_active': user.is_active,
        }
    })


@api_view(['POST'])
def superadmin_login(request):
    """Alias kept for URL backward compatibility."""
    return company_login(request)


@api_view(['POST'])
def create_super_admin(request):
    """Web creation disabled. Use: python manage.py createsuperadmin"""
    return Response({
        'success': False,
        'message': 'Use terminal command: python manage.py createsuperadmin'
    }, status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
def check_super_admin_exists(request):
    """Check whether an admin user exists for a given client_id."""
    client_id = request.data.get('client_id', '').strip()

    if not client_id:
        return Response({
            'success': False,
            'message': 'client_id is required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        company = CompanyInfo.objects.get(client_id=client_id, is_active=True)
    except CompanyInfo.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Company not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    admin_exists = AppUser.objects.filter(
        company=company, user_type='admin', is_active=True
    ).exists()

    return Response({
        'success': True,
        'admin_exists': admin_exists,
        'company': {
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
        }
    })


# ============================================
# USER MANAGEMENT
# ============================================

@api_view(['GET'])
def get_users(request):
    """
    Get users with user_type='user'.
    Pass ?client_id=... to filter by company.
    """
    client_id = request.query_params.get('client_id')
    queryset  = AppUser.objects.select_related('company').filter(user_type='user')
    if client_id:
        queryset = queryset.filter(company__client_id=client_id)
    serializer = AppUserSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def create_user(request):
    """
    Create a staff/waiter user linked to the admin's company.

    Required payload:
        username   – must be globally unique
        password   – plain text, will be hashed before storing
        client_id  – provided by the frontend from the logged-in admin session
    Optional:
        full_name  – display name shown in waiter dropdown (defaults to username)
        user_type  – always 'user' for waiter/staff created here
    """
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username', '').strip()
    password  = request.data.get('password', '')
    full_name = request.data.get('full_name', '').strip() or username

    # ── Required field validation ──────────────────────────────────────────
    if not client_id:
        return Response(
            {'success': False, 'message': 'client_id is required (from admin session).'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not username:
        return Response(
            {'success': False, 'message': 'Username is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not password:
        return Response(
            {'success': False, 'message': 'Password is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ── Company must already exist ─────────────────────────────────────────
    try:
        company = CompanyInfo.objects.get(client_id=client_id, is_active=True)
    except CompanyInfo.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Company not found for this client_id.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # ── Username must be unique ────────────────────────────────────────────
    if AppUser.objects.filter(username=username).exists():
        return Response({
            'success': False,
            'message': f'Username "{username}" is already taken. Choose a different one.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # ── Create user — role is NULL for user_type='user' (staff login uses full_name) ──
    user = AppUser.objects.create(
        company   = company,
        username  = username,
        password  = make_password(password),
        full_name = full_name,
        user_type = 'user',   # always 'user' — staff created from WaiterManagement
        role      = None,     # role not used; staff_login always returns role='both'
        is_active = True,
    )

    return Response({
        'success': True,
        'message': f'Waiter "{full_name}" created successfully.',
        'user': {
            'id':        user.id,
            'username':  user.username,
            'full_name': user.full_name,
            'user_type': user.user_type,
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
            'is_active': user.is_active,
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['PUT'])
def update_user(request, user_id):
    """
    Update an existing user.
    Editable fields: username, password (optional), full_name
    client_id (company) cannot be changed after creation.
    """
    try:
        user = AppUser.objects.select_related('company').get(id=user_id, user_type='user')
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'User not found.'},
                        status=status.HTTP_404_NOT_FOUND)

    new_username  = request.data.get('username', '').strip()
    new_password  = request.data.get('password', '').strip()
    new_full_name = request.data.get('full_name', '').strip()

    if not new_username:
        return Response({'success': False, 'message': 'Username is required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Username uniqueness check (ignore current user's own username)
    if AppUser.objects.filter(username=new_username).exclude(id=user_id).exists():
        return Response({
            'success': False,
            'message': f'Username "{new_username}" is already taken. Choose a different one.'
        }, status=status.HTTP_400_BAD_REQUEST)

    user.username  = new_username
    user.full_name = new_full_name or new_username
    if new_password:
        user.password = make_password(new_password)
    user.save()

    company = user.company
    return Response({
        'success': True,
        'message': f'User "{new_username}" updated successfully.',
        'user': {
            'id':        user.id,
            'username':  user.username,
            'full_name': user.full_name,
            'user_type': user.user_type,
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
            'is_active': user.is_active,
        }
    })


@api_view(['DELETE'])
def delete_user(request, user_id):
    """Delete a regular user (user_type='user' only)."""
    try:
        user = AppUser.objects.get(id=user_id, user_type='user')
        user.delete()
        return Response({'success': True, 'message': 'User deleted successfully.'})
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'User not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def get_user_stats(request):
    """Get menu/category stats for a given username."""
    username = request.query_params.get('username')
    if not username:
        return Response({'success': False, 'message': 'Username is required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    menu_items = MenuItem.objects.filter(username=username)
    categories = Category.objects.filter(username=username)

    return Response({
        'success': True,
        'stats': {
            'total_items':      menu_items.count(),
            'active_items':     menu_items.filter(status='active').count(),
            'inactive_items':   menu_items.filter(status='inactive').count(),
            'total_categories': categories.count(),
        }
    })


# ============================================
# WAITER LIST
# ============================================

@api_view(['GET'])
def get_waiter_list(request):
    """
    Return all active user_type='user' accounts for a given client_id.
    Used by WaiterPanel to populate the waiter name dropdown, and by
    WaiterManagement to show the list of created waiters.

    GET /api/waiters/?client_id=XXX
    """
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response(
            {'success': False, 'message': 'client_id is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Only filter by user_type='user' — no role filter needed since all
    # staff created from WaiterManagement have user_type='user' and role=None
    waiters = AppUser.objects.filter(
        user_type='user',
        company__client_id=client_id,
        is_active=True,
    ).values('id', 'username', 'full_name', 'user_type')

    return Response({'success': True, 'waiters': list(waiters)})


# ============================================
# COMPANY INFORMATION
# ============================================

@api_view(['GET'])
def get_company_info(request):
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        company    = CompanyInfo.objects.get(client_id=client_id)
        serializer = CompanyInfoSerializer(company)
        return Response({'success': True, 'company': serializer.data})
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def create_or_update_company(request):
    client_id = request.data.get('client_id')
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        company    = CompanyInfo.objects.get(client_id=client_id)
        serializer = CompanyInfoSerializer(company, data=request.data, partial=True)
    except CompanyInfo.DoesNotExist:
        serializer = CompanyInfoSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'message': 'Company information saved successfully.',
                         'company': serializer.data})
    return Response({'success': False, 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST)


# ============================================
# CUSTOMIZATION
# ============================================

@api_view(['GET'])
def get_customization(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username:
        return Response({'success': False, 'message': 'username is required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        customization = Customization.objects.get(username=username)
        serializer = CustomizationSerializer(
            customization,
            context={'request': request, 'client_id': client_id}
        )
        return Response({'success': True, 'customization': serializer.data})
    except Customization.DoesNotExist:
        return Response({'success': False, 'message': 'Customization not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def save_customization(request):
    username = request.data.get('username')
    if not username:
        return Response({'success': False, 'message': 'username is required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    fields = [
        'header_bg_color', 'header_text_color', 'primary_color',
        'accent_color', 'background_color', 'qr_foreground_color',
        'qr_background_color', 'qr_size', 'qr_margin', 'logo_shape',
        'tv_bg_color', 'tv_text_color', 'tv_accent_color', 'tv_card_bg_color',
    ]

    try:
        customization = Customization.objects.get(username=username)
        for f in fields:
            if f in request.data:
                setattr(customization, f, request.data[f])
        if 'logo' in request.FILES:
            customization.logo = request.FILES['logo']
        if 'tv_logo' in request.FILES:
            customization.tv_logo = request.FILES['tv_logo']
        customization.save()
    except Customization.DoesNotExist:
        customization = Customization.objects.create(
            username          = username,
            header_bg_color   = request.data.get('header_bg_color',   '#6366f1'),
            header_text_color = request.data.get('header_text_color', '#ffffff'),
            primary_color     = request.data.get('primary_color',     '#7c3aed'),
            accent_color      = request.data.get('accent_color',      '#10b981'),
            background_color  = request.data.get('background_color',  '#f9fafb'),
            qr_foreground_color = request.data.get('qr_foreground_color', '#000000'),
            qr_background_color = request.data.get('qr_background_color', '#ffffff'),
            qr_size           = request.data.get('qr_size',   512),
            qr_margin         = request.data.get('qr_margin', 2),
            logo_shape        = request.data.get('logo_shape', 'round'),
            tv_bg_color       = request.data.get('tv_bg_color',      '#000000'),
            tv_text_color     = request.data.get('tv_text_color',    '#ffffff'),
            tv_accent_color   = request.data.get('tv_accent_color',  '#9333ea'),
            tv_card_bg_color  = request.data.get('tv_card_bg_color', '#1f2937'),
            logo              = request.FILES.get('logo'),
            tv_logo           = request.FILES.get('tv_logo'),
        )

    serializer = CustomizationSerializer(customization, context={'request': request})
    return Response({'success': True, 'message': 'Customization saved successfully.',
                     'customization': serializer.data})


@api_view(['DELETE'])
def delete_customization_file(request):
    username  = request.query_params.get('username')
    file_type = request.query_params.get('file_type')
    if not username or not file_type:
        return Response({'success': False, 'message': 'username and file_type are required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        customization = Customization.objects.get(username=username)
        if file_type == 'logo' and customization.logo:
            customization.logo.delete()
            customization.logo = None
            customization.save()
        elif file_type == 'banner' and customization.banner:
            customization.banner.delete()
            customization.banner = None
            customization.save()
        return Response({'success': True, 'message': f'{file_type.capitalize()} deleted successfully.'})
    except Customization.DoesNotExist:
        return Response({'success': False, 'message': 'Customization not found.'},
                        status=status.HTTP_404_NOT_FOUND)


# ============================================
# BANNER MANAGEMENT
# ============================================

@api_view(['GET'])
def get_banners(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id are both required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    queryset   = Banner.objects.filter(
        username=username, client_id=client_id, is_active=True
    ).order_by('order')
    serializer = BannerSerializer(queryset, many=True, context={'request': request})
    banners_data = serializer.data
    return Response({'success': True, 'banners': banners_data, 'count': len(banners_data)})


@api_view(['POST'])
def upload_banners(request):
    username  = request.data.get('username')
    client_id = request.data.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id are required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    files = request.FILES.getlist('banners')
    if not files:
        return Response({'success': False, 'message': 'No banner files provided.'},
                        status=status.HTTP_400_BAD_REQUEST)

    max_order       = Banner.objects.filter(username=username).aggregate(Max('order'))['order__max'] or 0
    created_banners = []
    for idx, file in enumerate(files):
        banner = Banner.objects.create(
            client_id=client_id, username=username,
            image=file, order=max_order + idx + 1, is_active=True
        )
        created_banners.append(banner)

    serializer = BannerSerializer(created_banners, many=True, context={'request': request})
    return Response({'success': True,
                     'message': f'{len(created_banners)} banners uploaded successfully.',
                     'banners': serializer.data})


@api_view(['DELETE'])
def delete_banner(request, banner_id):
    username = request.query_params.get('username')
    if not username:
        return Response({'success': False, 'message': 'username is required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        banner = Banner.objects.get(id=banner_id, username=username)
        banner.image.delete()
        banner.delete()
        return Response({'success': True, 'message': 'Banner deleted successfully.'})
    except Banner.DoesNotExist:
        return Response({'success': False, 'message': 'Banner not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def reorder_banners(request):
    username      = request.data.get('username')
    banner_orders = request.data.get('banner_orders')
    if not username or not banner_orders:
        return Response({'success': False, 'message': 'username and banner_orders are required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        for item in banner_orders:
            Banner.objects.filter(id=item['id'], username=username).update(order=item['order'])
        return Response({'success': True, 'message': 'Banners reordered successfully.'})
    except Exception as e:
        return Response({'success': False, 'message': f'Error reordering banners: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================
# TABLE MASTER
# ============================================

@api_view(['GET'])
def get_tables(request):
    """
    List all tables for a restaurant.

    GET /api/tables/?username=<username>&client_id=<client_id>
    Optional: ?status=active  to return only active tables.
    """
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    status_f  = request.query_params.get('status')

    if not username or not client_id:
        return Response(
            {'success': False, 'message': 'username and client_id are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    qs = Table.objects.filter(username=username, client_id=client_id)
    if status_f:
        qs = qs.filter(status=status_f)

    serializer = TableSerializer(qs, many=True)
    return Response({'success': True, 'tables': serializer.data, 'count': qs.count()})


@api_view(['POST'])
def create_table(request):
    """
    Create a new table.

    POST /api/tables/create/
    Body: { client_id, username, table_number, table_name?, capacity?, status? }
    """
    serializer = TableSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(
            {'success': True, 'message': 'Table created successfully.', 'table': serializer.data},
            status=status.HTTP_201_CREATED
        )
    return Response({'success': False, 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH'])
def update_table(request, table_id):
    """
    Update an existing table.

    PUT/PATCH /api/tables/<table_id>/update/
    """
    try:
        table = Table.objects.get(id=table_id)
    except Table.DoesNotExist:
        return Response({'success': False, 'message': 'Table not found.'},
                        status=status.HTTP_404_NOT_FOUND)

    partial    = request.method == 'PATCH'
    serializer = TableSerializer(table, data=request.data, partial=partial)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'message': 'Table updated successfully.',
                         'table': serializer.data})
    return Response({'success': False, 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def delete_table(request, table_id):
    """
    Delete a table.

    DELETE /api/tables/<table_id>/
    """
    try:
        table = Table.objects.get(id=table_id)
    except Table.DoesNotExist:
        return Response({'success': False, 'message': 'Table not found.'},
                        status=status.HTTP_404_NOT_FOUND)

    table.delete()
    return Response({'success': True, 'message': 'Table deleted successfully.'})




# ============================================
# TV BANNER MANAGEMENT  (NEW)
# ============================================

@api_view(['GET'])
def get_tv_banners(request):
    """
    List all active TV banners for a restaurant.
    GET /api/tv-banners/?username=<username>&client_id=<client_id>
    """
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')

    if not username or not client_id:
        return Response(
            {'success': False, 'message': 'username and client_id are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    banners    = TVBanner.objects.filter(
        username=username, client_id=client_id, is_active=True
    ).order_by('order')
    serializer = TVBannerSerializer(banners, many=True, context={'request': request})
    data       = serializer.data
    return Response({'success': True, 'banners': data, 'count': len(data)})


@api_view(['POST'])
def upload_tv_banners(request):
    """
    Upload one or more TV banner images.
    POST /api/tv-banners/upload/
    Body (multipart): username, client_id, banners (files)
    """
    username  = request.data.get('username')
    client_id = request.data.get('client_id')

    if not username or not client_id:
        return Response(
            {'success': False, 'message': 'username and client_id are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    files = request.FILES.getlist('banners')
    if not files:
        return Response(
            {'success': False, 'message': 'No banner files provided.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    max_order = TVBanner.objects.filter(username=username).aggregate(
        Max('order')
    )['order__max'] or 0

    created = []
    for idx, file in enumerate(files):
        banner = TVBanner.objects.create(
            client_id=client_id,
            username=username,
            image=file,
            order=max_order + idx + 1,
            is_active=True,
        )
        created.append(banner)

    serializer = TVBannerSerializer(created, many=True, context={'request': request})
    return Response({
        'success': True,
        'message': f'{len(created)} TV banner(s) uploaded successfully.',
        'banners': serializer.data,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
def delete_tv_banner(request, banner_id):
    """
    Delete a TV banner image.
    DELETE /api/tv-banners/<banner_id>/?username=<username>
    """
    username = request.query_params.get('username')
    if not username:
        return Response(
            {'success': False, 'message': 'username is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        banner = TVBanner.objects.get(id=banner_id, username=username)
        banner.image.delete()
        banner.delete()
        return Response({'success': True, 'message': 'TV banner deleted successfully.'})
    except TVBanner.DoesNotExist:
        return Response(
            {'success': False, 'message': 'TV banner not found.'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def reorder_tv_banners(request):
    """
    Reorder TV banners.
    POST /api/tv-banners/reorder/
    Body: { username, banner_orders: [{ id, order }, ...] }
    """
    username      = request.data.get('username')
    banner_orders = request.data.get('banner_orders')

    if not username or not banner_orders:
        return Response(
            {'success': False, 'message': 'username and banner_orders are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        for item in banner_orders:
            TVBanner.objects.filter(id=item['id'], username=username).update(order=item['order'])
        return Response({'success': True, 'message': 'TV banners reordered successfully.'})
    except Exception as e:
        return Response(
            {'success': False, 'message': f'Error reordering TV banners: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# ============================================
# ORDER MANAGEMENT
# ============================================

def _build_ws_payload(order):
    """
    Build a plain-dict snapshot of an order safe for JSON serialisation
    and WebSocket broadcast.
    """
    return {
        'id':             order.id,
        'client_id':      order.client_id,
        'username':       order.username,
        'customer_name':  order.customer_name,
        'customer_phone': getattr(order, 'customer_phone', '') or '',
        'member_count':   getattr(order, 'member_count', 1) or 1,
        'table_number':   order.table_number,
        'waiter_name':    order.waiter_name or '',
        'total_amount':   str(order.total_amount),
        'status':         order.status,
        'order_time':     order.order_time.isoformat(),
        'created_at':     order.created_at.isoformat(),
        'items': [
            {
                'name':     item.name,
                'portion':  item.portion,
                'quantity': item.quantity,
                'price':    str(item.price),
            }
            for item in order.order_items.all()
        ],
    }


@api_view(['POST'])
def create_order(request):
    """
    Customer places an order.
    After saving, broadcasts 'new_order' to the waiter WebSocket group.
    """
    serializer = OrderCreateSerializer(data=request.data)
    if serializer.is_valid():
        order = serializer.save()

        if channel_layer:
            try:
                # Re-fetch with prefetch_related after save — Django clears
                # the prefetch cache on .save(), so order.order_items.all()
                # would return empty without this, sending items:[] to waiter.
                order_fresh = Order.objects.prefetch_related('order_items').get(id=order.id)
                async_to_sync(channel_layer.group_send)(
                    f"waiter_{order_fresh.client_id}",
                    {
                        'type':  'new_order',
                        'order': _build_ws_payload(order_fresh),
                    }
                )
            except Exception as e:
                print(f"⚠️  WebSocket broadcast to waiter failed: {e}")

        response_serializer = OrderSerializer(order)
        return Response({'success': True, 'message': 'Order created successfully.',
                         'order': response_serializer.data}, status=status.HTTP_201_CREATED)

    return Response({'success': False, 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def accept_order(request, order_id):
    """
    Waiter accepts a pending order.

    Request body: { "waiter_name": "Rajan" }

    Actions:
      1. Sets order.waiter_name and order.status = 'preparing'.
      2. Broadcasts 'order_accepted' to KitchenPanel WebSocket group.

    POST /api/orders/<order_id>/accept/
    """
    waiter_name = request.data.get('waiter_name', '').strip()
    if not waiter_name:
        return Response({'success': False, 'message': 'waiter_name is required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.prefetch_related('order_items').get(id=order_id)
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'},
                        status=status.HTTP_404_NOT_FOUND)

    if order.status != 'pending':
        return Response({
            'success': False,
            'message': f'Cannot accept an order with status "{order.status}". Only pending orders can be accepted.'
        }, status=status.HTTP_400_BAD_REQUEST)

    order.waiter_name = waiter_name
    order.status      = 'preparing'
    order.save()

    if channel_layer:
        try:
            # Re-fetch with prefetch_related after save — Django clears
            # the prefetch cache on .save(), so order.order_items.all()
            # would return empty without this, sending items:[] to kitchen.
            order_fresh = Order.objects.prefetch_related('order_items').get(id=order.id)
            async_to_sync(channel_layer.group_send)(
                f"kitchen_{order_fresh.client_id}",
                {
                    'type':  'order_accepted',
                    'order': _build_ws_payload(order_fresh),
                }
            )
        except Exception as e:
            print(f"⚠️  WebSocket broadcast to kitchen failed: {e}")

    serializer = OrderSerializer(order)
    return Response({
        'success': True,
        'message': f'Order accepted by {waiter_name} and sent to kitchen.',
        'order':   serializer.data,
    })


@api_view(['GET'])
def get_orders(request):
    client_id     = request.query_params.get('client_id')
    username      = request.query_params.get('username')
    status_filter = request.query_params.get('status')

    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Filter by client_id always.
    # username is optional — when provided it scopes to the restaurant owner's
    # QR-code username. When omitted, return all orders for the client_id.
    queryset = Order.objects.filter(client_id=client_id).prefetch_related('order_items')
    if username:
        queryset = queryset.filter(username=username)
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # ── Force full evaluation while DB connection is guaranteed open ──────────
    # Under ASGI the queryset is normally evaluated lazily inside the serializer.
    # By that point the middleware may have called close_old_connections().
    # Calling list() here fetches all rows (including prefetched order_items)
    # in a single atomic DB round-trip before we hand off to the serializer.
    orders = list(queryset.order_by('-created_at'))

    serializer  = OrderSerializer(orders, many=True)
    orders_data = serializer.data
    return Response({'success': True, 'orders': orders_data, 'count': len(orders_data)})


@api_view(['GET'])
def get_order_detail(request, order_id):
    try:
        order      = Order.objects.prefetch_related('order_items').get(id=order_id)
        serializer = OrderSerializer(order)
        return Response({'success': True, 'order': serializer.data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['PATCH'])
def update_order_status(request, order_id):
    new_status = request.data.get('status')
    if not new_status:
        return Response({'success': False, 'message': 'status is required.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        order        = Order.objects.get(id=order_id)
        order.status = new_status
        order.save()
        serializer   = OrderSerializer(order)
        return Response({'success': True, 'message': 'Order status updated successfully.',
                         'order': serializer.data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def cancel_order(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if order.status in ['completed', 'cancelled']:
            return Response({'success': False,
                             'message': f'Cannot cancel an order with status: {order.status}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        order.status = 'cancelled'
        order.save()
        serializer   = OrderSerializer(order)
        return Response({'success': True, 'message': 'Order cancelled successfully.',
                         'order': serializer.data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'},
                        status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def get_order_stats(request):
    client_id = request.query_params.get('client_id')
    username  = request.query_params.get('username')
    if not client_id or not username:
        return Response({'success': False, 'message': 'client_id and username are required.'},
                        status=status.HTTP_400_BAD_REQUEST)

    orders = Order.objects.filter(client_id=client_id, username=username)
    return Response({
        'success': True,
        'stats': {
            'total_orders':     orders.count(),
            'pending_orders':   orders.filter(status='pending').count(),
            'preparing_orders': orders.filter(status='preparing').count(),
            'ready_orders':     orders.filter(status='ready').count(),
            'completed_orders': orders.filter(status='completed').count(),
            'cancelled_orders': orders.filter(status='cancelled').count(),
            'total_revenue':    orders.filter(status='completed').aggregate(
                                    Sum('total_amount'))['total_amount__sum'] or 0,
        }
    })
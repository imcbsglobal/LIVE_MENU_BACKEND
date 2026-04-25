# api/views.py
# UPDATED:
#   - superadmin_login  → separate endpoint, secret_code required
#   - company_login     → only user_type='admin' allowed
#   - staff_login       → only user_type='user' allowed
#   - create_company_admin → Super Admin creates Company Admin
#   - get_all_companies    → Super Admin sees all companies
#   - MealTypeViewSet   → ADDED (fixes 404 on /api/meal-types/)
#   - All existing views unchanged

from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q, Count, Sum, Max, ProtectedError
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import (
    MenuItem, Category, Tax, AppUser, CompanyInfo,
    Customization, Banner, TVBanner, Table, Order, OrderItem,
    MealType, Kitchen, BillingRecord, SaleSession,
)
from .serializers import (
    MenuItemSerializer, CategorySerializer, TaxSerializer,
    AppUserSerializer, CompanyInfoSerializer,
    CustomizationSerializer, BannerSerializer, TVBannerSerializer,
    TableSerializer, OrderSerializer, OrderCreateSerializer,
    MealTypeSerializer, KitchenSerializer,
    BillingRecordSerializer, SaleSessionSerializer,
)
import requests

channel_layer       = get_channel_layer()
_SUPER_ADMIN_SECRET = getattr(settings, 'SUPER_ADMIN_SECRET', 'ADMIN@2024')

# ── Package → allowed_pages mapping (mirrors frontend PackageConfig.js) ──────
_PRO_PAGES = [
    'home', 'items-list', 'display', 'admin', 'category',
    'tax', 'customization', 'tv-banner', 'company-info', 'menu-qr',
    'staff-access', 'waiter-panel', 'meal-type',
]
_BASIC_PAGES = [
    'home', 'items-list', 'display', 'admin', 'category',
    'tax', 'customization', 'tv-banner', 'company-info', 'menu-qr',
    'meal-type',
]

def _allowed_pages_for_package(package):
    """Convert package key to allowed_pages list (None = unrestricted for premium)."""
    if package == 'pro':   return _PRO_PAGES
    if package == 'basic': return _BASIC_PAGES
    return None  # premium — unrestricted

def _detect_package(allowed_pages):
    """Guess package key from stored allowed_pages array."""
    if allowed_pages is None:
        return 'premium'
    s = sorted(allowed_pages)
    if s == sorted(_PRO_PAGES):   return 'pro'
    if s == sorted(_BASIC_PAGES): return 'basic'
    premium_only = {'kitchen-panel', 'table-master', 'kitchen-master'}
    if premium_only & set(allowed_pages): return 'premium'
    return 'basic'


# ─────────────────────────────────────────────────────────────
# CATEGORY VIEWSET
# ─────────────────────────────────────────────────────────────
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        client_id = self.request.query_params.get('client_id')
        username  = self.request.query_params.get('username')
        if client_id:
            return Category.objects.filter(client_id=client_id)
        if username:
            return Category.objects.filter(username=username)
        return Category.objects.none()

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProtectedError as e:
            count = len(list(e.protected_objects))
            names = ', '.join(str(o) for o in list(e.protected_objects)[:5])
            extra = f' ... and {count - 5} more.' if count > 5 else ''
            return Response({
                'detail': (
                    f'Cannot delete — {count} menu item(s) use this category. '
                    f'Reassign or delete them first. Items: {names}{extra}'
                ),
                'item_count': count,
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────
# TAX VIEWSET
# ─────────────────────────────────────────────────────────────
class TaxViewSet(viewsets.ModelViewSet):
    serializer_class = TaxSerializer

    def get_queryset(self):
        username      = self.request.query_params.get('username')
        status_filter = self.request.query_params.get('status')
        qs = Tax.objects.all()
        if username:      qs = qs.filter(username=username)
        if status_filter: qs = qs.filter(status=status_filter)
        return qs

    def destroy(self, request, *args, **kwargs):
        try:
            self.get_object().delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProtectedError as e:
            count = len(list(e.protected_objects))
            return Response({
                'detail': f'Cannot delete — used by {count} menu item(s).',
                'item_count': count,
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────
# MENU ITEM VIEWSET
# ─────────────────────────────────────────────────────────────
class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer

    def get_queryset(self):
        username      = self.request.query_params.get('username')
        client_id     = self.request.query_params.get('client_id')
        status_filter = self.request.query_params.get('status')
        category      = self.request.query_params.get('category')

        qs = MenuItem.objects.select_related('category').all()
        if client_id and username:
            qs = qs.filter(client_id=client_id, username=username)
        elif client_id:
            qs = qs.filter(client_id=client_id)
        elif username:
            qs = qs.filter(username=username)

        if status_filter: qs = qs.filter(status=status_filter)
        if category:      qs = qs.filter(category__name=category)
        return qs.order_by('category', 'name')

    # ── create ───────────────────────────────────────────────
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        menu_item = serializer.save()
        return Response(
            self.get_serializer(menu_item).data,
            status=status.HTTP_201_CREATED,
        )

    # ── update (PUT / PATCH) ──────────────────────────────────
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy()
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        menu_item = serializer.save()
        return Response(self.get_serializer(menu_item).data)


# ─────────────────────────────────────────────────────────────
# MEAL TYPE VIEWSET  ← ADDED
# Handles: GET/POST /api/meal-types/
#          GET/PUT/PATCH/DELETE /api/meal-types/{id}/
# ─────────────────────────────────────────────────────────────
class MealTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MealTypeSerializer

    def get_queryset(self):
        client_id = self.request.query_params.get('client_id')
        username  = self.request.query_params.get('username')
        qs = MealType.objects.all()
        if client_id:
            qs = qs.filter(client_id=client_id)
        if username:
            qs = qs.filter(username=username)
        return qs.order_by('start_time', 'name')

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────
# KITCHEN VIEWSET  ← NEW
# Handles: GET/POST /api/kitchens/
#          GET/PUT/PATCH/DELETE /api/kitchens/{id}/
# ─────────────────────────────────────────────────────────────
class KitchenViewSet(viewsets.ModelViewSet):
    serializer_class = KitchenSerializer

    def get_queryset(self):
        client_id = self.request.query_params.get('client_id')
        username  = self.request.query_params.get('username')
        qs = Kitchen.objects.all()
        if client_id:
            qs = qs.filter(client_id=client_id)
        if username:
            qs = qs.filter(username=username)
        return qs.order_by('kitchen_number')

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────
# KITCHEN FUNCTION-BASED VIEWS  ← NEW
# Mirrors the Table CRUD pattern used elsewhere in the app
# ─────────────────────────────────────────────────────────────

@api_view(['GET'])
def get_kitchens(request):
    client_id = request.query_params.get('client_id')
    username  = request.query_params.get('username')
    qs = Kitchen.objects.all()
    if client_id: qs = qs.filter(client_id=client_id)
    if username:  qs = qs.filter(username=username)
    serializer = KitchenSerializer(qs.order_by('kitchen_number'), many=True)
    return Response({'success': True, 'kitchens': serializer.data})


@api_view(['POST'])
def create_kitchen(request):
    serializer = KitchenSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'kitchen': serializer.data}, status=status.HTTP_201_CREATED)
    return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH'])
def update_kitchen(request, kitchen_id):
    try:
        kitchen = Kitchen.objects.get(pk=kitchen_id)
    except Kitchen.DoesNotExist:
        return Response({'success': False, 'detail': 'Kitchen not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = KitchenSerializer(kitchen, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'kitchen': serializer.data})
    return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def delete_kitchen(request, kitchen_id):
    try:
        kitchen = Kitchen.objects.get(pk=kitchen_id)
        kitchen.delete()
        return Response({'success': True, 'detail': 'Kitchen deleted.'}, status=status.HTTP_200_OK)
    except Kitchen.DoesNotExist:
        return Response({'success': False, 'detail': 'Kitchen not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'success': False, 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ─────────────────────────────────────────────────────────────
# 1. SUPER ADMIN LOGIN
#    POST /api/superadmin-login/
#    Body: { secret_code, username, password }
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def superadmin_login(request):
    secret_code = request.data.get('secret_code', '').strip()
    username    = request.data.get('username', '').strip()
    password    = request.data.get('password', '')

    if not secret_code:
        return Response({'success': False, 'message': 'Secret code is required.'}, status=400)
    if secret_code != _SUPER_ADMIN_SECRET:
        return Response({'success': False, 'message': 'Invalid secret code.'}, status=401)

    if not username or not password:
        return Response({'success': False, 'message': 'Username and password are required.'}, status=400)

    try:
        user = AppUser.objects.get(username=username, user_type='superadmin', is_active=True)
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'Super Admin account not found.'}, status=401)

    if not check_password(password, user.password):
        return Response({'success': False, 'message': 'Incorrect password.'}, status=401)

    return Response({
        'success': True,
        'message': 'Super Admin login successful.',
        'user': {
            'id':        user.id,
            'username':  user.username,
            'full_name': user.full_name or 'Super Admin',
            'user_type': 'superadmin',
            'client_id': None,
            'firm_name': 'Platform',
            'place':     '',
            'is_active': user.is_active,
        }
    })


# ─────────────────────────────────────────────────────────────
# 2. COMPANY ADMIN LOGIN
#    POST /api/company-login/
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def company_login(request):
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')

    if not username or not password:
        return Response({'success': False, 'message': 'Username and password are required.'}, status=400)

    try:
        user = AppUser.objects.select_related('company').get(username=username, is_active=True)
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'Invalid username or password.'}, status=401)

    if not check_password(password, user.password):
        return Response({'success': False, 'message': 'Invalid username or password.'}, status=401)

    if user.user_type != 'admin':
        return Response({
            'success': False,
            'message': 'This portal is for Company Admins only. Use Staff Login instead.'
        }, status=403)

    if not user.company or not user.company.is_active:
        return Response({'success': False, 'message': 'Company account is inactive.'}, status=403)

    company = user.company
    return Response({
        'success': True,
        'message': 'Login successful.',
        'user': {
            'id':            user.id,
            'username':      user.username,
            'full_name':     user.full_name,
            'user_type':     'company',
            'client_id':     company.client_id,
            'firm_name':     company.firm_name,
            'place':         company.place,
            'is_active':     user.is_active,
            'allowed_pages':  company.allowed_pages,
            'package':        company.package or _detect_package(company.allowed_pages),
            'instagram_url':  company.instagram_url or '',
            'google_url':     company.google_url    or '',
            'whatsapp':       company.whatsapp       or '',
        }
    })


# ─────────────────────────────────────────────────────────────
# 3. STAFF LOGIN
#    POST /api/staff-login/
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def staff_login(request):
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')

    if not username or not password:
        return Response({'success': False, 'message': 'Username and password are required.'}, status=400)

    try:
        user = AppUser.objects.select_related('company').get(username=username)
    except AppUser.DoesNotExist:
        return Response({
            'success': False,
            'message': f'No account found with username "{username}".'
        }, status=401)

    if user.user_type != 'user':
        return Response({
            'success': False,
            'message': 'Staff login is for staff accounts only. Use Company Admin Login.'
        }, status=401)

    if not user.is_active:
        return Response({'success': False, 'message': 'Account is deactivated.'}, status=401)

    stored = user.password or ''
    known_prefixes = ('pbkdf2_sha256$', 'pbkdf2_sha1$', 'argon2', 'bcrypt', 'md5$', 'sha1$')
    is_hashed = any(stored.startswith(p) for p in known_prefixes)
    if is_hashed:
        password_ok = check_password(password, stored)
    else:
        import hmac
        password_ok = hmac.compare_digest(stored, password)
        if password_ok:
            user.password = make_password(password)
            user.save(update_fields=['password'])

    if not password_ok:
        return Response({'success': False, 'message': 'Incorrect password.'}, status=401)

    if not user.company or not user.company.is_active:
        return Response({'success': False, 'message': 'Company account is inactive.'}, status=403)

    admin_user = (
        AppUser.objects
        .filter(company=user.company, user_type='admin', is_active=True)
        .order_by('created_at')
        .first()
    )
    restaurant_username = admin_user.username if admin_user else user.username

    return Response({
        'success': True,
        'message': 'Login successful.',
        'user': {
            'id':                  user.id,
            'username':            user.username,
            'full_name':           user.full_name or user.username,
            'restaurant_username': restaurant_username,
            'user_type':           'staff',
            'role':                user.role or 'both',
            'client_id':           user.company.client_id,
            'firm_name':           user.company.firm_name,
            'place':               user.company.place,
            'is_active':           user.is_active,
            'allowed_pages':       user.allowed_pages,
        }
    })


# ─────────────────────────────────────────────────────────────
# Legacy endpoint — kept for backward compat
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def user_login(request):
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username',  '').strip()
    password  = request.data.get('password',  '')

    if not client_id or not username or not password:
        return Response({
            'success': False,
            'message': 'Client ID, username, and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = AppUser.objects.select_related('company').get(
            company__client_id=client_id,
            username=username,
            is_active=True,
        )
    except AppUser.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid credentials. Please check your Client ID, username and password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not check_password(password, user.password):
        return Response({
            'success': False,
            'message': 'Invalid credentials. Please check your Client ID, username and password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if user.user_type not in ('admin', 'superadmin'):
        return Response({
            'success': False,
            'message': 'Access denied. This portal is for Company Admins only.'
        }, status=status.HTTP_403_FORBIDDEN)

    if not user.company or not user.company.is_active:
        return Response({
            'success': False,
            'message': 'Company account is inactive. Contact your Super Admin.'
        }, status=status.HTTP_403_FORBIDDEN)

    company = user.company
    return Response({
        'success': True,
        'message': 'Login successful',
        'user': {
            'id':            user.id,
            'username':      user.username,
            'full_name':     user.full_name,
            'user_type':     'company',
            'client_id':     company.client_id,
            'firm_name':     company.firm_name,
            'place':         company.place,
            'is_active':     user.is_active,
            'allowed_pages': company.allowed_pages,
            'package':       company.package or _detect_package(company.allowed_pages),
        }
    })


@api_view(['POST'])
def verify_secret_code(request):
    code = request.data.get('secret_code', '').strip()
    if not code:
        return Response({'success': False, 'message': 'Secret code required.'}, status=400)
    if code == _SUPER_ADMIN_SECRET:
        return Response({'success': True, 'message': 'Valid secret code.'})
    return Response({'success': False, 'message': 'Invalid secret code.'}, status=401)


# ═════════════════════════════════════════════════════════════
# SUPER ADMIN — COMPANY MANAGEMENT
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_all_companies(request):
    companies = CompanyInfo.objects.all().order_by('-created_at')
    data = []
    for c in companies:
        admin = AppUser.objects.filter(company=c, user_type='admin').order_by('created_at').first()
        admin_count = AppUser.objects.filter(company=c, user_type='admin').count()
        staff_count = AppUser.objects.filter(company=c, user_type='user').count()
        data.append({
            'client_id':         c.client_id,
            'firm_name':         c.firm_name,
            'place':             c.place,
            'is_active':         c.is_active,
            'allowed_pages':     c.allowed_pages,
            'package':           c.package or _detect_package(c.allowed_pages),
            'leasing_start_date': str(c.leasing_start_date) if c.leasing_start_date else None,
            'leasing_end_date':   str(c.leasing_end_date)   if c.leasing_end_date   else None,
            'admin_count':       admin_count,
            'staff_count':       staff_count,
            'created_at':        c.created_at.isoformat(),
            'admin_id':          admin.id       if admin else None,
            'admin_username':    admin.username if admin else None,
            'admin_full_name':   admin.full_name if admin else None,
            'admin_password':    admin.plain_password if admin else None,
        })
    return Response({'success': True, 'companies': data, 'count': len(data)})


@api_view(['POST'])
def create_company_admin(request):
    client_id = request.data.get('client_id', '').strip().upper()
    username  = request.data.get('username',  '').strip()
    password  = request.data.get('password',  '')
    full_name = request.data.get('full_name', '').strip()
    firm_name = request.data.get('firm_name', '').strip()
    place     = request.data.get('place',     '').strip()
    package   = request.data.get('package',   'premium').strip()
    if package not in ('premium', 'pro', 'basic'):
        package = 'premium'

    if not client_id: return Response({'success': False, 'message': 'Client ID is required.'}, status=400)
    if not username:  return Response({'success': False, 'message': 'Username is required.'}, status=400)
    if not password:  return Response({'success': False, 'message': 'Password is required.'}, status=400)
    if not firm_name: return Response({'success': False, 'message': 'Firm name is required.'}, status=400)

    if AppUser.objects.filter(username=username).exists():
        return Response({'success': False, 'message': f'Username "{username}" is already taken.'}, status=400)

    company, _ = CompanyInfo.objects.get_or_create(
        client_id=client_id,
        defaults={
            'firm_name': firm_name,
            'place':     place or '',
            'is_active': True,
        }
    )
    if firm_name: company.firm_name = firm_name
    if place:     company.place     = place
    company.is_active     = True
    company.package       = package
    company.allowed_pages = _allowed_pages_for_package(package)
    company.save()

    user = AppUser.objects.create(
        company=company,
        username=username,
        password=make_password(password),
        plain_password=password,
        full_name=full_name or username,
        user_type='admin',
        is_active=True,
    )

    return Response({
        'success': True,
        'message': f'Company Admin "{username}" created for {firm_name}.',
        'user': {
            'id':        user.id,
            'username':  user.username,
            'full_name': user.full_name,
            'user_type': user.user_type,
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
        }
    }, status=201)


@api_view(['POST'])
def toggle_company_active(request):
    client_id = request.data.get('client_id', '').strip()
    is_active = request.data.get('is_active')
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    try:
        company = CompanyInfo.objects.get(client_id=client_id)
        company.is_active = bool(is_active)
        company.save(update_fields=['is_active'])
        return Response({'success': True, 'message': f'Company {"activated" if is_active else "deactivated"}.'})
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)


@api_view(['POST'])
def set_company_pages(request):
    client_id     = request.data.get('client_id', '').strip()
    package       = request.data.get('package', '').strip()
    _SENTINEL     = object()
    allowed_pages = request.data.get('allowed_pages', _SENTINEL)

    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)

    if package in ('premium', 'pro', 'basic'):
        allowed_pages = _allowed_pages_for_package(package)
    elif allowed_pages is not _SENTINEL:
        if allowed_pages is not None and not isinstance(allowed_pages, list):
            return Response({'success': False, 'message': 'allowed_pages must be a list or null.'}, status=400)
    else:
        allowed_pages = None

    if not package:
        package = _detect_package(allowed_pages)

    try:
        company = CompanyInfo.objects.get(client_id=client_id)
        company.allowed_pages = allowed_pages
        company.package       = package
        company.save(update_fields=['allowed_pages', 'package'])
        return Response({
            'success':       True,
            'allowed_pages': company.allowed_pages,
            'package':       company.package,
        })
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)


@api_view(['DELETE'])
def delete_company(request):
    client_id = request.data.get('client_id', '').strip()
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    try:
        company = CompanyInfo.objects.get(client_id=client_id)
        firm_name = company.firm_name
        AppUser.objects.filter(company=company).delete()
        company.delete()
        return Response({'success': True, 'message': f'Company "{firm_name}" and all its users deleted.'})
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=500)


# ═════════════════════════════════════════════════════════════
# USER MANAGEMENT (Company Admin manages Staff)
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_users(request):
    client_id        = request.query_params.get('client_id', '').strip()
    exclude_username = request.query_params.get('exclude_username', '').strip()

    qs = AppUser.objects.select_related('company').all()
    if client_id:        qs = qs.filter(company__client_id=client_id)
    if exclude_username: qs = qs.exclude(username=exclude_username)

    data = []
    for u in qs:
        data.append({
            'id':                  u.id,
            'username':            u.username,
            'full_name':           u.full_name,
            'user_type':           u.user_type,
            'role':                u.role,
            'client_id':           u.company.client_id if u.company else None,
            'firm_name':           u.company.firm_name if u.company else '',
            'place':               u.company.place     if u.company else '',
            'is_active':           u.is_active,
            'allowed_pages':       u.company.allowed_pages if u.company else None,
            'staff_allowed_pages': u.allowed_pages,
        })
    return Response(data)


@api_view(['POST'])
def create_user(request):
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username', '').strip()
    password  = request.data.get('password', '')
    full_name = request.data.get('full_name', '').strip() or username
    role      = request.data.get('role', 'both') or 'both'

    if not client_id: return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    if not username:  return Response({'success': False, 'message': 'Username is required.'}, status=400)
    if not password:  return Response({'success': False, 'message': 'Password is required.'}, status=400)

    try:
        company = CompanyInfo.objects.get(client_id=client_id)
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)

    if not company.is_active:
        return Response({'success': False, 'message': 'Company is inactive.'}, status=403)

    if AppUser.objects.filter(username=username).exists():
        return Response({'success': False, 'message': f'Username "{username}" is already taken.'}, status=400)

    user = AppUser.objects.create(
        company=company,
        username=username,
        password=make_password(password),
        full_name=full_name,
        user_type='user',
        role=role,
        allowed_pages=None,
        is_active=True,
    )
    return Response({
        'success': True,
        'message': f'Staff "{full_name}" created.',
        'user': {
            'id':            user.id,
            'username':      user.username,
            'full_name':     user.full_name,
            'user_type':     user.user_type,
            'role':          user.role,
            'allowed_pages': user.allowed_pages,
            'client_id':     company.client_id,
            'firm_name':     company.firm_name,
            'place':         company.place,
            'is_active':     user.is_active,
        }
    }, status=201)


# Kept for backward compat
@api_view(['POST'])
def create_test_user(request):
    return create_company_admin(request)


@api_view(['PUT'])
def update_user(request, user_id):
    try:
        user = AppUser.objects.select_related('company').get(id=user_id)
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'User not found.'}, status=404)

    new_username  = request.data.get('username',  '').strip()
    new_password  = request.data.get('password',  '')
    new_full_name = request.data.get('full_name', '').strip()
    new_role      = request.data.get('role', None)

    if not new_username:
        return Response({'success': False, 'message': 'Username is required.'}, status=400)
    if AppUser.objects.filter(username=new_username).exclude(id=user_id).exists():
        return Response({'success': False, 'message': f'Username "{new_username}" is already taken.'}, status=400)

    user.username  = new_username
    user.full_name = new_full_name or new_username
    if new_password:
        user.password = make_password(new_password)
        user.plain_password = new_password
    if new_role is not None: user.role = new_role
    user.save()

    return Response({
        'success': True,
        'message': f'User "{new_username}" updated.',
        'user': {
            'id': user.id, 'username': user.username, 'full_name': user.full_name,
            'user_type': user.user_type, 'role': user.role,
            'client_id': user.company.client_id if user.company else None,
            'is_active': user.is_active,
            'allowed_pages':       user.company.allowed_pages if user.company else None,
            'staff_allowed_pages': user.allowed_pages,
        }
    })


@api_view(['POST'])
def save_user_pages(request, user_id):
    allowed_pages = request.data.get('allowed_pages', None)
    client_id     = request.data.get('client_id', '').strip()

    if allowed_pages is not None and not isinstance(allowed_pages, list):
        return Response({'success': False, 'message': 'allowed_pages must be list or null.'}, status=400)

    if client_id:
        try:
            company = CompanyInfo.objects.get(client_id=client_id)
        except CompanyInfo.DoesNotExist:
            return Response({'success': False, 'message': 'Company not found.'}, status=404)
    else:
        try:
            company = AppUser.objects.select_related('company').get(id=user_id).company
        except AppUser.DoesNotExist:
            return Response({'success': False, 'message': 'User not found.'}, status=404)

    company.allowed_pages = allowed_pages
    company.save(update_fields=['allowed_pages'])
    return Response({'success': True, 'allowed_pages': company.allowed_pages})


@api_view(['POST', 'PATCH'])
def save_staff_access(request, user_id):
    allowed_pages = request.data.get('allowed_pages', None)
    username      = (request.data.get('username') or '').strip()

    if allowed_pages is not None and not isinstance(allowed_pages, list):
        return Response({'success': False, 'message': 'allowed_pages must be list or null.'}, status=400)

    try:
        user = AppUser.objects.get(username=username) if username else AppUser.objects.get(id=user_id)
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'Staff user not found.'}, status=404)

    user.allowed_pages = allowed_pages
    user.save(update_fields=['allowed_pages'])
    return Response({'success': True, 'allowed_pages': user.allowed_pages})


@api_view(['DELETE'])
def delete_user(request, user_id):
    try:
        AppUser.objects.get(id=user_id).delete()
        return Response({'success': True, 'message': 'User deleted.'})
    except AppUser.DoesNotExist:
        return Response({'success': False, 'message': 'User not found.'}, status=404)


@api_view(['GET'])
def get_user_stats(request):
    username = request.query_params.get('username')
    if not username:
        return Response({'success': False, 'message': 'Username is required.'}, status=400)
    items = MenuItem.objects.filter(username=username)
    cats  = Category.objects.filter(username=username)
    return Response({
        'success': True,
        'stats': {
            'total_items':      items.count(),
            'active_items':     items.filter(status='active').count(),
            'inactive_items':   items.filter(status='inactive').count(),
            'total_categories': cats.count(),
        }
    })


@api_view(['GET'])
def get_waiter_list(request):
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    waiters = AppUser.objects.filter(user_type='user', company__client_id=client_id, is_active=True)
    return Response({'success': True, 'waiters': list(waiters.values('id', 'username', 'full_name', 'user_type'))})


# ─────────────────────────────────────────────────────────────
# Backward-compat stubs
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def create_super_admin(request):
    return Response({'success': False, 'message': 'Use: python manage.py createsuperadmin'}, status=403)

@api_view(['POST'])
def check_super_admin_exists(request):
    client_id = request.data.get('client_id', '').strip()
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    try:
        company      = CompanyInfo.objects.get(client_id=client_id, is_active=True)
        admin_exists = AppUser.objects.filter(company=company, user_type='admin', is_active=True).exists()
        return Response({'success': True, 'admin_exists': admin_exists,
                         'company': {'client_id': company.client_id, 'firm_name': company.firm_name}})
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)


# ═════════════════════════════════════════════════════════════
# COMPANY INFORMATION
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_company_info(request):
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    try:
        company = CompanyInfo.objects.get(client_id=client_id)
        return Response({'success': True, 'company': CompanyInfoSerializer(company).data})
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found.'}, status=404)


@api_view(['POST'])
def license_lookup(request):
    client_id = (request.data.get('client_id') or '').strip().upper()
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)
    endpoint = 'https://activate.imcbs.com/client-id-list/get-client-ids/'
    try:
        r = requests.get(endpoint, timeout=8)
        if not r.ok:
            return Response({'success': False, 'message': f'Licensing server error {r.status_code}.'}, status=502)

        data = r.json()

        # Unwrap: response may be a list directly, or { status, count, data: [...] }
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            candidates = data.get('data') or data.get('client_ids') or []
            if not isinstance(candidates, list):
                candidates = [candidates] if candidates else []
        else:
            candidates = []

        # Field names seen in the wild
        id_keys    = ['client_id', 'clientId', 'clientid', 'client', 'clientID']
        name_keys  = ['company_name', 'firm_name', 'company', 'name', 'firm']
        place_keys = ['place', 'city', 'location', 'address', 'district']

        for entry in candidates:
            if not isinstance(entry, dict):
                if isinstance(entry, str) and entry.upper() == client_id:
                    return Response({'success': True, 'valid': True, 'client_id': client_id,
                                     'company': {'firm_name': '', 'place': ''}})
                continue

            raw_id = ''
            for k in id_keys:
                if k in entry:
                    raw_id = str(entry[k]).upper()
                    break

            if raw_id != client_id:
                continue

            firm_name = ''
            for k in name_keys:
                if entry.get(k):
                    firm_name = str(entry[k])
                    break

            place = ''
            for k in place_keys:
                if entry.get(k):
                    place = str(entry[k])
                    break

            return Response({
                'success':   True,
                'valid':     True,
                'client_id': client_id,
                'firm_name': firm_name,
                'place':     place,
                'company':   {'firm_name': firm_name, 'place': place},
            })

        return Response({
            'success': False,
            'valid':   False,
            'message': f'Client ID "{client_id}" not found in licensing server.',
        }, status=404)

    except requests.RequestException as e:
        return Response({'success': False, 'message': f'Cannot reach licensing server: {e}'}, status=502)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=500)


@api_view(['POST'])
def create_or_update_company(request):
    client_id    = (request.data.get('client_id') or '').strip().upper()
    firm_name    = (request.data.get('firm_name')  or '').strip()
    place        = (request.data.get('place')       or '').strip()
    phone        = (request.data.get('phone')       or '').strip()
    email        = (request.data.get('email')       or '').strip()
    address      = (request.data.get('address')     or '').strip()
    instagram    = (request.data.get('instagram_url') or '').strip()
    google_url   = (request.data.get('google_url')    or '').strip()
    whatsapp     = (request.data.get('whatsapp')       or '').strip()
    username     = (request.data.get('username')       or '').strip()

    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)

    company, created = CompanyInfo.objects.get_or_create(
        client_id=client_id,
        defaults={'firm_name': firm_name or client_id, 'is_active': True}
    )
    if firm_name:  company.firm_name     = firm_name
    if place:      company.place         = place
    if phone:      company.phone         = phone
    if email:      company.email         = email
    if address:    company.address       = address
    if instagram:  company.instagram_url = instagram
    if google_url: company.google_url    = google_url
    if whatsapp:   company.whatsapp      = whatsapp

    logo   = request.FILES.get('logo')
    banner = request.FILES.get('banner')

    if logo:
        if company.logo:
            try: company.logo.delete(save=False)
            except Exception: pass
        company.logo = logo

    if banner:
        if company.banner:
            try: company.banner.delete(save=False)
            except Exception: pass
        company.banner = banner

    company.save()
    return Response({
        'success': True,
        'message': 'Company info saved.',
        'company': CompanyInfoSerializer(company, context={'request': request}).data,
    }, status=200)


# ═════════════════════════════════════════════════════════════
# CUSTOMIZATION
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_customization(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username:
        return Response({'success': False, 'message': 'username required.'}, status=400)
    try:
        c = Customization.objects.get(username=username)
        return Response({
            'success': True,
            'customization': CustomizationSerializer(
                c, context={'request': request, 'client_id': client_id}
            ).data
        })
    except Customization.DoesNotExist:
        return Response({'success': True, 'customization': None})


@api_view(['POST'])
def save_customization(request):
    username  = request.data.get('username')
    client_id = request.data.get('client_id')
    if not username:
        return Response({'success': False, 'message': 'username required.'}, status=400)

    c, _ = Customization.objects.get_or_create(username=username)

    fields = [
        'primary_color', 'secondary_color', 'accent_color', 'background_color',
        'text_color', 'font_family', 'border_radius', 'show_prices',
        'show_descriptions', 'layout_style', 'header_style', 'footer_text',
        'welcome_message', 'theme_name',
        # TV theme colors
        'tv_bg_color', 'tv_text_color', 'tv_accent_color', 'tv_card_bg_color',
        # TV layout theme
        'tv_theme',
    ]
    for f in fields:
        val = request.data.get(f)
        if val is not None:
            setattr(c, f, val)

    logo    = request.FILES.get('logo')
    banner  = request.FILES.get('banner')
    tv_logo = request.FILES.get('tv_logo')

    # ── Theme 2 background images ──────────────────────────────────────────────
    tv_theme2_left  = request.FILES.get('tv_theme2_left')
    tv_theme2_right = request.FILES.get('tv_theme2_right')

    # ── Theme 3 media ──────────────────────────────────────────────────────────
    tv_theme3_image = request.FILES.get('tv_theme3_image')
    tv_theme3_video = request.FILES.get('tv_theme3_video')

    if logo:
        if c.logo:
            try: c.logo.delete(save=False)
            except Exception: pass
        c.logo = logo
    if banner:
        if c.banner:
            try: c.banner.delete(save=False)
            except Exception: pass
        c.banner = banner
    if tv_logo:
        if c.tv_logo:
            try: c.tv_logo.delete(save=False)
            except Exception: pass
        c.tv_logo = tv_logo
    if tv_theme2_left:
        if c.tv_theme2_left:
            try: c.tv_theme2_left.delete(save=False)
            except Exception: pass
        c.tv_theme2_left = tv_theme2_left
    if tv_theme2_right:
        if c.tv_theme2_right:
            try: c.tv_theme2_right.delete(save=False)
            except Exception: pass
        c.tv_theme2_right = tv_theme2_right
    if tv_theme3_image:
        if c.tv_theme3_image:
            try: c.tv_theme3_image.delete(save=False)
            except Exception: pass
        c.tv_theme3_image = tv_theme3_image
    if tv_theme3_video:
        if c.tv_theme3_video:
            try: c.tv_theme3_video.delete(save=False)
            except Exception: pass
        c.tv_theme3_video = tv_theme3_video

    # ── Delete flags (sent when user removes a saved image/video) ──────────────
    if request.data.get('delete_tv_theme2_left') == 'true':
        if c.tv_theme2_left:
            try: c.tv_theme2_left.delete(save=False)
            except Exception: pass
        c.tv_theme2_left = None

    if request.data.get('delete_tv_theme2_right') == 'true':
        if c.tv_theme2_right:
            try: c.tv_theme2_right.delete(save=False)
            except Exception: pass
        c.tv_theme2_right = None

    if request.data.get('delete_tv_theme3_image') == 'true':
        if c.tv_theme3_image:
            try: c.tv_theme3_image.delete(save=False)
            except Exception: pass
        c.tv_theme3_image = None

    if request.data.get('delete_tv_theme3_video') == 'true':
        if c.tv_theme3_video:
            try: c.tv_theme3_video.delete(save=False)
            except Exception: pass
        c.tv_theme3_video = None

    c.save()
    return Response({
        'success': True,
        'message': 'Customization saved.',
        'customization': CustomizationSerializer(
            c, context={'request': request, 'client_id': client_id}
        ).data
    })


@api_view(['DELETE'])
def delete_customization_file(request):
    username  = request.query_params.get('username')
    file_type = request.query_params.get('file_type')
    if not username or not file_type:
        return Response({'success': False, 'message': 'username and file_type required.'}, status=400)
    try:
        c = Customization.objects.get(username=username)
        if file_type == 'logo'   and c.logo:   c.logo.delete();   c.logo   = None; c.save()
        elif file_type == 'banner' and c.banner: c.banner.delete(); c.banner = None; c.save()
        return Response({'success': True})
    except Customization.DoesNotExist:
        return Response({'success': False, 'message': 'Not found.'}, status=404)


# ═════════════════════════════════════════════════════════════
# BANNERS
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_banners(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id required.'}, status=400)
    qs   = Banner.objects.filter(username=username, client_id=client_id, is_active=True).order_by('order')
    data = BannerSerializer(qs, many=True, context={'request': request}).data
    return Response({'success': True, 'banners': data, 'count': len(data)})


@api_view(['POST'])
def upload_banners(request):
    username  = request.data.get('username')
    client_id = request.data.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id required.'}, status=400)
    files = request.FILES.getlist('banners')
    if not files:
        return Response({'success': False, 'message': 'No files provided.'}, status=400)
    max_order = Banner.objects.filter(username=username).aggregate(Max('order'))['order__max'] or 0
    created   = [Banner.objects.create(client_id=client_id, username=username, image=f, order=max_order + i + 1) for i, f in enumerate(files)]
    return Response({'success': True, 'banners': BannerSerializer(created, many=True, context={'request': request}).data}, status=201)


@api_view(['DELETE'])
def delete_banner(request, banner_id):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username:
        return Response({'success': False, 'message': 'username required.'}, status=400)
    try:
        qs = Banner.objects.filter(id=banner_id, username=username)
        if client_id: qs = qs.filter(client_id=client_id)
        b = qs.get()
        b.image.delete(); b.delete()
        return Response({'success': True})
    except Banner.DoesNotExist:
        return Response({'success': False, 'message': 'Banner not found.'}, status=404)


@api_view(['POST'])
def reorder_banners(request):
    username      = request.data.get('username')
    banner_orders = request.data.get('banner_orders')
    if not username or not banner_orders:
        return Response({'success': False, 'message': 'username and banner_orders required.'}, status=400)
    for item in banner_orders:
        Banner.objects.filter(id=item['id'], username=username).update(order=item['order'])
    return Response({'success': True})


# ═════════════════════════════════════════════════════════════
# TV BANNERS
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_tv_banners(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({'success': False, 'message': 'client_id required.'}, status=400)
    banners = (
        TVBanner.objects.filter(client_id=client_id, username=username, is_active=True).order_by('order')
        if username else TVBanner.objects.none()
    )
    if not banners.exists():
        banners = TVBanner.objects.filter(client_id=client_id, is_active=True).order_by('order')
    data = TVBannerSerializer(banners, many=True, context={'request': request}).data
    return Response({'success': True, 'banners': data, 'count': len(data)})


@api_view(['POST'])
def upload_tv_banners(request):
    username  = request.data.get('username')
    client_id = request.data.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id required.'}, status=400)
    files = request.FILES.getlist('banners')
    if not files:
        return Response({'success': False, 'message': 'No files provided.'}, status=400)

    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime'}
    ALLOWED_TYPES       = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES

    for f in files:
        if f.content_type not in ALLOWED_TYPES:
            return Response(
                {'success': False, 'message': f'Unsupported file type: {f.content_type}. Allowed: JPG, PNG, WEBP, MP4, WEBM.'},
                status=400
            )

    max_order = TVBanner.objects.filter(username=username).aggregate(Max('order'))['order__max'] or 0
    created   = [TVBanner.objects.create(client_id=client_id, username=username, image=f, order=max_order + i + 1) for i, f in enumerate(files)]
    return Response({'success': True, 'banners': TVBannerSerializer(created, many=True, context={'request': request}).data}, status=201)


@api_view(['DELETE'])
def delete_tv_banner(request, banner_id):
    client_id = request.query_params.get('client_id')
    username  = request.query_params.get('username')
    try:
        b = TVBanner.objects.get(id=banner_id, client_id=client_id) if client_id else TVBanner.objects.get(id=banner_id, username=username)
        b.image.delete(); b.delete()
        return Response({'success': True})
    except TVBanner.DoesNotExist:
        return Response({'success': False, 'message': 'TV banner not found.'}, status=404)


@api_view(['POST'])
def reorder_tv_banners(request):
    client_id     = request.data.get('client_id')
    username      = request.data.get('username')
    banner_orders = request.data.get('banner_orders')
    if not banner_orders:
        return Response({'success': False, 'message': 'banner_orders required.'}, status=400)
    for item in banner_orders:
        if client_id: TVBanner.objects.filter(id=item['id'], client_id=client_id).update(order=item['order'])
        else:         TVBanner.objects.filter(id=item['id'], username=username).update(order=item['order'])
    return Response({'success': True})


# ═════════════════════════════════════════════════════════════
# TABLES
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_tables(request):
    username  = request.query_params.get('username')
    client_id = request.query_params.get('client_id')
    if not username or not client_id:
        return Response({'success': False, 'message': 'username and client_id required.'}, status=400)
    tables = Table.objects.filter(username=username, client_id=client_id)
    data   = TableSerializer(tables, many=True).data
    return Response({'success': True, 'tables': data, 'count': len(data)})


@api_view(['POST'])
def create_table(request):
    s = TableSerializer(data=request.data)
    if s.is_valid():
        s.save()
        return Response({'success': True, 'table': s.data}, status=201)
    return Response({'success': False, 'errors': s.errors}, status=400)


@api_view(['PUT', 'PATCH'])
def update_table(request, table_id):
    try:
        table = Table.objects.get(id=table_id)
    except Table.DoesNotExist:
        return Response({'success': False, 'message': 'Table not found.'}, status=404)
    s = TableSerializer(table, data=request.data, partial=request.method == 'PATCH')
    if s.is_valid():
        s.save()
        return Response({'success': True, 'table': s.data})
    return Response({'success': False, 'errors': s.errors}, status=400)


@api_view(['DELETE'])
def delete_table(request, table_id):
    try:
        Table.objects.get(id=table_id).delete()
        return Response({'success': True})
    except Table.DoesNotExist:
        return Response({'success': False, 'message': 'Table not found.'}, status=404)


# ═════════════════════════════════════════════════════════════
# PUBLIC CUSTOMER MENU  (QR scan → read-only menu for customers)
# ═════════════════════════════════════════════════════════════

@api_view(['GET'])
def get_public_menu(request):
    client_id = request.query_params.get('client_id', '').strip()
    if not client_id:
        return Response({'success': False, 'message': 'client_id is required.'}, status=400)

    try:
        company = CompanyInfo.objects.get(client_id=client_id, is_active=True)
    except CompanyInfo.DoesNotExist:
        return Response({'success': False, 'message': 'Company not found or inactive.'}, status=404)

    admin = (
        AppUser.objects
        .filter(company=company, user_type='admin', is_active=True)
        .order_by('created_at')
        .first()
    )
    username = admin.username if admin else None

    items_qs = MenuItem.objects.select_related('category').filter(
        client_id=client_id, status='active'
    )
    if username:
        items_qs = items_qs.filter(username=username)
    items_qs = items_qs.order_by('category__name', 'name')

    items_data = MenuItemSerializer(items_qs, many=True, context={'request': request}).data

    customization_data = {}
    if username:
        try:
            cust = Customization.objects.get(username=username)
            customization_data = CustomizationSerializer(
                cust, context={'request': request, 'client_id': client_id}
            ).data
        except Customization.DoesNotExist:
            pass

    # ── Table info (capacity / occupancy) for the QR customer ───────────────
    table_number_param = request.query_params.get('table', '').strip()
    table_info = {}
    if table_number_param and username:
        try:
            tbl = Table.objects.get(
                client_id=client_id,
                username=username,
                table_number=table_number_param,
                status='active',
            )
            # Check if there is already an active self-order on this table.
            # A "self-order" is order_type='self' with a non-terminal status.
            active_self_order = Order.objects.filter(
                client_id=client_id,
                username=username,
                table_number=table_number_param,
                order_type='self',
            ).exclude(status__in=['completed', 'cancelled']).first()

            table_info = {
                'table_number':           tbl.table_number,
                'table_name':             tbl.table_name,
                'capacity':               tbl.capacity,
                'table_type':             tbl.table_type,
                'occupied_seats':         tbl.occupied_seats,
                'free_seats':             max(0, tbl.capacity - tbl.occupied_seats),
                'availability_status':    tbl.availability_status,
                # True when a customer has already placed a self-order that
                # hasn't been completed/cancelled yet. The customer-facing
                # MobileMenu / MenuView should block a second submission.
                'has_active_self_order':  active_self_order is not None,
                'active_self_order_id':   active_self_order.id if active_self_order else None,
                'active_self_order_status': active_self_order.status if active_self_order else None,
            }
        except Table.DoesNotExist:
            pass

    return Response({
        'success': True,
        'company': {
            'client_id': company.client_id,
            'firm_name': company.firm_name,
            'place':     company.place,
            'phone':     company.phone,
            'email':     company.email,
            'package':   company.package or _detect_package(company.allowed_pages),
        },
        'menu_items':    items_data,
        'customization': customization_data,
        'username':      username,
        'table_info':    table_info,
    })


# ─────────────────────────────────────────────────────────────
# Save billing report (called by frontend on Save & Print)
# POST /api/billings/save/
# Body: billing object (billing_id, order_id, customer_name, table_number,
#       table_name, items[], subtotal, tax_amount, total_amount, client_id, username)
# ─────────────────────────────────────────────────────────────
@api_view(['POST'])
def save_billing(request):
    try:
        data = request.data.copy()
        # ── Auto-stamp the currently active sale session for this client ──────
        client_id = (data.get('client_id') or '').strip()
        if client_id:
            active_session = SaleSession.objects.filter(
                client_id=client_id, status='active'
            ).order_by('-started_at').first()
            if active_session:
                data['sale_session'] = active_session.id
        serializer = BillingRecordSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'billing': serializer.data}, status=status.HTTP_201_CREATED)
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'success': False, 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────
# GET billing report
# GET /api/billings/?client_id=&username=&session_id=   ← primary (session-based)
# GET /api/billings/?client_id=&username=&date_from=&date_to=  ← legacy fallback
# Returns list of saved BillingRecords for the given session or date range.
# ─────────────────────────────────────────────────────────────
@api_view(['GET'])
def get_billings(request):
    try:
        client_id  = request.query_params.get('client_id',  '').strip()
        username   = request.query_params.get('username',   '').strip()
        session_id = request.query_params.get('session_id', '').strip()
        date_from  = request.query_params.get('date_from',  '').strip()
        date_to    = request.query_params.get('date_to',    '').strip()

        if not client_id or not username:
            return Response({'success': False, 'detail': 'client_id and username are required.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = BillingRecord.objects.filter(client_id=client_id, username=username)

        if session_id:
            # ── Primary path: exact session-based filter (works across midnight) ──
            qs = qs.filter(sale_session_id=session_id)
        else:
            # ── Legacy fallback: calendar date range ──────────────────────────────
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)

        qs = qs.order_by('-created_at')

        serializer = BillingRecordSerializer(qs, many=True)

        # Per-payment-method aggregates for the sale modal
        payment_totals = {}
        for method in ('cash', 'upi', 'card'):
            method_agg = qs.filter(payment_method=method).aggregate(
                bills=Count('billing_id'),
                total=Sum('total_amount'),
            )
            payment_totals[method] = {
                'bills': method_agg['bills'] or 0,
                'total': float(method_agg['total'] or 0),
            }

        return Response({
            'success': True,
            'billings': serializer.data,
            'count': qs.count(),
            'payment_totals': payment_totals,
        })
    except Exception as e:
        return Response({'success': False, 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ═════════════════════════════════════════════════════════════
# ORDERS
# ═════════════════════════════════════════════════════════════

def _ws_payload(order):
    # Build a lookup: menu_item_id → kitchen_number
    # We fetch MenuItem rows for all items in this order in one query.
    item_ids = [i.menu_item_id for i in order.order_items.all()]
    kitchen_map = {}
    if item_ids:
        for mi in MenuItem.objects.filter(id__in=item_ids).select_related('kitchen'):
            if mi.kitchen:
                kitchen_map[mi.id] = mi.kitchen.kitchen_number
            else:
                kitchen_map[mi.id] = None

    return {
        'id': order.id, 'client_id': order.client_id, 'username': order.username,
        'customer_name': order.customer_name, 'customer_phone': order.customer_phone or '',
        'member_count': order.member_count or 1, 'table_number': order.table_number,
        'waiter_name': order.waiter_name or '', 'total_amount': str(order.total_amount),
        'status': order.status, 'order_time': order.order_time.isoformat(),
        'created_at': order.created_at.isoformat(),
        'items': [
            {
                'name': i.name,
                'portion': i.portion,
                'quantity': i.quantity,
                'price': str(i.price),
                'kitchen_number': kitchen_map.get(i.menu_item_id),  # ← NEW
            }
            for i in order.order_items.all()
        ],
    }


def _occupy_table_seats(client_id, username, table_number, member_count):
    """
    Increment occupied_seats on the matching Table by member_count.
    Uses the actual member_count for both sitting and sharing tables so the
    display shows e.g. 3/6 instead of 6/6 when only 3 members placed an order.
    Safe to call; silently skips if table not found.
    """
    try:
        table = Table.objects.get(
            client_id=client_id,
            username=username,
            table_number=table_number,
            status='active',
        )
        # Both sitting and sharing: add the real member count, capped at capacity.
        # _release_table_seats handles the correct reset logic per table type on
        # order completion / cancellation.
        table.occupied_seats = min(table.capacity, table.occupied_seats + member_count)
        table.save(update_fields=['occupied_seats', 'updated_at'])
    except Table.DoesNotExist:
        pass  # Table not registered — skip silently


def _release_table_seats(client_id, username, table_number, member_count):
    """
    Decrement occupied_seats on the matching Table by member_count.
    For sitting tables, reset to 0 only when no more active (non-terminal) orders remain.
    Safe to call; silently skips if table not found.
    """
    try:
        table = Table.objects.get(
            client_id=client_id,
            username=username,
            table_number=table_number,
            status='active',
        )
        if table.table_type == 'sitting':
            # For sitting tables: reset to 0 only when ALL orders are done;
            # otherwise subtract the seats from this specific completed order so
            # the displayed count stays accurate (e.g. 3/6 → 0/6 when the last
            # active order is finished).
            active_orders = Order.objects.filter(
                client_id=client_id,
                username=username,
                table_number=table_number,
            ).exclude(status__in=['completed', 'cancelled']).count()
            if active_orders == 0:
                table.occupied_seats = 0
            else:
                table.occupied_seats = max(0, table.occupied_seats - member_count)
        else:
            # Sharing table: release only the seats belonging to this order
            table.occupied_seats = max(0, table.occupied_seats - member_count)
        table.save(update_fields=['occupied_seats', 'updated_at'])
    except Table.DoesNotExist:
        pass  # Table not registered — skip silently


@api_view(['POST'])
def create_order(request):
    s = OrderCreateSerializer(data=request.data)
    if s.is_valid():
        order = s.save()

        # ── Update table occupied seats ──────────────────────────────────────
        _occupy_table_seats(
            client_id    = order.client_id,
            username     = order.username,
            table_number = order.table_number,
            member_count = order.member_count or 1,
        )

        if channel_layer:
            try:
                fresh = Order.objects.prefetch_related('order_items').get(id=order.id)
                async_to_sync(channel_layer.group_send)(f"waiter_{fresh.client_id}", {'type': 'new_order', 'order': _ws_payload(fresh)})
            except Exception as e:
                print(f"WS broadcast failed: {e}")
        return Response({'success': True, 'order': OrderSerializer(order).data}, status=201)
    return Response({'success': False, 'errors': s.errors}, status=400)


@api_view(['POST'])
def accept_order(request, order_id):
    waiter_name = request.data.get('waiter_name', '').strip()
    if not waiter_name:
        return Response({'success': False, 'message': 'waiter_name required.'}, status=400)
    try:
        order = Order.objects.prefetch_related('order_items').get(id=order_id)
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'}, status=404)
    if order.status != 'pending':
        return Response({'success': False, 'message': f'Cannot accept — status is "{order.status}".'}, status=400)
    order.waiter_name = waiter_name
    order.status      = 'preparing'
    order.save()
    if channel_layer:
        try:
            fresh = Order.objects.prefetch_related('order_items').get(id=order.id)
            async_to_sync(channel_layer.group_send)(f"kitchen_{fresh.client_id}", {'type': 'order_accepted', 'order': _ws_payload(fresh)})
        except Exception as e:
            print(f"WS kitchen broadcast failed: {e}")
    return Response({'success': True, 'order': OrderSerializer(order).data})


@api_view(['GET'])
def get_orders(request):
    client_id     = request.query_params.get('client_id')
    username      = request.query_params.get('username')
    status_filter = request.query_params.get('status')
    if not client_id:
        return Response({'success': False, 'message': 'client_id required.'}, status=400)
    qs = Order.objects.filter(client_id=client_id).prefetch_related('order_items')
    if username:      qs = qs.filter(username=username)
    if status_filter: qs = qs.filter(status=status_filter)
    data = OrderSerializer(list(qs.order_by('-created_at')), many=True).data
    return Response({'success': True, 'orders': data, 'count': len(data)})


@api_view(['GET'])
def get_order_detail(request, order_id):
    try:
        order = Order.objects.prefetch_related('order_items').get(id=order_id)
        return Response({'success': True, 'order': OrderSerializer(order).data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'}, status=404)


@api_view(['PATCH'])
def update_order_status(request, order_id):
    new_status = request.data.get('status')
    if not new_status:
        return Response({'success': False, 'message': 'status required.'}, status=400)
    try:
        order      = Order.objects.get(id=order_id)
        old_status = order.status
        order.status = new_status
        order.save()

        # ── Release table seats when order moves to a terminal state ─────────
        terminal_statuses = ('completed', 'cancelled')
        if new_status in terminal_statuses and old_status not in terminal_statuses:
            _release_table_seats(
                client_id    = order.client_id,
                username     = order.username,
                table_number = order.table_number,
                member_count = order.member_count or 1,
            )

        return Response({'success': True, 'order': OrderSerializer(order).data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'}, status=404)


@api_view(['POST'])
def cancel_order(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if order.status in ['completed', 'cancelled']:
            return Response({'success': False, 'message': f'Cannot cancel — status is "{order.status}".'}, status=400)
        order.status = 'cancelled'
        order.save()

        # ── Release table seats on cancellation ──────────────────────────────
        _release_table_seats(
            client_id    = order.client_id,
            username     = order.username,
            table_number = order.table_number,
            member_count = order.member_count or 1,
        )

        return Response({'success': True, 'order': OrderSerializer(order).data})
    except Order.DoesNotExist:
        return Response({'success': False, 'message': 'Order not found.'}, status=404)


@api_view(['GET'])
def get_order_stats(request):
    client_id = request.query_params.get('client_id')
    username  = request.query_params.get('username')
    if not client_id:
        return Response({'success': False, 'message': 'client_id required.'}, status=400)
    orders = Order.objects.filter(client_id=client_id)
    if username: orders = orders.filter(username=username)
    return Response({
        'success': True,
        'stats': {
            'total_orders':     orders.count(),
            'pending_orders':   orders.filter(status='pending').count(),
            'preparing_orders': orders.filter(status='preparing').count(),
            'ready_orders':     orders.filter(status='ready').count(),
            'completed_orders': orders.filter(status='completed').count(),
            'cancelled_orders': orders.filter(status='cancelled').count(),
            'total_revenue':    orders.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        }
    })

# ═════════════════════════════════════════════════════════════
# SALE SESSION
# ═════════════════════════════════════════════════════════════
from django.utils import timezone


@api_view(['GET'])
def get_current_sale_session(request):
    """Return the active sale session for the given client, if any."""
    client_id = request.query_params.get('client_id', '').strip()
    username  = request.query_params.get('username', '').strip()
    if not client_id:
        return Response({'success': False, 'detail': 'client_id required.'}, status=400)
    session = SaleSession.objects.filter(
        client_id=client_id, status='active'
    ).order_by('-started_at').first()
    return Response({
        'success': True,
        'sale_session': SaleSessionSerializer(session).data if session else None,
    })


@api_view(['POST'])
def start_sale_session(request):
    """Start a new sale session (or return existing active one)."""
    client_id = request.data.get('client_id', '').strip()
    username  = request.data.get('username', '').strip()
    if not client_id:
        return Response({'success': False, 'detail': 'client_id required.'}, status=400)
    # Re-use existing active session if present
    existing = SaleSession.objects.filter(client_id=client_id, status='active').order_by('-started_at').first()
    if existing:
        return Response({'success': True, 'sale_session': SaleSessionSerializer(existing).data})
    session = SaleSession.objects.create(client_id=client_id, username=username, status='active')
    return Response({'success': True, 'sale_session': SaleSessionSerializer(session).data}, status=201)


@api_view(['PATCH'])
def end_sale_session(request, session_id):
    """End the active sale session and snapshot billing totals from linked bills."""
    try:
        session = SaleSession.objects.get(id=session_id, status='active')
    except SaleSession.DoesNotExist:
        return Response({'success': False, 'detail': 'Active sale session not found.'}, status=404)

    # ── Aggregate directly from bills stamped to this session (not by date) ───
    # This correctly handles sessions that span midnight (e.g. 2 PM → 2 AM).
    qs = BillingRecord.objects.filter(sale_session=session)
    agg = qs.aggregate(
        total_bills=Count('billing_id'),
        total_revenue=Sum('total_amount'),
        total_tax=Sum('tax_amount'),
    )
    session.total_bills   = agg['total_bills']   or 0
    session.total_revenue = agg['total_revenue'] or 0
    session.total_tax     = agg['total_tax']     or 0

    # Per-payment-method aggregation
    for method in ('cash', 'upi', 'card'):
        method_agg = qs.filter(payment_method=method).aggregate(
            bills=Count('billing_id'),
            total=Sum('total_amount'),
        )
        setattr(session, f'{method}_bills', method_agg['bills'] or 0)
        setattr(session, f'{method}_total', method_agg['total'] or 0)

    session.status   = 'ended'
    session.ended_at = timezone.now()
    session.save()
    return Response({'success': True, 'sale_session': SaleSessionSerializer(session).data})
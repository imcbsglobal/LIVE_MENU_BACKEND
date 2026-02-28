# backend/routing.py
from django.urls import path
from api.consumers import WaiterConsumer, KitchenConsumer

websocket_urlpatterns = [
    path('ws/waiter/<str:client_id>/',  WaiterConsumer.as_asgi()),
    path('ws/kitchen/<str:client_id>/', KitchenConsumer.as_asgi()),
]
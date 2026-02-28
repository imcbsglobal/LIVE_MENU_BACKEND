# api/consumers.py
# WebSocket consumers for real-time order notifications

import json
from channels.generic.websocket import AsyncWebsocketConsumer


class WaiterConsumer(AsyncWebsocketConsumer):
    """
    ws://host/ws/waiter/<client_id>/
    Waiter panel connects here — receives new order alerts from customers.
    """
    async def connect(self):
        self.client_id  = self.scope['url_route']['kwargs']['client_id']
        self.group_name = f"waiter_{self.client_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # waiter panel only receives, never sends

    # Called by create_order() in views.py via group_send
    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            'type':  'new_order',
            'order': event['order'],
        }))


class KitchenConsumer(AsyncWebsocketConsumer):
    """
    ws://host/ws/kitchen/<client_id>/
    Kitchen display connects here — receives accepted order alerts from waiter.
    """
    async def connect(self):
        self.client_id  = self.scope['url_route']['kwargs']['client_id']
        self.group_name = f"kitchen_{self.client_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # kitchen panel only receives, never sends

    # Called by accept_order() in views.py via group_send
    async def order_accepted(self, event):
        await self.send(text_data=json.dumps({
            'type':  'order_accepted',
            'order': event['order'],
        }))
from __future__ import annotations


class FakeBrokerClient:
    def __init__(self):
        self.create_order_no_called = 0
        self.preview_order_called = 0
        self.place_order_called = 0
        self.cancel_order_called = 0
        self.preview_payloads = []
        self.place_payloads = []
        self.cancel_payloads = []

    def create_order_no(self):
        self.create_order_no_called += 1
        return {"body": {"code": 0, "data": 1001}}

    def preview_order(self, payload):
        self.preview_order_called += 1
        self.preview_payloads.append(dict(payload))
        return {"body": {"code": 0, "data": {"isPass": True}}}

    def place_order(self, payload):
        self.place_order_called += 1
        self.place_payloads.append(dict(payload))
        return {"body": {"code": 0, "data": {"order_id": 1001}}}

    def cancel_order(self, **kwargs):
        self.cancel_order_called += 1
        self.cancel_payloads.append(dict(kwargs))
        return {"body": {"code": 0, "data": {"cancelled": True}}}

    def get_order(self, **kwargs):
        return {
            "body": {
                "code": 0,
                "data": {
                    "status": "Initial",
                    "filledQuantity": 0,
                    "quantity": 1,
                },
            }
        }

    def get_transactions(self, **kwargs):
        return {"body": {"code": 0, "data": []}}

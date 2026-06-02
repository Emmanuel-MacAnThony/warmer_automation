"""
Concrete adapters implementing the EmailSender / ReplyDetector /
BounceDetector ABCs defined in ``backend.infra.email.interfaces``.

Adding a new adapter:
  1. Create a new module here (e.g. microsoft.py)
  2. Define classes inheriting from the relevant ABCs
  3. Expose ``async def build(sender_account) -> EmailProvider``
  4. Register the module in ``backend.infra.email.factory._PROVIDER_MODULES``
"""

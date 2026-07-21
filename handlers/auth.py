from functools import wraps

from config import is_authorized
from database.access_control import AccessRegistry


# Temporary public mode. Set to False to restore the existing allow-list and
# AccessRegistry checks without rebuilding the authorization system.
PUBLIC_ACCESS_ENABLED = True


def authorized(handler):
    @wraps(handler)
    async def wrapped(update, context):
        if PUBLIC_ACCESS_ENABLED:
            await handler(update, context)
            return

        user = update.effective_user
        if user is None or not (
            is_authorized(user.id) or AccessRegistry().is_allowed(user.id)
        ):
            await update.effective_message.reply_text("Доступ к боту не разрешён.")
            return

        await handler(update, context)

    return wrapped

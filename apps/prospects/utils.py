from .models import ProspectActionLog


def log_prospect_action(prospect, user, action_type, description='', metadata=None):
    if metadata is None:
        metadata = {}
    ProspectActionLog.objects.create(
        prospect=prospect,
        user=user,
        action_type=action_type,
        description=description,
        metadata=metadata,
    )

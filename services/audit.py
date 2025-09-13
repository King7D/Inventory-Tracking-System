from flask_login import current_user
from extensions import db
from models import AuditLog

def audit(action: str, entity: str, entity_id=None, before=None, after=None) -> None:
    log = AuditLog(
        actor_id=getattr(current_user, "id", None),
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    db.session.add(log)

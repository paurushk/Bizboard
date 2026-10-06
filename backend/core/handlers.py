"""Document audit is written inside the money transaction.

See ``core.services.audit.record_document_event``. These events are not
subscribed here. A handler on the bus would swallow a failed insert, and
registering one beside the direct call would write two rows. PDF and
telemetry stay on the bus in the app that owns them.
"""

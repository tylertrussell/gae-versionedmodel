ERROR_MISSING_VERSION_UNIFIER = 'Missing VersionUnifier datastore entity'
ERROR_ORPHANED_MODEL = 'Orphaned model; every VersionedModel entity should have a VersionUnifier parent.'
ERROR_WRONG_PARENT_TYPE = 'Expected VersionedModel to have a VersionUnifier parent, but got a %s instead.'
ERROR_WRONG_VERSION_PARENT = 'The provided datastore key does not correspond to a version of this model.'

EVENT_CHANGED_ACTIVE_VERSION = 'changed active version'

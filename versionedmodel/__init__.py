"""Rudimentary versioning system for Google App Engine and Cloud Datastore."""

from datetime import datetime

from google.appengine.ext import db

from catnado.properties.key_property import KeyProperty
from catnado.properties.pickle_property import PickleProperty


ERROR_MISSING_VERSION_UNIFIER = 'Missing VersionUnifier datastore entity'
ERROR_WRONG_PARENT_TYPE = 'Expected VersionedModel to have a VersionUnifier parent, but got a %s instead.'
ERROR_WRONG_VERSION_PARENT = 'The provided datastore key does not correspond to a version of this model.'

EVENT_TYPE_CHANGED_ACTIVE_VERSION = 'changed active version'
EVENT_DATA_NEW_ACTIVE_VERSION = 'new version'
EVENT_DATA_TIMESTAMP = 'timestamp'
EVENT_DATA_OLD_ACTIVE_VERSION = 'old version'
EVENT_KEY = 'event'


class VersionUnifier(db.Model):
  """ Common datastore ancestor for every version of a versioned model.
  Authoritative source of which version is active.
  """

  # datastore key of the active `VersionedModel` entity
  active_version_key = KeyProperty()

  # JSON object containing historical changes to the
  active_version_history = PickleProperty(default=[])

  @db.transactional
  def set_active_version(self, active_version_key, info=None):
    """ Set the active version to the provided `active_version_key`, record
    the change in `active_version_history`, and set `VersionedModel.active`
    on the version that is becoming active (and, if applicable, the version
    that is becoming inactive).

    Args:
      active_version_key: `db.Key` of the new active version
      info: `dict` of extra information to store in `active_version_history`
    Raises:
      AssertionError if the provided key is not a descendant of this entity
    Returns:
      True to indicate success
    """
    if not isinstance(active_version_key, db.Key):
      raise ValueError('Expected active_version_key to be a db.Key')

    assert self.key() == active_version_key.parent(), ERROR_WRONG_VERSION_PARENT

    # must fetch the instance here for proper transactional semantics
    instance = VersionUnifier.get(self.key())

    default_history_info = {
      EVENT_KEY: EVENT_TYPE_CHANGED_ACTIVE_VERSION,
      EVENT_DATA_OLD_ACTIVE_VERSION: str(instance.active_version_key),
      EVENT_DATA_NEW_ACTIVE_VERSION: str(active_version_key),
      EVENT_DATA_TIMESTAMP: datetime.utcnow(),
    }
    if info:
      default_history_info.update(info)
    instance.active_version_history.append(default_history_info)

    if instance.active_version_key:
      version_becoming_inactive = VersionedModel.get(instance.active_version_key)
      version_becoming_inactive.active = False
      version_becoming_inactive._put()

    instance.active_version_key = active_version_key

    instance.put()

    version_becoming_active = VersionedModel.get(active_version_key)
    version_becoming_active.active = True
    version_becoming_active._put()

    return True


class VersionedModel(db.Model):
  """ Model with built-in versioning. Each entity represents a single version
  and all versions share a common `VersionUnifier` datastore parent.
  """

  # essentially the real parent_key value for this entity
  version_unifier_key = KeyProperty()

  # to allow queries to only return the active version
  active = db.BooleanProperty(default=False)

  created = db.DateTimeProperty(auto_now_add=True)

  def __init__(self, parent=None, key_name=None, _app=None, _from_entity=False, **kwargs):
    """ If a parent was specified when instantiating this `VersionedModel`,
    copy it elsewhere on the object so that it may be passed along to the
    `VersionUnifier` that will be this `VersionModel`'s real parent.

    See Model.__init__ for other documentation.

    Raises:
      BadArgumentError if the supplied parent is a VersionUnifier
    """
    super(VersionedModel, self).__init__(parent, key_name, _app, _from_entity, **kwargs)
    # self._parent_key will be present whether parent is specifeid by entity or
    # key whereas self._parent is only present if parent is specifeid by entity
    self._feaux_parent_key = self._parent_key
    if (self._feaux_parent_key and
        self._feaux_parent_key.parent().kind() == VersionUnifier.kind()):
      self._feaux_parent_key = self._feaux_parent_key.parent()
    self._parent = None
    self._parent_key = None

  def _reset_entity(self):
    """ Reset the entity's internal state so that a new version is saved.
    Also sets `active` to `False`.
    """
    self._entity = None
    self._key = None
    self._key_name = None
    self.active = False

  def put(self, **kwargs):
    """ Put a new version of this model to the datastore. Iff this is a new
    model, create a new `VersionUnifier` to track all of its versions.
    Args:
      Keyword args passed to super call
    Returns:
      `db.Key` for the newly-put version
    """
    creating_new_model = not self.is_saved()
    if creating_new_model:
      self.version_unifier_key = VersionUnifier(parent=self._feaux_parent_key).put()
    else:
      self.version_unifier_key = self.version_unifier_key
      self._reset_entity()
    self._parent_key = self.version_unifier_key
    my_key = self._put(**kwargs)
    if creating_new_model:
      self.set_active()
    return my_key

  def _put(self, **kwargs):
    """ The original `put` """
    return super(VersionedModel, self).put(**kwargs)

  @property
  def version_unifier(self):
    """
    Returns:
      `VersionUnifier` for this model, which is its real datastore parent.
    Raises:
      `AssertionError` if this entity has no parent or it has a parent with a
      kind other than `VersionUnifier`
    RPC Cost: 1 fetch by key
    """
    version_unifier = VersionUnifier.get(self.version_unifier_key)
    assert version_unifier is not None, ERROR_MISSING_VERSION_UNIFIER
    assert version_unifier.kind() == VersionUnifier.kind(), ERROR_WRONG_PARENT_TYPE
    return version_unifier

  def parent(self):
    """ Get this entity's feaux datastore parent (as opposed to its real parent
    which is a `VersionUnifier`).

    Returns:
      Datastore entity.
    Raises:
      The entity is loaded using `google.appengine.ext.db.get` which can raise
      exceptions (`KindError`?) if the Parent's Kind is not imported.
    RPC Cost:
      2x fetch-by-key if parent is `VersionedModel` descendant
      1x fetch-by-key otherwise
    """
    return db.get(self.parent_key())

  def parent_key(self):
    """ See: `parent`.

    Returns:
      The `db.Key` of this entity's feaux parent.
    RPC Cost:
      1x fetch-by-key if parent is `VersionedModel` descendant
      Free otherwise
    """
    feaux_parent_key = self.version_unifier_key.parent()
    # if the feaux datatore parent is a `VersionUnifier`, return its active
    # version's key
    if feaux_parent_key and feaux_parent_key.kind() == VersionUnifier.kind():
      version_unifier = VersionUnifier.get(feaux_parent_key)
      return version_unifier.active_version_key
    return feaux_parent_key

  def set_active(self, info=None):
    """ Transactionally activate this version.

    Args:
      info: optional `dict` of info to record with the change
    """
    if self.version_unifier.set_active_version(self.key(), info=info):
      self.active = True  # set value locally if transaction succeeds

  @classmethod
  def _all(cls, **kwargs):
    """ The original all() function.

    Returns:
      google.appengine.ext.db.Query
    """
    return super(VersionedModel, cls).all(**kwargs)

  @classmethod
  def all(cls, **kwargs):
    """ When composing datastore queries, only find the active version.

    Note: this may cause required indexes to be different than you might
    expect.

    Args:
      **kwargs passed to super
    Returns:
      google.appengine.ext.db.Query with an "active=True" filter applied
    """
    return cls._all().filter('active', True)

  def all_versions(self):
    """ Get a query that will fetch all of the versions of the given instance of
    VersionedModel, ordered by their ascending creation date.

    This function requires the following datastore index

    kind: VersionedModel
    properties:
      - name: version_unifier_key
        direction: asc

    Args:
      instance: Any instance of any `VersionedModel` subclass.
    Returns:
      google.appengine.ext.db.Query
    """
    return (self._all().filter('version_unifier_key', self.version_unifier_key)
                       .order('created'))

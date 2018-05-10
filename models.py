from datetime import datetime
import json

from google.appengine.api.datastore_errors import BadArgumentError
from google.appengine.ext import db

from ext.aetycoon import KeyProperty, PickleProperty
from constants import (
  ERROR_MISSING_VERSION_UNIFIER,
  ERROR_ORPHANED_MODEL, 
  ERROR_WRONG_PARENT_TYPE,
  EVENT_CHANGED_ACTIVE_VERSION,
)


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
      'event': EVENT_CHANGED_ACTIVE_VERSION,
      'old_active_version': str(instance.active_version_key),
      'new_active_version': str(active_version_key),
      'timestamp': datetime.utcnow(),
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
    model, create a new `VersionUnifier` to track all of its versions. """
    creating_new_model = not self.is_saved()
    if creating_new_model:
      version_unifier_key = VersionUnifier(parent=self._feaux_parent_key).put()
    else:
      version_unifier_key = self.version_unifier_key
      self._reset_entity()
    self._parent_key = version_unifier_key
    my_key = super(VersionedModel, self).put(**kwargs)
    if creating_new_model:
      self.set_active()
    return my_key

  def _put(self, **kwargs):
    super(VersionedModel, self).put(**kwargs)

  @property
  def version_unifier(self):
    """ See _real_parent """
    return self._real_parent()

  @property
  def version_unifier_key(self):
    """ See _real_parent_key """
    return self._real_parent_key()

  def _real_parent(self):
    """
    Returns:
      `VersionUnifier` for this model, which is its real datastore parent.
    Raises:
      `AssertionError` if this entity has no parent or it has a parent with a
      kind other than `VersionUnifier`
    RPC Cost: 1 fetch by key
    """
    real_parent_key = self._real_parent_key()
    real_parent = VersionUnifier.get(real_parent_key)

    assert real_parent is not None, ERROR_MISSING_VERSION_UNIFIER

    return real_parent

  def _real_parent_key(self):
    """ 
    Returns:
      db.Key of the `VersionUnifier` for this model, which is its real
      datastore parent.
    Raises:
      `AssertionError` if this entity has no parent or it has a parent with a
      kind other than `VersionUnifier`
    """
    real_parent_key = self.key().parent()

    assert real_parent_key is not None, ERROR_OPRHANED_MODEL
    kind = real_parent_key.kind()
    assert kind == VersionUnifier.kind(), ERROR_WRONG_PARENT_TYPE % (kind)

    return real_parent_key

  def parent(self):
    """ Get this entity's feaux datastore parent (as opposed to its real parent
    which is a `VersionUnifier`).

    Returns:
      Datastore entity. 
    Raises:
      Iff parent is `VersionedModel` descendant, the entity is loaded using 
      `google.appengine.ext.db.get` which can raise exceptions (`KindError`?)
      if the Parent's Kind is not imported.
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

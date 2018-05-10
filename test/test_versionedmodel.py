from google.appengine.api.datastore_errors import BadArgumentError
from google.appengine.ext import db

from test.testcase import SimpleAppEngineTestCase
from models import VersionedModel, VersionUnifier


class SimpleVersionedModel(VersionedModel):
  """ A simple versioned model with a `name` property for testing. """
  name = db.StringProperty()


class TestVersionedModelQueries(SimpleAppEngineTestCase):

  def test_query_only_returns_current_version(self):
    foo = SimpleVersionedModel(name='foo')
    foo.put()

    foo.name = 'foobar'
    foo.put()

    # query for both values...
    query = SimpleVersionedModel.all().filter('name IN', ('foo', 'foobar'))
    query_results = query.fetch(None)

    # but we should only get the 'foobar' version
    self.assertEqual(1, len(query_results))
    self.assertEqual(query_results[0].name, 'foobar')


class TestVersionedModelVersions(SimpleAppEngineTestCase):

  def test_creating_first_version(self):
    """ The first version should create a `VersionUnifier` to act as parent
    for all versions and automatically be set active. """

    foo = SimpleVersionedModel(name='foo')
    foo.put()

    self.assertTrue(foo.active)
    self.assertEqual(
      foo.version_unifier.active_version_key,
      foo.key()
    )

    all_version_unifiers = VersionUnifier.all().fetch(None)
    all_versioned_models = SimpleVersionedModel.all().fetch(None)

    self.assertEqual(1, len(all_versioned_models))
    self.assertEqual(1, len(all_version_unifiers))

    self.assertEqual(
      all_version_unifiers[0].key(),
      all_versioned_models[0].key().parent(),
    )

  def test_private_put_doesnt_save_new_version(self):
    foo = SimpleVersionedModel(name='foo')
    foo.put()
    
    self.assertEqual(1, len(SimpleVersionedModel.all().fetch(None)))

    foo.active = False
    foo._put()

    self.assertEqual(1, len(SimpleVersionedModel.all().fetch(None)))
    
    # might as well double check there's only one version unifier :)
    self.assertEqual(1, len(VersionUnifier.all().fetch(None)))


class TestVersionedModelParents(SimpleAppEngineTestCase):
  """ Creating `VersionedModel`s with specific datastore parents should more
  or less be the same as with regular `Model`s.
  """

  def test_creating_versioned_model_with_parent_entity_or_key(self):
    """ Create datastore relationships using `parent` kwarg, access the feaux
    parent through parent() or parent_key() """

    # one parent that will hold all the children
    parent = SimpleVersionedModel(name='parent')
    parent.put()

    # specify parent as an entity
    child = SimpleVersionedModel(name='child', parent=parent)
    child.put()

    parent_from_child = child.parent()
    self.assertEqual(parent_from_child.name, parent.name)
    parent_key_from_child = child.parent_key()
    self.assertEqual(parent_key_from_child, parent_from_child.key())

    # specify parent as a key
    child = SimpleVersionedModel(name='key_child', parent=parent.key())
    child.put()

    parent_from_child = child.parent()
    self.assertEqual(parent_from_child.name, parent.name)
    parent_key_from_child = child.parent_key()
    self.assertEqual(parent_key_from_child, parent_from_child.key())

  def test_creating_versioned_model_with_version_unifier_parent(self):
    """ `VersionUnifier` is intended to be an invisible layer in the datastore 
    hierarchy--if someone tries to create a `VersionedModel` with a specific
    `VersionUnifier` as a parent, we should raise an error.
    """

    foo = SimpleVersionedModel(name='foo')
    foo.put()

    foo_version_unifier = foo.version_unifier

    with self.assertRaises(BadArgumentError):
      bar = SimpleVersionedModel(name='bar', parent=foo_version_unifier)

    with self.assertRaises(BadArgumentError):
      bar = SimpleVersionedModel(name='bar', parent=foo_version_unifier.key())


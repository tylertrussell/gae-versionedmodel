def setup_cloud_sdk_paths():
  import os
  import sys
  gae_dir = os.environ.get('APPENGINE_SDK_DIR')
  assert gae_dir is not None, 'Please set $APPENGINE_SDK_DIR'
  sys.path.append(gae_dir)
  # importing dev_appserver handles adding rest of libraries to sys.path
  import dev_appserver
  dev_appserver.fix_sys_path()

import sys

paths_need_setup = not any(['google_appengine' in path for path in sys.path])
if paths_need_setup:
  setup_cloud_sdk_paths()

import time
import unittest

from google.appengine.ext import db, testbed

from versionedmodel import VersionedModel, VersionUnifier


class SimpleAppEngineTestCase(unittest.TestCase):

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_datastore_v3_stub()

  def tearDown(self):
    self.testbed.deactivate()


class SimpleEntity(VersionedModel):
  """ A simple versioned model for testing. """
  name = db.StringProperty()


class TestVersionedModelQueries(SimpleAppEngineTestCase):

  def test_query_only_returns_active_version(self):
    foo = SimpleEntity(name='foo')
    foo.put()

    foo.name = 'foobar'
    foo.put()

    # we should still get 'foo' from an `all` query
    query_results = SimpleEntity.all().fetch(None)
    self.assertEqual(len(query_results), 1)
    self.assertEqual(query_results[0].name, 'foo')

    # until the new version is set active
    foo.set_active()
    query_results = SimpleEntity.all().fetch(None)
    self.assertEqual(len(query_results), 1)
    self.assertEqual(query_results[0].name, 'foobar')

  def test_all_versions_query(self):
    # Create a versioned entity and a bunch of inactive versions
    first_foo = SimpleEntity.get(SimpleEntity(name='foo-0').put())
    expected_names = ['foo-0']

    # Store the expected names as we create them
    for i in range(1, 11):
      first_foo.name = first_foo.name[:-1] + str(i)
      first_foo.put()
      expected_names.append(first_foo.name)
      # sleep to space out the creation times
      time.sleep(0.1)

    # We should get all the versions back in the same order (since they were
    # sorted by creation date)
    found_names = [foo.name for foo in first_foo.all_versions().fetch(None)]
    self.assertEqual(expected_names, found_names)



class TestVersionedModelVersions(SimpleAppEngineTestCase):

  def test_creating_first_version(self):
    """ The first version should create a `VersionUnifier` to act as parent
    for all versions and automatically be set active. """

    foo = SimpleEntity(name='foo')
    foo.put()

    self.assertTrue(foo.active)
    self.assertEqual(
      foo.version_unifier.active_version_key,
      foo.key()
    )

    all_version_unifiers = VersionUnifier.all().fetch(None)
    all_versioned_models = SimpleEntity.all().fetch(None)

    self.assertEqual(len(all_versioned_models), 1)
    self.assertEqual(len(all_version_unifiers), 1)

    self.assertEqual(
      all_version_unifiers[0].key(),
      all_versioned_models[0].key().parent(),
    )

  def test_private_put_doesnt_save_new_version(self):
    foo = SimpleEntity(name='foo')
    foo.put()
    
    self.assertEqual(len(SimpleEntity._all().fetch(None)), 1)

    foo.active = False
    foo._put()

    self.assertEqual(len(SimpleEntity._all().fetch(None)), 1)

  def test_putting_new_version(self):
    foo = SimpleEntity(name='foo')
    original_key = foo.put()

    foo.name = 'foo2'
    second_key = foo.put()

    self.assertNotEqual(original_key, second_key)

    # two versions
    all_versions = SimpleEntity._all().fetch(None)
    self.assertEqual(len(all_versions), 2)

    # one version unifier
    version_unifiers = VersionUnifier.all().fetch(None)
    self.assertEqual(len(version_unifiers), 1)


class TestVersionedModelParents(SimpleAppEngineTestCase):

  def test_versioned_model_parent_always_returns_active_version(self):
    foo = SimpleEntity(name='foo')
    foo.put()

    bar = SimpleEntity(name='bar', parent=foo.key())
    bar.put()

    foo.name = 'foo2'
    foo.put()
    foo.set_active()

    self.assertEqual(bar.parent().name, 'foo2')

  def test_creating_versioned_model_with_parent_entity_or_key(self):
    """ Create datastore relationships using `parent` kwarg, access the feaux
    parent through parent() or parent_key() """

    # one parent that will hold all the children
    parent = SimpleEntity(name='parent')
    parent.put()

    # specify parent as an entity
    child = SimpleEntity(name='child', parent=parent)
    child.put()

    parent_from_child = child.parent()
    self.assertEqual(parent_from_child.name, parent.name)
    parent_key_from_child = child.parent_key()
    self.assertEqual(parent_key_from_child, parent_from_child.key())

    # specify parent as a key
    child = SimpleEntity(name='key_child', parent=parent.key())
    child.put()

    parent_from_child = child.parent()
    self.assertEqual(parent_from_child.name, parent.name)
    parent_key_from_child = child.parent_key()
    self.assertEqual(parent_key_from_child, parent_from_child.key())

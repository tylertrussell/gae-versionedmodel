# gae-versionedmodel
Rudimentary versioning system for Google App Engine and Cloud Datastore.

## Overview
User classes inherit from `VersionedModel` to gain automatic versioning. 

Every call to `put` on an existing entity will create a new _version_ of that 
entity instead of overwriting it. Consequently new versions must be marked
"active" deliberately via `set_active`.

```
class SimpleEntity(VersionedModel):
  name = db.StringProperty(required=True)

# create the first version, which automatically becomes "active"
obj = SimpleEntity(name='foo')
obj.put()

# editing an existing entity puts a new version instead
obj.name = 'bar'
obj.put()

# but it won't be returned by queries yet because it's not active
SimpleEntity.all().filter('name', 'bar').get()  # returns None
foo.set_active()
SimpleEntity.all().filter('name', 'bar').get()  # returns obj
```

### Datastore Indexes
Only the active version of any `VersionedModel` descendant is returned by
datastore queries. This is accomplished by overriding `VersionedModel.all`
to add a filter on the `active` property. Thus any indexes you create on 
`VersionedModel` descendants will need to start with `active`.

```
- kind: Cat
  properties:
  - name: active  # required because Cat descends from VersionedModel
  - name: name
  - name: age
    direction: desc
```

### Datastore Ancestry
Every unique versioned entity shares a common `VersionUnifier` parent which
keeps track of the current version. 

Any version can access its unifier via `version_unifier`. `parent()` returns 
whatever parent was specified when creating the first version. If the specified 
parent is another instance of `VersionedModel`, then the active version of that
entity is returned.

```
parent_obj = SimpleEntity(name='foo')
parent_obj.put()

child_obj = SimpleEntity(name='child foo', parent=parent_obj)
child_obj.put()

""" Real Datastore Ancestry
- VersionUnifier
  - SimpleEntity(name='foo')
  - VersionUnifier
    - SimpleEntity(name='child foo')
"""

parent_obj.name = 'foo fighter'
parent_obj.put()
parent_obj.set_active()

child_obj.parent()  # foo fighter
```


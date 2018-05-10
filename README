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
  value

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


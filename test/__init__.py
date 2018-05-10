def setup_cloud_sdk_paths():
  import os
  import sys
  gae_dir = os.environ.get('APPENGINE_SDK_DIR')
  assert gae_dir is not None, 'Please set $APPENGINE_SDK_DIR'
  sys.path.append(gae_dir)
  # importing dev_appserver handles adding rest of libraries to sys.path
  import dev_appserver
  dev_appserver.fix_sys_path()

try:
  from models import VersionedModel
except ImportError as e:
  setup_cloud_sdk_paths()

"""Fixed qualification-only fresh-process receipt observation; no replay or SDK."""
import json
from pathlib import Path
import sys
from uuid import UUID


def file_identity(path: Path):
    info = path.stat(follow_symlinks=False)
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


# Only identities and selection enter this fresh stdlib process. No parent
# ExecutionReceipt, native terminal outcome or output is supplied to it.
READER = '''import hashlib,json,os,stat,sys
assert (sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode)==(1,1,1)
root=sys.argv[1];selection=json.loads(sys.argv[2]);fds=[]
def keep(fd):fds.append(fd);return fd
def stamp(info):
 return [info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
def observe(suffix,expected):
 name=selection['operation']+'.'+suffix+'.json'
 try:fd=keep(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory))
 except FileNotFoundError:
  assert suffix=='result' and expected is None
  return None,None
 info=os.fstat(fd)
 assert expected is not None and stamp(info)==expected
 assert stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1
 assert stat.S_IMODE(info.st_mode)==384 and 0<=info.st_size<=16384
 data=b''
 while len(data)<=16384:
  chunk=os.read(fd,16385-len(data))
  if not chunk:break
  data+=chunk
 assert len(data)==info.st_size and len(data)<=16384 and stamp(os.fstat(fd))==expected
 assert stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==expected
 value=json.loads(data)
 assert value['operation']==selection['operation'] and value['handle']==selection['handle']
 return value,hashlib.sha256(data).hexdigest()
try:
 directory=keep(os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
 info=os.fstat(directory);identity=dict(dev=info.st_dev,inode=info.st_ino,uid=info.st_uid)
 assert identity==selection['root_identity'] and info.st_uid==os.geteuid()
 assert stat.S_IMODE(info.st_mode)==448
 intent,intent_hash=observe('intent',selection['intent_identity'])
 assert intent['delivery']=='not_dispatched' and intent['completion']=='unknown'
 assert intent['reason']=='pending' and intent['pending_delivery']=='unknown until an authoritative result is observed'
 result,result_hash=observe('result',selection['result_identity'])
 if result is not None:
  assert (result['reason'],result['delivery'],result['completion'])==('worker_loss','unknown','unknown')
  assert (result['failure_layer'],result['worker_exit'],result['worker_cleanup'])==('host_supervision',-9,'confirmed')
 current=os.stat(root,follow_symlinks=False)
 assert (current.st_dev,current.st_ino,current.st_uid)==(info.st_dev,info.st_ino,info.st_uid)
 fields=open('/proc/self/stat').read().rsplit(')',1)[1].split()
 print(json.dumps(dict(operation=selection['operation'],handle=selection['handle'],root_identity=identity,
  intent_sha256=intent_hash,result_sha256=result_hash,result_present=result is not None,
  delivery='unknown',completion='unknown',replay_permitted=False,pid=os.getpid(),start_ticks=fields[19],
  observation='persisted_worker_loss' if result is not None else 'intent_without_authoritative_result'),sort_keys=True))
finally:
 for fd in reversed(fds):os.close(fd)
'''


def reader_command(root, operation, handle, identity, intent_identity, result_identity):
    """Fixed UUID filenames and original host identities, never execution output."""
    if not isinstance(root, Path) or not root.is_absolute() or not isinstance(operation, UUID):
        raise ValueError('Absolute original receipt root and UUID required')
    selection = dict(operation=str(operation), handle=handle, root_identity=identity,
                     intent_identity=intent_identity, result_identity=result_identity)
    return [sys.executable, '-I', '-S', '-B', '-c', READER, str(root), json.dumps(selection, sort_keys=True)]

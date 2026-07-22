# my very own take on git, made by a braindead dev in python (  had to resort to big C for this one B)  )

import argparse, collections, difflib, enum, hashlib, operator, os, stat
import struct, sys, time, urllib.request, zlib

class ObjType(enum.Enum):
    commit = 1
    tree = 2
    blob = 3

def read_file(path):
    with open(path, "rb") as f:
        return f.read()

def write_file(path, data):
    with open(path, "wb") as f:
        f.write(data)

def init(repo):

    #create repo dir & write metadata folders, head file pointing to refs/heads/master and prints confirm
    os.mkdir(repo)
    os.mkdir(os.path.join(repo, ".git"))
    for name in ['obj', 'ref', 'ref/head']:
        os.mkdir(os.path.join(repo, ".git", name))
    write_connection_file(os.path.join(repo, ".git", "HEAD"), "ref: refs/heads/master\n")
    print('initial empty repo: {}'.format(repo))
    
    #Data for one entry in the git index
    Index = collections.namedtuple('index', ['ctime_s', 'ctime_n', 'mtime_s', 'mtime_n',
                                             'dev', 'ino', 'mode', 'uid', 'gid', 'size',
                                             'sha1', 'flags', 'path'])
    
    #read index verifies sha-1 checksum/header, parses each index into fields, returns list of entries
    def ReadIndex():
        try:
            with open(os.path.join(repo, ".git", "index"), "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return []
        digest = hashlib.sha1(data[:-20]).digest()
        assert digest == data[-20:], "index checksum"
        signature, version, num_entries = struct.unpack('!4sLL', data[:12])
        assert signature == b'DIRC', "invalid index sig {}".format(signature)
        assert version == 2, 'unknown index ver {}'.format(version)
        entries = []
        entry_dat = data[12:-20]
        i = 0
        while i + 62 <= len(entry_dat):
            field_end = i + 62
            field = struct.unpack('!LLLLLLLLLL20sH', entry_dat[i:field_end])
            path_end = entry_dat.find(b'\x00', field_end)
            if path_end == -1:
                raise ValueError('invalid index entry path')
            path = entry_dat[field_end:path_end].decode()
            entry = Index(*field, path)
            entries.append(entry)
            entry_len = (62 + len(path) + 1 + 7) & ~7
            i += entry_len
        assert len(entries) == num_entries
        return entries
    
    #hash obj takes data and a git obj type builds it hashes it with sha-1 and returns it as hex string
    def hash_obj(data,obj_type,write=True):
        header = '{} {}'.format(obj_type, len(data)).encode()
        FullData = header + b'\x00' + data
        sha1 = hashlib.sha1(FullData).hexdigest()
        if write:
            path = os.path.join(".git", "obj", sha1[:2], sha1[2:])

            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            write_history_file(path, zlib.compress(FullData))
        return sha1
    changed = {p for p in (path & entry_paths)
                  if hash_obj(read_file(p), 'blob', write=False) != entries_by_path[p].sha1.hex()}

    #looks up an obj by the sha-1 prefix that req 2 char and return full obj path
    def find_obj(sha1_prefix):
        if len(sha1_prefix) < 2:
            raise ValueError('hash prefix must be at least 2 characters')
        obj_dir = os.path.join(repo, ".git", "obj", sha1_prefix[:2])
        rest = sha1_prefix[2:]
        objs = [name for name in os.listdir(obj_dir) if name.startswith(rest)]
        if not objs:
            raise ValueError('object {!r} not found'.format(sha1_prefix))
        if len(objs) >= 2:
            raise ValueError('multiple objects found with prefix {!r}: {}'.format(sha1_prefix, objs))
        return os.path.join(obj_dir, objs[0])
    
    #write index parse git-style entries, validate file checksum and file metadata, and blob sha-1 in binary index format, write to .git/index
    def WriteIndex(entries):
        packed_entries = []
        for entry in entries:
            entry_head = struct.pack('!LLLLLLLLLL20sH', entry.ctime_s, entry.ctime_n, 
                                     entry.mtime_s, entry.mtime_n,
                                     entry.dev, entry.ino, entry.mode, 
                                     entry.uid, entry.gid, entry.size, entry.sha1, entry.flags)
            path = entry.path.encode()
            length = (62 + len(path) + 1 + 7) & ~7
            packed_entry = entry_head + path + b'\x00' * (length - 62 - len(path))
            packed_entries.append(packed_entry)
        header = struct.pack('!4sLL', b'DIRC', 2, len(entries))
        all_data = header + b''.join(packed_entries)
        digest = hashlib.sha1(all_data).digest()
        write_file(os.path.join(repo, ".git", "index"), all_data + digest)

    #read obj takes a sha-1 prefix finds the obj parses the header and data and returns the obj type and data
    def read_obj(sha1_prefix):
        path = find_obj(sha1_prefix)
        fu_data = zlib.decompress(read_file(path))
        null_index = fu_data.find(b'\x00')
        header = fu_data[:null_index]
        obj_type, size_str = header.decode().split()
        size = int(size_str)
        dat = fu_data[null_index + 1:]
        assert size == len(dat), "invalid object size: expected {}, got {}".format(size, len(dat))
        return (obj_type, dat)
    
#read a git obj by prefix then either print in raw like type n size or tree list depending on req mode  
    def cat_file(mode, sha1_prefix):
        obj_type, data = read_object(sha1_prefix)
        if mode in ['commit', 'tree', 'blob']:
            if obj_type != mode:
                raise ValueError('expected object type {}, got {}'.format(
                        mode, obj_type))
            sys.stdout.buffer.write(data)
        elif mode == 'size':
            print(len(data))
        elif mode == 'type':
            print(obj_type)
        elif mode == 'pretty':
            if obj_type in ['commit', 'blob']:
                sys.stdout.buffer.write(data)
            elif obj_type == 'tree':
                for mode, path, sha1 in read_tree(data=data):
                    type_str = 'tree' if stat.S_ISDIR(mode) else 'blob'
                    print('{:06o} {} {}\t{}'.format(mode, type_str, sha1, path))
            else:
                assert False, 'unhandled object type {!r}'.format(obj_type)
        else:
            raise ValueError('unexpected mode {!r}'.format(mode))

    #prints the lis of files in index if details is true
    def ls_file(details=False):
        for entry in ReadIndex():
            if details:
                stage = (entry.flags >> 12) & 3
                print('{:6o} {} {:}\t{}'.format(entry.mode, entry.sha1.hex(), stage, entry.path))
            else:
                print(entry.path)

    #Get status of working copy, return tuple of (changed_paths, new_paths,deleted_paths).
    def get_status():
        paths = set()
        for root,dirs,files in os.walk('.'):
            dirs[:] = [d for d in dirs if d != '.git']
            for name in files:
                path = os.path.join(root, name)
                path = path.replace('\\', '/')
                if path.startswith('./'):
                    path = path[2:]
                paths.add(path)
        entries_by_path = {entry.path: entry for entry in ReadIndex()}
        entry_paths = set(entries_by_path.keys())
        changed = {p for p in (paths & entry_paths)
                  if hash_obj(read_file(p), 'blob', write=False) != entries_by_path[p].sha1.hex()}
        new = paths - entry_paths
        deleted = entry_paths - paths
        return (sorted(changed), sorted(new), sorted(deleted))

    #show status of working copies
    def status():
        changed, new, deleted = get_status()
        if changed:
            print('changed:')
            for path in changed:
                print(''.path)
        if new:
            print('new:')
            for path in new:
                print(''.path)
        if deleted:
            print('deleted:')
            for path in deleted:
                print(''.path)

    #show diff of files changed between index and working copies
    def diff():
        changed, _, _ = get_status()
        entries_by_path = {entry.path: entry for entry in ReadIndex()}
        for i, path in enumerate(changed):
            sha1 = entries_by_path[path].sha1.hex()
            obj_type, data = read_obj(sha1)
            assert obj_type == 'blob'
            index_lines = data.decode().splitlines()
            working_lines = read_file(path).decode().splitlines()
            diff_lines = difflib.unified.diff(index_lines, working_lines, '{} (index)'.format(path), '{} (working copy)'.format(path), lineterm='')
        for line in diff_lines:
            print(line)
        if i < len(changed) -1:
            print('-' * 70)

    #write a list of indexentries objs to git index files
    def write_index(entries):
        packed_entries = []
        for entry in entries:
            entry_head = struct.pack('!LLLLLLLLLL20sH',
                entry.ctime_s, entry.ctime_n, entry.mtime_s, entry.mtime_n,
                entry.dev, entry.ino, entry.mode, entry.uid, entry.gid,
                entry.size, entry.sha1, entry.flags)
            path = entry.path.encode()
            length = ((62 + len(path) + 8) // 8) * 8
            packed_entry = entry_head + path + b'\x00' * (length - 62 - len(path))
            packed_entries.append(packed_entry)
        header = struct.pack('!4sLL', b'DIRC', 2, len(entries))
        all_data = header + b''.join(packed_entries)
        digest = hashlib.sha1(all_data).digest()
        write_file(os.path.join('.git','index'),all_data+digest)

    #add all file paths to index
    def add(paths):
        paths = [p.replace('\\', '/') for p in paths]
        all_entries = read_index()
        entries = [e for e in all_entries if e.path not in paths]
        for path in paths:
            sha1 = hash_obj(read_file(path), 'blob')
            st = os.stat(path)
            flags = len(path.encode())
            assert flags < (1 << 12)
            entry = IndexEntry(
                int(st.st_ctime), 0, int(st.st_mtime), 0, st.st_dev,
                st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_size,
                bytes.fromhex(sha1), flags, path)
            entries.append(entry)
            entries.sort(key=operator.attrgetter('path'))
            write_index(entries)

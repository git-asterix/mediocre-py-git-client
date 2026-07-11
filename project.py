from compression import zlib
import enum
import hashlib
from inspect import signature
import os
import collections
from os import path
from readline import write_history_file
import struct
from ipykernel import write_connection_file


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
                  if hash_obj(read_file(p), 'blob', write = false) != entries_by_path[p].sha1.hex()}
    
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

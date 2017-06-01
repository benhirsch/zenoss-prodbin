##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from BTrees.OOBTree import OOBTree
from OFS.SimpleItem import SimpleItem
from persistent.list import PersistentList
from itertools import chain
from zlib import adler32


DEFAULT_N_SHARDS = 127


def default_hash_func(data):
    """
    adler32 chosen as hashing mechanism since we dont need a cryptographic hashing
    """
    # In python < 3.0 adler32 returns a signed value
    return adler32(data) & 0xffffffff


class ShardedBTree(SimpleItem):
    """
    Sharded BTree to reduce the number of ConflictErrors
    """
    def __init__(self, n_shards=DEFAULT_N_SHARDS, hash_func=default_hash_func):
        """ """
        super(ShardedBTree, self).__init__()
        self.n_shards = n_shards
        self.hash_func = hash_func
        self.shards = None
        self._init_shards()

    def _init_shards(self):
        self.shards = PersistentList()
        for _ in xrange(self.n_shards):
            self.shards.append(OOBTree())

    def _get_shard_id(self, key):
        return self.hash_func(key) % self.n_shards

    def _get_shard(self, key):
        shard_id = self._get_shard_id(key)
        return self.shards[shard_id]

    def __setitem__(self, key, item):
        shard = self._get_shard(key)
        shard[key] = item

    def __getitem__(self, key):
        shard = self._get_shard(key)
        return shard[key]

    def __len__(self):
        total = 0
        for shard in self.shards:
            total += len(shard)
        return total

    def __delitem__(self, key):
        shard = self._get_shard(key)
        del shard[key]

    def __contains__(self, key):
        return self.has_key(key)

    def __iter__(self):
        return self.iterkeys()

    def get(self, key, default=None):
        shard = self._get_shard(key)
        return shard.get(key, default)

    def clear(self):
        for shard in self.shards:
            shard.clear()

    def has_key(self, key):
        shard = self._get_shard(key)
        return shard.has_key(key) > 0

    def keys(self):
        all_keys = []
        for shard in self.shards:
            all_keys.extend(shard.keys())
        return all_keys

    def values(self):
        all_values = []
        for shard in self.shards:
            all_values.extend(shard.values())
        return all_values

    def items(self):
        all_items = []
        for shard in self.shards:
            all_items.extend(shard.items())
        return all_items
        
    def iterkeys(self):
        to_chain = []
        for shard in self.shards:
            to_chain.append(shard.iterkeys())
        return chain(*to_chain)

    def itervalues(self):
        to_chain = []
        for shard in self.shards:
            to_chain.append(shard.itervalues())
        return chain(*to_chain)
        
    def iteritems(self):
        to_chain = []
        for shard in self.shards:
            to_chain.append(shard.iteritems())
        return chain(*to_chain)

    def update(self, thing):
        if not hasattr(thing, "iteritems"):
            raise TypeError("Can't create ShardedBTree from {}".format(thing.__class__))
        for k, v in thing.iteritems():
            self[k] = v

    def stats(self):
        stats = {}
        lengths = []
        for shard in self.shards:
            lengths.append(len(shard))
        values = self.values()
        stats["number of shards"] = self.n_shards
        stats["number of keys"] = len(self)
        stats["Min keys per shard"] = min(lengths)
        stats["Max keys per shard"] = max(lengths)
        stats["Avg keys per shard"] = float(sum(lengths)) / float(self.n_shards)
        return stats

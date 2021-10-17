# Copyright (c) 2021, scufre
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import datetime
import struct
from . import common


# https://github.com/libyal/libfshfs/blob/main/documentation/Hierarchical%20File%20System%20(HFS).asciidoc#volume_attribute_flags
# https://en.wikipedia.org/wiki/Apple_Partition_Map
# https://github.com/nlitsme/hfstools/
# https://github.com/Distrotech/hfsutils/
# https://github.com/ahknight/hfsinspect
# https://github.com/JotaRandom/hfsutils


def _to_datetime(apple_timestamp):
	return datetime.datetime.fromtimestamp(apple_timestamp - 0x7C25B080)
	
def _to_string(buffer):
	return buffer.decode("ascii")
	
class Volume(common.FileSystem, common.Dumpeable):
	def __init__(self, image, base_offset=0):
		self._image = image
		self._base_offset = base_offset
		self._block_size = 512
		
		# block0
		data = self.read_blocks(0)
		signature, self._block_size, self._block_count, self._device_type, self._device_id, self._driver_data, driver_descriptor_count, driver_descriptor_table, unused1 = \
			struct.unpack(">2sHIHHIH64s430s", data)
			
		if signature != b"ER":
			raise ValueError("invalid signature for apple volume block0")
			
		if self._block_size != 512:
			raise ValueError("invalid block size for apple volume block0 ({})".format(self._block_size))
			
		self._partition_map = []
		data = self.read_blocks(1)
		self._partition_map = Partition.from_sector(data, self)
		
	def read_blocks(self, address, count=1):
		block_index = (address * self.block_size) // self._image.block_size
		block_offset = (address * self.block_size) % self._image.block_size
		data = self._image.read_blocks_data(self._base_offset + block_index)[block_offset:]
		while len(data) < count * self.block_size:
			block_index += 1
			data += self._image.read_blocks_data(self._base_offset + block_index)
		return data[:count * self.block_size]
			
	@property
	def block_size(self):
		return self._block_size
	
	@property
	def partitions(self):
		return self._partition_map._partitions
	
	def dump(self, indent=0):
		return self._TAB * indent + "AppleVolume:\n" + \
			self._TAB * indent + "- Block Size: {}\n".format(self._block_size) + \
			self._TAB * indent + "- Block Count: {}\n".format(self._block_count) + \
			self._TAB * indent + "- Device Type: {}\n".format(self._device_type) + \
			self._TAB * indent + "- Device Id: {}\n".format(self._device_id) + \
			self._TAB * indent + "- Driver Data: {}\n".format(self._driver_data) + \
			self._partition_map.dump(indent + 1)

class Partition(common.Dumpeable):
	def __init__(self, partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume):
		self._partition_count = partition_count
		self._start_block = start_block
		self._block_count = block_count
		self._name = name
		self._logical_block_start = logical_block_start
		self._logical_block_count = logical_block_count
		self._flags = flags
		self._volume = volume

	def read_blocks(self, address, count=1):
		return self._volume.read_blocks(self._start_block + address, count)
	
	def dump(self, indent=0):
		return self._TAB * indent + "{} ({}):\n".format(self.__class__.__name__, self.type) + \
			self._TAB * indent + "- Partition Count: {}\n".format(self._partition_count) + \
			self._TAB * indent + "- Start Block: {}\n".format(self._start_block) + \
			self._TAB * indent + "- Block Count: {}\n".format(self._block_count) + \
			self._TAB * indent + "- Name: {}\n".format(repr(self._name)) + \
			self._TAB * indent + "- Type: {}\n".format(repr(self.get_type())) + \
			self._TAB * indent + "- Logical Block Start: {}\n".format(self._logical_block_start) + \
			self._TAB * indent + "- Logical Block Count: {}\n".format(self._logical_block_count) + \
			self._TAB * indent + "- Flags: {}".format(self._flags)
			
	@classmethod
	def get_type(cls):
		raise NotImplementedError
	
	@classmethod
	def from_sector(cls, data, volume):
		signature, unused2, partition_count, start_block, block_count, name, _type, logical_block_start, logical_block_count, flags, unused3 = \
			struct.unpack(">2s2sIII32s32sIII420s", data)

		if signature != b"PM":
			raise ValueError("invalid signature for apple block1")
			
		name = name.decode("ascii").rstrip("\x00")
		_type = _type.decode("ascii").rstrip("\x00")
		
		for c in cls.__subclasses__():
			if c.get_type() == _type:
				return c(partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume)
		raise ValueError("unknown apple partition type ({})".format(_type))
		
class PartitionMap(Partition):
	def __init__(self, partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume):
		super().__init__(partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume)
		
		self._partitions = []
		for i in range(self._partition_count - 1):
			data = self.read_blocks(1 + i)
			partition = Partition.from_sector(data, volume)
			self._partitions.append(partition)
			
	@property
	def partitions(self):
		return tuple(self._partitions)
	
	def dump(self, indent=0):
		return super().dump(indent) + "\n" + \
			self._TAB * indent + "- Partitions:\n" + \
			"\n".join([partition.dump(indent + 1) for partition in self._partitions])

	@classmethod
	def get_type(cls):
		return "Apple_partition_map"
		
class HFSPartition(Partition, common.Partition):
	def __init__(self, partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume):
		super().__init__(partition_count, start_block, block_count, name, logical_block_start, logical_block_count, flags, volume)
		
		data = self.read_blocks(0, 2)	
		"""
		signature, self._boot_entry_point, self._boot_version, self._page_flags, \
			system_filename, shell_filename, debugger1_filename, debugger2_filename, startup_screen, startup_program, scrap_filename, \
			self._allocated_control_blocks, self._max_event_queue_elements, self._system_heap_size_128, self._system_heap_size_256, self._system_heap_size, \
			unused1, self._additional_heap, self._ram_for_system_heap = struct.unpack(">2sIHH15s15s15s15s15s15s15sHHIIIHII", data[:141])
			
		if signature != b"LK":
			raise ValueError("invalid signature for HFS volume boot block {}".format(repr(signature)))
		
		self._system_filename = system_filename.decode("ascii").rstrip("\x00")
		self._shell_filename = shell_filename.decode("ascii").rstrip("\x00")
		self._debugger1_filename = debugger1_filename.decode("ascii").rstrip("\x00")
		self._debugger2_filename = debugger2_filename.decode("ascii").rstrip("\x00")
		self._startup_screen = startup_screen.decode("ascii").rstrip("\x00")
		self._startup_program = startup_program.decode("ascii").rstrip("\x00")
		self._scrap_filename = scrap_filename.decode("ascii").rstrip("\x00")
		"""
		
		data = self.read_blocks(2)
		signature, volume_creation_timestamp, volume_modification_timestamp, self._volume_attribute_flags, self._root_directory_files, self._volume_bitmap_block, \
			unused1, self._allocation_blocks, self._allocation_block_size, self._default_clump_size, self._extents_start_block, self._next_catalog_node_identifier, \
			self._unused_allocation_blocks, volume_label_size, volume_label, backup_datetime, self._backup_sequence, self._volume_wrtie_count, \
			self._extents_clump_size, self._catalog_clump_size, self._root_directory_directories, self._total_files, self._total_directories, \
			finder_information, self._volume_signature, extent_descriptor, self._extents_file_size, extents_record, self._catalog_file_size, catalog_extent_records = \
			struct.unpack(">2sIIHHHHHIIHIHB27s4sHIIIHII32s2s4sI12sI12s", data[:162])
			
		if signature != b"BD":
			raise ValueError("invalid signature for HFS master directory block {}".format(repr(signature)))
			
		if self._allocation_block_size % volume.block_size != 0:
			raise ValueError("invalid allocation block size for HFS master directory block {}".format(self._allocation_block_size))
			
		self._volume_creation_datetime = _to_datetime(volume_creation_timestamp)
		self._volume_modification_datetime = _to_datetime(volume_modification_timestamp)
			
		catalog_file_extents = ExtentGroup(catalog_extent_records, 3, self)
		if self._catalog_file_size != catalog_file_extents.size * self._allocation_block_size:
			raise ValueError("incorrect size for catalog file extent records")
		self._catalog_file = CatalogFile(catalog_file_extents, self) 
		
		self._extents = ExtentGroup(extents_record, 3, self)

	def read_extent_blocks(self, address, count):
		return self.read_blocks(self._extents_start_block + address * self._allocation_block_size // self._volume.block_size, count * self._allocation_block_size // self._volume.block_size)
	
	@property
	def type(self):
		return "applehfs"

	@property
	def label(self):
		return self.root_directory.name
	
	@property
	def root_directory(self):
		return self._catalog_file.root_directory

	def dump(self, indent=0):
		return super().dump(indent) + "\n" + \
			self._TAB * indent + "- Volume Creation: {}\n".format(self._volume_creation_datetime.isoformat()) + \
			self._TAB * indent + "- Volume Modification: {}\n".format(self._volume_modification_datetime.isoformat()) + \
			self._TAB * indent + "- Volume Attribute Flags: {}\n".format(self._volume_attribute_flags) + \
			self._TAB * indent + "- Root Directory Files: {}\n".format(self._root_directory_files) + \
			self._TAB * indent + "- Volume Bitmap Block: {}\n".format(self._volume_bitmap_block) + \
			self._TAB * indent + "- Allocation Blocks: {}\n".format(self._allocation_blocks) + \
			self._TAB * indent + "- Allocation Block Size: {}\n".format(self._allocation_block_size) + \
			self._TAB * indent + "- Default Clump Size: {}\n".format(self._default_clump_size) + \
			self._TAB * indent + "- Extents Start Block: {}\n".format(self._extents_start_block) + \
			self._TAB * indent + "- Next Catalog Node Identifier: {}\n".format(self._next_catalog_node_identifier) + \
			self._TAB * indent + "- Unused Allocation Blocks: {}\n".format(self._unused_allocation_blocks) + \
			self._TAB * indent + "- Backup Sequence Number: {}\n".format(self._backup_sequence) + \
			self._TAB * indent + "- Volume Write Count: {}\n".format(self._volume_wrtie_count) + \
			self._TAB * indent + "- Extents Clump Size: {}\n".format(self._extents_clump_size) + \
			self._TAB * indent + "- Catalog Clump Size: {}\n".format(self._catalog_clump_size) + \
			self._TAB * indent + "- Root directory directories: {}\n".format(self._root_directory_directories) + \
			self._TAB * indent + "- Files: {}\n".format(self._total_files) + \
			self._TAB * indent + "- Directories: {}\n".format(self._total_directories) + \
			self._TAB * indent + "- Embedded Volume Signature: {}\n".format(self._volume_signature.hex()) + \
			self._TAB * indent + "- Extents File Size: {}\n".format(self._extents_file_size) + \
			self._TAB * indent + "- Extents:\n" + \
			self._extents.dump(indent + 1) + "\n" + \
			self._TAB * indent + "- Catalog File Size: {}\n".format(self._catalog_file_size) + \
			self._TAB * indent + "- Catalog File:\n" + \
			self._catalog_file.dump(indent + 1)

	@classmethod
	def get_type(cls):
		return "Apple_HFS"

class ExtentGroup(common.Dumpeable):
	def __init__(self, data, count, partition):
		if len(data) != count * 4:
			raise ValueError("incorrect data size for apple extent group")
		
		self._extents = [struct.unpack(">HH", data[index * 4:(index + 1) * 4]) for index in range(count)]
		self._partition = partition
		
	def read_blocks(self, address, count):
		result = b""
		for start, size in self._extents:
			if address < size:
				chunk_size = count if address + count <= size else size - address
				result += self._partition.read_extent_blocks(start + address, chunk_size)
				count -= chunk_size
			if count == 0:
				return result
			address -= size
		raise ValueError("read past extent group end")
	
	def read_all_blocks(self):
		return b"".join([self._partition.read_extent_blocks(start, size) for start, size in self._extents if size > 0])
		
	@property
	def size(self):
		return sum([size for start, size in self._extents])

	def dump(self, indent=0):
		return self._TAB * indent + "AppleExtentGroup:\n" + \
			"\n".join([ \
				self._TAB * indent + "- Start Block: {}\n".format(start) + \
				self._TAB * indent + "- Block Count: {}".format(count) \
				for start, count in self._extents])

class CatalogFile(common.Dumpeable):
	def __init__(self, extents, partition):
		self._partition = partition
		self._btree = BTree(extents, self)
			
	def build_key(self, data):
		return CatalogKey(data)
		
	def build_record(self, key, data):
		return CatalogRecord.from_key_data(key, data)
		
	def get_extent_contents(self, extents_records, size):
		extents = ExtentGroup(extents_records, 3, self._partition)
		return extents.read_all_blocks()[:size]
		
	def _get_childs(self, identifier, _type):
		return filter(lambda record: isinstance(record, _type), self._btree.search(CatalogSearchKeyByParentIdentifier(identifier)))
	
	def get_directories(self, identifier):
		return self._get_childs(identifier, CatalogDirectoryRecord)

	def get_files(self, identifier):
		return self._get_childs(identifier, CatalogFileRecord)
			
	@property
	def root_directory(self):
		return Directory(next(self.get_directories(1)), self)

	def dump(self, indent=0):
		return self._TAB * indent + "AppleCatalogFile:\n" + \
			self._btree.dump(indent + 1)
			
class CatalogKey(common.Dumpeable):
	def __init__(self, data):
		size, unused, self._parent_identifier, name_size = struct.unpack(">BBIB", data[:7])
		self._name = _to_string(data[7:7 + name_size])
		
	def dump(self, indent=0):
		return self._TAB * indent + "AppleCatalogKey:\n" + \
			self._TAB * indent + "- Parent Identifier: {}\n".format(self._parent_identifier) + \
			self._TAB * indent + "- Name: {}".format(self._name)

class CatalogRecord(common.Dumpeable):
	def __init__(self, key, data):
		pass
		
	@classmethod
	def get_type(cls):
		raise NotImplementedError
		
	@classmethod
	def from_key_data(cls, key, data):
		_type, unused = struct.unpack(">BB", data[:2])
		
		if unused != 0:
			raise ValueError("invalid catalog record")
		
		for c in cls.__subclasses__():
			if c.get_type() == _type:
				return c(key, data)
				
		raise ValueError("unknown catalog record type ({})".format(data.hex()))
		
class CatalogDirectoryRecord(CatalogRecord):
	def __init__(self, key, data):
		self._name = key._name
		_type, self._flags, self._entry_count, self._identifier, creation_timestamp, modification_timestamp, backup_timestamp, \
			self._folder_information, self._extended_folder_information, unused = struct.unpack(">HHHIIII16s16s16s", data[:70])

	@property
	def name(self):
		return self._name
	
	@property
	def identifier(self):
		return self._identifier
		
	def dump(self, indent=0):
		return self._TAB * indent + "AppleCatalogDirectoryRecord:\n" + \
			self._TAB * indent + "- Name: {}\n".format(self._name) + \
			self._TAB * indent + "- Flags: {:04x}\n".format(self._flags) + \
			self._TAB * indent + "- Entry Count: {}\n".format(self._entry_count) + \
			self._TAB * indent + "- Identifier: {}".format(self._identifier)

	@classmethod
	def get_type(cls):
		return 1

class CatalogFileRecord(CatalogRecord):
	def __init__(self, key, data):
		self._name = key._name
		_type, self._flags, self._file_type, self._file_information, self._identifier, \
			self._data_fork_number, self._data_fork_size, self._data_fork_allocated_size, self._resource_fork_number, self._resource_fork_size, self._resource_fork_allocated_size, \
			creation_timestamp, modification_timestamp, backup_timestamp, \
			self._extended_file_information, self._clump_size, self._data_fork_extents_records, self._resource_fork_extents_records, unused = \
			struct.unpack(">HBB16sIHIIHIIIII16sH12s12sI", data[:102])

	@property
	def name(self):
		return self._name
		
	@property
	def data_size(self):
		return self._data_fork_size
	
	@property
	def resource_size(self):
		return self._resource_fork_size

	@property
	def data_extents_records(self):
		return self._data_fork_extents_records
		
	@property
	def resource_extents_records(self):
		return self._resource_fork_extents_records
		
	@classmethod
	def _get_extents_content(cls, extents, size):
		data = extents.read_blocks(0, extents.size)
		return data[:size]
	
	def get_content(self, stream=0):
		if stream == 0:
			return self._get_extents_content(self._data_fork_extents_records, self._data_fork_size)
		elif stream == 1:
			return self._get_extents_content(self._resource_fork_extents_records, self._resource_fork_size)		
		raise ValueError("unknown stream")
		
	def dump(self, indent=0):
		return self._TAB * indent + "AppleCatalogFileRecord:\n" + \
			self._TAB * indent + "- Name: {}\n".format(repr(self._name)) + \
			self._TAB * indent + "- Flags: {:04x}\n".format(self._flags) + \
			self._TAB * indent + "- File Type: {}\n".format(self._file_type) + \
			self._TAB * indent + "- Identifier: {}\n".format(self._identifier) + \
			self._TAB * indent + "- Data Fork Number: {}\n".format(self._data_fork_number) + \
			self._TAB * indent + "- Data Fork Size: {}\n".format(self._data_fork_size) + \
			self._TAB * indent + "- Data Fork Allocated Size: {}\n".format(self._data_fork_allocated_size) + \
			self._TAB * indent + "- Resource Fork Number: {}\n".format(self._resource_fork_number) + \
			self._TAB * indent + "- Resource Fork Size: {}\n".format(self._resource_fork_size) + \
			self._TAB * indent + "- Resource Fork Allocated Size: {}\n".format(self._resource_fork_allocated_size) + \
			self._TAB * indent + "- Clump Size: {}\n".format(self._clump_size) + \
			self._TAB * indent + "- First Data Fork Extents Record: {}\n".format(self._data_fork_extents_records.hex()) + \
			self._TAB * indent + "- First Resource Fork Extents Record: {}".format(self._resource_fork_extents_records.hex())
			
	@classmethod
	def get_type(cls):
		return 2

class CatalogThreadRecord(common.Dumpeable):
	def __init__(self, key, data):
		_type, unused, self._parent_identifier, name_size = struct.unpack(">H8sIB", data[:15])
		
		self._name = data[15:15 + name_size].decode("ascii")
			
	def dump(self, indent=0):
		return self._TAB * indent + "{}:\n".format(self.__class__.__name__) + \
			self._TAB * indent + "- Parent Identifier: {}\n".format(self._parent_identifier) + \
			self._TAB * indent + "- Name: {}".format(self._name)

class CatalogDirectoryThreadRecord(CatalogThreadRecord, CatalogRecord):
	@classmethod
	def get_type(cls):
		return 3
		
class CatalogFileThreadRecord(CatalogThreadRecord, CatalogRecord):
	@classmethod
	def get_type(cls):
		return 4
		
class CatalogSearchKeyByParentIdentifier(object):
	def __init__(self, parent_identifier):
		self._parent_identifier = parent_identifier
		
	def __gt__(self, other):
		if not isinstance(other, CatalogKey):
			raise ValueError("can't compare against {}".format(other.__class__.__name__))
		return self._parent_identifier > other._parent_identifier
		
	def __eq__(self, other):
		if not isinstance(other, CatalogKey):
			raise ValueError("can't compare against {}".format(other.__class__.__name__))
		return self._parent_identifier == other._parent_identifier
		
class BTree(common.Dumpeable):
	def __init__(self, extents, file):
		# get the node size from the header node first
		data = extents.read_blocks(0, 1)
		node_size = struct.unpack(">H", data[32:34])[0]
		block_size = len(data)
		
		self._header_node = self._read_node(0, node_size, extents, block_size, file)
		
		self._nodes = [self._header_node, ]
		self._records = {}
		for index in range(1, self._header_node.node_count):
			if self._header_node.is_used(index):
				node = self._read_node(index, node_size, extents, block_size, file)
			else:
				node = None
								
			self._nodes.append(node)
	
	@classmethod
	def _read_node(cls, index, node_size, extents, block_size, file):
		if block_size >= node_size:
			block_index = index * node_size // block_size
			block_offset = (index * node_size) % block_size
			block = extents.read_blocks(block_index, 1)
			data = block[block_offset:block_offset + node_size]
		else:
			node_blocks = node_size // block_size
			block_index = index * node_blocks
			data = extents.read_blocks(block_index, node_blocks)
		return BTreeNode.from_sector(data, file)
	
	def search(self, key):
		current_node = self._nodes[self._header_node.root_node]
		while isinstance(current_node, BTreeIndexNode):
			try:
				current_node = self._nodes[current_node.search(key)]
			except KeyError as e:
				return []

		result = []
		while True:
			try:
				node_records = current_node.search(key)
				result.extend(node_records)
				if current_node.next_node == 0:
					return result
			except KeyError as e:
				return result
			current_node = self._nodes[current_node.next_node]
				
	def dump(self, indent=0):
		return self._TAB * indent + "- AppleBTree:\n" + \
			"\n".join([node.dump(indent + 1) for node in self._nodes if node is not None])

class BTreeNode(common.Dumpeable):
	def __init__(self, next, previous, level, record_offsets, data, file):
		self._next = next
		self._previous = previous
		self._level = level
		self._record_offsets = record_offsets
		
	@property
	def next_node(self):
		return self._next
		
	@property
	def previous_node(self):
		return self._previous
		
	def dump(self, indent=0):
		return self._TAB * indent + "{}:\n".format(self.__class__.__name__) + \
			self._TAB * indent + "- Next: {}\n".format(self._next) + \
			self._TAB * indent + "- Previous: {}\n".format(self._previous) + \
			self._TAB * indent + "- Level: {}\n".format(self._level) + \
			self._TAB * indent + "- Records Offsets: {}".format(", ".join(map(str, self._record_offsets)))
			
	@classmethod
	def get_type(cls):
		raise NotImplementedError
		
	@classmethod
	def from_sector(cls, data, file):
		node_size = len(data)
		next, previous, _type, level, record_count, unused = struct.unpack(">IIBBHH", data[:14])
		
		record_offsets = []
		for index in range(record_count):
			record_offsets.append(struct.unpack(">H", data[node_size - (index + 1) * 2:node_size - index * 2])[0])
			
		for c in cls.__subclasses__():
			if c.get_type() == _type:
				return c(next, previous, level, record_offsets, data, file)
				
		raise ValueError("unknown node type ({})".format(_type))
				
class BTreeHeaderNode(BTreeNode):
	def __init__(self, next, previous, level, record_offsets, data, file):
		super().__init__(next, previous, level, record_offsets, data, file)
		
		self._tree_depth, self._root_node, self._data_records, self._first_leaf, self._last_leaf, self._node_size, self._max_key_size, self._node_count, self._free_nodes = \
			struct.unpack(">HIIIIHHII", data[self._record_offsets[0]:self._record_offsets[0] + 30])
			
		self._used = data[self._record_offsets[2]:self._record_offsets[2] + self._node_size - 256]

	@property
	def node_count(self):
		return self._node_count
		
	@property
	def root_node(self):
		return self._root_node
		
	def is_used(self, index):
		return self._used[index // 8] & (1 << (7 - (index % 8))) != 0
	
	def dump(self, indent=0):
		return super().dump(indent) + "\n" + \
			self._TAB * indent + "- Tree Depth: {}\n".format(self._tree_depth) + \
			self._TAB * indent + "- Root Node: {}\n".format(self._root_node) + \
			self._TAB * indent + "- Data Records: {}\n".format(self._data_records) + \
			self._TAB * indent + "- First Leaf: {}\n".format(self._first_leaf) + \
			self._TAB * indent + "- Last Leaf: {}\n".format(self._last_leaf) + \
			self._TAB * indent + "- Node Size: {}\n".format(self._node_size) + \
			self._TAB * indent + "- Max Key Size: {}\n".format(self._max_key_size) + \
			self._TAB * indent + "- Node Count: {}\n".format(self._node_count) + \
			self._TAB * indent + "- Free Nodes: {}".format(self._free_nodes)
			
	@classmethod
	def get_type(cls):
		return 1

class BTreeIndexNode(BTreeNode):
	def __init__(self, next, previous, level, record_offsets, data, file):
		super().__init__(next, previous, level, record_offsets, data, file)
		
		self._childs = []
		for index in self._record_offsets:
			key_size = data[index]
			if key_size > 0:
				key_size += 1
				if key_size & 0x01:
					key_size += 1
				key = file.build_key(data[index:index + key_size])
				number = struct.unpack(">I", data[index + key_size:index + key_size + 4])[0]
				self._childs.append((key, number))
					
	def search(self, key):
		# fail if the key is before the first child
		if not (key > self._childs[0][0] or key == self._childs[0][0]):
			raise KeyError
		result = self._childs[0][1]
		for child_key, child_index in self._childs[1:]:
			if key > child_key:
				result = child_index
			else:
				break
		return result
		
	def dump(self, indent=0):
		return super().dump(indent) + "\n" + \
			self._TAB * indent + "- Childs:\n" + \
			"\n".join([key.dump(indent + 1) + "\n" + self._TAB * (indent + 1) + "- Pointer: {}".format(number) for key, number in self._childs])
	
	@classmethod
	def get_type(cls):
		return 0

class BTreeLeafNode(BTreeNode):
	def __init__(self, next, previous, level, record_offsets, data, file):
		super().__init__(next, previous, level, record_offsets, data, file)

		self._records = []
		for index in self._record_offsets:
			key_size = data[index]
			if key_size > 0:
				key_size += 1
				if key_size & 0x01:
					key_size += 1
				key = file.build_key(data[index:index + key_size])
				record = file.build_record(key, data[index + key_size:])
				self._records.append((key, record))

	def search(self, key):
		# fail if the key is before the first child
		if not (key > self._records[0][0] or key == self._records[0][0]):
			raise KeyError
		result = []
		for current_key, current_record in self._records:
			if key > current_key:
				continue
			elif key == current_key:
				result.append(current_record)
			else:
				return result
		return result
	
	def dump(self, indent=0):
		return super().dump(indent) + "\n" + \
			self._TAB * indent + "- Records:\n" + \
			"\n".join([key.dump(indent + 1) + "\n" + record.dump(indent + 1) for key, record in self._records])
			
	@classmethod
	def get_type(cls):
		return 255
		
class File(common.File, common.Dumpeable):
	def __init__(self, record, catalog):
		self._record = record
		self._catalog = catalog
		
	@property
	def name(self):
		return self._record.name
		
	@property
	def streams(self):
		result = []
		if self._record.data_size > 0:
			result.append(0)
		if self._record.resource_size > 0:
			result.append(1)
		return result
	
	def get_content(self, stream=0):
		if stream == 0:
			if self._record.data_size > 0:
				return self._catalog.get_extent_contents(self._record.data_extents_records, self._record.data_size)
			else:
				return b""
		elif stream == 1:
			if self._record.resource_size > 0:
				return self._catalog.get_extent_contents(self._record.resource_extents_records, self._record.resource_size)
			else:
				return b""
		raise ValueError("unknown stream")
		
	def dump(self, indent=0):
		return self._record.dump(indent)
		
class Directory(common.Directory, common.Dumpeable):
	def __init__(self, record, catalog):
		self._record = record
		self._catalog = catalog
		
	@property
	def name(self):
		return self._record.name

	@property
	def directories(self):
		return tuple(map(lambda record: Directory(record, self._catalog), self._catalog.get_directories(self._record.identifier)))
		
	@property
	def files(self):
		return tuple(map(lambda record: File(record, self._catalog), self._catalog.get_files(self._record.identifier)))
		
	def dump(self, indent=0):
		return self._record.dump(indent)
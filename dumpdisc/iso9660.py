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

# See:
# https://wiki.osdev.org/ISO_9660

import datetime
import struct
from . import common


def _to_string(buffer, encoding):
	return buffer.rstrip(b"\x00").decode(encoding).strip()

def _parse_date_time(data):
	if len(data) != 17:
		raise ValueError("datetime data size incorrect")
	
	return datetime.datetime.strptime(_to_string(data[:14], "ascii"), "%Y%m%d%H%M%S")

def _unpack(format, data):
	result = ()
	while len(format) > 0:
		if format[0] in (">", "<"):
			current_format = format[0]
			format = format[1:]
		else:
			current_format = ""
		while len(format) > 0 and not format[0] in (">", "<"):
			current_format = current_format + format[0]
			format = format[1:]
		
		current_size = struct.calcsize(current_format)
		current_data = data[:current_size]
		data = data[current_size:]
		result = result + struct.unpack(current_format, current_data)
		
	if len(data) != 0:
		raise ValueError("remaining data to unpack")
		
	return result

class ISO9660(common.FileSystem, common.Dumpeable):
	def __init__(self, image, base_offset=0):
		self._image = image
		self._base_offset = base_offset
	
		self._system_area = self.read_blocks(self._base_offset, 16)
		
		self._volume_descriptors = []
		index = 0
		while True:
			vd = VolumeDescriptor.from_sector(self.read_blocks(self._base_offset + 16 + index, 1), self)
			self._volume_descriptors.append(vd)
			if isinstance(vd, VolumeDescriptorSetTerminator):
				break
			index += 1
	
	@property
	def block_size(self):
		return 2048
			
	def read_blocks(self, address, count=1):
		return self._image.read_blocks(address, count)
	
	def read_extent(self, address, size):
		remainder = (-size) % self._image.block_size
		data = self.read_blocks(address, (size // self._image.block_size) + (1 if size % self._image.block_size != 0 else 0))
		return data if remainder == 0 else data[:-remainder]
		
	def read_extent_as_raw(self, address, size):
		if size % self._image.block_size != 0:
			raise ValueError("size must match whole blocks")
		return self._image.read_blocks_raw(address, size // self._image.block_size)

	@property
	def partitions(self):
		return tuple(filter(lambda vd: isinstance(vd, common.Partition), self._volume_descriptors))
			
	def dump(self, indent=0):
		return self._TAB * indent + "ISO9660:\n" + \
			self._TAB * indent + "- Volume Descriptors:\n" + \
			"\n".join([vd.dump(indent + 1) for vd in self._volume_descriptors])

class VolumeDescriptor(common.Dumpeable):
	def __init__(self, _type, identifier, version, data, image):
		self._type = _type
		self._identifier = identifier
		self._version = version
		self._data = data
		self._image = image
		
	@classmethod
	def from_sector(cls, sector, image):
		_type, identifier, version, data = _unpack("B5sB2041s", sector)
		for c in cls.__subclasses__():
			if c.get_type() == _type:
				return c(_type, identifier, version, data, image)
		raise ValueError("unknown volume descriptor type ({})".format(_type))
		
	@classmethod
	def get_type(cls):
		raise NotImplementedError
		
class BootRecordVolumeDescriptor(VolumeDescriptor):
	def __init__(self, _type, identifier, version, data, image):
		super().__init__(_type, identifier, version, data, image)
		
		self._boot_system_identifier, self._boot_identifier = _unpack("32s32s", data[:64])
		self._custom_data = data[64:]
		
		if self._identifier != b"CD001":
			raise ValueError("invalid identifier for boot record volume descriptor")
			
		if self._version != 1:
			raise ValueError("invalid version for boot record volume descriptor")
		
	@classmethod
	def get_type(cls):
		return 0
		
	def dump(self, indent=0):
		return self._TAB * indent + "BootRecordVolumeDescriptor:\n" + \
			self._TAB * indent + "- Boot System Identifier: " + repr(self._boot_system_identifier) + "\n" + \
			self._TAB * indent + "- Boot Identifier: " + repr(self._boot_identifier) + "\n" + \
			self._TAB * indent + "- Custom: " + self._custom.hex() + "\n"

class PartitionVolumeDescriptor(common.Partition):
	def __init__(self, identifier, version, data, image):
		self._image = image
		
		volume_flags, system_identifier, volume_identifier, unused1, self._volume_space_size, volume_space_size_msb, self._escape_sequences, \
			self._volume_set_size, volume_set_size_msb, self._volume_sequence_number, volume_sequence_number_msb, \
			self._logical_block_size, logical_block_size_msb, self._path_table_size, path_table_size_msb, \
			type_l_path_table_location, type_l_optional_path_table_location, type_m_path_table_location, type_m_optional_path_table_location, \
			root_directory_entry, volume_set_identifier, publisher_identifier, data_preparer_identifier, application_identifier, \
			copyright_file_identifier, abstract_file_identifier, bibliographic_file_identifier, \
			volume_creation_datetime, volume_modification_datetime, volume_expiration_datetime, volume_effective_datetime, \
			file_structure_version, unused4, self._application_data, self._reserved = \
			_unpack("B32s32s8s<I>I32s<H>H<H>H<H>H<I>I<I<I>I>I34s128s128s128s128s37s37s37s17s17s17s17sBB512s653s", data)
		
		if identifier != b"CD001":
			raise ValueError("invalid identifier for primary/secondary volume descriptor")
			
		if version != 1:
			raise ValueError("invalid version for primary/secondary volume descriptor")
			
		if volume_flags == 0x00:
			self._additional_escape_sequences = False
		elif volume_flags == 0x01:
			self._additional_escape_sequences = True
		else:
			raise ValueError("invalid volume flags for primary/secondary volume descriptor ({})".format(volume_flags))
		
		self._system_identifier = _to_string(system_identifier, self.encoding)
		self._volume_identifier = _to_string(volume_identifier, self.encoding)

		if unused1 != b"\x00" * 8:
			raise ValueError("invalid unused1 for primary/secondary volume descriptor ({})".format(unused1))
		
		if self._volume_space_size != volume_space_size_msb:
			raise ValueError("volume space size fields do not match for primary volume descriptor")
		
		if self._volume_set_size != volume_set_size_msb:
			raise ValueError("volume set size fields do not match for primary volume descriptor")

		if self._volume_sequence_number != volume_sequence_number_msb:
			raise ValueError("volume sequence number fields do not match for primary volume descriptor")

		if self._logical_block_size != logical_block_size_msb:
			raise ValueError("logical block size fields do not match for primary volume descriptor")

		if self._path_table_size != path_table_size_msb:
			raise ValueError("path table size fields do not match for primary volume descriptor")
			
		self._type_l_path_table = self._read_path_table(True, type_l_path_table_location, self._path_table_size)
		self._type_m_path_table = self._read_path_table(False, type_m_path_table_location, self._path_table_size)
			
		self._root_directory_record = DirectoryRecord(root_directory_entry, self.encoding)
			
		self._volume_set_identifier = _to_string(volume_set_identifier, self.encoding)
		self._publisher_identifier = _to_string(publisher_identifier, self.encoding)
		self._data_preparer_identifier = _to_string(data_preparer_identifier, self.encoding)
		self._application_identifier = _to_string(application_identifier, self.encoding)
		self._data_preparer_identifier = _to_string(data_preparer_identifier, self.encoding)
		self._copyright_file_identifier = _to_string(copyright_file_identifier, self.encoding)
		self._abstract_file_identifier = _to_string(abstract_file_identifier, self.encoding)
		self._bibliographic_file_identifier = _to_string(bibliographic_file_identifier, self.encoding)

		self._volume_create_date = _parse_date_time(volume_creation_datetime)
		self._volume_modification_date = _parse_date_time(volume_modification_datetime)
		if volume_expiration_datetime != b"\x00" * 17:
			self._volume_expiration_date = _parse_date_time(volume_expiration_datetime)
		else:
			self._volume_expiration_date = None
		if volume_effective_datetime != b"\x00" * 17:
			self._volume_effective_date = _parse_date_time(volume_effective_datetime)
		else:
			self._volume_effective_date = None
		
		if file_structure_version != 1:
			raise ValueError("invalid file structure version for primary volume descriptor")

		if unused4 != 0:
			raise ValueError("invalid unused4 for primary volume descriptor")
			
	@property
	def encoding(self):
		raise NotImplementedError

	def _read_path_table(self, lsb, location, size):
		data = self._image.read_extent(location, size)
		path_table = []
		while len(data) > 0 and data[0] > 0:
			entry = PathTableEntry(lsb, data, self.encoding)
			path_table.append(entry)
			data = data[8 + entry._identifier_length + (entry._identifier_length & 0x01):]
		return path_table

	@property
	def label(self):
		return self._volume_identifier
	
	@property
	def root_directory(self):
		return Directory(self._root_directory_record, self._image)
		
	def dump(self, indent=0):
		return self._TAB * indent + "{} ({}):\n".format(self.__class__.__name__, self.type) + \
			self._TAB * indent + "- System Identifier: {}\n".format(repr(self._system_identifier)) + \
			self._TAB * indent + "- Volume Identifier: {}\n".format(repr(self._volume_identifier)) + \
			self._TAB * indent + "- Volume Space Size: {} blocks\n".format(self._volume_space_size) + \
			self._TAB * indent + "- Volume Set Size: {} discs\n".format(self._volume_set_size) + \
			self._TAB * indent + "- Volume Sequence Number: {}\n".format(self._volume_sequence_number) + \
			self._TAB * indent + "- Logical Block Size: {} bytes\n".format(self._logical_block_size) + \
			self._TAB * indent + "- Path Table Size: {} bytes\n".format(self._path_table_size) + \
			self._TAB * indent + "- Type-L Path Table:\n" + \
			"\n".join([entry.dump(indent + 1) for entry in self._type_l_path_table]) + "\n" + \
			self._TAB * indent + "- Type-M Path Table:\n" + \
			"\n".join([entry.dump(indent + 1) for entry in self._type_m_path_table]) + "\n" + \
			self._TAB * indent + "- Root Directory Entry:\n" + \
			self._root_directory_record.dump(indent + 1) + "\n" + \
			self._TAB * indent + "- Volume Set Identifier: {}\n".format(repr(self._volume_set_identifier)) + \
			self._TAB * indent + "- Volume Set Identifier: {}\n".format(repr(self._volume_set_identifier)) + \
			self._TAB * indent + "- Publisher Identifier: {}\n".format(repr(self._publisher_identifier)) + \
			self._TAB * indent + "- Data Preparer Identifier: {}\n".format(repr(self._data_preparer_identifier)) + \
			self._TAB * indent + "- Application Identifier: {}\n".format(repr(self._application_identifier)) + \
			self._TAB * indent + "- Copyright File Identifier: {}\n".format(repr(self._copyright_file_identifier)) + \
			self._TAB * indent + "- Abstract File Identifier: {}\n".format(repr(self._abstract_file_identifier)) + \
			self._TAB * indent + "- Bibliographic File Identifier: {}\n".format(repr(self._bibliographic_file_identifier)) + \
			self._TAB * indent + "- Volume Creation: {}\n".format(self._volume_create_date.isoformat()) + \
			self._TAB * indent + "- Volume Modification: {}\n".format(self._volume_modification_date.isoformat()) + \
			self._TAB * indent + "- Volume Expiration: {}\n".format(self._volume_expiration_date.isoformat() if self._volume_expiration_date != None else "not specified") + \
			self._TAB * indent + "- Volume Effective: {}\n".format(self._volume_effective_date.isoformat() if self._volume_effective_date != None else "not specified")

class PrimaryVolumeDescriptor(VolumeDescriptor, PartitionVolumeDescriptor):
	def __init__(self, _type, identifier, version, data, image):
		VolumeDescriptor.__init__(self, _type, identifier, version, data, image)
		PartitionVolumeDescriptor.__init__(self, identifier, version, data, image)

		if self._additional_escape_sequences:
			raise ValueError("invalid volume flags for primary volume descriptor")

		if self._escape_sequences != b"\x00" * 32:
			raise ValueError("invalid escape sequences for primary volume descriptor")

	@classmethod
	def get_type(cls):
		return 1

	@property
	def encoding(self):
		return "ascii"

	@property
	def type(self):
		return "iso9660"

	def dump(self, indent=0):
		return PartitionVolumeDescriptor.dump(self, indent)

class SupplementaryVolumeDescriptor(VolumeDescriptor, PartitionVolumeDescriptor):
	def __init__(self, _type, identifier, version, data, image):
		VolumeDescriptor.__init__(self, _type, identifier, version, data, image)
		PartitionVolumeDescriptor.__init__(self, identifier, version, data, image)

		if self._additional_escape_sequences:
			raise ValueError("additional escape sequences for secondary volume descriptor are not supported")

		if self._escape_sequences not in (b"\x25\x2f\x40".ljust(32, b"\x00"), b"\x25\x2f\x43".ljust(32, b"\x00"), b"\x25\x2f\x45".ljust(32, b"\x00")):
			raise ValueError("not supported escape sequences for secondary volume descriptor")

	@classmethod
	def get_type(cls):
		return 2

	@property
	def encoding(self):
		return "utf-16_be"

	@property
	def type(self):
		return "joliet"

	def dump(self, indent=0):
		return PartitionVolumeDescriptor.dump(self, indent)

class VolumePartitionDescriptor(VolumeDescriptor):
	@classmethod
	def get_type(cls):
		return 3
		
	def dump(self, indent=0):
		return self._TAB * indent + "VolumePartitionDescriptor"

class VolumeDescriptorSetTerminator(VolumeDescriptor):
	@classmethod
	def get_type(cls):
		return 255
		
	def dump(self, indent=0):
		return self._TAB * indent + "VolumeDescriptorSetTerminator"

class PathTableEntry(common.Dumpeable):
	def __init__(self, lsb, data, encoding):
		endianness = "<" if lsb else ">"
		self._identifier_length, extended_attributes_length, self._extent, self._parent_index = _unpack(endianness + "BBIH", data[:8])
		
		self._identifier = _to_string(data[8:8 + self._identifier_length], encoding)
		
	def dump(self, indent=0):
		return self._TAB * indent + "PathTableEntry:\n" + \
			self._TAB * indent + "- Identifier: {}\n".format(self._identifier) + \
			self._TAB * indent + "- Extent Location: {}\n".format(self._extent) + \
			self._TAB * indent + "- Parent Directory Index: {}".format(self._parent_index)
			
# TODO: merge different versions of the same file in a single instance and manage them through streams
class DirectoryRecord(common.Dumpeable):
	def __init__(self, data, encoding):
		self._length, self._extended_attributes_length, self._extent, extent_msb, self._data_length, data_length_msb, \
			recording_datetime_year, recording_datetime_month, recording_datetime_day, recording_datetime_hours, recording_datetime_minutes, recording_datetime_seconds, recording_datetime_tz, \
			flags, self._file_unit_size, self._interleave_gap_size, self._volume_sequence_number, volume_sequence_number_msb, self._file_indentifier_length = \
			_unpack("BB<I>I<I>IBBBBBBBBBB<H>HB", data[:33])
		self._encoding = encoding
		
		self._identifier = data[33:33 + self._file_indentifier_length]
		
		if self._length == 0:
			raise ValueError("invalid length for directory record ({})".format(self._identifier))
		
		if self._length + self._extended_attributes_length > len(data):
			raise ValueError("data length mismatch for directory record")
		
		if self._extent != extent_msb:
			raise ValueError("extent location fields do not match for directory record")
			
		if self._data_length != data_length_msb:
			raise ValueError("data length fields do not match for directory record")
			
		if self._volume_sequence_number != volume_sequence_number_msb:
			raise ValueError("volume sequence number fields do not match for directory record")
			
		self._recording_date_time = datetime.datetime(recording_datetime_year + 1900, recording_datetime_month, recording_datetime_day, recording_datetime_hours, recording_datetime_minutes, recording_datetime_seconds)
		
		self._is_hidden = flags & 0x01 == 0x01
		self._is_directory = flags & 0x02 == 0x02
		self._is_associated_file = flags & 0x04 == 0x04
		self._contains_file_format_information = flags & 0x08 == 0x08
		self._contains_persmissions = flags & 0x10 == 0x10
		self._is_final = flags & 0x80 == 0x80
		
	@property
	def name(self):
		return _to_string(self._identifier.split(b";", 2)[0], self._encoding)
	
	@property
	def is_directory(self):
		return self._is_directory
		
	def get_childs(self, image):
		childs = []
		if not self._is_directory:
			raise ValueError("not a directory")
		
		data = image.read_extent(self._extent, self._data_length)
		# skip the . and .. entries
		data = data[data[0] + data[1]:]
		data = data[data[0] + data[1]:]
		# TODO: take into account directory records cannot cross block boundaries
		while len(data) > 0 and data[0] > 0:
			record = DirectoryRecord(data, self._encoding)
			childs.append(record)
			if record._is_final:
				break
			data = data[record._length + record._extended_attributes_length:]
		
		return childs
		
	def get_content(self, image, stream=0):
		if self._is_directory:
			raise TypeError("not a file")
		if stream != 0:
			raise ValueError("only stream 0 available")
		
		try:
			return image.read_extent(self._extent, self._data_length)
		except Exception as e:
			# Wrap CDXA files (having Mode 2 Form 2 sectors) into a RIFF container
			# See https://github.com/microsoft/Windows-driver-samples/blob/7895dd22785ddba5e973662ed942be3b3452b89d/filesys/cdfs/cddata.c#L150
			#     https://github.com/kicker12/scripts/blob/dfe8613ed64a89120c04782ae388d54174c3b663/psxc-media/MediaInfoLib/Source/MediaInfo/Multiple/File_Cdxa.cpp#L329	
			data = image.read_extent_as_raw(self._extent, self._data_length)
			header = struct.pack("<4sI4s4sIHHH2sB7s4sI", b"RIFF", 36 + len(data), b"CDXA", b"fmt ", 16, 0, 0, 0x1111, b"XA", 1, b"\x00" * 7, b"data", len(data))
			return header + data
				
	def dump(self, indent=0):
		return self._TAB * indent + "DirectoryRecord:\n" + \
			self._TAB * indent + "- Identifier: {}\n".format(self.name) + \
			self._TAB * indent + "- Extent Location: {}\n".format(self._extent) + \
			self._TAB * indent + "- Data Length: {}\n".format(self._data_length) + \
			self._TAB * indent + "- Recorded: {}\n".format(self._recording_date_time.isoformat()) + \
			self._TAB * indent + "- Hidden: {}\n".format(repr(self._is_hidden)) + \
			self._TAB * indent + "- Directory: {}\n".format(repr(self._is_directory)) + \
			self._TAB * indent + "- Associated File: {}\n".format(repr(self._is_associated_file)) + \
			self._TAB * indent + "- Contains File Format Information: {}\n".format(repr(self._contains_file_format_information)) + \
			self._TAB * indent + "- Contains Permissions: {}\n".format(repr(self._contains_persmissions)) + \
			self._TAB * indent + "- Final: {}\n".format(repr(self._is_final)) + \
			self._TAB * indent + "- File Unit Size: {}\n".format(self._file_unit_size) + \
			self._TAB * indent + "- Interleave Gap Size: {}\n".format(self._interleave_gap_size) + \
			self._TAB * indent + "- Volume Sequence Number: {}\n".format(self._volume_sequence_number) + \
			self._TAB * indent + "- Extended Attributes Length: {}".format(self._extended_attributes_length)

class Directory(common.Directory):
	def __init__(self, record, image):
		self._record = record
		self._image = image
		
	@property
	def name(self):
		return self._record.name

	def _get_child_records(self, directories, wrapper):
		return tuple(map(lambda record: wrapper(record, self._image), filter(lambda record: record.is_directory == directories, self._record.get_childs(self._image))))
	
	@property
	def directories(self):
		return self._get_child_records(True, Directory)
		
	@property
	def files(self):
		return self._get_child_records(False, File)
		
	def dump(self, indent=0):
		return self._record.dump(indent)
		
class File(common.File):
	def __init__(self, record, image):
		self._record = record
		self._image = image

	@property
	def name(self):
		return self._record.name
		
	@property
	def streams(self):
		return [0, ]
	
	def get_content(self, stream=0):
		return self._record.get_content(self._image, stream)

	def dump(self, indent=0):
		return self._record.dump(indent)

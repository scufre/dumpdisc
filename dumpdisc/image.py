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

import os
import struct
from . import cdrom

class Image(object):
	def read_blocks(self, address=None, count=1):
		raise NotImplementedError
		
	def read_blocks_data(self, address=None, count=1):
		raise NotImplementedError
	
	def read_blocks_raw(self, address=None, count=1):
		raise NotImplementedError
	
	@property
	def current_block(self):
		raise NotImplementedError
	
	@property
	def block_size(self):
		raise NotImplementedError
		
	def close(self):
		raise NotImplementedError
	
	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.close()
		
class ISOImage(Image):
	def __init__(self, f, block_size=2048):
		self._block_size = block_size
		self._f = f
		
		self._f.seek(0, os.SEEK_END)
		self._sectors = self.current_block
		
	def read_blocks(self, address=None, count=1):
		if address != None:
			self._f.seek(address * self.block_size)
		return self._f.read(count * self.block_size)
		
	def read_blocks_data(self, address=None, count=1):
		return self.read_blocks(address, count)
	
	def read_blocks_raw(self, address=None, count=1):
		raise NotImplementedError
		
	@property
	def current_block(self):
		return self._f.tell() // self.block_size
	
	@property
	def block_size(self):
		return self._block_size

	@property
	def size(self):
		return self._sectors
		
	def close(self):
		self._f.close()		
		

# See:
# https://github.com/libyal/libodraw/blob/main/documentation/Optical%20disc%20RAW%20format.asciidoc
# https://psx-spx.consoledev.net/cdromdrive/#cdrom-sector-encoding
class RawCDImage(Image):
	RAW_SECTOR_SIZE = 2352
	DATA_SECTOR_SIZE = 2048

	def __init__(self, f):
		self._offset = 0
		self._current_sector = 0
		self._f = f
		
		self._f.seek(0, os.SEEK_END)
		self._sectors = self._f.tell() // self.RAW_SECTOR_SIZE
		
		self._ecc = cdrom.ECC()
		self._edc = cdrom.EDC()
		
	def _read_raw_sector(self, address=None):
		if address != None:
			self._current_sector = address
			self._f.seek(address * self.RAW_SECTOR_SIZE)
		data = self._f.read(self.RAW_SECTOR_SIZE)
		if len(data) != self.RAW_SECTOR_SIZE:
			raise IOError("can't read entire sector")
		self._current_sector += 1
		return data
	
	def _read_sector(self, strict_size=False, address=None):
		sector = self._read_raw_sector(address)
		
		sync, offset, mode, data = struct.unpack("12s3sB2336s", sector)
		if sync != b'\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00':
			raise IOError("sync for sector invalid")
		if mode == 0:
			data = b'\x00' * self.DATA_SECTOR_SIZE
		elif mode == 1:
			data, edc, reserved, ecc = struct.unpack("2048sI8s276s", data)
			if edc != self._edc.compute(sync + offset + mode + data):
				raise IOError("edc invalid for sector {}".format(self._current_sector - 1))
			if ecc != self._ecc.compute(offset + mode + data + struct.pack("<I", edc)):
				raise IOError("ecc invalid for sector {}".format(self._current_sector - 1))				
		elif mode == 2:
			subheader, data = struct.unpack("8s2328s", data)
			if subheader[2] != subheader[6]:
				raise IOError("submode flags do not match for sector {} ({} {})".format(self._current_sector - 1, subheader[2], subheader[6]))
			if subheader[2] & 0x20 == 0:
				data, edc, ecc = struct.unpack("2048sI276s", data)
				if ecc != self._ecc.compute(b"\x00" * 4 + subheader + data + struct.pack("<I", edc)):
					raise IOError("ecc invalid for sector {}".format(self._current_sector - 1))
			else:
				data, edc = struct.unpack("2324sI", data)
			if edc != self._edc.compute(subheader + data):
				raise IOError("edc invalid for sector {}".format(self._current_sector - 1))
			if strict_size and len(data) != self.DATA_SECTOR_SIZE:
				raise IOError("mode 2 form 1 sector found")
		else:
			raise IOError("invalid mode for sector {} ({})".format(self._current_sector - 1, mode))
		
		return data
		
	def _read_blocks(self, read_sector, address, count):
		data = read_sector(address)
		for i in range(count - 1):
			data += read_sector()
		return data

	def read_blocks(self, address=None, count=1):
		return self._read_blocks(lambda a=None: self._read_sector(True, a), address, count)
		
	def read_blocks_data(self, address=None, count=1):
		return self._read_blocks(lambda a=None: self._read_sector(False, a), address, count)
	
	def read_blocks_raw(self, address=None, count=1):
		return self._read_blocks(lambda a=None: self._read_raw_sector(a), address, count)
		
	@property
	def current_block(self):
		return self._current_sector
	
	@property
	def block_size(self):
		return self.DATA_SECTOR_SIZE
		
	@property
	def size(self):
		return self._sectors
		
	def close(self):
		self._f.close()
		
	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.close()
		

def _parse_c_number(text):
	text = text.strip()
	if text.startswith("0x"):
		return int(text, 16)
	elif text.startswith("0"):
		return int(text, 8)
	else:
		return int(text)
		
class DDRescueImage(Image):
	STATUS_COPYING_NONTRIED_BLOCKS = '?'
	STATUS_TRIMMING_NONTRIED_BLOCKS = '*'
	STATUS_SCRAPING_NONSCRAPED_BLOCKS = '/'
	STATUS_RETRYING_BAD_SECTORS = '-'
	STATUS_FILLING_SPECIFIED_BLOCKS = 'F'
	STATUS_GENERATING_APROXIMATE_MAP_FILE = 'G'
	STATUS_FINISHED = '+'

	BLOCK_STATUS_NON_TRIED = '?'
	BLOCK_STATUS_NON_TRIMMED = '*'
	BLOCK_STATUS_NON_SCRAPED = '/'
	BLOCK_STATUS_BAD_SECTORS = '-'
	BLOCK_STATUS_FINISHED = '+'

	def __init__(self, image, map_filename):
		self._image = image

		with open(map_filename, "r") as mf:
			lines = mf.readlines()

			index = 0
			while index < len(lines):
				line = lines[index]
				index += 1
				if line.strip()[0] != '#':
					current_pos, status, current_pass = line.strip().split()
					break

			current_pos = _parse_c_number(current_pos)

			if not (status in (self.STATUS_COPYING_NONTRIED_BLOCKS, self.STATUS_TRIMMING_NONTRIED_BLOCKS, self.STATUS_SCRAPING_NONSCRAPED_BLOCKS, self.STATUS_RETRYING_BAD_SECTORS, self.STATUS_FILLING_SPECIFIED_BLOCKS, self.STATUS_GENERATING_APROXIMATE_MAP_FILE, self.STATUS_FINISHED)):
				raise Exception('unknown status')

			current_pass = int(current_pass)

			self._bad_areas = []

			while index < len(lines):
				line = lines[index]
				index += 1
				if line.strip()[0] != '#':
					start, size, status = line.strip().split()
					start = _parse_c_number(start)
					size = _parse_c_number(size)
					if not (status in (self.BLOCK_STATUS_NON_TRIED, self.BLOCK_STATUS_NON_TRIMMED, self.BLOCK_STATUS_NON_SCRAPED, self.BLOCK_STATUS_BAD_SECTORS, self.BLOCK_STATUS_FINISHED)):
						raise Exception('unknown block status')

					if status != self.BLOCK_STATUS_FINISHED:
						self._bad_areas.append((start, start + size))

	def read_blocks(self, address=None, count=1):
		start = (address if address != None else self.current_block) * self.block_size
		end = start + count * self.block_size
		for area in self._bad_areas:
			if (area[0] <= start and start < area[1]) or (area[0] <= end and end < area[1]):
				raise IOError("bad block (area from {} to {})".format(area[0], area[1]))
		return self._image.read_blocks(address, count)
	
	def read_blocks_data(self, address=None, count=1):
		return self.read_blocks(address, count)
	
	def read_blocks_raw(self, address=None, count=1):
		raise NotImplementedError
	
	@property
	def current_block(self):
		return self._image.current_block
	
	@property
	def block_size(self):
		return self._image.block_size
		
	def close(self):
		self._image.close()
		
class ImageWithBadMap(Image):
	def __init__(self, image, bad_map, bad_map_offset=0):
		self._image = image
		
		with open(bad_map, "r") as mf:
			self._bad_blocks = set(map(lambda line: int(line.strip()) - bad_map_offset, filter(lambda line: len(line.strip()) > 0, mf.readlines())))

	def _check_blocks(self, address, count):
		start = address if address != None else self.current_block
		end = start + count
		for offset in range(start, end):
			if offset in self._bad_blocks:
				raise IOError("bad block ({})".format(offset))	
	
	def read_blocks(self, address=None, count=1):
		self._check_blocks(address, count)
		return self._image.read_blocks(address, count)
		
	def read_blocks_data(self, address=None, count=1):
		self._check_blocks(address, count)
		return self._image.read_blocks_data(address, count)
		
	def read_blocks_raw(self, address=None, count=1):
		self._check_blocks(address, count)
		return self._image.read_blocks_raw(address, count)
		
	@property
	def current_block(self):
		return self._image.current_block
	
	@property
	def block_size(self):
		return self._image.block_size
		
	def close(self):
		self._image.close()

class OffsetedImage(Image):
	def __init__(self, image, offset):
		self._image = image
		self._offset = offset
		
	def read_blocks(self, address=None, count=1):
		if address != None:
			address -= self._offset
		return self._image.read_blocks(address, count)
		
	def read_blocks_data(self, address=None, count=1):
		if address != None:
			address -= self._offset
		return self._image.read_blocks_data(address, count)
		
	def read_blocks_raw(self, address=None, count=1):
		if address != None:
			address -= self._offset
		return self._image.read_blocks_raw(address, count)
		
	@property
	def current_block(self):
		return self._image.current_block + offset
	
	@property
	def block_size(self):
		return self._image.block_size
		
	def close(self):
		self._image.close()
